from typing import Any, Dict
from fastapi import HTTPException, Request, status
import bcrypt

from app.services.auth_service import get_session_user, serialize_user, update_user


def get_account_profile(request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in first.")
    return {
        "user": serialize_user(user),
        "addresses": user.get("addresses", []),
        "default_address_id": user.get("default_address_id"),
        "settings": user.get("settings", {"notifications": True, "marketing": False}),
    }


def update_account_profile(payload: Any, request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in first.")

    changes: Dict[str, Any] = {}
    if getattr(payload, "name", None) is not None:
        name = str(payload.name).strip()
        if len(name) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name must be at least 2 characters.")
        changes["name"] = name
    if getattr(payload, "phone", None) is not None:
        changes["phone"] = str(payload.phone).strip()
    if getattr(payload, "gender", None) is not None:
        changes["gender"] = str(payload.gender).strip()
    if getattr(payload, "addresses", None) is not None:
        changes["addresses"] = [address for address in payload.addresses if isinstance(address, dict)]
    if getattr(payload, "default_address_id", None) is not None:
        changes["default_address_id"] = str(payload.default_address_id)
    if getattr(payload, "settings", None) is not None:
        changes["settings"] = payload.settings

    updated = update_user(user["id"], changes) or user
    return {
        "success": True,
        "message": "Profile updated.",
        "profile": get_account_profile_from_user(updated),
    }


def get_account_profile_from_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "user": serialize_user(user),
        "addresses": user.get("addresses", []),
        "default_address_id": user.get("default_address_id"),
        "settings": user.get("settings", {"notifications": True, "marketing": False}),
    }


def change_account_password(payload: Any, request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in first.")

    current = str(getattr(payload, "current_password", "") or "").strip()
    new_pwd = str(getattr(payload, "new_password", "") or "").strip()

    if len(new_pwd) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters."
        )

    # ── Verify current password against bcrypt hash ──────────────────────────
    stored_hash = user.get("password_hash") or user.get("password") or ""
    if stored_hash:
        try:
            stored_bytes = stored_hash.encode("utf-8") if isinstance(stored_hash, str) else stored_hash
            current_bytes = current.encode("utf-8")
            # Check if stored value is a bcrypt hash (starts with $2b$ or $2a$)
            if stored_hash.startswith(("$2b$", "$2a$", "$2y$")):
                if not bcrypt.checkpw(current_bytes, stored_bytes):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Current password is incorrect."
                    )
            else:
                # Plaintext fallback (legacy or dev-seeded accounts without hash)
                if stored_hash != current:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Current password is incorrect."
                    )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Password verification failed."
            )

    # ── Hash new password with bcrypt before saving ───────────────────────────
    new_hash = bcrypt.hashpw(new_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    update_user(user["id"], {"password_hash": new_hash, "password": None})
    return {"success": True, "message": "Password changed successfully."}
