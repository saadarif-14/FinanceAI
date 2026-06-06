import io
from collections import defaultdict
from datetime import date, datetime as dt
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
import pandas as pd
from supabase import Client
from database import get_db
import auth_utils
from services.analytics_service import recompute_analytics
from limiter import cache_invalidate

router = APIRouter(prefix="/transactions", tags=["transactions"])

CATEGORY_MAP = {
    "Groceries": ["imtiaz", "carrefour", "metro cash", "alfatah", "naheed", "hyperstar", "chase up",
                  "agha", "united mart", "bin hashim", "supermarket", "grocery", "departmental"],
    "Dining": ["kfc", "mcdonald", "burger", "pizza hut", "dominos", "hardee", "subway", "bar.b.q",
               "cafe", "restaurant", "biryani", "karahi", "bakers", "lasania", "cosa nostra",
               "food panda", "bykea food", "cheetay", "cheezious"],
    "Transportation": ["careem", "uber", "bykea", "indrive", "pso", "shell", "total parco", "attock",
                       "caltex", "parking", "toll", "daewoo", "faisal movers", "bus", "rickshaw"],
    "Subscriptions": ["netflix", "spotify", "youtube premium", "jazz", "telenor", "zong", "ufone",
                      "ptcl", "starzplay", "tapmad", "icloud", "microsoft 365", "adobe", "dropbox",
                      "gym", "fitness", "f45", "anytime fitness"],
    "Entertainment": ["cinema", "nueplex", "cinepax", "atrium", "eveready", "concert", "event",
                      "movie", "steam", "playstation", "xbox", "nintendo"],
    "Healthcare": ["pharmacy", "medipak", "ds pharma", "alta pharmacy", "agha khan", "shifa",
                   "liaquat", "doctor", "dental", "clinic", "hospital", "lab", "chughtai",
                   "dr essa", "diagnostic", "medical"],
    "Shopping": ["daraz", "naheed", "breakout", "alkaram", "gul ahmed", "khaadi", "sapphire",
                 "bonanza", "outfitters", "limelight", "j.", "bata", "servis", "stylo",
                 "electronics", "mobile", "laptop", "techno city"],
    "Utilities": ["k-electric", "lesco", "iesco", "gepco", "sui gas", "ssgc", "sngpl", "ptcl",
                  "nayatel", "stormfiber", "wi-tribe", "internet", "electricity", "gas bill", "water"],
    "Income": ["salary", "payroll", "employer", "payment received", "income", "freelance",
               "transfer in", "refund", "commission", "bonus", "dividend"],
}


def categorize(merchant: str, description: str = "") -> str:
    text = f"{merchant} {description}".lower()
    for category, keywords in CATEGORY_MAP.items():
        if any(kw in text for kw in keywords):
            return category
    return "Other"


class TransactionCreate(BaseModel):
    date: date
    amount: float
    merchant: str
    category: Optional[str] = None
    description: Optional[str] = ""


def _fmt(t: dict) -> dict:
    return {
        "id": t["id"],
        "date": t["date"],
        "amount": t["amount"],
        "merchant": t["merchant"],
        "category": t["category"],
        "description": t.get("description", ""),
        "source": t.get("source", "manual"),
    }


@router.get("")
def list_transactions(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    query = db.table("transactions").select("*", count="exact").eq("user_id", uid)

    if start_date:
        query = query.gte("date", start_date)
    if end_date:
        query = query.lte("date", end_date)
    if category:
        query = query.eq("category", category)

    result = query.order("date", desc=True).range(offset, offset + limit - 1).execute()

    return {
        "total": result.count or 0,
        "transactions": [_fmt(t) for t in result.data],
    }


@router.post("")
def create_transaction(
    req: TransactionCreate,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    record = {
        "user_id": uid,
        "date": req.date.isoformat(),
        "amount": req.amount,
        "merchant": req.merchant,
        "category": req.category or categorize(req.merchant, req.description or ""),
        "description": req.description or "",
        "source": "manual",
    }
    result = db.table("transactions").insert(record).execute()
    t = result.data[0]
    cache_invalidate(f"summary:{uid}")
    return {"id": t["id"], "date": t["date"], "amount": t["amount"], "merchant": t["merchant"], "category": t["category"]}


@router.post("/import")
async def import_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    date_col     = next((c for c in df.columns if "date" in c), None)
    amount_col   = next((c for c in df.columns if "amount" in c or "price" in c or "cost" in c), None)
    merchant_col = next((c for c in df.columns if any(k in c for k in ["merchant", "description", "payee", "name", "vendor"])), None)
    category_col = next((c for c in df.columns if "category" in c or "type" in c), None)

    if not date_col or not amount_col or not merchant_col:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns for date, amount, and merchant. Found: {list(df.columns)}",
        )

    uid = str(current_user.id)
    records = []
    skipped = 0
    duplicates = 0
    errors = []

    for idx, row in df.iterrows():
        try:
            raw_date = str(row[date_col]).strip()
            parsed_date = None
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%Y/%m/%d"):
                try:
                    parsed_date = dt.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_date is None:
                skipped += 1
                continue

            raw_amount = str(row[amount_col]).strip().replace(",", "").replace("Rs", "").replace("(", "-").replace(")", "")
            amount = float(raw_amount)
            if amount == 0:
                skipped += 1
                continue

            merchant = str(row[merchant_col]).strip()
            if not merchant or merchant.lower() in ("nan", "none", ""):
                skipped += 1
                continue

            cat_val = str(row.get(category_col, "")).strip() if category_col else ""
            category = cat_val if cat_val and cat_val.lower() not in ("nan", "none", "") else categorize(merchant)

            records.append({
                "user_id": uid,
                "date": parsed_date.isoformat(),
                "amount": amount,
                "merchant": merchant,
                "category": category,
                "description": "",
                "source": "csv",
            })

        except Exception as e:
            errors.append(f"Row {idx}: {e}")
            skipped += 1

    conflicts = []

    if records:
        # Fetch existing transactions that overlap the date range of this import
        dates = [r["date"] for r in records]
        existing_res = (
            db.table("transactions")
            .select("date,amount,merchant,source")
            .eq("user_id", uid)
            .gte("date", min(dates))
            .lte("date", max(dates))
            .execute()
        )
        existing = existing_res.data

        # Build exact-fingerprint set for duplicate detection
        existing_fingerprints = {
            (r["date"], r["amount"], r["merchant"].strip().lower())
            for r in existing
        }

        unique_records = []
        for r in records:
            fp = (r["date"], r["amount"], r["merchant"].strip().lower())
            if fp in existing_fingerprints:
                duplicates += 1
            else:
                existing_fingerprints.add(fp)
                unique_records.append(r)

        # Conflict detection: same merchant ± date ± 15% amount but different source
        for new_r in unique_records:
            new_d = dt.strptime(new_r["date"], "%Y-%m-%d").date()
            new_amt = abs(new_r["amount"])
            new_merchant = new_r["merchant"].lower().strip()
            for ex in existing:
                ex_source = ex.get("source", "")
                if ex_source == "csv":
                    continue  # only flag csv vs manual/bank conflicts
                ex_d = dt.strptime(ex["date"], "%Y-%m-%d").date()
                if abs((new_d - ex_d).days) > 2:
                    continue
                ex_amt = abs(ex["amount"])
                if ex_amt == 0 or new_amt == 0:
                    continue
                diff_pct = abs(new_amt - ex_amt) / max(new_amt, ex_amt)
                if diff_pct > 0.15:
                    continue
                ex_merchant = ex["merchant"].lower().strip()
                if ex_merchant not in new_merchant and new_merchant not in ex_merchant:
                    continue
                conflicts.append({
                    "existing": {
                        "date": ex["date"],
                        "amount": ex["amount"],
                        "merchant": ex["merchant"],
                        "source": ex_source,
                    },
                    "imported": {
                        "date": new_r["date"],
                        "amount": new_r["amount"],
                        "merchant": new_r["merchant"],
                        "source": "csv",
                    },
                    "amount_difference": round(abs(new_amt - ex_amt), 2),
                    "date_difference_days": abs((new_d - ex_d).days),
                })

        for i in range(0, len(unique_records), 500):
            db.table("transactions").insert(unique_records[i:i + 500]).execute()

        records = unique_records

    cache_invalidate(f"summary:{uid}")
    background_tasks.add_task(recompute_analytics, uid)

    return {
        "imported": len(records),
        "skipped": skipped,
        "duplicates": duplicates,
        "conflicts": conflicts[:10],
        "errors": errors[:10] if errors else [],
    }


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    existing = db.table("transactions").select("id").eq("id", transaction_id).eq("user_id", uid).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.table("transactions").delete().eq("id", transaction_id).eq("user_id", uid).execute()
    cache_invalidate(f"summary:{uid}")
    return {"deleted": True}


@router.get("/stats/categories")
def stats_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    query = db.table("transactions").select("category,amount").eq("user_id", uid).lt("amount", 0)
    if start_date:
        query = query.gte("date", start_date)
    if end_date:
        query = query.lte("date", end_date)

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
    return {"categories": categories, "total": round(sum(c["total"] for c in categories), 2)}
