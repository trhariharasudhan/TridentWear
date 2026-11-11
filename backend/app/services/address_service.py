"""Saved delivery addresses, stored in the `addresses` table.

Previously addresses lived as a list on the user record, which the SQL adapter
silently dropped (users has no `addresses` column), so they vanished in postgres
mode. This service uses the real table in both JSON and SQL modes.
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import HTTPException, Request, status

from app.core.db_switch import db
from app.services.auth_service import get_session_user

MAX_ADDRESSES = 10
PIN_RE = re.compile(r"^[1-9][0-9]{5}$")
FIELDS = ("label", "name", "phone", "street", "area", "city", "state", "pin")


def _user(request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in first.")
    return user


def _clean(payload: Dict[str, Any], partial: bool = False) -> Dict[str, Any]:
    data = {k: str(payload.get(k) or "").strip() for k in FIELDS if k in payload or not partial}
    if not partial or "street" in data:
        if len(data.get("street", "")) < 4:
            raise HTTPException(status_code=400, detail="Enter the house number and street.")
    if not partial or "city" in data:
        if len(data.get("city", "")) < 2:
            raise HTTPException(status_code=400, detail="Enter a city.")
    if not partial or "state" in data:
        if len(data.get("state", "")) < 2:
            raise HTTPException(status_code=400, detail="Enter a state.")
    if not partial or "pin" in data:
        if not PIN_RE.match(data.get("pin", "")):
            raise HTTPException(status_code=400, detail="Enter a valid 6-digit PIN code.")
    if "phone" in data and data["phone"] and not re.fullmatch(r"[6-9][0-9]{9}", re.sub(r"\D", "", data["phone"])[-10:]):
        raise HTTPException(status_code=400, detail="Enter a valid 10-digit mobile number.")
    if "label" in data:
        data["label"] = (data["label"] or "Home")[:24]
    for k in ("name", "street", "area", "city", "state"):
        if k in data:
            data[k] = data[k][:120]
    return data


def _public(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: row.get(k) for k in ("address_id", "label", "street", "area", "city", "state", "pin", "country")}
    out["is_default"] = bool(row.get("is_default"))
    return out


def list_addresses(request: Request) -> List[Dict[str, Any]]:
    user = _user(request)
    rows = db.read("addresses", {"user_id": user["id"]})
    rows.sort(key=lambda r: (not r.get("is_default"), str(r.get("created_at") or "")))
    return [_public(r) for r in rows]


def _clear_default(user_id: int) -> None:
    for row in db.read("addresses", {"user_id": user_id}):
        if row.get("is_default"):
            db.update("addresses", {"address_id": row["address_id"]}, {"is_default": False})


def add_address(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    user = _user(request)
    existing = db.read("addresses", {"user_id": user["id"]})
    if len(existing) >= MAX_ADDRESSES:
        raise HTTPException(status_code=400, detail=f"You can save up to {MAX_ADDRESSES} addresses.")
    data = _clean(payload)
    make_default = bool(payload.get("is_default")) or not existing
    if make_default:
        _clear_default(user["id"])
    row = {
        "address_id": "ADR-" + uuid.uuid4().hex[:10].upper(),
        "user_id": user["id"],
        "label": data["label"], "street": data["street"], "area": data.get("area", ""),
        "city": data["city"], "state": data["state"], "pin": data["pin"], "country": "India",
        "is_default": make_default,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return _public(db.insert("addresses", row))


def _owned(user: Dict[str, Any], address_id: str) -> Dict[str, Any]:
    rows = db.read("addresses", {"address_id": address_id})
    if not rows or rows[0].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Address not found.")
    return rows[0]


def update_address(address_id: str, payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    user = _user(request)
    _owned(user, address_id)
    data = _clean(payload, partial=True)
    data.pop("name", None); data.pop("phone", None)  # not columns; kept on the user profile
    if payload.get("is_default"):
        _clear_default(user["id"])
        data["is_default"] = True
    updated = db.update("addresses", {"address_id": address_id}, data)
    return _public(updated[0] if updated else _owned(user, address_id))


def delete_address(address_id: str, request: Request) -> Dict[str, Any]:
    user = _user(request)
    row = _owned(user, address_id)
    db.delete("addresses", {"address_id": address_id})
    if row.get("is_default"):  # promote the next one so checkout always has a default
        rest = db.read("addresses", {"user_id": user["id"]})
        if rest:
            db.update("addresses", {"address_id": rest[0]["address_id"]}, {"is_default": True})
    return {"success": True, "message": "Address removed."}
