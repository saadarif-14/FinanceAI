from datetime import date, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func
import models

COMMON_INTERVALS = [7, 14, 30, 90, 365]


def _closest_interval(avg: float) -> int:
    return min(COMMON_INTERVALS, key=lambda x: abs(x - avg))


def detect_subscriptions(user_id: int, db: Session) -> List[Dict]:
    txns = (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == user_id, models.Transaction.amount < 0)
        .order_by(models.Transaction.date)
        .all()
    )

    merchant_groups: Dict[str, list] = {}
    for t in txns:
        key = t.merchant.strip().lower()
        merchant_groups.setdefault(key, []).append(t)

    subscriptions = []
    for merchant_key, group in merchant_groups.items():
        if len(group) < 2:
            continue

        amounts = [abs(t.amount) for t in group]
        avg_amount = sum(amounts) / len(amounts)
        # Skip if amount varies more than 15% — not a subscription
        if any(abs(a - avg_amount) / avg_amount > 0.15 for a in amounts):
            continue

        dates = sorted(t.date for t in group)
        intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        avg_interval = sum(intervals) / len(intervals)
        closest = _closest_interval(avg_interval)

        # Accept if within 25% of a standard period
        if abs(avg_interval - closest) / closest <= 0.25:
            subscriptions.append({
                "merchant": group[0].merchant,
                "amount": round(avg_amount, 2),
                "frequency_days": closest,
                "last_seen": dates[-1].isoformat(),
                "occurrence_count": len(group),
            })

    return subscriptions


def detect_anomalies(user_id: int, db: Session) -> List[Dict]:
    ninety_days_ago = date.today() - timedelta(days=90)

    # Historical baseline: transactions older than 90 days
    historical = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date < ninety_days_ago,
            models.Transaction.amount < 0,
        )
        .all()
    )

    # Compute mean + std per category
    cat_amounts: Dict[str, List[float]] = {}
    for t in historical:
        cat_amounts.setdefault(t.category, []).append(abs(t.amount))

    cat_stats: Dict[str, tuple] = {}
    for cat, amts in cat_amounts.items():
        if len(amts) < 3:
            continue
        mean = sum(amts) / len(amts)
        variance = sum((a - mean) ** 2 for a in amts) / len(amts)
        std = variance ** 0.5
        if std > 0:
            cat_stats[cat] = (mean, std)

    # Check recent transactions against baseline
    recent = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= ninety_days_ago,
            models.Transaction.amount < 0,
        )
        .all()
    )

    anomalies = []
    for t in recent:
        if t.category not in cat_stats:
            continue
        mean, std = cat_stats[t.category]
        z_score = (abs(t.amount) - mean) / std
        if z_score >= 2.0:
            severity = "high" if z_score >= 3.0 else "medium"
            anomalies.append({
                "transaction_id": t.id,
                "merchant": t.merchant,
                "amount": abs(t.amount),
                "category": t.category,
                "date": t.date.isoformat(),
                "reason": f"${abs(t.amount):.2f} is {z_score:.1f}x above your usual {t.category} spending (avg ${mean:.2f})",
                "severity": severity,
            })

    return anomalies


def recompute_analytics(user_id: int, db: Session):
    """Run after CSV import to refresh subscriptions + anomaly tables."""
    # Clear existing computed data
    db.query(models.Subscription).filter(models.Subscription.user_id == user_id).delete()
    db.query(models.Anomaly).filter(models.Anomaly.user_id == user_id).delete()

    subs = detect_subscriptions(user_id, db)
    for s in subs:
        db.add(models.Subscription(
            user_id=user_id,
            merchant=s["merchant"],
            amount=s["amount"],
            frequency_days=s["frequency_days"],
            last_seen=date.fromisoformat(s["last_seen"]),
            occurrence_count=s["occurrence_count"],
        ))

    anomalies = detect_anomalies(user_id, db)
    for a in anomalies:
        db.add(models.Anomaly(
            user_id=user_id,
            transaction_id=a.get("transaction_id"),
            merchant=a["merchant"],
            amount=a["amount"],
            category=a["category"],
            date=date.fromisoformat(a["date"]),
            reason=a["reason"],
            severity=a["severity"],
        ))

    db.commit()
