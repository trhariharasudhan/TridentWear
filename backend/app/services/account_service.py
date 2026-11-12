import re
import secrets
from datetime import date, datetime, timezone
from typing import Any, Dict
from fastapi import HTTPException, Request, status
import bcrypt

from app.core.db_switch import db

DEFAULT_SETTINGS = {"order_updates_email": True, "order_updates_whatsapp": False, "new_drops": True, "marketing": False}


def _settings(user: Dict[str, Any]) -> Dict[str, Any]:
    stored = user.get("settings") if isinstance(user.get("settings"), dict) else {}
    return {k: bool(stored.get(k, v)) for k, v in DEFAULT_SETTINGS.items()}


def _clean_birthday(value: Any) -> Any:
    raw = str(value or "").strip()
    if not raw:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise HTTPException(status_code=400, detail="Enter your birthday as a date.")
    try:
        born = date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Enter a real date for your birthday.")
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age < 13 or age > 110:
        raise HTTPException(status_code=400, detail="Enter a valid birthday.")
    return raw

from app.services.auth_service import get_session_user, serialize_user, update_user


def get_account_profile(request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in first.")
    return {
        "user": serialize_user(user),
        "addresses": user.get("addresses", []),
        "default_address_id": user.get("default_address_id"),
        "settings": _settings(user),
        "birthday": user.get("birthday"),
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
        # only known switches, always booleans
        merged = {**_settings(user), **{k: bool(v) for k, v in dict(payload.settings).items() if k in DEFAULT_SETTINGS}}
        changes["settings"] = merged
    if getattr(payload, "birthday", None) is not None:
        changes["birthday"] = _clean_birthday(payload.birthday)

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
        "settings": _settings(user),
        "birthday": user.get("birthday"),
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


def delete_account(payload: Any, request: Request) -> Dict[str, Any]:
    """Right to erasure (DPDP Act): anonymise the person, keep orders for tax/invoice records.

    Requires the current password and the word DELETE. Admin accounts cannot delete themselves here.
    """
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in first.")
    if str(getattr(payload, "confirm", "")).strip().upper() != "DELETE":
        raise HTTPException(status_code=400, detail="Type DELETE to confirm.")
    if user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin accounts can't be deleted from the storefront.")
    stored = user.get("password_hash") or ""
    try:
        ok = bool(stored) and bcrypt.checkpw(str(getattr(payload, "password", "")).encode(), stored.encode())
    except ValueError:
        ok = False
    if not ok:
        raise HTTPException(status_code=400, detail="That password is not correct.")

    for row in db.read("addresses", {"user_id": user["id"]}):
        db.delete("addresses", {"address_id": row["address_id"]})
    update_user(user["id"], {
        "name": "Deleted user",
        "email": f"deleted-{user['id']}-{secrets.token_hex(4)}@deleted.invalid",
        "phone": None, "gender": None, "birthday": None, "settings": {},
        "password_hash": bcrypt.hashpw(secrets.token_bytes(24), bcrypt.gensalt()).decode(),
        "is_active": False, "deleted_at": datetime.now(timezone.utc).isoformat(),
    })
    from app.services.auth_service import logout_user
    logout_user(request)
    return {"success": True, "message": "Your account has been deleted. Your past orders are kept only for invoices."}
