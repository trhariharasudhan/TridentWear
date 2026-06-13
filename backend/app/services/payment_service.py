import os
import hmac
import hashlib
import uuid
import logging
from typing import Dict, Any
from fastapi import Request, HTTPException
from app.services.order_service import create_payment_order_record
from app.services.auth_service import get_session_user
from app.core.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET, IS_PRODUCTION
from app.core.db_switch import db

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


def verify_webhook_signature(body: bytes, signature: str) -> None:
    """Verifies Razorpay webhook HMAC signature."""
    if not signature or not signature.strip():
        raise HTTPException(status_code=400, detail="Webhook signature is missing.")

    if not RAZORPAY_WEBHOOK_SECRET:
        if IS_PRODUCTION:
            raise HTTPException(status_code=503, detail="Webhook secret not configured.")
        log.warning("[DEV] RAZORPAY_WEBHOOK_SECRET not set — skipping webhook verification.")
        return

    expected = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature.strip()):
        log.warning("Webhook signature mismatch.")
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")


def process_webhook(raw_body: bytes, signature: str) -> Dict[str, Any]:
    """Processes verified Razorpay webhook events idempotently."""
    verify_webhook_signature(raw_body, signature)

    import json
    try:
        event = json.loads(raw_body)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    event_id = event.get("id")
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event ID.")

    event_name = event.get("event")

    # 1. Idempotency Check: check if event already processed
    existing = db.read("payment_events", {"event_id": event_id})
    if existing:
        return {"success": True, "message": "Event already processed"}

    # 2. Extract key fields
    payload = event.get("payload", {})
    payment = payload.get("payment", {}).get("entity", {})
    payment_id = payment.get("id")
    razorpay_order_id = payment.get("order_id")

    # 3. Duplicate payment prevention: check if this payment already succeeded
    if payment_id:
        duplicate = db.read("payment_events", {"payment_id": payment_id, "status": "payment.captured"})
        if duplicate:
            db.insert("payment_events", {
                "event_id": event_id,
                "payment_id": payment_id,
                "order_id": razorpay_order_id,
                "status": event_name,
                "payload": event
            })
            return {"success": True, "message": "Payment already processed"}

    # 4. Save event record
    db.insert("payment_events", {
        "event_id": event_id,
        "payment_id": payment_id,
        "order_id": razorpay_order_id,
        "status": event_name,
        "payload": event
    })

    # 5. Handle success/failure transitions
    if event_name == "payment.captured":
        if razorpay_order_id:
            orders_list = db.read("orders", {"razorpay_order_id": razorpay_order_id})
            if orders_list:
                for order in orders_list:
                    db.update("orders", {"id": order["id"]}, {
                        "payment_status": "paid",
                        "status": "placed",
                        "razorpay_payment_id": payment_id
                    })
    elif event_name == "payment.failed":
        if razorpay_order_id:
            orders_list = db.read("orders", {"razorpay_order_id": razorpay_order_id})
            if orders_list:
                for order in orders_list:
                    db.update("orders", {"id": order["id"]}, {
                        "payment_status": "failed"
                    })

    return {"success": True, "message": f"Webhook processed: {event_name}"}
