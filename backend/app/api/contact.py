from fastapi import APIRouter, Request, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import re
from app.services.contact_service import (
    create_contact_message, process_send_chat, fetch_chat_messages, fetch_admin_chats, process_admin_reply
)
from app.services.auth_service import get_session_user, require_admin

router = APIRouter(prefix="/api/v1", tags=["contact", "chat"])

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

class ContactPayload(BaseModel):
    name: str
    email: str
    subject: Optional[str] = None
    message: str

class ChatMessagePayload(BaseModel):
    message: str
    admin_reply: bool = False
    thread_id: Optional[str] = None

@router.post("/contact")
def create_contact(payload: ContactPayload) -> Dict[str, Any]:
    name = payload.name.strip()
    email = payload.email.strip().lower()
    subject = payload.subject.strip() if payload.subject else "No Subject"
    message = payload.message.strip()

    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Name is required.")
    if len(message) < 10:
        raise HTTPException(status_code=400, detail="Message must be at least 10 characters.")

    return create_contact_message(name, email, message, subject)

@router.post("/chat/send")
def send_chat(payload: ChatMessagePayload, request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    return process_send_chat(user, payload.thread_id, payload.message)

@router.get("/chat/messages")
def get_chat_messages(thread_id: str) -> List[Dict[str, Any]]:
    return fetch_chat_messages(thread_id)

@router.get("/admin/chat")
def admin_get_chats(_: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return fetch_admin_chats()

@router.post("/admin/chat/reply")
def admin_reply_chat(payload: ChatMessagePayload, request: Request, _: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    if not payload.thread_id:
        raise HTTPException(status_code=400, detail="Thread ID required")
    return process_admin_reply(payload.thread_id, payload.message)
