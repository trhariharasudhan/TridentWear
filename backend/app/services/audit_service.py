import logging
from typing import Any, Dict, Optional
from fastapi import Request
from app.core.db_switch import db

log = logging.getLogger(__name__)

def log_action(
    admin_id: Optional[int],
    action_type: str,
    target_entity: str,
    target_id: Optional[str],
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None
) -> Optional[Dict[str, Any]]:
    """
    Log an administrative action in the audit logs.
    Supports both JSON and SQL configurations via db.insert.
    """
    ip_address = None
    user_agent = None

    if request is not None:
        if request.client:
            ip_address = request.client.host
        user_agent = request.headers.get("user-agent")

    payload = {
        "admin_id": admin_id,
        "action_type": action_type,
        "target_entity": target_entity,
        "target_id": str(target_id) if target_id is not None else None,
        "before_state": before_state,
        "after_state": after_state,
        "ip_address": ip_address,
        "user_agent": user_agent,
    }

    try:
        inserted = db.insert("admin_audit_logs", payload)
        log.info(
            "Audit logged successfully: action_type=%s, target_entity=%s, target_id=%s",
            action_type,
            target_entity,
            target_id
        )
        return inserted
    except Exception as e:
        log.error("Failed to write to admin_audit_logs: %s", e)
        return None
