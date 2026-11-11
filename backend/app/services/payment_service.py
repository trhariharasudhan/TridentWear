import os
import hmac
import hashlib
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import Request, HTTPException
from app.services.order_service import create_payment_order_record, create_pending_payment_order, send_order_email, now_iso
from app.services.product_service import deduct_stock
from app.services.auth_service import get_session_user
from app.core.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET, IS_PRODUCTION
from app.core.db_switch import db
from app.db.database import InsufficientStockError, CouponConflictError

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
    fbt_token: str = None,
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
        "fbt_token": fbt_token,
        "status": "placed",
        "test_mode": test_mode,
    }
    new_order = create_payment_order_record(order_data)
    return {"success": True, "order_id": new_order["order_id"], "message": "COD order placed successfully"}


def fetch_gateway_payment(payment_id: str, test_mode: bool = False) -> Dict[str, Any]:
    """
    Fetches payment details from Razorpay's official API to verify amount, currency, and status.
    Fail-closed: if authoritative details cannot be obtained, raises HTTPException.
    """
    if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
        if IS_PRODUCTION:
            raise HTTPException(status_code=503, detail="Payment gateway is not configured.")
        raise HTTPException(
            status_code=503,
            detail="Payment gateway keys not configured for server-side verification."
        )

    try:
        import razorpay
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        payment = client.payment.fetch(payment_id)
        return payment
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to fetch payment {payment_id} from Razorpay: {e}")
        raise HTTPException(status_code=400, detail=f"Could not verify payment with gateway: {str(e)}")


def create_gateway_order(amount: int, currency: str, receipt: str, test_mode: bool = False) -> str:
    """
    Creates an order with Razorpay gateway.
    In development or test_mode without live API credentials, generates mock order ID.
    """
    if test_mode or not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
        return f"order_{uuid.uuid4().hex[:14]}"

    import razorpay
    client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    rz_order = client.order.create({
        "amount": amount,
        "currency": currency,
        "receipt": receipt,
        "notes": {"order_id": receipt}
    })
    actual_id = rz_order.get("id")
    if not actual_id:
        raise RuntimeError("Gateway did not return an order ID.")
    return actual_id


def process_razorpay_create(
    amount: Optional[int] = None,
    currency: str = "INR",
    order_data: Optional[Dict[str, Any]] = None,
    request: Request = None,
) -> Dict[str, Any]:
    if currency != "INR":
        raise HTTPException(status_code=400, detail="Only INR currency is supported.")

    if not order_data:
        raise HTTPException(status_code=400, detail="Missing required order_data for payment initiation.")

    key_id = RAZORPAY_KEY_ID or "rzp_test_mockkey"
    mock_order_id = f"order_{uuid.uuid4().hex[:14]}"

    order_payload = dict(order_data)
    order_payload["razorpay_order_id"] = mock_order_id

    # Create and persist the server-validated pending order
    res = create_pending_payment_order(order_payload, currency=currency, request=request)
    authoritative_amount_paise = res["amount_paise"]
    razorpay_order_id = mock_order_id

    # Create order on Razorpay gateway (or generate mock ID if test/dev)
    try:
        actual_rz_id = create_gateway_order(
            amount=authoritative_amount_paise,
            currency="INR",
            receipt=res["order_id"],
            test_mode=bool(order_data.get("test_mode", False)),
        )
        if actual_rz_id != razorpay_order_id:
            db.update("orders", {"order_id": res["order_id"]}, {"razorpay_order_id": actual_rz_id})
            razorpay_order_id = actual_rz_id
    except HTTPException:
        db.delete("orders", {"order_id": res["order_id"]})
        raise
    except Exception as e:
        # Clean up pending order if gateway order creation fails
        db.delete("orders", {"order_id": res["order_id"]})
        log.error(f"Failed to create Razorpay order: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to create payment order with gateway: {str(e)}")

    return {
        "success": True,
        "order_id": res["order_id"],
        "razorpay_order_id": razorpay_order_id,
        "amount": authoritative_amount_paise,
        "currency": "INR",
        "key_id": key_id,
    }


def _handle_cancelled_order_payment(
    current_order: Dict[str, Any],
    order_id: Optional[Any],
    order_human_id: str,
    razorpay_payment_id: str,
) -> Dict[str, Any]:
    """
    Safely reconciles a captured payment arriving for a cancelled order.
    Ensures:
    1. status='cancelled' is preserved.
    2. payment_status='paid' is recorded via atomic CAS predicate.
    3. fulfillment_status='manual_review_required' is set.
    4. Duplicate callbacks for the same payment ID return idempotently.
    5. Conflicting payment IDs for an already-paid cancelled order raise HTTP 409/400.
    6. No stock deduction, coupon redemption, or fulfillment occurs.
    """
    read_filter = {"id": order_id} if order_id is not None else {"order_id": order_human_id}

    # If already marked paid on initial read
    if current_order.get("payment_status") == "paid":
        if current_order.get("razorpay_payment_id") != razorpay_payment_id:
            raise HTTPException(
                status_code=400,
                detail=f"Order has already been paid with payment ID '{current_order.get('razorpay_payment_id')}'; cannot bind '{razorpay_payment_id}'."
            )
        return {
            "success": True,
            "order_id": order_human_id,
            "payment_status": "paid",
            "stock_status": current_order.get("stock_status", "pending"),
            "email_status": current_order.get("email_status", "pending"),
            "fulfillment_status": "manual_review_required",
            "fulfillment_complete": False,
            "message": "Payment captured for cancelled order; flagged for manual review/refund.",
        }

    # Atomic CAS update: only update if status is still cancelled and payment_status is still observed non-paid
    current_status = current_order.get("payment_status") or "pending"
    target_filter = {
        "status": "cancelled",
        "payment_status": current_status,
    }
    if order_id is not None:
        target_filter["id"] = order_id
    else:
        target_filter["order_id"] = order_human_id

    cancelled_update = {
        "payment_status": "paid",
        "razorpay_payment_id": razorpay_payment_id,
        "fulfillment_status": "manual_review_required",
        "updated_at": now_iso(),
    }
    claimed = db.update("orders", target_filter, cancelled_update)
    if not claimed:
        # Re-read authoritative order state
        fresh = db.read("orders", read_filter)
        if not fresh:
            raise HTTPException(status_code=404, detail="Order not found.")
        persisted = fresh[0]
        if persisted.get("payment_status") == "paid":
            if persisted.get("razorpay_payment_id") == razorpay_payment_id:
                # Idempotent duplicate callback
                return {
                    "success": True,
                    "order_id": order_human_id,
                    "payment_status": "paid",
                    "stock_status": persisted.get("stock_status", "pending"),
                    "email_status": persisted.get("email_status", "pending"),
                    "fulfillment_status": "manual_review_required",
                    "fulfillment_complete": False,
                    "message": "Payment captured for cancelled order; flagged for manual review/refund.",
                }
            raise HTTPException(
                status_code=409,
                detail=f"Order is already paid with payment ID '{persisted.get('razorpay_payment_id')}'; cannot bind '{razorpay_payment_id}'."
            )
        raise HTTPException(
            status_code=409,
            detail="Failed to record payment for cancelled order due to concurrent conflict."
        )

    current_order.update(cancelled_update)
    return {
        "success": True,
        "order_id": order_human_id,
        "payment_status": "paid",
        "stock_status": current_order.get("stock_status", "pending"),
        "email_status": current_order.get("email_status", "pending"),
        "fulfillment_status": "manual_review_required",
        "fulfillment_complete": False,
        "message": "Payment captured for cancelled order; flagged for manual review/refund.",
    }


def finalize_paid_order(
    order: Dict[str, Any],
    razorpay_payment_id: str,
    test_mode: bool = False,
) -> Dict[str, Any]:
    """
    Atomically finalizes an order to 'paid' and manages idempotent fulfillment side effects.
    Guarantees that:
    1. A captured payment is never marked unpaid due to fulfillment errors.
    2. Side effects (coupon, stock, email) are idempotent and safely resumable.
    3. Conflicting payment IDs are rejected.
    4. Stock shortage post-capture flags manual review rather than claiming false completion.
    """
    order_id = order.get("id")
    order_human_id = order.get("order_id", str(order_id))

    # Guard: check if payment_id is already bound to a different order
    existing_with_payment = db.read("orders", {"razorpay_payment_id": razorpay_payment_id})
    if existing_with_payment and str(existing_with_payment[0].get("id")) != str(order_id):
        raise HTTPException(status_code=400, detail="Payment ID has already been used for another order.")

    # Re-read fresh order state
    fresh_orders = None
    if order_id is not None:
        fresh_orders = db.read("orders", {"id": order_id})
    if not fresh_orders and order.get("razorpay_order_id"):
        fresh_orders = db.read("orders", {"razorpay_order_id": order["razorpay_order_id"]})
    if not fresh_orders and order.get("order_id"):
        fresh_orders = db.read("orders", {"order_id": order["order_id"]})
    if not fresh_orders:
        fresh_orders = [order]
    current_order = fresh_orders[0]
    if current_order.get("id") is not None:
        order_id = current_order["id"]

    # Guard: check if order was cancelled before payment capture
    if current_order.get("status") == "cancelled":
        return _handle_cancelled_order_payment(current_order, order_id, order_human_id, razorpay_payment_id)

    # Guard: check if order is already paid with a DIFFERENT payment ID
    if current_order.get("payment_status") == "paid":
        if current_order.get("razorpay_payment_id") != razorpay_payment_id:
            raise HTTPException(status_code=400, detail="Order has already been paid with a different payment ID.")
    else:
        current_status = current_order.get("payment_status") or "pending"
        current_order_status = current_order.get("status")
        update_data = {
            "status": "placed",
            "payment_status": "paid",
            "razorpay_payment_id": razorpay_payment_id,
            "stock_status": current_order.get("stock_status") or "pending",
            "email_status": current_order.get("email_status") or "pending",
            "updated_at": now_iso(),
        }

        # Conditional atomic claim: order ID matches, payment_status matches, AND status still matches non-cancelled read
        # Prevents race where order is cancelled after the read above
        claim_filter = {
            "payment_status": current_status,
        }
        if current_order_status is not None:
            claim_filter["status"] = current_order_status
        if order_id is not None:
            claim_filter["id"] = order_id
        else:
            claim_filter["order_id"] = order_human_id

        claimed = db.update("orders", claim_filter, update_data)
        if not claimed:
            # Re-read to check if order was cancelled concurrently or if competing thread completed this exact payment
            read_filter = {"id": order_id} if order_id is not None else {"order_id": order_human_id}
            after_race = db.read("orders", read_filter)
            if not after_race:
                raise HTTPException(status_code=404, detail="Order not found.")
            raced_order = after_race[0]

            if raced_order.get("status") == "cancelled":
                # Case B / Case C: Cancellation won the race before payment finalization could claim the order
                return _handle_cancelled_order_payment(raced_order, order_id, order_human_id, razorpay_payment_id)

            if raced_order.get("payment_status") == "paid" and raced_order.get("razorpay_payment_id") == razorpay_payment_id:
                current_order = raced_order
            else:
                raise HTTPException(status_code=409, detail="Order status updated concurrently by another request.")
        else:
            current_order.update(update_data)

    # --- Idempotent Fulfillment Pipeline ---
    needs_stock = (current_order.get("stock_status") == "pending")
    needs_email = (current_order.get("email_status") in ("pending", "failed"))
    needs_coupon = bool(current_order.get("coupon_code") and current_order.get("coupon_status") not in ("redeemed", "exhausted_post_capture"))

    # 1. Coupon outcome
    if needs_coupon:
        coupon_code = current_order["coupon_code"]
        today_iso = datetime.now(timezone.utc).date().isoformat()
        offer_id = current_order.get("fbt_offer_id")
        try:
            if offer_id:
                redeemed = db.redeem_coupon(coupon_code, today_iso, order_id=order_human_id, offer_id=offer_id)
            else:
                redeemed = db.redeem_coupon(coupon_code, today_iso, order_id=order_human_id)
            new_coupon_status = "redeemed" if redeemed else "exhausted_post_capture"
            if not redeemed:
                log.warning(f"[COUPON_EXHAUSTED_POST_CAPTURE] Order {order_human_id} paid but coupon {coupon_code} could not be redeemed.")
            db.update("orders", {"id": order_id}, {"coupon_status": new_coupon_status})
            current_order["coupon_status"] = new_coupon_status
        except CouponConflictError as cce:
            log.error(f"[COUPON_CONFLICT] Order {order_human_id}: {cce}")
            db.update("orders", {"id": order_id}, {
                "coupon_status": "conflict_post_capture",
                "fulfillment_status": "manual_review_required"
            })
            current_order["coupon_status"] = "conflict_post_capture"
            current_order["fulfillment_status"] = "manual_review_required"

    # 2. Stock deduction
    is_test = test_mode or bool(current_order.get("test_mode", False))
    if needs_stock and not is_test:
        try:
            try:
                deduct_stock(current_order.get("items", []), order_id=order_human_id)
            except TypeError as te:
                if "order_id" in str(te):
                    deduct_stock(current_order.get("items", []))
                else:
                    raise
            db.update("orders", {"id": order_id}, {"stock_status": "deducted"})
            current_order["stock_status"] = "deducted"
        except InsufficientStockError as stock_shortage:
            log.error(f"[STOCK_FULFILLMENT_FAILED_OUT_OF_STOCK] Order {order_human_id}: {stock_shortage}")
            db.update("orders", {"id": order_id}, {
                "stock_status": "failed_insufficient_stock",
                "fulfillment_status": "manual_review_required"
            })
            current_order["stock_status"] = "failed_insufficient_stock"
            current_order["fulfillment_status"] = "manual_review_required"
        except Exception as stock_err:
            log.error(f"[STOCK_DEDUCTION_FAILED] Order {order_human_id}: {stock_err}")
            # Leave stock_status as 'pending' for subsequent retry
    elif is_test and needs_stock:
        db.update("orders", {"id": order_id}, {"stock_status": "deducted"})
        current_order["stock_status"] = "deducted"

    # 3. Customer email dispatch
    if needs_email:
        try:
            send_order_email(current_order)
            db.update("orders", {"id": order_id}, {"email_status": "sent"})
            current_order["email_status"] = "sent"
        except Exception as email_err:
            log.warning(f"[EMAIL_DISPATCH_FAILED] Order {order_human_id}: {email_err}")
            db.update("orders", {"id": order_id}, {"email_status": "failed"})
            current_order["email_status"] = "failed"

    # Evaluate final fulfillment state
    stock_done = current_order.get("stock_status") in ("deducted", None)
    email_done = current_order.get("email_status") in ("sent", None)
    no_manual_review = (current_order.get("fulfillment_status") != "manual_review_required")
    fulfillment_complete = bool(stock_done and email_done and no_manual_review)

    if current_order.get("stock_status") == "failed_insufficient_stock":
        return {
            "success": True,
            "order_id": order_human_id,
            "payment_status": "paid",
            "stock_status": "failed_insufficient_stock",
            "fulfillment_status": "manual_review_required",
            "message": "Payment verified; item out of stock, flagged for priority fulfillment review.",
            "fulfillment_complete": False,
        }

    if current_order.get("fulfillment_status") == "manual_review_required":
        return {
            "success": True,
            "order_id": order_human_id,
            "payment_status": "paid",
            "stock_status": current_order.get("stock_status", "deducted"),
            "email_status": current_order.get("email_status", "sent"),
            "fulfillment_status": "manual_review_required",
            "message": "Payment verified; fulfillment flagged for manual review.",
            "fulfillment_complete": False,
        }

    # Persist fulfillment completion if all side-effects succeeded and order is not under manual review
    if fulfillment_complete:
        if current_order.get("fulfillment_status") != "fulfilled":
            try:
                updated = db.update("orders", {"id": order_id}, {"fulfillment_status": "fulfilled"})
                if updated:
                    current_order["fulfillment_status"] = "fulfilled"
                else:
                    log.error(f"[FULFILLMENT_STATUS_PERSIST_FAILED] Order {order_human_id}: db.update returned no rows.")
                    fulfillment_complete = False
            except Exception as persist_err:
                log.error(f"[FULFILLMENT_STATUS_PERSIST_ERROR] Order {order_human_id}: {persist_err}")
                fulfillment_complete = False

    return {
        "success": True,
        "order_id": order_human_id,
        "payment_status": "paid",
        "stock_status": current_order.get("stock_status", "deducted"),
        "email_status": current_order.get("email_status", "sent"),
        "fulfillment_status": current_order.get("fulfillment_status") or ("fulfilled" if fulfillment_complete else "pending"),
        "message": "Payment verified and order placed",
        "fulfillment_complete": fulfillment_complete,
    }


def process_razorpay_verify(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
    order_data_payload: Optional[Dict[str, Any]] = None,
    request: Request = None,
) -> Dict[str, Any]:
    test_mode = bool(order_data_payload.get("test_mode", False)) if order_data_payload else False

    # 1. Cryptographic HMAC signature check
    _verify_razorpay_signature(
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_signature=razorpay_signature,
        test_mode=test_mode,
    )

    # 2. Look up the persisted pending order intent
    orders_list = db.read("orders", {"razorpay_order_id": razorpay_order_id})
    if not orders_list:
        raise HTTPException(status_code=404, detail="No pending order found for this payment intent.")
    order = orders_list[0]

    # 3. Idempotency Check: if this order is already paid with this payment ID, return it cleanly
    if order.get("payment_status") == "paid" and order.get("razorpay_payment_id") == razorpay_payment_id:
        return {"success": True, "order_id": order["order_id"], "message": "Payment verified and order placed"}

    # 4. Check if payment_id is already bound to a different order
    existing_with_payment = db.read("orders", {"razorpay_payment_id": razorpay_payment_id})
    if existing_with_payment and existing_with_payment[0]["order_id"] != order["order_id"]:
        raise HTTPException(status_code=400, detail="Payment ID has already been used for another order.")

    # 5. Authoritative Gateway Verification
    gateway_payment = fetch_gateway_payment(razorpay_payment_id, test_mode=bool(order.get("test_mode", False)))

    # Verify order association
    if gateway_payment.get("order_id") and gateway_payment["order_id"] != razorpay_order_id:
        raise HTTPException(status_code=400, detail="Payment does not belong to the expected Razorpay order.")

    # Verify currency
    gw_currency = str(gateway_payment.get("currency") or "").upper()
    if gw_currency != "INR":
        raise HTTPException(status_code=400, detail=f"Invalid payment currency: {gw_currency}. Expected INR.")

    # Verify captured status (F-02: authorized is NOT captured)
    gw_status = gateway_payment.get("status")
    if gw_status != "captured":
        raise HTTPException(status_code=400, detail=f"Payment status is '{gw_status}', not captured.")

    # Verify amount matching (authoritative order total in paise vs gateway amount)
    expected_paise = int(round(float(order.get("total", 0.0)) * 100))
    actual_paise = gateway_payment.get("amount")
    if actual_paise is None or int(actual_paise) != expected_paise:
        raise HTTPException(
            status_code=400,
            detail=f"Payment amount mismatch: gateway received {actual_paise}, expected {expected_paise}."
        )

    # 6. Finalize order transition to paid atomically (F-01, F-03, F-05)
    return finalize_paid_order(
        order=order,
        razorpay_payment_id=razorpay_payment_id,
        test_mode=test_mode or bool(order.get("test_mode", False)),
    )


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

    # 5. Handle success/failure transitions with order-tied coupon lifecycle
    if event_name == "payment.captured":
        if razorpay_order_id:
            orders_list = db.read("orders", {"razorpay_order_id": razorpay_order_id})
            if orders_list:
                for order in orders_list:
                    finalize_paid_order(
                        order=order,
                        razorpay_payment_id=payment_id,
                        test_mode=bool(order.get("test_mode", False)),
                    )
    elif event_name == "payment.failed":
        if razorpay_order_id:
            orders_list = db.read("orders", {"razorpay_order_id": razorpay_order_id})
            if orders_list:
                for order in orders_list:
                    # Guard 1: An order already confirmed as paid must NEVER transition to failed
                    if order.get("payment_status") == "paid":
                        log.info(f"[PAYMENT_FAILED_IGNORED] Order {order.get('order_id')} is already confirmed as paid. Ignoring late failure webhook.")
                        continue

                    # Guard 2: If order is cancelled, do not alter its status
                    if order.get("status") == "cancelled":
                        log.info(f"[PAYMENT_FAILED_IGNORED] Order {order.get('order_id')} is already cancelled.")
                        continue

                    order_id = order["id"]
                    order_human_id = order.get("order_id", str(order_id))
                    old_coupon_status = order.get("coupon_status")
                    current_payment_status = order.get("payment_status") or "pending"

                    # Duplicate failure callback idempotency
                    if current_payment_status == "failed":
                        log.info(f"[PAYMENT_FAILED_IDEMPOTENT] Order {order_human_id} is already marked as failed.")
                        continue

                    update_payload = {
                        "payment_status": "failed",
                        "updated_at": now_iso(),
                    }
                    if old_coupon_status in ("redeemed", "reserved"):
                        update_payload["coupon_status"] = "released"

                    # Atomic conditional transition: only transition if payment_status is still current_payment_status
                    claimed = db.update("orders", {"id": order_id, "payment_status": current_payment_status}, update_payload)
                    if not claimed:
                        fresh = db.read("orders", {"id": order_id})
                        if fresh and fresh[0].get("payment_status") == "paid":
                            log.info(f"[PAYMENT_FAILED_RACED] Order {order_human_id} was paid concurrently. Ignoring failure.")
                            continue
                        continue

                    # Only release coupons if the atomic CAS transition actually claimed the failure
                    if old_coupon_status in ("redeemed", "reserved"):
                        coupon_code = order.get("coupon_code")
                        offer_id = order.get("fbt_offer_id")
                        if coupon_code:
                            try:
                                if old_coupon_status == "reserved" and offer_id:
                                    db.release_coupon_offer(coupon_code, order_id=order_human_id, offer_id=offer_id)
                                else:
                                    db.release_coupon(coupon_code, order_id=order_human_id, offer_id=offer_id)
                            except Exception as e:
                                log.error(f"[COUPON_RELEASE_FAILED] Order {order_human_id}: {e}")

    return {"success": True, "message": f"Webhook processed: {event_name}"}
