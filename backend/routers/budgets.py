from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client
from database import get_db
import auth_utils

router = APIRouter(prefix="/budgets", tags=["budgets"])


class BudgetCreate(BaseModel):
    category: str
    amount: float
    period: str = "monthly"


@router.get("")
def list_budgets(
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    from services.finance_tools import _get_budgets
    return _get_budgets({}, str(current_user.id), db)


@router.post("")
def create_budget(
    req: BudgetCreate,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    if req.period not in ("monthly", "weekly"):
        raise HTTPException(status_code=400, detail="period must be 'monthly' or 'weekly'")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    uid = str(current_user.id)
    record = {"user_id": uid, "category": req.category, "amount": req.amount, "period": req.period}

    result = db.table("budgets").upsert(record, on_conflict="user_id,category").execute()
    b = result.data[0]
    return {"id": b["id"], "category": b["category"], "amount": b["amount"], "period": b["period"]}


@router.delete("/{budget_id}")
def delete_budget(
    budget_id: int,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    existing = db.table("budgets").select("id").eq("id", budget_id).eq("user_id", uid).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.table("budgets").delete().eq("id", budget_id).eq("user_id", uid).execute()
    return {"deleted": True}
