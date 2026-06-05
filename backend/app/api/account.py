from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.account_service import get_account_profile, update_account_profile, change_account_password


router = APIRouter(prefix="/api/v1/account", tags=["account"])


class AccountProfilePayload(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    addresses: Optional[List[Dict[str, Any]]] = None
    default_address_id: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


@router.get("/profile")
def profile(request: Request) -> Dict[str, Any]:
    return get_account_profile(request)


@router.put("/profile")
def update_profile(payload: AccountProfilePayload, request: Request) -> Dict[str, Any]:
    return update_account_profile(payload, request)


class PasswordChangePayload(BaseModel):
    current_password: str
    new_password: str


@router.post("/password-change")
def password_change(payload: PasswordChangePayload, request: Request) -> Dict[str, Any]:
    return change_account_password(payload, request)
