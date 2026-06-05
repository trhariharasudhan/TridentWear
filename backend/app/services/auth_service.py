import os
import json
import re
import uuid
import bcrypt
import jwt
import base64
import hashlib
import hmac
import random
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import Request, HTTPException, status

from app.db.json_manager import read_json, update_json, write_json
from app.core.config import get_jwt_secret, JWT_ALGORITHM, JWT_EXPIRATION_DAYS, ENVIRONMENT, ADMIN_EMAIL, ADMIN_PASSWORD_HASH

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DB_DIR = BASE_DIR / "db"
USERS_PATH = str(DB_DIR / "users.json")
OTP_SESSIONS_PATH = str(DB_DIR / "otp_sessions.json")

# JWT_SECRET resolved at call-time via get_jwt_secret() from config.py
OTP_EXPIRY_MINUTES = int(os.getenv("TRIDENT_OTP_EXPIRY_MINUTES", "5"))
OTP_RESEND_SECONDS = int(os.getenv("TRIDENT_OTP_RESEND_SECONDS", "45"))
OTP_MAX_ATTEMPTS = int(os.getenv("TRIDENT_OTP_MAX_ATTEMPTS", "5"))
OTP_MAX_SENDS_PER_HOUR = int(os.getenv("TRIDENT_OTP_MAX_SENDS_PER_HOUR", "5"))
OTP_BLOCK_MINUTES = int(os.getenv("TRIDENT_OTP_BLOCK_MINUTES", "15"))
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^\d{10}$")
REVOKED_TOKEN_IDS: set[str] = set()

# Default admin credentials loaded from environment variables.
# ADMIN_EMAIL and ADMIN_PASSWORD_HASH must be set before production deployment.
# The fallback hash below is for local development only (password: "TridentAdmin@123").
_DEFAULT_ADMIN_HASH = ADMIN_PASSWORD_HASH or "$2b$12$7Q07pQBBqNur7Rdxq4R7pebAeUdR89zN4T.NQfpcPZ/p4CVB3TRJq"
DEFAULT_ADMIN = {
    "id": 1,
    "name": "Trident Admin",
    "email": ADMIN_EMAIL,
    "password_hash": _DEFAULT_ADMIN_HASH,
    "role": "admin",
    "created_at": "2026-04-12T00:00:00+00:00",
}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def load_users() -> List[Dict[str, Any]]:
    users = read_json(USERS_PATH)
    if not users:
        return [DEFAULT_ADMIN]
    return users

def next_id(items: List[Dict[str, Any]]) -> int:
    if not items:
        return 1
    return max(int(item.get("id", 0)) for item in items) + 1

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    _ = salt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_legacy_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_encoded, digest_encoded = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iterations_text)
        salt_bytes = base64.b64decode(salt_encoded.encode("utf-8"))
        expected = base64.b64decode(digest_encoded.encode("utf-8"))
    except (TypeError, ValueError):
        return False
    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
    return hmac.compare_digest(computed, expected)

def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("pbkdf2_sha256$"):
        return verify_legacy_password(password, stored_hash)
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        return False

def find_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    target = email.strip().lower()
    for user in load_users():
        if user.get("email", "").lower() == target:
            return user
    return None

def find_user_by_phone(phone: str, country_code: str = "+91") -> Optional[Dict[str, Any]]:
    normalized = normalize_phone(phone, country_code)
    for user in load_users():
        stored = str(user.get("phone") or "").strip()
        if stored == normalized["e164"] or stored == normalized["national"]:
            return user
    return None

def find_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    for user in load_users():
        if int(user.get("id", 0)) == int(user_id):
            return user
    return None

def update_user(user_id: int, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    updated_user = None

    def _apply_update(users: list):
        nonlocal updated_user
        if not users:
            users = [DEFAULT_ADMIN]
        for index, user in enumerate(users):
            if int(user.get("id", 0)) == int(user_id):
                users[index] = {**user, **changes}
                updated_user = users[index]
                break
        return users

    update_json(USERS_PATH, _apply_update)
    return updated_user

def issue_auth_token(user: Dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "name": user["name"],
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRATION_DAYS),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def get_request_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    token = request.headers.get("x-session-token", "").strip()
    return token or None

def store_session_user(request: Request, user: Dict[str, Any]) -> None:
    request.session.clear()
    request.session["user_id"] = int(user["id"])

def upgrade_password_hash_if_needed(user: Dict[str, Any], password: str) -> Dict[str, Any]:
    stored_hash = user.get("password_hash", "")
    if not stored_hash.startswith("pbkdf2_sha256$"):
        return user
    upgraded_user = update_user(user["id"], {"password_hash": hash_password(password)})
    return upgraded_user or user

def get_session_user(request: Request) -> Optional[Dict[str, Any]]:
    token = get_request_token(request)
    user_id = None
    if token:
        try:
            payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
            if payload.get("jti") in REVOKED_TOKEN_IDS:
                raise jwt.InvalidTokenError("Token has been revoked.")
            user_id = payload.get("sub")
        except jwt.PyJWTError:
            pass
    if not user_id:
        user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = find_user_by_id(int(user_id))
    if user and user.get("is_active", True) is False:
        request.session.clear()
        return None
    if user:
        return user
    request.session.clear()
    return None

def validate_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_PATTERN.match(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a valid email address.")
    return normalized

def normalize_phone(phone: str, country_code: str = "+91") -> Dict[str, str]:
    digits = re.sub(r"\D", "", str(phone or ""))
    code_digits = re.sub(r"\D", "", str(country_code or "+91")) or "91"
    if digits.startswith(code_digits) and len(digits) > 10:
        digits = digits[len(code_digits):]
    if not PHONE_PATTERN.match(digits):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a valid 10-digit mobile number.")
    code = f"+{code_digits}"
    return {"national": digits, "country_code": code, "e164": f"{code}{digits}"}

def hash_otp(phone_e164: str, otp: str) -> str:
    return hmac.new(get_jwt_secret().encode("utf-8"), f"{phone_e164}:{otp}".encode("utf-8"), hashlib.sha256).hexdigest()

def load_otp_sessions() -> List[Dict[str, Any]]:
    sessions = read_json(OTP_SESSIONS_PATH)
    return sessions if isinstance(sessions, list) else []

def mask_phone(phone_e164: str) -> str:
    return f"{phone_e164[:3]}******{phone_e164[-3:]}"

def get_otp_provider_name() -> str:
    return os.getenv("TRIDENT_OTP_PROVIDER", "dev").strip().lower() or "dev"

def send_sms_otp(phone_e164: str, otp: str) -> None:
    provider = get_otp_provider_name()
    if provider == "dev":
        if ENVIRONMENT == "production":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Development OTP provider is disabled in production.")
        print(f"[TRIDENT_DEV_OTP] Mobile login OTP for {mask_phone(phone_e164)}: {otp}")
        return
    # Provider hooks intentionally live here so Twilio/MSG91/Fast2SMS/Firebase/AWS SNS can be added without changing routes.
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"OTP provider '{provider}' is not configured yet.")

def client_ip(request: Optional[Request]) -> str:
    if not request:
        return ""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""

def send_mobile_otp(payload: Any, request: Optional[Request] = None) -> Dict[str, Any]:
    phone = normalize_phone(payload.phone, getattr(payload, "country_code", "+91"))
    now = datetime.now(timezone.utc)
    ip_address = client_ip(request)
    otp = f"{random.randint(0, 999999):06d}"
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    debug_otp = otp if ENVIRONMENT != "production" and get_otp_provider_name() == "dev" else None

    def _upsert(sessions: list):
        sessions = sessions if isinstance(sessions, list) else []
        active = []
        for session in sessions:
            try:
                if session.get("blocked_until") and datetime.fromisoformat(session.get("blocked_until")) > now and session.get("phone") == phone["e164"]:
                    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many OTP requests. Please try again later.")
                if datetime.fromisoformat(session.get("expires_at")) > now and session.get("phone") != phone["e164"]:
                    active.append(session)
            except HTTPException:
                raise
            except Exception:
                continue
            if session.get("phone") == phone["e164"]:
                try:
                    sent_at = datetime.fromisoformat(session.get("last_sent_at"))
                    if (now - sent_at).total_seconds() < OTP_RESEND_SECONDS:
                        remaining = OTP_RESEND_SECONDS - int((now - sent_at).total_seconds())
                        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Please wait {remaining}s before requesting another OTP.")
                    send_count = int(session.get("send_count", 1))
                    window_started_at = datetime.fromisoformat(session.get("window_started_at", session.get("last_sent_at")))
                    if (now - window_started_at).total_seconds() < 3600 and send_count >= OTP_MAX_SENDS_PER_HOUR:
                        session["blocked_until"] = (now + timedelta(minutes=OTP_BLOCK_MINUTES)).isoformat()
                        active.append(session)
                        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many OTP requests. Please try again later.")
                except HTTPException:
                    raise
                except Exception:
                    pass
        previous = next((session for session in sessions if session.get("phone") == phone["e164"]), {})
        previous_window = previous.get("window_started_at") or now.isoformat()
        try:
            window_started_at = datetime.fromisoformat(previous_window)
        except Exception:
            window_started_at = now
        send_count = int(previous.get("send_count", 0)) + 1 if (now - window_started_at).total_seconds() < 3600 else 1
        active.append({
            "phone": phone["e164"],
            "country_code": phone["country_code"],
            "otp_hash": hash_otp(phone["e164"], otp),
            "expires_at": expires_at.isoformat(),
            "last_sent_at": now.isoformat(),
            "window_started_at": window_started_at.isoformat() if send_count > 1 else now.isoformat(),
            "send_count": send_count,
            "ip_address": ip_address,
            "purpose": "login",
            "attempts": 0,
        })
        return active

    update_json(OTP_SESSIONS_PATH, _upsert)
    send_sms_otp(phone["e164"], otp)

    response = {
        "success": True,
        "message": f"OTP sent to {mask_phone(phone['e164'])}.",
        "expires_in": OTP_EXPIRY_MINUTES * 60,
        "resend_after": OTP_RESEND_SECONDS,
        "phone_masked": mask_phone(phone["e164"]),
    }
    if debug_otp:
        response["dev_otp"] = debug_otp
    return response

def verify_mobile_otp(payload: Any, request: Request) -> Dict[str, Any]:
    phone = normalize_phone(payload.phone, getattr(payload, "country_code", "+91"))
    otp = str(payload.otp or "").strip()
    if not re.fullmatch(r"\d{6}", otp):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter the 6-digit OTP.")

    now = datetime.now(timezone.utc)
    sessions = load_otp_sessions()
    matched_session = next((session for session in sessions if session.get("phone") == phone["e164"]), None)
    if not matched_session:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please request an OTP first.")
    try:
        expires_at = datetime.fromisoformat(matched_session.get("expires_at"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired. Please request a new one.")
    if expires_at <= now:
        write_json(OTP_SESSIONS_PATH, [session for session in sessions if session.get("phone") != phone["e164"]])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired. Please request a new one.")
    attempts = int(matched_session.get("attempts", 0))
    if attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many OTP attempts. Please request a new OTP.")
    if not hmac.compare_digest(matched_session.get("otp_hash", ""), hash_otp(phone["e164"], otp)):
        matched_session["attempts"] = attempts + 1
        write_json(OTP_SESSIONS_PATH, sessions)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect OTP.")
    write_json(OTP_SESSIONS_PATH, [session for session in sessions if session.get("phone") != phone["e164"]])

    user = find_user_by_phone(phone["national"], phone["country_code"])
    if not user:
        user = create_mobile_user(phone)

    store_session_user(request, user)
    token = issue_auth_token(user)
    return {"success": True, "message": "Mobile verified successfully.", "token": token, "user": serialize_user(user)}

def create_mobile_user(phone: Dict[str, str]) -> Dict[str, Any]:
    created_user = None

    def _create(users: list):
        nonlocal created_user
        users = users if isinstance(users, list) and users else [DEFAULT_ADMIN]
        existing = next((u for u in users if str(u.get("phone")) in {phone["e164"], phone["national"]}), None)
        if existing:
            created_user = existing
            return users
        seq = next_id(users)
        created_user = {
            "id": seq,
            "user_id": f"TW{datetime.now().strftime('%y')}-{seq:03d}",
            "name": f"Trident Member {phone['national'][-4:]}",
            "email": f"{phone['national']}@mobile.trident.local",
            "phone": phone["e164"],
            "password_hash": hash_password(uuid.uuid4().hex),
            "role": "customer",
            "otp_verification_status": True,
            "profile_completed_status": False,
            "created_at": now_iso(),
        }
        users.append(created_user)
        return users

    update_json(USERS_PATH, _create)
    return created_user

def serialize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "created_at": user["created_at"],
        "gender": user.get("gender"),
        "phone": user.get("phone"),
        "user_id": user.get("user_id"),
        "profile_completed_status": user.get("profile_completed_status", True),
    }

# EXPORTED ENDPOINT LOGIC

def get_current_user_state(request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    return {"authenticated": bool(user), "user": serialize_user(user) if user else None}

def register_user(payload: Any) -> Dict[str, Any]:
    name = payload.name.strip()
    email = validate_email(payload.email)
    password = payload.password.strip()

    if len(name) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name must be at least 2 characters.")
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters.")
    if payload.confirm_password is not None and payload.confirm_password.strip() != password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match.")
    if find_user_by_email(email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists.")

    otp = str(random.randint(100000, 999999))
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")

    if smtp_host and smtp_user:
        msg = MIMEText(f"Hello {name},\n\nYour Trident Wear verification code is: {otp}\n\nThis code will expire in 10 minutes.\n\nThank you,\nTrident Wear Team")
        msg["Subject"] = "Trident Wear - Email Verification OTP"
        msg["From"] = smtp_user
        msg["To"] = email
        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [email], msg.as_string())
        except Exception as e:
            pass

    new_user = None

    def _register(users: list):
        nonlocal new_user
        if not users:
            users = [DEFAULT_ADMIN]

        current_year_suffix = datetime.now().strftime("%y")
        highest_seq = 0
        prefix = f"TW{current_year_suffix}-"
        for u in users:
            uid = str(u.get("user_id", ""))
            if uid.startswith(prefix):
                try:
                    seq = int(uid.split("-")[1])
                    if seq > highest_seq:
                        highest_seq = seq
                except Exception:
                    pass
        
        seq_number = str(highest_seq + 1).zfill(3)
        user_id_formatted = f"{prefix}{seq_number}"

        new_user = {
            "id": next_id(users),
            "user_id": user_id_formatted,
            "name": name,
            "email": email,
            "password_hash": hash_password(password),
            "role": "customer",
            "gender": getattr(payload, "gender", None),
            "otp": otp,
            "otp_expiry": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "otp_verification_status": False,
            "profile_completed_status": False,
            "created_at": now_iso(),
        }
        users.append(new_user)
        return users

    update_json(USERS_PATH, _register)

    if not (smtp_host and smtp_user):
        return {"success": True, "message": f"Account created. (Dev Mode OTP: {otp})", "email": email, "dev_otp": otp}

    return {"success": True, "message": "Account created. Please check your email for the OTP.", "email": email}

def login_user(payload: Any, request: Request) -> Dict[str, Any]:
    email = validate_email(payload.email)
    password = payload.password.strip()
    user = find_user_by_email(email)

    if not user or not verify_password(password, user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
    if user.get("is_active", True) is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is deactivated.")
    
    if user.get("role") != "admin" and not user.get("otp_verification_status", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email OTP before logging in.")

    user = upgrade_password_hash_if_needed(user, password)
    store_session_user(request, user)
    token = issue_auth_token(user)

    return {"success": True, "message": "Signed in successfully.", "token": token, "user": serialize_user(user)}

def logout_user(request: Request) -> Dict[str, Any]:
    revoke_auth_token(get_request_token(request))
    request.session.clear()
    return {"success": True, "message": "Signed out."}

def revoke_auth_token(token: Optional[str]) -> None:
    if not token:
        return
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
    except jwt.PyJWTError:
        return
    if payload.get("jti"):
        REVOKED_TOKEN_IDS.add(payload["jti"])

def logout_all_devices(request: Request) -> Dict[str, Any]:
    request.session.clear()
    return {
        "success": True,
        "message": "All-device logout placeholder acknowledged. Persisted token versioning should be enabled in PostgreSQL before public launch.",
    }

def deactivate_account_placeholder(request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in.")
    return {
        "success": True,
        "message": "Account deactivate/delete placeholder acknowledged. Add owner confirmation, retention policy, and admin review before enabling.",
    }

def require_admin(request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden: Admins only.")
    return user
