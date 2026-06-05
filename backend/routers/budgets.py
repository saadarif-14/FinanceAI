from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
import models
import auth_utils

router = APIRouter(prefix="/budgets", tags=["budgets"])


class BudgetCreate(BaseModel):
    category: str
    amount: float
    period: str = "monthly"


@router.get("")
def list_budgets(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    from services.finance_tools import _get_budgets
    return _get_budgets({}, current_user.id, db)


@router.post("")
def create_budget(
    req: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    if req.period not in ("monthly", "weekly"):
        raise HTTPException(status_code=400, detail="period must be 'monthly' or 'weekly'")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    existing = db.query(models.Budget).filter(
        models.Budget.user_id == current_user.id,
        models.Budget.category == req.category,
    ).first()

    if existing:
        existing.amount = req.amount
        existing.period = req.period
    else:
        existing = models.Budget(
            user_id=current_user.id,
            category=req.category,
            amount=req.amount,
            period=req.period,
        )
        db.add(existing)

    db.commit()
    db.refresh(existing)
    return {"id": existing.id, "category": existing.category, "amount": existing.amount, "period": existing.period}


@router.delete("/{budget_id}")
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    b = db.query(models.Budget).filter(
        models.Budget.id == budget_id,
        models.Budget.user_id == current_user.id,
    ).first()
    if not b:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(b)
    db.commit()
    return {"deleted": True}
