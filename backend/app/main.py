from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import os

from app.core.config import CORS_ORIGINS, get_session_secret, SESSION_MAX_AGE, validate_production_secrets

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
app.mount("/components", StaticFiles(directory=str(FRONTEND_ROOT / "components")), name="components")

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
    DB_DIR = os.path.join(BASE_DIR, "db")
    recover_db_files(DB_DIR)

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
                
                response = JSONResponse(status_code=response.status_code, content=wrapped_data)
            except json.JSONDecodeError:
                pass
                
    return response

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    is_prod = os.getenv("ENVIRONMENT", "development") == "production"
    if is_prod:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
    csp_directives = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com https://checkout.razorpay.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: https://*.razorpay.com; "
        "connect-src 'self' https://*.razorpay.com; "
        "frame-src 'self' https://accounts.google.com https://api.razorpay.com;"
    )
    response.headers["Content-Security-Policy"] = csp_directives
    return response

# In-memory rate limiting dictionary
rate_limit_records = {}

@app.middleware("http")
async def rate_limiter(request: Request, call_next):
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
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        if client_ip not in rate_limit_records:
            rate_limit_records[client_ip] = []
            
        timestamps = rate_limit_records[client_ip]
        rate_limit_records[client_ip] = [t for t in timestamps if now - t < 60]
        
        if len(rate_limit_records[client_ip]) >= 15:
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
            
        rate_limit_records[client_ip].append(now)
        
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
