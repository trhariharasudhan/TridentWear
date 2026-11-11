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


# ---------------------------------------------------------------- saved addresses
from app.services.address_service import list_addresses, add_address, update_address, delete_address


class AddressPayload(BaseModel):
    label: Optional[str] = None
    street: Optional[str] = None
    area: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pin: Optional[str] = None
    is_default: Optional[bool] = None


@router.get("/addresses")
def addresses(request: Request) -> Dict[str, Any]:
    return {"addresses": list_addresses(request)}


@router.post("/addresses")
def addresses_add(payload: AddressPayload, request: Request) -> Dict[str, Any]:
    return {"address": add_address(payload.model_dump(exclude_none=True), request)}


@router.put("/addresses/{address_id}")
def addresses_update(address_id: str, payload: AddressPayload, request: Request) -> Dict[str, Any]:
    return {"address": update_address(address_id, payload.model_dump(exclude_none=True), request)}


@router.delete("/addresses/{address_id}")
def addresses_delete(address_id: str, request: Request) -> Dict[str, Any]:
    return delete_address(address_id, request)
