from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional

from app.services.auth_service import (
    register_user,
    login_user,
    get_current_user_state,
    deactivate_account_placeholder,
    logout_all_devices,
    logout_user,
    send_mobile_otp,
    verify_mobile_otp,
    verify_email_otp,
    setup_user_profile,
    request_password_reset,
    confirm_password_reset,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
legacy_auth_router = APIRouter(prefix="/api/auth", tags=["auth-legacy"])

class LoginPayload(BaseModel):
    email: str
    password: str

class RegisterPayload(BaseModel):
    name: str
    email: str
    password: str
    confirm_password: Optional[str] = None
    gender: Optional[str] = None

class SendOtpPayload(BaseModel):
    phone: str
    country_code: str = "+91"

class VerifyOtpPayload(BaseModel):
    phone: str
    otp: str
    country_code: str = "+91"

class VerifyEmailPayload(BaseModel):
    email: str
    otp: str

class ProfileSetupPayload(BaseModel):
    gender: str
    phone: Optional[str] = None

class PasswordResetRequestPayload(BaseModel):
    email: str

class PasswordResetConfirmPayload(BaseModel):
    email: str
    token: str
    new_password: str

@router.get("/me")
def get_auth_state(request: Request) -> Dict[str, Any]:
    return get_current_user_state(request)

@router.post("/register")
def register(payload: RegisterPayload, request: Request) -> Dict[str, Any]:
    return register_user(payload)

@router.post("/login")
def login(payload: LoginPayload, request: Request) -> Dict[str, Any]:
    return login_user(payload, request)

@router.post("/send-otp")
def send_otp(payload: SendOtpPayload, request: Request) -> Dict[str, Any]:
    return send_mobile_otp(payload, request)

@router.post("/verify-otp")
def verify_otp(payload: VerifyOtpPayload, request: Request) -> Dict[str, Any]:
    return verify_mobile_otp(payload, request)

@router.post("/logout")
def logout(request: Request) -> Dict[str, Any]:
    return logout_user(request)

@router.post("/logout-all")
def logout_all(request: Request) -> Dict[str, Any]:
    return logout_all_devices(request)

@router.post("/deactivate")
def deactivate_account(request: Request) -> Dict[str, Any]:
    return deactivate_account_placeholder(request)

@router.post("/password-reset/request")
def password_reset_request(payload: PasswordResetRequestPayload) -> Dict[str, Any]:
    return request_password_reset(payload)

@router.post("/password-reset/confirm")
def password_reset_confirm(payload: PasswordResetConfirmPayload) -> Dict[str, Any]:
    return confirm_password_reset(payload)

@legacy_auth_router.post("/otp/verify-email")
def verify_email(payload: VerifyEmailPayload) -> Dict[str, Any]:
    return verify_email_otp(payload)

@legacy_auth_router.post("/profile/setup")
def profile_setup(payload: ProfileSetupPayload, request: Request) -> Dict[str, Any]:
    return setup_user_profile(payload, request)
