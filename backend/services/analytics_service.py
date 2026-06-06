from datetime import date, timedelta
from typing import List, Dict
from database import get_db

COMMON_INTERVALS = [7, 14, 30, 90, 365]


def _closest_interval(avg: float) -> int:
    return min(COMMON_INTERVALS, key=lambda x: abs(x - avg))


def detect_subscriptions(user_id: str, db) -> List[Dict]:
    result = db.table("transactions").select("id,merchant,amount,date") \
        .eq("user_id", user_id).lt("amount", 0).order("date").execute()
    txns = result.data

    merchant_groups: Dict[str, list] = {}
    for t in txns:
        key = t["merchant"].strip().lower()
        merchant_groups.setdefault(key, []).append(t)

    subscriptions = []
    for merchant_key, group in merchant_groups.items():
        if len(group) < 2:
            continue

        amounts = [abs(t["amount"]) for t in group]
        avg_amount = sum(amounts) / len(amounts)
        if any(abs(a - avg_amount) / avg_amount > 0.15 for a in amounts):
            continue

        dates = sorted(date.fromisoformat(t["date"]) for t in group)
        intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        avg_interval = sum(intervals) / len(intervals)
        closest = _closest_interval(avg_interval)

        if abs(avg_interval - closest) / closest <= 0.25:
            subscriptions.append({
                "merchant": group[0]["merchant"],
                "amount": round(avg_amount, 2),
                "frequency_days": closest,
                "last_seen": dates[-1].isoformat(),
                "occurrence_count": len(group),
            })

    return subscriptions


def detect_anomalies(user_id: str, db) -> List[Dict]:
    ninety_days_ago = date.today() - timedelta(days=90)

    historical_res = db.table("transactions").select("category,amount") \
        .eq("user_id", user_id).lt("date", ninety_days_ago.isoformat()).lt("amount", 0).execute()

    cat_amounts: Dict[str, List[float]] = {}
    for t in historical_res.data:
        cat_amounts.setdefault(t["category"], []).append(abs(t["amount"]))

    cat_stats: Dict[str, tuple] = {}
    for cat, amts in cat_amounts.items():
        if len(amts) < 3:
            continue
        mean = sum(amts) / len(amts)
        variance = sum((a - mean) ** 2 for a in amts) / len(amts)
        std = variance ** 0.5
        if std > 0:
            cat_stats[cat] = (mean, std)

    recent_res = db.table("transactions").select("id,merchant,amount,category,date") \
        .eq("user_id", user_id).gte("date", ninety_days_ago.isoformat()).lt("amount", 0).execute()

    anomalies = []
    for t in recent_res.data:
        if t["category"] not in cat_stats:
            continue
        mean, std = cat_stats[t["category"]]
        z_score = (abs(t["amount"]) - mean) / std
        if z_score >= 2.0:
            severity = "high" if z_score >= 3.0 else "medium"
            anomalies.append({
                "transaction_id": t["id"],
                "merchant": t["merchant"],
                "amount": abs(t["amount"]),
                "category": t["category"],
                "date": t["date"],
                "reason": f"Rs {abs(t['amount']):.0f} is {z_score:.1f}x above your usual {t['category']} spending (avg Rs {mean:.0f})",
                "severity": severity,
            })

    return anomalies


def recompute_analytics(user_id: str):
    db = get_db()

    db.table("subscriptions").delete().eq("user_id", user_id).execute()
    db.table("anomalies").delete().eq("user_id", user_id).execute()

    subs = detect_subscriptions(user_id, db)
    if subs:
        db.table("subscriptions").insert([
            {
                "user_id": user_id,
                "merchant": s["merchant"],
                "amount": s["amount"],
                "frequency_days": s["frequency_days"],
                "last_seen": s["last_seen"],
                "occurrence_count": s["occurrence_count"],
            }
            for s in subs
        ]).execute()

    anomalies = detect_anomalies(user_id, db)
    if anomalies:
        db.table("anomalies").insert([
            {
                "user_id": user_id,
                "transaction_id": a.get("transaction_id"),
                "merchant": a["merchant"],
                "amount": a["amount"],
                "category": a["category"],
                "date": a["date"],
                "reason": a["reason"],
                "severity": a["severity"],
            }
            for a in anomalies
        ]).execute()
