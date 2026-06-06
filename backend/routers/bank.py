"""
Mock Bank API — simulates a real bank's open-banking REST endpoint.

Endpoints (no auth — the "bank" is a public API users connect to):
  GET /bank/accounts                           → list mock accounts
  GET /bank/transactions?account_id=&from_date=&to_date=&page=&limit=

Import endpoint (requires user auth):
  POST /bank/sync   { account_id, from_date?, to_date? }
       → pulls from mock bank and saves to the logged-in user's transactions
"""
from datetime import date, timedelta
import math
import random
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client
from database import get_db
import auth_utils
from routers.transactions import categorize

router = APIRouter(prefix="/bank", tags=["bank"])

# ── Mock accounts ─────────────────────────────────────────────────────────────

MOCK_ACCOUNTS = [
    {
        "account_id": "HBL-001-PKR",
        "bank_name": "Habib Bank Limited",
        "account_type": "Current Account",
        "account_number": "****4821",
        "currency": "PKR",
        "balance": 284750.00,
        "owner": "Demo User",
    },
    {
        "account_id": "MCB-002-PKR",
        "bank_name": "MCB Bank",
        "account_type": "Savings Account",
        "account_number": "****9134",
        "currency": "PKR",
        "balance": 120300.00,
        "owner": "Demo User",
    },
]

# ── Transaction seed data (merchant, category, amount_range, monthly_freq) ───

TRANSACTION_SEEDS = [
    # Income
    ("Employer Payroll",       "Income",          (180000, 200000),  1),
    ("Freelance Payment",      "Income",          (30000,  80000),   0.4),
    # Groceries
    ("Imtiaz Super Market",    "Groceries",       (3500,   8000),    4),
    ("Chase Up",               "Groceries",       (2000,   5000),    3),
    ("Metro Cash & Carry",     "Groceries",       (5000,   12000),   1),
    ("Naheed Super Market",    "Groceries",       (2500,   6000),    2),
    # Dining
    ("KFC Pakistan",           "Dining",          (900,    2500),    3),
    ("McDonald's Pakistan",    "Dining",          (800,    2000),    2),
    ("Hardee's",               "Dining",          (1000,   2200),    1),
    ("Burns Road Nihari",      "Dining",          (1500,   3500),    2),
    ("Cafe Flo",               "Dining",          (2000,   5000),    1),
    ("Gloria Jean's",          "Dining",          (600,    1500),    4),
    # Transportation
    ("Careem",                 "Transportation",  (300,    1200),    8),
    ("InDrive",                "Transportation",  (200,    900),     6),
    ("Pakistan Railways",      "Transportation",  (2000,   8000),   0.3),
    ("PSO Fuel Station",       "Transportation",  (3000,   6000),    3),
    # Subscriptions (fixed monthly)
    ("Netflix",                "Subscriptions",   (1500,   1500),    1),
    ("Spotify",                "Subscriptions",   (379,    379),     1),
    ("YouTube Premium",        "Subscriptions",   (329,    329),     1),
    ("Jazz Postpaid",          "Subscriptions",   (1200,   1800),    1),
    ("PTCL Internet",          "Subscriptions",   (2500,   2500),    1),
    ("Gym Membership",         "Subscriptions",   (3500,   5000),    1),
    # Utilities
    ("K-Electric",             "Utilities",       (4000,   12000),   1),
    ("SSGC Gas Bill",          "Utilities",       (1500,   5000),    1),
    ("KWSB Water Bill",        "Utilities",       (800,    1500),    1),
    # Healthcare
    ("Aga Khan Hospital",      "Healthcare",      (2000,   15000),   0.3),
    ("Sehat Kahani Pharmacy",  "Healthcare",      (800,    3000),    1),
    ("Dr. Ziauddin Hospital",  "Healthcare",      (3000,   8000),    0.2),
    # Shopping
    ("Daraz.pk",               "Shopping",        (1500,   8000),    3),
    ("Outfitters",             "Shopping",        (3000,   10000),   0.5),
    ("Khaadi",                 "Shopping",        (4000,   15000),   0.4),
    ("Sapphire",               "Shopping",        (3500,   12000),   0.3),
    ("Ideas by Gul Ahmed",     "Shopping",        (2500,   9000),    0.3),
    # Entertainment
    ("Cinepax Cinemas",        "Entertainment",   (1200,   3000),    1),
    ("Nueplex Cinema",         "Entertainment",   (1500,   3500),    0.5),
    ("Steam Games",            "Entertainment",   (500,    4000),    0.5),
]

# ── Anomalies injected randomly (once or twice per year) ─────────────────────

ANOMALY_SEEDS = [
    ("Daraz.pk - Big Sale",    "Shopping",        (35000,  90000)),
    ("Outfitters Eid Special", "Shopping",        (25000,  60000)),
    ("Pakistan Tour Package",  "Entertainment",   (40000,  120000)),
    ("Laptop - Techno City",   "Shopping",        (80000,  180000)),
    ("Mobile Phone - iZone",   "Shopping",        (60000,  150000)),
    ("Wedding Shopping",       "Shopping",        (50000,  200000)),
    ("Medical Emergency",      "Healthcare",      (30000,  80000)),
]


def _generate_transactions(account_id: str, from_date: date, to_date: date) -> list:
    """
    Deterministically generate transactions for a date range.
    Uses account_id + date as seed so same request always returns same data.
    """
    transactions = []
    txn_id = 1

    current = date(from_date.year, from_date.month, 1)
    end = date(to_date.year, to_date.month, 1)

    while current <= end:
        year, month = current.year, current.month
        seed = int(account_id.replace("-", "").replace("PKR", "0").replace("HBL", "1").replace("MCB", "2"), 36 if False else 10) + year * 100 + month
        rng = random.Random(seed)

        for merchant, category, (low, high), freq in TRANSACTION_SEEDS:
            occurrences = int(freq) + (1 if rng.random() < (freq % 1) else 0)
            for _ in range(occurrences):
                day = rng.randint(1, 28)
                txn_date = date(year, month, day)
                if txn_date < from_date or txn_date > to_date:
                    continue

                amount = round(rng.uniform(low, high), 0)
                if category == "Income":
                    amount = abs(amount)
                else:
                    amount = -abs(amount)

                # small random variance on subscriptions (±2%)
                if category == "Subscriptions" and low == high:
                    amount = -low

                transactions.append({
                    "transaction_id": f"{account_id}-{year}{month:02d}-{txn_id:04d}",
                    "date": txn_date.isoformat(),
                    "amount": amount,
                    "merchant": merchant,
                    "category": category,
                    "description": "",
                    "currency": "PKR",
                    "status": "settled",
                })
                txn_id += 1

        # Inject anomaly roughly twice a year (months 3 and 9)
        if month in (3, 9) or (month == 6 and rng.random() < 0.4):
            anomaly = rng.choice(ANOMALY_SEEDS)
            a_merchant, a_cat, (a_low, a_high) = anomaly
            day = rng.randint(10, 25)
            txn_date = date(year, month, day)
            if from_date <= txn_date <= to_date:
                transactions.append({
                    "transaction_id": f"{account_id}-{year}{month:02d}-ANOM-{txn_id}",
                    "date": txn_date.isoformat(),
                    "amount": -round(rng.uniform(a_low, a_high), 0),
                    "merchant": a_merchant,
                    "category": a_cat,
                    "description": "Large purchase",
                    "currency": "PKR",
                    "status": "settled",
                })
                txn_id += 1

        # Next month
        if month == 12:
            current = date(year + 1, 1, 1)
        else:
            current = date(year, month + 1, 1)

    # Sort by date descending (newest first)
    transactions.sort(key=lambda t: t["date"], reverse=True)

    # Filter strictly to requested range
    transactions = [t for t in transactions if from_date.isoformat() <= t["date"] <= to_date.isoformat()]
    return transactions


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/accounts")
def list_accounts():
    """Returns mock bank accounts. No auth required (simulates open-banking discovery)."""
    return {"accounts": MOCK_ACCOUNTS}


@router.get("/transactions")
def bank_transactions(
    account_id: str = Query(..., description="Account ID from /bank/accounts"),
    from_date: str = Query(default=None, description="YYYY-MM-DD — defaults to 3 years ago"),
    to_date: str = Query(default=None, description="YYYY-MM-DD — defaults to today"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, le=500),
):
    """
    Returns paginated transactions for a mock bank account.
    Covers up to 3 years of history by default.
    """
    if account_id not in [a["account_id"] for a in MOCK_ACCOUNTS]:
        raise HTTPException(status_code=404, detail="Account not found")

    today = date.today()
    try:
        start = date.fromisoformat(from_date) if from_date else date(today.year - 3, today.month, 1)
        end = date.fromisoformat(to_date) if to_date else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="from_date must be before to_date")

    all_txns = _generate_transactions(account_id, start, end)

    total = len(all_txns)
    total_pages = math.ceil(total / limit) if total > 0 else 1
    offset = (page - 1) * limit
    page_txns = all_txns[offset: offset + limit]

    return {
        "account_id": account_id,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "limit": limit,
        "transactions": page_txns,
    }


# ── Sync endpoint (requires user auth) ────────────────────────────────────────

class SyncRequest(BaseModel):
    account_id: str
    from_date: Optional[str] = None
    to_date: Optional[str] = None


@router.post("/sync")
def sync_bank(
    req: SyncRequest,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    """
    Pulls all transactions from the mock bank account and saves them
    to the authenticated user's transaction history.
    Skips duplicates based on transaction_id stored in description field.
    """
    from services.analytics_service import recompute_analytics

    if req.account_id not in [a["account_id"] for a in MOCK_ACCOUNTS]:
        raise HTTPException(status_code=404, detail="Account not found")

    today = date.today()
    try:
        start = date.fromisoformat(req.from_date) if req.from_date else date(today.year - 3, today.month, 1)
        end = date.fromisoformat(req.to_date) if req.to_date else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    uid = str(current_user.id)
    all_txns = _generate_transactions(req.account_id, start, end)

    records = [
        {
            "user_id": uid,
            "date": t["date"],
            "amount": t["amount"],
            "merchant": t["merchant"],
            "category": t["category"],
            "description": t["transaction_id"],
            "source": "bank",
        }
        for t in all_txns
    ]

    imported = 0
    if records:
        for i in range(0, len(records), 500):
            db.table("transactions").insert(records[i:i + 500]).execute()
        imported = len(records)

    recompute_analytics(uid)

    account = next(a for a in MOCK_ACCOUNTS if a["account_id"] == req.account_id)
    return {
        "imported": imported,
        "account": account["bank_name"],
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "message": f"Successfully synced {imported} transactions from {account['bank_name']}",
    }
