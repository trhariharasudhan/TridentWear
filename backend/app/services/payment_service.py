import os
import hmac
import hashlib
import uuid
import logging
from typing import Dict, Any
from fastapi import Request, HTTPException
from app.services.order_service import create_payment_order_record
from app.services.auth_service import get_session_user
from app.core.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, IS_PRODUCTION

log = logging.getLogger(__name__)


def _verify_razorpay_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
    test_mode: bool = False,
) -> None:
    """
    Verifies the Razorpay payment signature using HMAC-SHA256.
    Raises HTTP 400 if signature is missing or invalid.
    In development with no key secret configured, skips verification only when
    test_mode=True and ENVIRONMENT != production.
    """
    if not razorpay_signature or not razorpay_signature.strip():
        raise HTTPException(status_code=400, detail="Razorpay signature is missing.")

    if not RAZORPAY_KEY_SECRET:
        if IS_PRODUCTION:
            raise HTTPException(
                status_code=503,
                detail="Payment gateway is not configured. Contact support.",
            )
        if test_mode:
            log.warning(
                "[DEV] RAZORPAY_KEY_SECRET not set — skipping signature verification "
                "because test_mode=True. Never allow this in production."
            )
            return
        raise HTTPException(
            status_code=503,
            detail="Razorpay key secret not configured. Set RAZORPAY_KEY_SECRET.",
        )

    # Razorpay signature spec:
    # HMAC-SHA256( key=RAZORPAY_KEY_SECRET, msg="{order_id}|{payment_id}" )
    message = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, razorpay_signature.strip()):
        log.warning(
            "Razorpay signature mismatch. order_id=%s payment_id=%s",
            razorpay_order_id,
            razorpay_payment_id,
        )
        raise HTTPException(status_code=400, detail="Invalid payment signature.")


def process_cod_order(
    subtotal: float,
    customer: Dict[str, Any],
    shipping: Dict[str, Any],
    items: list,
    coupon_code: str = None,
    test_mode: bool = False,
    request: Request = None,
) -> Dict[str, Any]:
    # Inject logged-in user_id so orders appear in profile history
    if request is not None:
        session_user = get_session_user(request)
        if session_user:
            customer = {**customer, "user_id": session_user["id"]}
    order_data = {
        "method": "COD",
        "payment_method": "cod",
        "payment_status": "cod_pending",
        "subtotal": subtotal,
        "total": subtotal,
        "customer": customer,
        "shipping": shipping,
        "items": items,
        "coupon_code": coupon_code,
        "status": "placed",
        "test_mode": test_mode,
    }
    new_order = create_payment_order_record(order_data)
    return {"success": True, "order_id": new_order["order_id"], "message": "COD order placed successfully"}


def process_razorpay_create(amount: int, currency: str = "INR") -> Dict[str, Any]:
    key_id = RAZORPAY_KEY_ID or "rzp_test_mockkey"
    mock_order_id = f"order_{uuid.uuid4().hex[:14]}"
    return {
        "success": True,
        "razorpay_order_id": mock_order_id,
        "key_id": key_id,
    }


def process_razorpay_verify(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
    order_data_payload: Dict[str, Any],
    request: Request = None,
) -> Dict[str, Any]:
    test_mode = bool(order_data_payload.get("test_mode", False))

    # ── SECURITY: Verify HMAC signature before touching the database ──────────
    _verify_razorpay_signature(
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_signature=razorpay_signature,
        test_mode=test_mode,
    )

    customer = dict(order_data_payload.get("customer") or {})
    # Inject logged-in user_id
    if request is not None:
        session_user = get_session_user(request)
        if session_user:
            customer["user_id"] = session_user["id"]

    order_data = {
        "method": "Razorpay",
        "payment_method": "razorpay",
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "subtotal": order_data_payload.get("subtotal"),
        "total": order_data_payload.get("subtotal"),
        "discount_amount": order_data_payload.get("discount_amount", 0),
        "customer": customer,
        "shipping": order_data_payload.get("shipping"),
        "items": order_data_payload.get("items"),
        "coupon_code": order_data_payload.get("coupon_code"),
        "status": "placed",
        "payment_status": "paid",
        "test_mode": test_mode,
    }

    new_order = create_payment_order_record(order_data)
    return {"success": True, "order_id": new_order["order_id"], "message": "Payment verified and order placed"}
