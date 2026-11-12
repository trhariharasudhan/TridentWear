"""
TridentWear — Centralised Security Configuration
All secrets are loaded from environment variables.
In production mode, missing or default secrets cause a startup failure (fail-fast).
"""
import os
import secrets
import logging
from pathlib import Path
from dotenv import load_dotenv

# Auto-load .env from the backend/ directory (no-op if file does not exist).
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=False)  # override=False: real env vars take priority

log = logging.getLogger(__name__)

# ── Environment ────────────────────────────────────────────────────────────────
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION: bool = ENVIRONMENT == "production"

# ── Known-weak dev-only placeholders ──────────────────────────────────────────
_DEV_JWT_SECRET = "trident-dev-jwt-secret-NOT-FOR-PRODUCTION"
_DEV_SESSION_SECRET = "trident-dev-session-secret-NOT-FOR-PRODUCTION"
_DEV_FBT_SECRET = "trident-dev-fbt-secret-NOT-FOR-PRODUCTION"

# ── Database ──────────────────────────────────────────────────────────────────
# Default to SQLite/JSON in local development if not specified
DATABASE_URL: str = os.getenv("DATABASE_URL", os.getenv("PG_DSN", "")).strip()
TRIDENT_TEST_MODE: bool = os.getenv("TRIDENT_TEST_MODE", "").strip().lower() in ("1", "true", "yes") or ENVIRONMENT in ("testing", "test")
TRIDENT_DB_DIR: str = os.getenv("TRIDENT_DB_DIR", "").strip()

# ── JWT ────────────────────────────────────────────────────────────────────────
JWT_SECRET: str = os.getenv("TRIDENT_JWT_SECRET", os.getenv("JWT_SECRET", "")).strip()
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRATION_DAYS: int = int(os.getenv("TRIDENT_JWT_EXPIRATION_DAYS", "7"))

# ── FBT Offer Security ────────────────────────────────────────────────────────
FBT_SECRET: str = os.getenv("TRIDENT_FBT_SECRET", "").strip()
FBT_OFFER_EXPIRATION_HOURS: int = int(os.getenv("TRIDENT_FBT_EXPIRATION_HOURS", "24"))

# ── Session ────────────────────────────────────────────────────────────────────
SESSION_SECRET: str = os.getenv("TRIDENT_SESSION_SECRET", os.getenv("SESSION_SECRET", "")).strip()
SESSION_MAX_AGE: int = int(os.getenv("TRIDENT_SESSION_MAX_AGE_SECONDS", "604800"))

# ── Razorpay ───────────────────────────────────────────────────────────────────
RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", os.getenv("RAZORPAY_KEY", "")).strip()
RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", os.getenv("RAZORPAY_SECRET", "")).strip()
RAZORPAY_WEBHOOK_SECRET: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()

# ── Trusted Proxies ───────────────────────────────────────────────────────────
_raw_proxies = os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1").strip()
TRUSTED_PROXIES: list = [p.strip() for p in _raw_proxies.split(",") if p.strip()]

# ── Distributed Cache & Rate Limiting (Redis) ─────────────────────────────────
REDIS_URL: str = os.getenv("REDIS_URL", "").strip()

# ── CORS ───────────────────────────────────────────────────────────────────────
_raw_origins = os.getenv("ALLOWED_ORIGINS", "").strip()

if _raw_origins:
    CORS_ORIGINS: list = [o.strip() for o in _raw_origins.split(",") if o.strip()]
elif IS_PRODUCTION:
    CORS_ORIGINS = []
else:
    CORS_ORIGINS = [
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8010",
        "http://127.0.0.1:8020",
        "http://127.0.0.1:8021",
        "http://127.0.0.1:8022",
        "http://127.0.0.1:8023",
        "http://127.0.0.1:8030",
        "http://localhost:8000",
        "http://localhost:8010",
        "http://localhost:8020",
        "http://localhost:8021",
        "http://localhost:8022",
        "http://localhost:8023",
        "http://localhost:8030",
    ]

# ── Admin seed ────────────────────────────────────────────────────────────────
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@trident.local").strip()
ADMIN_PASSWORD_RAW: str = os.getenv("ADMIN_PASSWORD", "").strip()
ADMIN_PASSWORD_HASH: str = os.getenv("ADMIN_PASSWORD_HASH", "").strip()

# ── SMTP Mail Configuration ────────────────────────────────────────────────────
SMTP_HOST: str = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "noreply@tridentwear.in").strip()
SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"

# ── OTP Abstraction ───────────────────────────────────────────────────────────
OTP_PROVIDER: str = os.getenv("OTP_PROVIDER", "mock").strip().lower()
OTP_EXPIRY_SECONDS: int = int(os.getenv("OTP_EXPIRY_SECONDS", "300"))
OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
OTP_RESEND_COOLDOWN_SECONDS: int = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))

# ── Google OAuth ──────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "").strip()

# ── Base URLs & Logging ────────────────────────────────────────────────────────
APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://127.0.0.1:8020").strip()
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()


def is_razorpay_placeholder() -> bool:
    """Returns True if Razorpay key credentials are missing or default test placeholders."""
    return (
        not RAZORPAY_KEY_ID
        or not RAZORPAY_KEY_SECRET
        or RAZORPAY_KEY_ID in ("rzp_test_key_id", "rzp_test_mockkey")
        or RAZORPAY_KEY_SECRET in ("rzp_test_key_secret", "rzp_test_mocksecret")
    )


def validate_production_secrets() -> None:
    """
    Called at startup. In production mode, fail fast if any required secret is
    missing or still set to a known-weak placeholder.
    """
    issues: list[str] = []

    checks = [
        ("TRIDENT_JWT_SECRET", JWT_SECRET, [_DEV_JWT_SECRET, "trident-super-secret-key-12345", ""]),
        ("TRIDENT_SESSION_SECRET", SESSION_SECRET, [_DEV_SESSION_SECRET, "trident-local-session-secret", ""]),
        ("ALLOWED_ORIGINS", _raw_origins, [""]),
        ("DATABASE_URL", DATABASE_URL, [""]),
    ]

    for name, value, known_bad in checks:
        if not value:
            issues.append(f"  - {name} is not set")
        elif known_bad and value in known_bad:
            issues.append(f"  - {name} is set to a missing or known-insecure placeholder")

    if IS_PRODUCTION:
        if TRIDENT_TEST_MODE:
            issues.append("  - TRIDENT_TEST_MODE is enabled in production environment")
        if is_razorpay_placeholder():
            issues.append("  - Razorpay credentials are unset or configured with mock placeholders in production")
        _DEV_ADMIN_HASH = "$2b$12$R.S4wN69Y4iR9wJ7C8mEeuJ81pM0mD7FqA1S4xZ0sF8K0kR8wJ7C8"
        if not ADMIN_PASSWORD_HASH and not ADMIN_PASSWORD_RAW:
            issues.append("  - ADMIN_PASSWORD_HASH / ADMIN_PASSWORD is not set in production")
        elif ADMIN_PASSWORD_HASH == _DEV_ADMIN_HASH or ADMIN_PASSWORD_RAW in ("Admin@123", "admin", "password"):
            issues.append("  - Admin credentials are set to known-insecure default placeholders in production")
        if not FBT_SECRET and not JWT_SECRET:
            issues.append("  - Neither TRIDENT_FBT_SECRET nor TRIDENT_JWT_SECRET is set in production")

    if issues:
        message = "Security configuration problems detected:\n" + "\n".join(issues)
        if IS_PRODUCTION:
            raise RuntimeError(f"[SECURITY] Startup aborted — {message}")
        else:
            log.warning(f"[SECURITY WARNING — dev mode only] {message}")


def get_jwt_secret() -> str:
    """Returns the JWT secret. Falls back to a dev placeholder in development only."""
    if JWT_SECRET:
        return JWT_SECRET
    if IS_PRODUCTION:
        raise RuntimeError("[SECURITY] TRIDENT_JWT_SECRET is not set in production.")
    return _DEV_JWT_SECRET


def get_session_secret() -> str:
    """Returns the session secret. Falls back to a dev placeholder in development only."""
    if SESSION_SECRET:
        return SESSION_SECRET
    if IS_PRODUCTION:
        raise RuntimeError("[SECURITY] TRIDENT_SESSION_SECRET is not set in production.")
    return _DEV_SESSION_SECRET


def get_fbt_secret() -> str:
    """Returns the FBT secret for signing/verifying offer tokens.
    Falls back to JWT_SECRET if TRIDENT_FBT_SECRET is not set, or dev placeholder in development."""
    if FBT_SECRET:
        return FBT_SECRET
    if JWT_SECRET:
        return JWT_SECRET
    if IS_PRODUCTION:
        raise RuntimeError("[SECURITY] TRIDENT_FBT_SECRET / TRIDENT_JWT_SECRET is not set in production.")
    return _DEV_FBT_SECRET


def allow_client_test_mode(requested: bool) -> bool:
    """Clients may only request test_mode (mock payments, no stock deduction) outside production."""
    return bool(requested) and os.getenv("ENVIRONMENT", "development").strip().lower() != "production"
