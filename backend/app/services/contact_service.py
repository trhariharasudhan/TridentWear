import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.core.db_switch import db

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def create_contact_message(name: str, email: str, message: str) -> Dict[str, Any]:
    db.insert("contacts", {
        "name": name,
        "email": email,
        "message": message,
    })
    return {"success": True, "message": "Message sent successfully."}

def process_send_chat(user: Optional[Dict[str, Any]], thread_id: Optional[str], message: str) -> Dict[str, Any]:
    if user:
        tid = f"user_{user['id']}"
        author = user["name"]
    else:
        tid = thread_id
        if not tid or tid == "undefined" or tid == "null":
            tid = f"anon_{uuid.uuid4().hex[:8]}"
        author = "Guest"
        
    msg = {
        "thread_id": tid,
        "author": author,
        "role": "user",
        "message": message,
        "timestamp": now_iso(),
        "read": False
    }

    inserted = db.insert("chat_messages", msg)
    return {"success": True, "message": inserted, "thread_id": tid}

def fetch_chat_messages(thread_id: str) -> List[Dict[str, Any]]:
    return db.read("chat_messages", {"thread_id": thread_id})

def fetch_admin_chats() -> Dict[str, Any]:
    chats = db.read("chat_messages", {})
    threads = {}
    for c in chats:
        tid = c["thread_id"]
        if tid not in threads:
            threads[tid] = []
        threads[tid].append(c)
    return threads

def process_admin_reply(thread_id: str, message: str) -> Dict[str, Any]:
    msg = {
        "thread_id": thread_id,
        "author": "Supporting Staff",
        "role": "admin",
        "message": message,
        "timestamp": now_iso(),
        "read": True
    }

    # Mark other messages in the thread as read
    db.update("chat_messages", {"thread_id": thread_id}, {"read": True})
    inserted = db.insert("chat_messages", msg)
    return {"success": True, "message": inserted}
