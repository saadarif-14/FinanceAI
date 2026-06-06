import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from supabase import Client
from database import get_db
import auth_utils
from services import ai_service
from limiter import check_rate_limit

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    image_data: Optional[str] = None
    image_type: Optional[str] = None


def _display_messages(messages: list) -> list:
    result = []
    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            result.append({"role": role, "content": content})
        elif isinstance(content, list):
            texts = [b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
            if texts:
                result.append({"role": role, "content": " ".join(texts)})
    return result


@router.get("/conversations")
def list_conversations(
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    result = db.table("conversations").select("id,title,created_at,updated_at,messages") \
        .eq("user_id", uid).order("updated_at", desc=True).execute()
    return [
        {
            "id": c["id"],
            "title": c["title"],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
            "message_count": len(_display_messages(c.get("messages") or [])),
        }
        for c in result.data
    ]


@router.post("/conversations")
def new_conversation(
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    result = db.table("conversations").insert({"user_id": uid, "title": "New Chat", "messages": []}).execute()
    c = result.data[0]
    return {"id": c["id"], "title": c["title"], "created_at": c["created_at"]}


@router.get("/conversations/{conv_id}")
def get_conversation(
    conv_id: int,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    result = db.table("conversations").select("*").eq("id", conv_id).eq("user_id", uid).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    c = result.data[0]
    return {
        "id": c["id"],
        "title": c["title"],
        "messages": _display_messages(c.get("messages") or []),
        "created_at": c["created_at"],
    }


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: int,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    existing = db.table("conversations").select("id").eq("id", conv_id).eq("user_id", uid).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.table("conversations").delete().eq("id", conv_id).eq("user_id", uid).execute()
    return {"deleted": True}


@router.post("")
def chat(
    req: ChatRequest,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    if not req.message and not req.image_data:
        raise HTTPException(status_code=400, detail="Provide a message or an image")

    check_rate_limit(str(current_user.id))

    response, conv_id, title = ai_service.chat(
        user=current_user,
        message=req.message,
        db=db,
        conversation_id=req.conversation_id,
        image_data=req.image_data,
        image_type=req.image_type,
    )
    return {"response": response, "conversation_id": conv_id, "title": title}


@router.post("/stream")
def chat_stream(
    req: ChatRequest,
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    if not req.message and not req.image_data:
        raise HTTPException(status_code=400, detail="Provide a message or an image")
    check_rate_limit(str(current_user.id))

    def generate():
        try:
            for item in ai_service.chat_stream(
                user=current_user,
                message=req.message,
                db=db,
                conversation_id=req.conversation_id,
                image_data=req.image_data,
                image_type=req.image_type,
            ):
                if isinstance(item, dict):
                    yield f"data: {json.dumps({'type': 'done', **item})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'chunk', 'content': item})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history")
def get_history(
    db: Client = Depends(get_db),
    current_user=Depends(auth_utils.get_current_user),
):
    uid = str(current_user.id)
    result = db.table("conversations").select("messages").eq("user_id", uid) \
        .order("updated_at", desc=True).limit(1).execute()
    if not result.data:
        return {"messages": []}
    return {"messages": _display_messages(result.data[0].get("messages") or [])}
