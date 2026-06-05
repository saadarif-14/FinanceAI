from datetime import date
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
import models
import auth_utils
from services.analytics_service import recompute_analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/subscriptions")
def get_subscriptions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    subs = db.query(models.Subscription).filter(models.Subscription.user_id == current_user.id).all()
    freq_label = {7: "weekly", 14: "bi-weekly", 30: "monthly", 90: "quarterly", 365: "annual"}
    return {
        "subscriptions": [
            {
                "merchant": s.merchant,
                "amount": s.amount,
                "frequency": freq_label.get(s.frequency_days, f"every {s.frequency_days} days"),
                "last_seen": s.last_seen.isoformat() if s.last_seen else None,
                "occurrence_count": s.occurrence_count,
                "annual_cost": round(s.amount * (365 / s.frequency_days), 2),
            }
            for s in subs
        ],
        "total_monthly": round(
            sum(s.amount * (30 / s.frequency_days) for s in subs), 2
        ),
    }


@router.get("/anomalies")
def get_anomalies(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    anomalies = (
        db.query(models.Anomaly)
        .filter(models.Anomaly.user_id == current_user.id)
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


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Full financial summary for the dashboard."""
    today = date.today()
    month_start = date(today.year, today.month, 1)

    # Current month spending by category
    rows = (
        db.query(
            models.Transaction.category,
            func.sum(models.Transaction.amount).label("total"),
            func.count(models.Transaction.id).label("count"),
        )
        .filter(
            models.Transaction.user_id == current_user.id,
            models.Transaction.date >= month_start,
            models.Transaction.date <= today,
            models.Transaction.amount < 0,
        )
        .group_by(models.Transaction.category)
        .all()
    )
    categories = sorted(
        [{"category": r.category, "total": round(abs(r.total), 2), "count": r.count} for r in rows],
        key=lambda x: x["total"],
        reverse=True,
    )

    # Current month income
    income = (
        db.query(func.sum(models.Transaction.amount))
        .filter(
            models.Transaction.user_id == current_user.id,
            models.Transaction.date >= month_start,
            models.Transaction.date <= today,
            models.Transaction.amount > 0,
        )
        .scalar()
        or 0.0
    )

    # Total transactions
    total_txns = db.query(func.count(models.Transaction.id)).filter(
        models.Transaction.user_id == current_user.id
    ).scalar()

    # Recent transactions
    recent = (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == current_user.id)
        .order_by(models.Transaction.date.desc())
        .limit(5)
        .all()
    )

    # Subscription count + monthly cost
    subs = db.query(models.Subscription).filter(models.Subscription.user_id == current_user.id).all()
    sub_monthly = sum(s.amount * (30 / s.frequency_days) for s in subs)

    # Anomaly count
    anomaly_count = db.query(func.count(models.Anomaly.id)).filter(
        models.Anomaly.user_id == current_user.id
    ).scalar()

    # Budget status
    budgets = db.query(models.Budget).filter(models.Budget.user_id == current_user.id).all()
    over_budget = []
    for b in budgets:
        spent = (
            db.query(func.sum(func.abs(models.Transaction.amount)))
            .filter(
                models.Transaction.user_id == current_user.id,
                models.Transaction.category == b.category,
                models.Transaction.date >= month_start,
                models.Transaction.amount < 0,
            )
            .scalar()
            or 0.0
        )
        if spent > b.amount * 0.85:
            over_budget.append({
                "category": b.category,
                "budget": b.amount,
                "spent": round(spent, 2),
                "percent": round((spent / b.amount) * 100, 1),
            })

    return {
        "current_month": {
            "total_spending": round(sum(c["total"] for c in categories), 2),
            "total_income": round(income, 2),
            "categories": categories,
        },
        "recent_transactions": [
            {
                "date": t.date.isoformat(),
                "amount": t.amount,
                "merchant": t.merchant,
                "category": t.category,
            }
            for t in recent
        ],
        "subscriptions": {
            "count": len(subs),
            "monthly_cost": round(sub_monthly, 2),
        },
        "anomalies": {"count": anomaly_count},
        "budget_alerts": over_budget,
        "total_transactions": total_txns,
    }


@router.post("/recompute")
def recompute(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    background_tasks.add_task(recompute_analytics, current_user.id, db)
    return {"status": "recomputing in background"}
