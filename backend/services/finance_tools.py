"""
Tool definitions for GPT-4o. Uses Supabase client for all DB queries.
.
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict
import httpx

TOOLS = [
    {
        "name": "get_user_context",
        "description": "Retrieve stored facts about the user's financial preferences. Always call this first.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_transaction",
        "description": (
            "Save a new transaction to the user's financial history. "
            "Use this after the user confirms saving a receipt or manually mentions a purchase/payment. "
            "After analyzing a receipt image, always offer to save it, then call this when they confirm."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Transaction date in YYYY-MM-DD format. Use today if not visible on receipt.",
                },
                "amount": {
                    "type": "number",
                    "description": "Amount in PKR. Always NEGATIVE for expenses/purchases, POSITIVE for income.",
                },
                "merchant": {
                    "type": "string",
                    "description": "Merchant or payee name exactly as on the receipt.",
                },
                "category": {
                    "type": "string",
                    "enum": ["Groceries", "Dining", "Transportation", "Subscriptions",
                             "Entertainment", "Healthcare", "Shopping", "Utilities", "Income", "Other"],
                    "description": "Best matching category for this transaction.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional short note, e.g. itemized summary or receipt number.",
                },
            },
            "required": ["date", "amount", "merchant", "category"],
        },
    },
    {
        "name": "remember_user_fact",
        "description": "Persist an important fact the user shares (pay day, exclusions, goals).",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "get_spending_summary",
        "description": "Get total spending by category for a date range. Use for aggregate questions.",
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
        "description": "Fetch individual transactions with filters. Limited to 50 results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "category": {"type": "string"},
                "merchant": {"type": "string", "description": "Partial merchant name match"},
                "min_amount": {"type": "number"},
                "max_amount": {"type": "number"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "get_monthly_trend",
        "description": "Get month-by-month spending totals for trend analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "months": {"type": "integer", "default": 6},
            },
        },
    },
    {
        "name": "get_subscriptions",
        "description": "Get detected recurring subscriptions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_anomalies",
        "description": "Get unusual transactions flagged by statistical analysis.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_budgets",
        "description": "Get budget allocations with actual spending vs budget.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_budget",
        "description": "Create or update a spending budget for a category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "amount": {"type": "number"},
                "period": {"type": "string", "enum": ["monthly", "weekly"]},
            },
            "required": ["category", "amount", "period"],
        },
    },
    {
        "name": "lookup_merchant",
        "description": "Look up what an unfamiliar merchant is via web search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant_name": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["merchant_name"],
        },
    },
    {
        "name": "get_conflicts",
        "description": (
            "Detect transactions that appear to be the same purchase recorded twice from different sources "
            "(e.g. a manual entry and a CSV import for the same merchant on the same day with a similar amount). "
            "Use this when the user asks about data discrepancies, double entries, or contradicting records."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "How many recent days to scan. Default 90.",
                    "default": 90,
                },
            },
        },
    },
]


def execute_tool(name: str, tool_input: Dict, user_id: str, db) -> Any:
    handlers = {
        "get_user_context": _get_user_context,
        "remember_user_fact": _remember_user_fact,
        "create_transaction": _create_transaction,
        "get_spending_summary": _get_spending_summary,
        "get_transactions": _get_transactions,
        "get_monthly_trend": _get_monthly_trend,
        "get_subscriptions": _get_subscriptions,
        "get_anomalies": _get_anomalies,
        "get_budgets": _get_budgets,
        "set_budget": _set_budget,
        "lookup_merchant": _lookup_merchant,
        "get_conflicts": _get_conflicts,
    }
    handler = handlers.get(name)
    if not handler:
        return {"error": f"Unknown tool: {name}"}
    return handler(tool_input, user_id, db)


def _get_user_context(inp: Dict, user_id: str, db) -> Dict:
    result = db.table("user_context").select("key,value").eq("user_id", user_id).execute()
    return {r["key"]: r["value"] for r in result.data}


def _remember_user_fact(inp: Dict, user_id: str, db) -> Dict:
    key, value = inp["key"], inp["value"]
    db.table("user_context").upsert(
        {"user_id": user_id, "key": key, "value": value},
        on_conflict="user_id,key",
    ).execute()
    return {"stored": True, "key": key, "value": value}


def _create_transaction(inp: Dict, user_id: str, db) -> Dict:
    record = {
        "user_id": user_id,
        "date": inp["date"],
        "amount": float(inp["amount"]),
        "merchant": inp["merchant"],
        "category": inp.get("category", "Other"),
        "description": inp.get("description", ""),
        "source": "assistant",
    }
    result = db.table("transactions").insert(record).execute()
    t = result.data[0]
    return {
        "saved": True,
        "id": t["id"],
        "date": t["date"],
        "amount": t["amount"],
        "merchant": t["merchant"],
        "category": t["category"],
        "message": f"Transaction saved: Rs {abs(t['amount']):.0f} at {t['merchant']} on {t['date']}",
    }


def _get_spending_summary(inp: Dict, user_id: str, db) -> Dict:
    start = inp["start_date"]
    end = inp["end_date"]
    category = inp.get("category")

    query = db.table("transactions").select("category,amount") \
        .eq("user_id", user_id).gte("date", start).lte("date", end).lt("amount", 0)
    if category:
        query = query.eq("category", category)

    result = query.execute()

    totals: dict = defaultdict(float)
    counts: dict = defaultdict(int)
    for t in result.data:
        totals[t["category"]] += abs(t["amount"])
        counts[t["category"]] += 1

    categories = sorted(
        [{"category": cat, "total": round(total, 2), "count": counts[cat]} for cat, total in totals.items()],
        key=lambda x: x["total"],
        reverse=True,
    )
    return {
        "period": f"{start} to {end}",
        "total_spending": round(sum(c["total"] for c in categories), 2),
        "categories": categories,
    }


def _get_transactions(inp: Dict, user_id: str, db) -> Dict:
    query = db.table("transactions").select("id,date,amount,merchant,category,description") \
        .eq("user_id", user_id)

    if "start_date" in inp:
        query = query.gte("date", inp["start_date"])
    if "end_date" in inp:
        query = query.lte("date", inp["end_date"])
    if inp.get("category"):
        query = query.eq("category", inp["category"])
    if inp.get("merchant"):
        query = query.ilike("merchant", f"%{inp['merchant']}%")

    limit = min(int(inp.get("limit", 20)), 50)
    result = query.order("date", desc=True).limit(limit * 2).execute()

    txns = result.data
    if "min_amount" in inp:
        txns = [t for t in txns if abs(t["amount"]) >= inp["min_amount"]]
    if "max_amount" in inp:
        txns = [t for t in txns if abs(t["amount"]) <= inp["max_amount"]]
    txns = txns[:limit]

    return {"transactions": txns, "count": len(txns)}


def _get_monthly_trend(inp: Dict, user_id: str, db) -> Dict:
    months = int(inp.get("months", 6))
    category = inp.get("category")
    today = date.today()

    # Compute start date
    m = (today.month - months) % 12 + 1 if (today.month - months) % 12 != 0 else 12
    y = today.year - (months // 12) - (1 if today.month <= months % 12 else 0)
    start_date = date(y, m, 1).isoformat()

    query = db.table("transactions").select("date,amount,category") \
        .eq("user_id", user_id).gte("date", start_date).lt("amount", 0)
    if category:
        query = query.eq("category", category)

    result = query.execute()

    monthly: dict = defaultdict(float)
    for t in result.data:
        month_key = t["date"][:7]  # "YYYY-MM"
        monthly[month_key] += abs(t["amount"])

    results = []
    for i in range(months - 1, -1, -1):
        mo = (today.month - i - 1) % 12 + 1
        yr = today.year + ((today.month - i - 1) // 12)
        month_key = f"{yr:04d}-{mo:02d}"
        month_start = date(yr, mo, 1)
        results.append({
            "month": month_key,
            "label": month_start.strftime("%b %Y"),
            "total_spending": round(monthly.get(month_key, 0), 2),
        })

    return {"trend": results, "category": category or "all"}


def _get_subscriptions(inp: Dict, user_id: str, db) -> Dict:
    result = db.table("subscriptions").select("*").eq("user_id", user_id).execute()
    subs = result.data
    return {
        "subscriptions": [
            {
                "merchant": s["merchant"],
                "amount": s["amount"],
                "frequency_days": s["frequency_days"],
                "frequency_label": _freq_label(s["frequency_days"]),
                "last_seen": s.get("last_seen"),
                "occurrence_count": s.get("occurrence_count", 0),
                "annual_cost": round(s["amount"] * (365 / s["frequency_days"]), 2),
            }
            for s in subs
        ],
        "total_monthly_cost": round(sum(s["amount"] * (30 / s["frequency_days"]) for s in subs), 2),
    }


def _freq_label(days: int) -> str:
    return {7: "weekly", 14: "bi-weekly", 30: "monthly", 90: "quarterly", 365: "annual"}.get(
        days, f"every {days} days"
    )


def _get_anomalies(inp: Dict, user_id: str, db) -> Dict:
    result = db.table("anomalies").select("*").eq("user_id", user_id).order("amount", desc=True).execute()
    return {
        "anomalies": [
            {
                "merchant": a.get("merchant"),
                "amount": a.get("amount"),
                "category": a.get("category"),
                "date": a.get("date"),
                "reason": a.get("reason"),
                "severity": a.get("severity"),
            }
            for a in result.data
        ]
    }


def _get_budgets(inp: Dict, user_id: str, db) -> Dict:
    budgets_res = db.table("budgets").select("*").eq("user_id", user_id).execute()
    today = date.today()

    result = []
    for b in budgets_res.data:
        if b["period"] == "monthly":
            start = date(today.year, today.month, 1).isoformat()
            end = today.isoformat()
        else:
            start = (today - timedelta(days=today.weekday())).isoformat()
            end = today.isoformat()

        spent_res = db.table("transactions").select("amount") \
            .eq("user_id", user_id).eq("category", b["category"]) \
            .gte("date", start).lte("date", end).lt("amount", 0).execute()
        spent = sum(abs(t["amount"]) for t in spent_res.data)

        result.append({
            "id": b["id"],
            "category": b["category"],
            "budget": b["amount"],
            "spent": round(spent, 2),
            "remaining": round(b["amount"] - spent, 2),
            "percent_used": round((spent / b["amount"]) * 100, 1) if b["amount"] > 0 else 0,
            "period": b["period"],
            "status": "over" if spent > b["amount"] else "warning" if spent > b["amount"] * 0.85 else "ok",
        })

    return {"budgets": result}


def _set_budget(inp: Dict, user_id: str, db) -> Dict:
    category, amount, period = inp["category"], float(inp["amount"]), inp["period"]
    db.table("budgets").upsert(
        {"user_id": user_id, "category": category, "amount": amount, "period": period},
        on_conflict="user_id,category",
    ).execute()
    return {"set": True, "category": category, "amount": amount, "period": period}


def _lookup_merchant(inp: Dict, user_id: str, db) -> Dict:
    merchant = inp["merchant_name"]
    amount = inp.get("amount")
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                "https://api.duckduckgo.com/",
                params={"q": f"{merchant} company what is", "format": "json", "no_redirect": "1"},
            )
            abstract = resp.json().get("AbstractText", "")
            if abstract:
                return {"merchant": merchant, "info": abstract, "source": "DuckDuckGo"}
    except Exception:
        pass

    return {
        "merchant": merchant,
        "info": f"No web result for '{merchant}'. Amount Rs {amount:.0f} suggests a {_guess_cat(amount) if amount else 'general'} expense.",
        "source": "inference",
    }


def _guess_cat(amount: float) -> str:
    if amount < 500:
        return "small app or in-app purchase"
    if amount < 2000:
        return "streaming or digital subscription"
    if amount < 8000:
        return "software, utility, or mid-tier service"
    if amount < 30000:
        return "retail, dining, or professional service"
    return "large purchase or business expense"


def _get_conflicts(inp: Dict, user_id: str, db) -> Dict:
    days = int(inp.get("days", 90))
    since = (date.today() - timedelta(days=days)).isoformat()

    result = db.table("transactions") \
        .select("id,date,amount,merchant,source,category") \
        .eq("user_id", user_id) \
        .gte("date", since) \
        .order("date", desc=False) \
        .execute()

    txns = result.data
    conflicts = []
    seen_pairs = set()

    for i, t1 in enumerate(txns):
        for t2 in txns[i + 1:]:
            # Only flag across different sources
            if t1.get("source") == t2.get("source"):
                continue

            # Date within 2 days
            d1 = date.fromisoformat(t1["date"])
            d2 = date.fromisoformat(t2["date"])
            if abs((d1 - d2).days) > 2:
                continue

            # Amount within 15%
            a1, a2 = abs(t1["amount"]), abs(t2["amount"])
            if a1 == 0 or a2 == 0:
                continue
            diff_pct = abs(a1 - a2) / max(a1, a2)
            if diff_pct > 0.15:
                continue

            # Merchant substring match
            m1 = t1["merchant"].lower().strip()
            m2 = t2["merchant"].lower().strip()
            if m1 not in m2 and m2 not in m1:
                continue

            pair = (min(t1["id"], t2["id"]), max(t1["id"], t2["id"]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            conflicts.append({
                "record_a": {
                    "id": t1["id"],
                    "date": t1["date"],
                    "merchant": t1["merchant"],
                    "amount": t1["amount"],
                    "source": t1.get("source"),
                },
                "record_b": {
                    "id": t2["id"],
                    "date": t2["date"],
                    "merchant": t2["merchant"],
                    "amount": t2["amount"],
                    "source": t2.get("source"),
                },
                "amount_difference": round(abs(a1 - a2), 2),
                "date_difference_days": abs((d1 - d2).days),
            })

    return {
        "conflicts_found": len(conflicts),
        "conflicts": conflicts[:20],
        "note": "Each conflict is the same purchase likely recorded from two different sources. Review and delete the duplicate.",
    }
