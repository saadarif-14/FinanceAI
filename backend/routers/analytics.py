from collections import defaultdict
from datetime import date
from fastapi import APIRouter, Depends, BackgroundTasks
from supabase import Client
from database import get_db
import auth_utils
from services.analytics_service import recompute_analytics
from limiter import cache_get, cache_set

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/subscriptions")
def get_subscriptions(
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    result = db.table("subscriptions").select("*").eq("user_id", uid).execute()
    subs = result.data
    freq_label = {7: "weekly", 14: "bi-weekly", 30: "monthly", 90: "quarterly", 365: "annual"}
    return {
        "subscriptions": [
            {
                "merchant": s["merchant"],
                "amount": s["amount"],
                "frequency": freq_label.get(s["frequency_days"], f"every {s['frequency_days']} days"),
                "last_seen": s.get("last_seen"),
                "occurrence_count": s.get("occurrence_count", 0),
                "annual_cost": round(s["amount"] * (365 / s["frequency_days"]), 2),
            }
            for s in subs
        ],
        "total_monthly": round(sum(s["amount"] * (30 / s["frequency_days"]) for s in subs), 2),
    }


@router.get("/anomalies")
def get_anomalies(
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    result = db.table("anomalies").select("*").eq("user_id", uid).order("amount", desc=True).execute()
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


@router.get("/summary")
def get_summary(
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    cache_key = f"summary:{uid}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    today = date.today()
    month_start = date(today.year, today.month, 1).isoformat()
    today_str = today.isoformat()

    # Current month transactions
    month_txns_res = db.table("transactions").select("category,amount,date,merchant") \
        .eq("user_id", uid).gte("date", month_start).lte("date", today_str).execute()
    month_txns = month_txns_res.data

    # Split expenses vs income
    expense_totals: dict = defaultdict(float)
    expense_counts: dict = defaultdict(int)
    total_income = 0.0

    for t in month_txns:
        if t["amount"] < 0:
            expense_totals[t["category"]] += abs(t["amount"])
            expense_counts[t["category"]] += 1
        else:
            total_income += t["amount"]

    categories = sorted(
        [{"category": cat, "total": round(total, 2), "count": expense_counts[cat]}
         for cat, total in expense_totals.items()],
        key=lambda x: x["total"],
        reverse=True,
    )

    # Total transaction count
    total_txns_res = db.table("transactions").select("id", count="exact").eq("user_id", uid).execute()
    total_txns = total_txns_res.count or 0

    # Recent transactions (last 5)
    recent_res = db.table("transactions").select("date,amount,merchant,category") \
        .eq("user_id", uid).order("date", desc=True).limit(5).execute()

    # Subscriptions
    subs_res = db.table("subscriptions").select("amount,frequency_days").eq("user_id", uid).execute()
    subs = subs_res.data
    sub_monthly = sum(s["amount"] * (30 / s["frequency_days"]) for s in subs)

    # Anomalies count
    anomaly_res = db.table("anomalies").select("id", count="exact").eq("user_id", uid).execute()
    anomaly_count = anomaly_res.count or 0

    # Budget alerts — single query for all category spending, no N+1
    budgets_res = db.table("budgets").select("*").eq("user_id", uid).execute()
    over_budget = []
    if budgets_res.data:
        budget_cats = [b["category"] for b in budgets_res.data]
        # One query covering all budgeted categories for the month
        budget_spent_res = (
            db.table("transactions")
            .select("category,amount")
            .eq("user_id", uid)
            .in_("category", budget_cats)
            .gte("date", month_start)
            .lte("date", today_str)
            .lt("amount", 0)
            .execute()
        )
        cat_spent: dict = defaultdict(float)
        for t in budget_spent_res.data:
            cat_spent[t["category"]] += abs(t["amount"])

        for b in budgets_res.data:
            spent = cat_spent.get(b["category"], 0.0)
            if spent > b["amount"] * 0.85:
                over_budget.append({
                    "category": b["category"],
                    "budget": b["amount"],
                    "spent": round(spent, 2),
                    "percent": round((spent / b["amount"]) * 100, 1),
                })

    payload = {
        "current_month": {
            "total_spending": round(sum(c["total"] for c in categories), 2),
            "total_income": round(total_income, 2),
            "categories": categories,
        },
        "recent_transactions": recent_res.data,
        "subscriptions": {"count": len(subs), "monthly_cost": round(sub_monthly, 2)},
        "anomalies": {"count": anomaly_count},
        "budget_alerts": over_budget,
        "total_transactions": total_txns,
    }
    cache_set(cache_key, payload, ttl=60)
    return payload


@router.post("/recompute")
def recompute(
    background_tasks: BackgroundTasks,
    current_user=Depends(auth_utils.get_current_user),
):
    background_tasks.add_task(recompute_analytics, str(current_user.id))
    return {"status": "recomputing in background"}
