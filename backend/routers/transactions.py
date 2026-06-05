import io
from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import pandas as pd
from database import get_db
import models
import auth_utils
from services.analytics_service import recompute_analytics

router = APIRouter(prefix="/transactions", tags=["transactions"])

CATEGORY_MAP = {
    "Groceries": ["whole foods", "safeway", "kroger", "trader joe", "costco", "walmart", "target", "aldi",
                  "publix", "fresh market", "sprouts", "stop & shop", "giant", "meijer"],
    "Dining": ["restaurant", "cafe", "coffee", "starbucks", "mcdonalds", "mcdonald", "chipotle", "subway",
               "pizza", "sushi", "doordash", "uber eats", "grubhub", "postmates", "panera", "dunkin",
               "chick-fil-a", "wendy", "burger king", "taco bell", "five guys", "shake shack"],
    "Transportation": ["uber", "lyft", "gas station", "shell", "chevron", "bp ", "exxon", "mobil", "citgo",
                       "parking", "metro", "transit", "amtrak", "greyhound", "enterprise", "hertz", "zipcar"],
    "Subscriptions": ["netflix", "spotify", "hulu", "disney+", "hbo", "apple music", "amazon prime",
                      "microsoft 365", "office 365", "adobe", "dropbox", "icloud", "google one",
                      "gym", "fitness", "planet fitness", "la fitness", "24 hour"],
    "Entertainment": ["movie", "cinema", "theater", "concert", "ticketmaster", "steam", "xbox", "playstation",
                      "nintendo", "fandango", "amc ", "regal"],
    "Healthcare": ["pharmacy", "cvs", "walgreens", "rite aid", "doctor", "dental", "clinic", "hospital",
                   "medical", "optometrist", "urgent care", "lab corp", "quest diagnostics"],
    "Shopping": ["amazon", "ebay", "etsy", "zara", "h&m", "nike", "apple store", "best buy", "home depot",
                 "lowes", "ikea", "macy", "nordstrom", "gap", "old navy", "tj maxx", "marshalls"],
    "Utilities": ["electric", "electricity", "water utility", "gas utility", "internet", "comcast", "xfinity",
                  "at&t", "verizon", "t-mobile", "spectrum", "pg&e", "con ed", "duke energy"],
    "Income": ["salary", "payroll", "direct deposit", "paycheck", "income", "transfer in", "refund"],
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


@router.get("")
def list_transactions(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    query = db.query(models.Transaction).filter(models.Transaction.user_id == current_user.id)
    if start_date:
        query = query.filter(models.Transaction.date >= date.fromisoformat(start_date))
    if end_date:
        query = query.filter(models.Transaction.date <= date.fromisoformat(end_date))
    if category:
        query = query.filter(models.Transaction.category == category)

    total = query.count()
    txns = query.order_by(models.Transaction.date.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "transactions": [
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "amount": t.amount,
                "merchant": t.merchant,
                "category": t.category,
                "description": t.description,
                "source": t.source,
            }
            for t in txns
        ],
    }


@router.post("")
def create_transaction(
    req: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    t = models.Transaction(
        user_id=current_user.id,
        date=req.date,
        amount=req.amount,
        merchant=req.merchant,
        category=req.category or categorize(req.merchant, req.description or ""),
        description=req.description or "",
        source="manual",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "date": t.date.isoformat(), "amount": t.amount, "merchant": t.merchant, "category": t.category}


@router.post("/import")
async def import_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Import transactions from CSV. Expected columns (flexible):
    date, amount, merchant/description, category (optional)

    Handles: duplicates, missing fields, mixed date formats, junk rows.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Flexible column detection
    date_col = next((c for c in df.columns if "date" in c), None)
    amount_col = next((c for c in df.columns if "amount" in c or "price" in c or "cost" in c), None)
    merchant_col = next((c for c in df.columns if any(k in c for k in ["merchant", "description", "payee", "name", "vendor"])), None)
    category_col = next((c for c in df.columns if "category" in c or "type" in c), None)

    if not date_col or not amount_col or not merchant_col:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns for date, amount, and merchant. Found: {list(df.columns)}",
        )

    imported = 0
    skipped = 0
    errors = []

    for idx, row in df.iterrows():
        try:
            # Parse date (try multiple formats)
            raw_date = str(row[date_col]).strip()
            from datetime import datetime as dt
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

            raw_amount = str(row[amount_col]).strip().replace(",", "").replace("$", "").replace("(", "-").replace(")", "")
            amount = float(raw_amount)
            if amount == 0:
                skipped += 1
                continue

            merchant = str(row[merchant_col]).strip()
            if not merchant or merchant.lower() in ("nan", "none", ""):
                skipped += 1
                continue

            category = str(row[category_col]).strip() if category_col and str(row.get(category_col, "")).lower() not in ("nan", "none", "") else None
            if not category:
                category = categorize(merchant)

            t = models.Transaction(
                user_id=current_user.id,
                date=parsed_date,
                amount=amount,
                merchant=merchant,
                category=category,
                description="",
                source="csv",
            )
            db.add(t)
            imported += 1

        except Exception as e:
            errors.append(f"Row {idx}: {e}")
            skipped += 1

    db.commit()

    # Re-run analytics in background after import
    background_tasks.add_task(recompute_analytics, current_user.id, db)

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:10] if errors else [],
    }


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    t = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.user_id == current_user.id,
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(t)
    db.commit()
    return {"deleted": True}


@router.get("/stats/categories")
def stats_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    query = db.query(
        models.Transaction.category,
        func.sum(models.Transaction.amount).label("total"),
        func.count(models.Transaction.id).label("count"),
    ).filter(
        models.Transaction.user_id == current_user.id,
        models.Transaction.amount < 0,
    )
    if start_date:
        query = query.filter(models.Transaction.date >= date.fromisoformat(start_date))
    if end_date:
        query = query.filter(models.Transaction.date <= date.fromisoformat(end_date))

    rows = query.group_by(models.Transaction.category).all()
    categories = sorted(
        [{"category": r.category, "total": round(abs(r.total), 2), "count": r.count} for r in rows],
        key=lambda x: x["total"],
        reverse=True,
    )
    return {"categories": categories, "total": round(sum(c["total"] for c in categories), 2)}
