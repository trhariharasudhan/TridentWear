import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import os

from app.core.config import CORS_ORIGINS, get_session_secret, SESSION_MAX_AGE, validate_production_secrets, TRUSTED_PROXIES

from app.api.health import router as health_router, root_health_router
from app.api.auth import router as auth_router, legacy_auth_router
from app.api.products import router as products_router
from app.api.orders import router as orders_router
from app.api.admin import router as admin_router
from app.api.payments import router as payments_router
from app.api.frontend import router as frontend_router
from app.api.contact import router as contact_router
from app.api.account import router as account_router
from app.api.reviews import router as reviews_router
from app.api.wishlist import router as wishlist_router
from app.api.coupons import router as coupons_router
from app.api.tryon import router as tryon_router
from app.api.site import router as site_router
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Disable Swagger UI and ReDoc in production to prevent API schema exposure
_IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"
app = FastAPI(
    title="TridentWear API",
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_ROOT = BASE_DIR / "frontend"
ASSETS_DIR = FRONTEND_ROOT / "assets"
IMAGES_DIR = FRONTEND_ROOT / "assets" / "images"

app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

# CORS — never wildcard when credentials=True.
# In development, CORS_ORIGINS = explicit localhost list (set in config.py).
# In production, CORS_ORIGINS = value of ALLOWED_ORIGINS env var.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=get_session_secret(),
    same_site="lax",
    https_only=os.getenv("ENVIRONMENT", "development") == "production",
    max_age=SESSION_MAX_AGE,
)

# Mount our extracted routes!
app.include_router(health_router)        # /api/v1/health
app.include_router(root_health_router)  # /health  (Render/Railway/Docker probe)
app.include_router(auth_router)
app.include_router(legacy_auth_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(admin_router)
app.include_router(payments_router)
app.include_router(contact_router)
app.include_router(account_router)
app.include_router(reviews_router)
app.include_router(wishlist_router)
app.include_router(coupons_router)
app.include_router(tryon_router)
app.include_router(site_router)
app.include_router(frontend_router)  # frontend last — catch-all routes

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import json
import time
import logging

import uuid
from app.core.logger import app_logger
from app.db.json_manager import recover_db_files

@app.on_event("startup")
async def startup_event():
    # Fail fast on missing/insecure secrets in production; warn in development.
    validate_production_secrets()
    from app.core.db_switch import get_db_dir, validate_db_safety, is_test_mode
    validate_db_safety()
    active_db_dir = get_db_dir()
    app_logger.info(
        f"[DB STARTUP] Mode: {os.getenv('DB_MODE', 'json')} | Active DB Dir: {active_db_dir} | Test Mode: {is_test_mode()}"
    )
    recover_db_files(str(active_db_dir))
    from app.services.auth_service import ensure_admin_user
    ensure_admin_user()

# Idempotency cache: { "key": {"timestamp": 123456, "status_code": 200, "response": {...}} }
idempotency_cache = {}

@app.middleware("http")
async def api_response_wrapper(request: Request, call_next):
    start_time = time.time()
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    
    # --- IDEMPOTENCY PRE-CHECK ---
    idempotency_key = request.headers.get("Idempotency-Key")
    is_idempotent_target = request.url.path.startswith(("/api/v1/payments", "/api/v1/orders", "/api/v1/chat/send"))
    
    if is_idempotent_target and idempotency_key:
        now = time.time()
        # Cleanup expired keys
        keys_to_delete = [k for k, v in idempotency_cache.items() if now - v['timestamp'] > 600]
        for k in keys_to_delete:
            del idempotency_cache[k]
            
        if idempotency_key in idempotency_cache:
            cached = idempotency_cache[idempotency_key]
            wrapped_data = cached['response'].copy()
            wrapped_data['request_id'] = request_id
            wrapped_data['idempotent'] = True
            
            app_logger.info(
                f"API Request (IDEMPOTENT CACHE): {request.method} {request.url.path} - {cached['status_code']}",
                extra={
                    "request_id": request_id,
                    "endpoint": request.url.path,
                    "method": request.method,
                    "response_time_ms": 0,
                    "status_code": cached['status_code'],
                    "user_id": request.session.get("user_id") if hasattr(request, "session") else None
                }
            )
            return JSONResponse(status_code=cached['status_code'], content=wrapped_data)
    
    # --- PROCEED WITH REQUEST ---
    response = await call_next(request)
    
    process_time_ms = (time.time() - start_time) * 1000
    is_success = response.status_code < 400
    
    if request.url.path.startswith("/api/"):
        app_logger.info(
            f"API Request: {request.method} {request.url.path} - {response.status_code}",
            extra={
                "request_id": request_id,
                "endpoint": request.url.path,
                "method": request.method,
                "response_time_ms": round(process_time_ms, 2),
                "status_code": response.status_code,
                "user_id": request.session.get("user_id") if hasattr(request, "session") else None
            }
        )
        
        if is_success and response.headers.get("content-type") == "application/json":
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            try:
                data = json.loads(body)
                if isinstance(data, dict) and "success" in data and "error" in data:
                    wrapped_data = data
                    if "request_id" not in wrapped_data:
                        wrapped_data["request_id"] = request_id
                else:
                    wrapped_data = {
                        "success": True,
                        "request_id": request_id,
                        "data": data,
                        "error": None
                    }
                
                # --- IDEMPOTENCY STORE ---
                if is_idempotent_target and idempotency_key:
                    idempotency_cache[idempotency_key] = {
                        "timestamp": time.time(),
                        "status_code": response.status_code,
                        "response": wrapped_data.copy()
                    }
                
                new_response = JSONResponse(status_code=response.status_code, content=wrapped_data)
                for header_key, header_val in response.headers.items():
                    if header_key.lower() not in ("content-length", "content-type"):
                        new_response.headers[header_key] = header_val
                for raw_k, raw_v in getattr(response, "raw_headers", []):
                    if raw_k.lower() == b"set-cookie":
                        new_response.headers.append("set-cookie", raw_v.decode("latin-1"))
                response = new_response
            except json.JSONDecodeError:
                pass
                
    return response

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Camera is needed by the virtual try-on page (same origin only)
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"

    # Caching: with no header, browsers guess and keep old CSS/JS after an update, which
    # mixes new HTML with old code (blank / unstyled pages). Code and pages revalidate on
    # every load (cheap 304 via ETag); images and fonts can be cached for a week.
    path = request.url.path
    if "cache-control" not in response.headers:
        if path.endswith((".css", ".js", ".mjs", ".json", ".webmanifest", ".html")) or path == "/" or (
            not path.startswith(("/api/", "/assets/", "/images/")) and "." not in path.rsplit("/", 1)[-1]
        ):
            response.headers["Cache-Control"] = "no-cache"
        elif path.startswith(("/assets/", "/images/")):
            response.headers["Cache-Control"] = "public, max-age=604800"

    is_prod = os.getenv("ENVIRONMENT", "development") == "production"
    if is_prod:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    csp_directives = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://checkout.razorpay.com https://cdn.razorpay.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob: https://*.razorpay.com https://replicate.delivery https://*.replicate.delivery; "
        "media-src 'self' blob: mediastream:; "
        "connect-src 'self' https://*.razorpay.com https://cdn.jsdelivr.net https://storage.googleapis.com; "
        "worker-src 'self' blob:; "
        "frame-src https://api.razorpay.com https://checkout.razorpay.com; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self';"
    )
    response.headers["Content-Security-Policy"] = csp_directives
    return response

MAX_ADMIN_PAYLOAD_SIZE = 15 * 1024 * 1024  # 15MB
MAX_STANDARD_PAYLOAD_SIZE = 2 * 1024 * 1024  # 2MB

# In-memory rate limiting dictionary
rate_limit_records = {}

@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
                max_size = MAX_ADMIN_PAYLOAD_SIZE if request.url.path.startswith("/api/v1/admin") else MAX_STANDARD_PAYLOAD_SIZE
                if length > max_size:
                    request_id = getattr(request.state, "request_id", None)
                    return JSONResponse(
                        status_code=413,
                        content={
                            "success": False,
                            "request_id": request_id,
                            "data": None,
                            "error": {
                                "message": f"Payload too large. Maximum allowed size is {max_size // (1024 * 1024)}MB.",
                                "code": 413
                            }
                        }
                    )
            except ValueError:
                pass

    sensitive_prefixes = (
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/otp/send",
        "/api/v1/auth/otp/verify",
        "/api/v1/account/password-change",
        "/api/v1/payments/cod",
        "/api/v1/payments/verify",
        "/api/v1/contact",
        "/api/v1/reviews",
    )
    
    if request.url.path.startswith(sensitive_prefixes) and request.method != "OPTIONS":
        direct_peer = request.client.host if request.client else "unknown"
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for and direct_peer in TRUSTED_PROXIES:
            client_ip = x_forwarded_for.split(",")[0].strip()
        else:
            client_ip = direct_peer
        from app.core.redis_client import check_rate_limit
        allowed, _ = check_rate_limit(
            key=client_ip,
            max_requests=15,
            window_seconds=60,
            in_memory_store=rate_limit_records
        )
        if not allowed:
            request_id = getattr(request.state, "request_id", None)
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "request_id": request_id,
                    "data": None,
                    "error": {
                        "message": "Too many requests. Please try again in a minute.",
                        "code": 429
                    }
                },
                headers={"Retry-After": "60"}
            )
        
    return await call_next(request)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    if not request.url.path.startswith("/api/"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "request_id": request_id,
            "data": None,
            "error": {
                "message": str(exc.detail),
                "code": exc.status_code
            }
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "request_id": request_id,
            "data": None,
            "error": {
                "message": "Validation Error",
                "details": exc.errors(),
                "code": 422
            }
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    app_logger.exception(
        f"Unhandled exception: {request.method} {request.url.path}",
        extra={
            "request_id": request_id,
            "endpoint": request.url.path,
            "method": request.method,
            "status_code": 500,
            "user_id": request.session.get("user_id") if hasattr(request, "session") else None,
        },
    )
    if not request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "request_id": request_id,
            "data": None,
            "error": {
                "message": "Internal Server Error",
                "code": 500
            }
        }
    )
