import os
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client
from database import get_db
import auth_utils

router = APIRouter(prefix="/auth", tags=["auth"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(req: RegisterRequest, db: Client = Depends(get_db)):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    try:
        result = db.auth.admin.create_user({
            "email": req.email.lower().strip(),
            "password": req.password,
            "user_metadata": {"name": req.name.strip()},
            "email_confirm": True,
        })
        if not result.user:
            raise HTTPException(status_code=400, detail="Registration failed")
        return {"message": "Account created successfully. You can now sign in."}
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "already registered" in msg or "already exists" in msg or "email address is already registered" in msg:
            raise HTTPException(status_code=400, detail="Email already registered")
        raise HTTPException(status_code=400, detail=f"Registration failed: {e}")


@router.post("/login")
def login(req: LoginRequest, db: Client = Depends(get_db)):
    try:
        resp = httpx.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Content-Type": "application/json",
            },
            json={"email": req.email.lower().strip(), "password": req.password},
            timeout=10.0,
        )
        data = resp.json()
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        sb_user = data.get("user", {})
        access_token = data.get("access_token")
        name = sb_user.get("user_metadata", {}).get("name", "")

        return {
            "token": access_token,
            "refresh_token": data.get("refresh_token"),
            "user": {
                "id": sb_user.get("id"),
                "email": sb_user.get("email"),
                "name": name,
            },
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
def refresh(req: RefreshRequest):
    try:
        resp = httpx.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Content-Type": "application/json",
            },
            json={"refresh_token": req.refresh_token},
            timeout=10.0,
        )
        data = resp.json()
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
        return {
            "token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")


@router.get("/me")
def me(current_user=Depends(auth_utils.get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "name": auth_utils.user_name(current_user),
    }
