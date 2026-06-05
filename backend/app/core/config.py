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

# ── JWT ────────────────────────────────────────────────────────────────────────
JWT_SECRET: str = os.getenv("TRIDENT_JWT_SECRET", os.getenv("JWT_SECRET", "")).strip()
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRATION_DAYS: int = int(os.getenv("TRIDENT_JWT_EXPIRATION_DAYS", "7"))

# ── Session ────────────────────────────────────────────────────────────────────
SESSION_SECRET: str = os.getenv("TRIDENT_SESSION_SECRET", "").strip()
SESSION_MAX_AGE: int = int(os.getenv("TRIDENT_SESSION_MAX_AGE_SECONDS", "604800"))

# ── Razorpay ───────────────────────────────────────────────────────────────────
# Supports both old name (RAZORPAY_KEY/RAZORPAY_SECRET) and new canonical names.
RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", os.getenv("RAZORPAY_KEY", "")).strip()
RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", os.getenv("RAZORPAY_SECRET", "")).strip()

# ── CORS ───────────────────────────────────────────────────────────────────────
_raw_origins = os.getenv("ALLOWED_ORIGINS", "").strip()

if _raw_origins:
    CORS_ORIGINS: list = [o.strip() for o in _raw_origins.split(",") if o.strip()]
elif IS_PRODUCTION:
    # Production: no ALLOWED_ORIGINS set — CORS will block everything (safe default).
    # This will trigger the startup guard below.
    CORS_ORIGINS = []
else:
    # Development: allow common local origins explicitly. Never wildcard with credentials.
    CORS_ORIGINS = [
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8010",
        "http://localhost:8000",
        "http://localhost:8010",
    ]

# ── Admin seed ────────────────────────────────────────────────────────────────
# Read from env; fall back to dev-only defaults in development.
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@trident.local").strip()
# Raw password used only if no hash is provided (dev mode; will be hashed at first use).
ADMIN_PASSWORD_RAW: str = os.getenv("ADMIN_PASSWORD", "").strip()
# Pre-computed bcrypt hash preferred over raw password for production.
ADMIN_PASSWORD_HASH: str = os.getenv("ADMIN_PASSWORD_HASH", "").strip()


def _check_secret(name: str, value: str, known_bad: list | None = None) -> None:
    """Raise RuntimeError if a required secret is missing or insecure in production."""
    if not value:
        raise RuntimeError(
            f"[SECURITY] Required secret '{name}' is not set. "
            f"Set it in the environment before starting in production."
        )
    if known_bad and value in known_bad:
        raise RuntimeError(
            f"[SECURITY] '{name}' is still set to a known-insecure default. "
            f"Generate a secure value: python -c \"import secrets; print(secrets.token_hex(32))\""
        )


def validate_production_secrets() -> None:
    """
    Called at startup. In production mode, fail fast if any required secret is
    missing or still set to a known-weak placeholder.
    In development, log warnings instead of crashing.
    """
    issues: list[str] = []

    checks = [
        ("TRIDENT_JWT_SECRET", JWT_SECRET, [_DEV_JWT_SECRET, "trident-super-secret-key-12345"]),
        ("TRIDENT_SESSION_SECRET", SESSION_SECRET, [_DEV_SESSION_SECRET, "trident-local-session-secret"]),
        ("ALLOWED_ORIGINS", _raw_origins, []),
        ("RAZORPAY_KEY_ID", RAZORPAY_KEY_ID, []),
        ("RAZORPAY_KEY_SECRET", RAZORPAY_KEY_SECRET, []),
    ]

    for name, value, known_bad in checks:
        if not value:
            issues.append(f"  - {name} is not set")
        elif known_bad and value in known_bad:
            issues.append(f"  - {name} is set to a known-insecure placeholder")

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
