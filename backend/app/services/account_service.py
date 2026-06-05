from typing import Any, Dict
from fastapi import HTTPException, Request, status

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters.")

    stored = user.get("password_hash") or user.get("password") or ""
    if stored and stored != current:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")

    update_user(user["id"], {"password": new_pwd})
    return {"success": True, "message": "Password changed successfully."}

