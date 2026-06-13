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

from app.core.db_switch import db
from app.core.config import get_jwt_secret, JWT_ALGORITHM, JWT_EXPIRATION_DAYS, ENVIRONMENT, ADMIN_EMAIL, ADMIN_PASSWORD_HASH, APP_BASE_URL

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

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
# The fallback hash below is for local development only (password: "Admin@123").
_DEFAULT_ADMIN_HASH = ADMIN_PASSWORD_HASH or "$2b$12$R.S4wN69Y4iR9wJ7C8mEeuJ81pM0mD7FqA1S4xZ0sF8K0kR8wJ7C8" # Admin@123
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
    res = db.read("users", {})
    if not res:
        db.insert("users", DEFAULT_ADMIN)
        res = db.read("users", {})
    return res

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
    res = db.read("users", {"email": target})
    if res:
        return res[0]
    if target == DEFAULT_ADMIN["email"].lower():
        load_users()
        res = db.read("users", {"email": target})
        if res:
            return res[0]
    return None

def find_user_by_phone(phone: str, country_code: str = "+91") -> Optional[Dict[str, Any]]:
    normalized = normalize_phone(phone, country_code)
    users = load_users()
    for user in users:
        stored = str(user.get("phone") or "").strip()
        if stored == normalized["e164"] or stored == normalized["national"]:
            return user
    return None

def find_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    res = db.read("users", {"id": int(user_id)})
    if res:
        return res[0]
    return None

def update_user(user_id: int, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    updated = db.update("users", {"id": int(user_id)}, changes)
    if updated:
        return updated[0]
    return None

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
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip()
    return None

def store_session_user(request: Request, user: Dict[str, Any]) -> None:
    request.session["user_id"] = user["id"]

def upgrade_password_hash_if_needed(user: Dict[str, Any], password: str) -> Dict[str, Any]:
    stored = user.get("password_hash") or user.get("password") or ""
    if stored and not stored.startswith(("$2b$", "$2a$", "$2y$")):
        new_hash = hash_password(password)
        db.update("users", {"id": user["id"]}, {"password_hash": new_hash, "password": None})
        user["password_hash"] = new_hash
        user["password"] = None
    return user

def get_session_user(request: Request) -> Optional[Dict[str, Any]]:
    token = get_request_token(request)
    if token:
        try:
            payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
            if payload.get("jti") in REVOKED_TOKEN_IDS:
                return None
            user_id = int(payload["sub"])
            return find_user_by_id(user_id)
        except (jwt.PyJWTError, ValueError, KeyError):
            pass

    session_user_id = request.session.get("user_id")
    if session_user_id:
        return find_user_by_id(int(session_user_id))
    return None

def validate_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_PATTERN.match(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a valid email address.")
    return normalized

def normalize_phone(phone: str, country_code: str = "+91") -> Dict[str, str]:
    digits = re.sub(r"\D", "", phone)
    code_digits = re.sub(r"\D", "", country_code) or "91"
    if digits.startswith(code_digits) and len(digits) > 10:
        digits = digits[len(code_digits):]
    if not PHONE_PATTERN.match(digits):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a valid 10-digit mobile number.")
    return {
        "national": digits,
        "country_code": f"+{code_digits}",
        "e164": f"+{code_digits}{digits}",
    }

def hash_otp(phone_e164: str, otp: str) -> str:
    return hmac.new(get_jwt_secret().encode("utf-8"), f"{phone_e164}:{otp}".encode("utf-8"), hashlib.sha256).hexdigest()

def load_otp_sessions() -> List[Dict[str, Any]]:
    return db.read("otp_sessions", {})

def mask_phone(phone_e164: str) -> str:
    return f"{phone_e164[:3]}******{phone_e164[-3:]}"

def get_otp_provider_name() -> str:
    return os.getenv("OTP_PROVIDER", "mock").strip().lower()

def send_sms_otp(phone_e164: str, otp: str) -> None:
    provider = get_otp_provider_name()
    if provider == "mock":
        if ENVIRONMENT == "production":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Development OTP provider is disabled in production.")
        print(f"[TRIDENT_DEV_OTP] Mobile login OTP for {mask_phone(phone_e164)}: {otp}")
        return
    # In Phase 7 we will add actual production Twilio provider support
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
    debug_otp = otp if ENVIRONMENT != "production" and get_otp_provider_name() == "mock" else None

    # Load existing sessions to enforce rate limits
    sessions = db.read("otp_sessions", {"phone": phone["e164"]})
    if sessions:
        session = sessions[0]
        # Check blocked
        blocked_until_str = session.get("blocked_until")
        if blocked_until_str:
            blocked_until = datetime.fromisoformat(blocked_until_str)
            if blocked_until > now:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many OTP requests. Please try again later.")
        
        # Check resend cooldown
        last_sent_str = session.get("last_sent_at")
        if last_sent_str:
            last_sent = datetime.fromisoformat(last_sent_str)
            if (now - last_sent).total_seconds() < OTP_RESEND_SECONDS:
                remaining = OTP_RESEND_SECONDS - int((now - last_sent).total_seconds())
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Please wait {remaining}s before requesting another OTP.")
        
        # Check hourly send count limits
        send_count = int(session.get("send_count", 1))
        window_started_str = session.get("window_started_at") or session.get("last_sent_at")
        if window_started_str:
            window_started = datetime.fromisoformat(window_started_str)
            if (now - window_started).total_seconds() < 3600:
                if send_count >= OTP_MAX_SENDS_PER_HOUR:
                    blocked_until = (now + timedelta(minutes=OTP_BLOCK_MINUTES)).isoformat()
                    db.update("otp_sessions", {"phone": phone["e164"]}, {"blocked_until": blocked_until})
                    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many OTP requests. Please try again later.")
                send_count += 1
            else:
                send_count = 1
                window_started = now
        else:
            send_count = 1
            window_started = now
            
        updates = {
            "otp_hash": hash_otp(phone["e164"], otp),
            "expires_at": expires_at.isoformat(),
            "last_sent_at": now.isoformat(),
            "window_started_at": window_started.isoformat(),
            "send_count": send_count,
            "ip_address": ip_address,
            "attempts": 0
        }
        db.update("otp_sessions", {"phone": phone["e164"]}, updates)
    else:
        new_session = {
            "phone": phone["e164"],
            "country_code": phone["country_code"],
            "otp_hash": hash_otp(phone["e164"], otp),
            "expires_at": expires_at.isoformat(),
            "last_sent_at": now.isoformat(),
            "window_started_at": now.isoformat(),
            "send_count": 1,
            "ip_address": ip_address,
            "purpose": "login",
            "attempts": 0,
        }
        db.insert("otp_sessions", new_session)

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
    sessions = db.read("otp_sessions", {"phone": phone["e164"]})
    if not sessions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please request an OTP first.")
    matched_session = sessions[0]
    
    try:
        expires_at = datetime.fromisoformat(matched_session.get("expires_at"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired. Please request a new one.")
    
    if expires_at <= now:
        db.delete("otp_sessions", {"phone": phone["e164"]})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired. Please request a new one.")
    
    attempts = int(matched_session.get("attempts", 0))
    if attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many OTP attempts. Please request a new OTP.")
    
    if not hmac.compare_digest(matched_session.get("otp_hash", ""), hash_otp(phone["e164"], otp)):
        db.update("otp_sessions", {"phone": phone["e164"]}, {"attempts": attempts + 1})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect OTP.")
        
    db.delete("otp_sessions", {"phone": phone["e164"]})

    user = find_user_by_phone(phone["national"], phone["country_code"])
    if not user:
        user = create_mobile_user(phone)

    store_session_user(request, user)
    token = issue_auth_token(user)
    return {"success": True, "message": "Mobile verified successfully.", "token": token, "user": serialize_user(user)}

def create_mobile_user(phone: Dict[str, str]) -> Dict[str, Any]:
    users = db.read("users", {})
    existing = next((u for u in users if str(u.get("phone")) in {phone["e164"], phone["national"]}), None)
    if existing:
        return existing
        
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
        "user_id": user_id_formatted,
        "name": f"Trident Member {phone['national'][-4:]}",
        "email": f"{phone['national']}@mobile.trident.local",
        "phone": phone["e164"],
        "password_hash": hash_password(uuid.uuid4().hex),
        "role": "customer",
        "otp_verification_status": True,
        "profile_completed_status": False,
        "created_at": now_iso(),
    }
    inserted = db.insert("users", new_user)
    return inserted

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
    smtp_user = os.getenv("SMTP_USERNAME", os.getenv("SMTP_USER", ""))
    smtp_pass = os.getenv("SMTP_PASSWORD", os.getenv("SMTP_PASS", ""))
    from_email = os.getenv("SMTP_FROM_EMAIL", "noreply@tridentwear.in")

    if smtp_host and smtp_user:
        msg = MIMEText(f"Hello {name},\n\nYour Trident Wear verification code is: {otp}\n\nThis code will expire in 10 minutes.\n\nThank you,\nTrident Wear Team")
        msg["Subject"] = "Trident Wear - Email Verification OTP"
        msg["From"] = from_email
        msg["To"] = email
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls(context=ctx)
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, [email], msg.as_string())
        except Exception:
            pass

    users = db.read("users", {})
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
    inserted = db.insert("users", new_user)

    if not smtp_host:
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

def verify_email_otp(payload: Any) -> Dict[str, Any]:
    email = validate_email(payload.email)
    otp = str(payload.otp or "").strip()
    
    user = find_user_by_email(email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        
    if user.get("otp_verification_status"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account already verified.")
        
    # Check OTP expiry
    otp_expiry_str = user.get("otp_expiry")
    if otp_expiry_str:
        try:
            otp_expiry = datetime.fromisoformat(otp_expiry_str)
            if otp_expiry <= datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired. Please register again.")
        except Exception:
            pass
            
    if user.get("otp") != otp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect OTP.")
        
    updated = update_user(user["id"], {
        "otp_verification_status": True,
        "otp": None,
        "otp_expiry": None
    })
    return {"success": True, "message": "Email verified successfully.", "user": serialize_user(updated or user)}

def setup_user_profile(payload: Any, request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in first.")
        
    changes = {
        "gender": str(payload.gender).strip(),
        "profile_completed_status": True
    }
    if getattr(payload, "phone", None):
        phone_val = str(payload.phone).strip()
        try:
            normalized = normalize_phone(phone_val)
            changes["phone"] = normalized["e164"]
        except Exception:
            changes["phone"] = phone_val
            
    updated = update_user(user["id"], changes) or user
    store_session_user(request, updated)
    return {"success": True, "message": "Profile setup complete", "user": serialize_user(updated)}

def request_password_reset(payload: Any) -> Dict[str, Any]:
    email = str(payload.email).strip().lower()
    
    success_response = {
        "success": True,
        "message": "If that email exists in our system, we have sent a password reset link to it."
    }
    
    user = find_user_by_email(email)
    if not user:
        return success_response
        
    token = uuid.uuid4().hex
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    
    update_user(user["id"], {
        "password_reset_token": token,
        "password_reset_expires_at": expiry
    })
    
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME", os.getenv("SMTP_USER", ""))
    smtp_pass = os.getenv("SMTP_PASSWORD", os.getenv("SMTP_PASS", ""))
    from_email = os.getenv("SMTP_FROM_EMAIL", "noreply@tridentwear.in")
    
    reset_url = f"{APP_BASE_URL}/reset-password?token={token}&email={email}"
    
    if smtp_host and smtp_user:
        body = (
            f"Hello {user.get('name', 'User')},\n\n"
            f"We received a request to reset the password for your TridentWear account.\n"
            f"Click the link below to set a new password. This link will expire in 1 hour:\n\n"
            f"{reset_url}\n\n"
            f"If you did not request this, you can safely ignore this email.\n\n"
            f"Thank you,\nTridentWear Team"
        )
        msg = MIMEText(body)
        msg["Subject"] = "TridentWear - Password Reset Link"
        msg["From"] = from_email
        msg["To"] = email
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls(context=ctx)
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, [email], msg.as_string())
        except Exception:
            pass
            
    if not smtp_host:
        print(f"[TRIDENT_DEV_RESET] Password reset link for {email}: {reset_url}")
        success_response["dev_reset_link"] = reset_url
        
    return success_response

def confirm_password_reset(payload: Any) -> Dict[str, Any]:
    email = str(payload.email).strip().lower()
    token = str(payload.token).strip()
    new_password = str(payload.new_password).strip()
    
    if len(new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters.")
        
    user = find_user_by_email(email)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request or expired token.")
        
    stored_token = user.get("password_reset_token")
    expires_str = user.get("password_reset_expires_at")
    
    if not stored_token or stored_token != token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request or expired token.")
        
    if expires_str:
        try:
            expires = datetime.fromisoformat(expires_str)
            if expires <= datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password reset link has expired.")
        except Exception:
            pass
            
    new_hash = hash_password(new_password)
    update_user(user["id"], {
        "password_hash": new_hash,
        "password": None,
        "password_reset_token": None,
        "password_reset_expires_at": None
    })
    
    return {"success": True, "message": "Password has been reset successfully. Please login with your new password."}
