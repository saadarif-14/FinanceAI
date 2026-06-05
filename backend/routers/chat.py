from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
import models
import auth_utils
from services import ai_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    image_data: Optional[str] = None   # base64-encoded, no data URI prefix
    image_type: Optional[str] = None   # e.g. "image/jpeg"


@router.post("")
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    if not req.message and not req.image_data:
        raise HTTPException(status_code=400, detail="Provide a message or an image")

    response = ai_service.chat(
        user=current_user,
        message=req.message,
        db=db,
        image_data=req.image_data,
        image_type=req.image_type,
    )
    return {"response": response}


@router.get("/history")
def get_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    conv = db.query(models.Conversation).filter(models.Conversation.user_id == current_user.id).first()
    if not conv:
        return {"messages": []}

    # Return only text turns for display (strip tool internals)
    display = []
    for msg in (conv.messages or []):
        role = msg.get("role")
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            display.append({"role": role, "content": content})
        elif isinstance(content, list):
            texts = [b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
            if texts:
                display.append({"role": role, "content": " ".join(texts)})

    return {"messages": display}


@router.delete("/history")
def clear_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    conv = db.query(models.Conversation).filter(models.Conversation.user_id == current_user.id).first()
    if conv:
        conv.messages = []
        db.add(conv)
        db.commit()
    return {"cleared": True}
