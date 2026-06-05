"""
Tool definitions and execution for the Claude AI assistant.

Design: Claude gets pre-computed aggregates when possible (fast + cheap).
Raw transaction scans are limited to 50 rows per call.
"""
import json
from datetime import date, timedelta
from typing import Any, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func
import httpx
import models

# ── Tool schemas (passed to Anthropic API) ────────────────────────────────────

TOOLS = [
    {
        "name": "get_user_context",
        "description": "Retrieve stored facts about the user's financial preferences (pay day, exclusions, goals). Always call this first.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "remember_user_fact",
        "description": "Persist an important fact the user shares (e.g. 'I get paid on the 1st', 'don't count rent in food budget'). Call whenever user shares personal financial context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Short label, e.g. 'pay_day', 'food_exclusion'"},
                "value": {"type": "string", "description": "The fact to remember"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "get_spending_summary",
        "description": "Get total spending by category for a date range. Use this for aggregate questions like 'how much did I spend on X?' — much faster than scanning raw transactions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "category": {"type": "string", "description": "Filter to one category, or omit for all"},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_transactions",
        "description": "Fetch individual transactions with filters. Use only when you need specific transactions, not for aggregate questions. Limited to 50 results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "category": {"type": "string"},
                "merchant": {"type": "string", "description": "Partial merchant name match"},
                "min_amount": {"type": "number", "description": "Minimum absolute amount"},
                "max_amount": {"type": "number", "description": "Maximum absolute amount"},
                "limit": {"type": "integer", "default": 20, "description": "Max 50"},
            },
        },
    },
    {
        "name": "get_monthly_trend",
        "description": "Get month-by-month spending totals for trend analysis. Use for 'am I spending more than usual?' questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter to one category, or omit for total"},
                "months": {"type": "integer", "default": 6, "description": "How many months back to look"},
            },
        },
    },
    {
        "name": "get_subscriptions",
        "description": "Get detected recurring subscriptions and charges the user may have forgotten.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_anomalies",
        "description": "Get unusual or out-of-pattern transactions flagged by statistical analysis.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_budgets",
        "description": "Get current budget allocations with actual spending vs budget for this period.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_budget",
        "description": "Create or update a spending budget for a category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "amount": {"type": "number", "description": "Budget limit amount"},
                "period": {"type": "string", "enum": ["monthly", "weekly"]},
            },
            "required": ["category", "amount", "period"],
        },
    },
    {
        "name": "lookup_merchant",
        "description": "Look up what an unfamiliar merchant or charge likely is. Uses web search for real-time info.",
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant_name": {"type": "string"},
                "amount": {"type": "number", "description": "Optional charge amount for context"},
            },
            "required": ["merchant_name"],
        },
    },
]


# ── Tool executor ─────────────────────────────────────────────────────────────

def execute_tool(name: str, tool_input: Dict, user_id: int, db: Session) -> Any:
    handlers = {
        "get_user_context": _get_user_context,
        "remember_user_fact": _remember_user_fact,
        "get_spending_summary": _get_spending_summary,
        "get_transactions": _get_transactions,
        "get_monthly_trend": _get_monthly_trend,
        "get_subscriptions": _get_subscriptions,
        "get_anomalies": _get_anomalies,
        "get_budgets": _get_budgets,
        "set_budget": _set_budget,
        "lookup_merchant": _lookup_merchant,
    }
    handler = handlers.get(name)
    if not handler:
        return {"error": f"Unknown tool: {name}"}
    return handler(tool_input, user_id, db)


# ── Individual tools ──────────────────────────────────────────────────────────

def _get_user_context(inp: Dict, user_id: int, db: Session) -> Dict:
    rows = db.query(models.UserContext).filter(models.UserContext.user_id == user_id).all()
    return {r.key: r.value for r in rows}


def _remember_user_fact(inp: Dict, user_id: int, db: Session) -> Dict:
    key, value = inp["key"], inp["value"]
    existing = (
        db.query(models.UserContext)
        .filter(models.UserContext.user_id == user_id, models.UserContext.key == key)
        .first()
    )
    if existing:
        existing.value = value
    else:
        db.add(models.UserContext(user_id=user_id, key=key, value=value))
    db.commit()
    return {"stored": True, "key": key, "value": value}


def _get_spending_summary(inp: Dict, user_id: int, db: Session) -> Dict:
    start = date.fromisoformat(inp["start_date"])
    end = date.fromisoformat(inp["end_date"])
    category = inp.get("category")

    query = db.query(
        models.Transaction.category,
        func.sum(models.Transaction.amount).label("total"),
        func.count(models.Transaction.id).label("count"),
    ).filter(
        models.Transaction.user_id == user_id,
        models.Transaction.date >= start,
        models.Transaction.date <= end,
        models.Transaction.amount < 0,
    )
    if category:
        query = query.filter(models.Transaction.category == category)

    rows = query.group_by(models.Transaction.category).all()
    categories = [
        {"category": r.category, "total": round(abs(r.total), 2), "count": r.count}
        for r in rows
    ]
    categories.sort(key=lambda x: x["total"], reverse=True)

    total = sum(c["total"] for c in categories)
    return {
        "period": f"{start} to {end}",
        "total_spending": round(total, 2),
        "categories": categories,
    }


def _get_transactions(inp: Dict, user_id: int, db: Session) -> Dict:
    query = db.query(models.Transaction).filter(models.Transaction.user_id == user_id)

    if "start_date" in inp:
        query = query.filter(models.Transaction.date >= date.fromisoformat(inp["start_date"]))
    if "end_date" in inp:
        query = query.filter(models.Transaction.date <= date.fromisoformat(inp["end_date"]))
    if inp.get("category"):
        query = query.filter(models.Transaction.category == inp["category"])
    if inp.get("merchant"):
        query = query.filter(models.Transaction.merchant.ilike(f"%{inp['merchant']}%"))
    if inp.get("min_amount") is not None:
        query = query.filter(func.abs(models.Transaction.amount) >= inp["min_amount"])
    if inp.get("max_amount") is not None:
        query = query.filter(func.abs(models.Transaction.amount) <= inp["max_amount"])

    limit = min(int(inp.get("limit", 20)), 50)
    txns = query.order_by(models.Transaction.date.desc()).limit(limit).all()

    return {
        "transactions": [
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "amount": t.amount,
                "merchant": t.merchant,
                "category": t.category,
                "description": t.description,
            }
            for t in txns
        ],
        "count": len(txns),
    }


def _get_monthly_trend(inp: Dict, user_id: int, db: Session) -> Dict:
    months = int(inp.get("months", 6))
    category = inp.get("category")
    today = date.today()

    # Build months list going back N months
    results = []
    for i in range(months - 1, -1, -1):
        # first day of month i months ago
        m = (today.month - i - 1) % 12 + 1
        y = today.year + ((today.month - i - 1) // 12)
        month_start = date(y, m, 1)
        # last day of that month
        if m == 12:
            month_end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(y, m + 1, 1) - timedelta(days=1)

        query = db.query(func.sum(models.Transaction.amount)).filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= month_start,
            models.Transaction.date <= month_end,
            models.Transaction.amount < 0,
        )
        if category:
            query = query.filter(models.Transaction.category == category)

        total = query.scalar() or 0.0
        results.append({
            "month": month_start.strftime("%Y-%m"),
            "label": month_start.strftime("%b %Y"),
            "total_spending": round(abs(total), 2),
        })

    return {"trend": results, "category": category or "all"}


def _get_subscriptions(inp: Dict, user_id: int, db: Session) -> Dict:
    subs = db.query(models.Subscription).filter(models.Subscription.user_id == user_id).all()
    return {
        "subscriptions": [
            {
                "merchant": s.merchant,
                "amount": s.amount,
                "frequency_days": s.frequency_days,
                "frequency_label": _freq_label(s.frequency_days),
                "last_seen": s.last_seen.isoformat() if s.last_seen else None,
                "occurrence_count": s.occurrence_count,
                "annual_cost": round(s.amount * (365 / s.frequency_days), 2),
            }
            for s in subs
        ],
        "total_monthly_cost": round(
            sum(s.amount * (30 / s.frequency_days) for s in subs), 2
        ),
    }


def _freq_label(days: int) -> str:
    return {7: "weekly", 14: "bi-weekly", 30: "monthly", 90: "quarterly", 365: "annual"}.get(days, f"every {days} days")


def _get_anomalies(inp: Dict, user_id: int, db: Session) -> Dict:
    anomalies = (
        db.query(models.Anomaly)
        .filter(models.Anomaly.user_id == user_id)
        .order_by(models.Anomaly.amount.desc())
        .all()
    )
    return {
        "anomalies": [
            {
                "merchant": a.merchant,
                "amount": a.amount,
                "category": a.category,
                "date": a.date.isoformat() if a.date else None,
                "reason": a.reason,
                "severity": a.severity,
            }
            for a in anomalies
        ]
    }


def _get_budgets(inp: Dict, user_id: int, db: Session) -> Dict:
    budgets = db.query(models.Budget).filter(models.Budget.user_id == user_id).all()
    today = date.today()

    result = []
    for b in budgets:
        if b.period == "monthly":
            start = date(today.year, today.month, 1)
            end = today
        else:  # weekly
            start = today - timedelta(days=today.weekday())
            end = today

        spent = (
            db.query(func.sum(func.abs(models.Transaction.amount)))
            .filter(
                models.Transaction.user_id == user_id,
                models.Transaction.category == b.category,
                models.Transaction.date >= start,
                models.Transaction.date <= end,
                models.Transaction.amount < 0,
            )
            .scalar()
            or 0.0
        )

        result.append({
            "id": b.id,
            "category": b.category,
            "budget": b.amount,
            "spent": round(spent, 2),
            "remaining": round(b.amount - spent, 2),
            "percent_used": round((spent / b.amount) * 100, 1) if b.amount > 0 else 0,
            "period": b.period,
            "status": "over" if spent > b.amount else "warning" if spent > b.amount * 0.85 else "ok",
        })

    return {"budgets": result}


def _set_budget(inp: Dict, user_id: int, db: Session) -> Dict:
    category, amount, period = inp["category"], float(inp["amount"]), inp["period"]
    existing = (
        db.query(models.Budget)
        .filter(models.Budget.user_id == user_id, models.Budget.category == category)
        .first()
    )
    if existing:
        existing.amount = amount
        existing.period = period
    else:
        db.add(models.Budget(user_id=user_id, category=category, amount=amount, period=period))
    db.commit()
    return {"set": True, "category": category, "amount": amount, "period": period}


def _lookup_merchant(inp: Dict, user_id: int, db: Session) -> Dict:
    merchant = inp["merchant_name"]
    amount = inp.get("amount")

    # DuckDuckGo instant answers — free, no API key needed
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                "https://api.duckduckgo.com/",
                params={"q": f"{merchant} company what is", "format": "json", "no_redirect": "1"},
            )
            data = resp.json()
            abstract = data.get("AbstractText", "")
            if abstract:
                return {"merchant": merchant, "info": abstract, "source": "DuckDuckGo"}
    except Exception:
        pass

    return {
        "merchant": merchant,
        "info": f"No web result found for '{merchant}'. Based on typical charge patterns, this may be a subscription or retail service. Amount ${amount:.2f} suggests it could be a {_guess_category_from_amount(amount) if amount else 'general'} expense.",
        "source": "inference",
    }


def _guess_category_from_amount(amount: float) -> str:
    if amount < 5:
        return "app or small subscription"
    if amount < 20:
        return "streaming/subscription"
    if amount < 60:
        return "software or mid-tier subscription"
    return "software, service, or retail"
