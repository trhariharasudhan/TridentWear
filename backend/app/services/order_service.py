import os
import json
import uuid
import math
import smtplib
import ssl
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from fastapi import HTTPException, status, Request

from app.core.db_switch import db
from app.core.logger import app_logger
from app.db.database import InsufficientStockError, CouponConflictError
from app.services.product_service import load_products, deduct_stock, normalize_image_path
from app.services.auth_service import get_session_user, validate_email
from app.services.fbt_service import validate_fbt_bundle_qualification

def _extract_field(payload: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(field_name, default)
    val = getattr(payload, field_name, None)
    if val is not None:
        return val
    if hasattr(payload, "model_extra") and isinstance(payload.model_extra, dict):
        return payload.model_extra.get(field_name, default)
    if hasattr(payload, "__dict__") and isinstance(payload.__dict__, dict):
        return payload.__dict__.get(field_name, default)
    return default

ORDER_STATUSES = {"placed", "confirmed", "packed", "shipped", "delivered", "cancelled"}
PAYMENT_STATUSES = {"pending", "paid", "failed", "refunded", "cod_pending"}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def load_orders() -> List[Dict[str, Any]]:
    return db.read("orders", {})

def send_order_email(order: Dict[str, Any]) -> None:
    """Non-blocking email; silently skips if SMTP not configured."""
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USERNAME", os.getenv("SMTP_USER", ""))
    password = os.getenv("SMTP_PASSWORD", os.getenv("SMTP_PASS", ""))
    from_email = os.getenv("SMTP_FROM_EMAIL", "noreply@tridentwear.in")
    
    if not (host and user and password):
        return
    to_email = order.get("customer", {}).get("email", "")
    if not to_email:
        return
    items_text = ", ".join(
        f"{i.get('name', 'Product')} x{i.get('qty', 1)}" for i in order.get("items", [])
    )
    body = (
        f"Hi {order['customer'].get('name', 'Customer')},\n\n"
        f"Your TridentWear order {order['order_id']} has been placed!\n"
        f"Status: {order.get('status','confirmed')}\n"
        f"Items: {items_text}\n"
        f"Total: \u20b9{order.get('total', 0)}\n\n"
        f"Thank you for shopping with us!\n\nTeam TridentWear"
    )
    msg = MIMEText(body)
    msg["Subject"] = f"Order Confirmed - {order['order_id']}"
    msg["From"] = from_email
    msg["To"] = to_email
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.login(user, password)
            smtp.sendmail(from_email, [to_email], msg.as_string())
    except Exception:
        pass

def get_stats_data() -> Dict[str, int]:
    orders = load_orders()
    unique_users = set(o.get("customer", {}).get("email") for o in orders if o.get("customer", {}).get("email"))
    baseline = 150
    return {"customers": baseline + len(unique_users) if unique_users else baseline + len(orders)}

def process_create_order(payload: Any, request: Request) -> Dict[str, Any]:
    if not payload.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your cart is empty.")
    
    # 1. Server-side price lookup and stock validation
    products = load_products()
    prod_map = {p["id"]: p for p in products}
    
    items = []
    subtotal = 0
    
    for item in payload.items:
        pid = int(item.get("id") or item.get("product_id") or 0)
        qty = max(int(item.get("qty", 1)), 1)
        if pid not in prod_map:
            raise HTTPException(status_code=400, detail=f"Product with ID {pid} not found.")
            
        db_product = prod_map[pid]
        
        # Stock check
        if db_product["stock"] < qty:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {db_product['name']}.")
            
        items.append({
            "id": pid,
            "name": db_product["name"],
            "price": db_product["price"],
            "image": normalize_image_path(db_product.get("image", "")),
            "qty": qty,
            "size": str(item.get("size", "")).strip().upper(),
        })
        subtotal += db_product["price"] * qty

    # Validate customer and shipping info before attempting coupon redemption
    session_user = get_session_user(request)
    customer_name = str(payload.customer.get("name", "")).strip()
    customer_email = validate_email(str(payload.customer.get("email", "") or "guest@trident.local"))
    shipping_address = str(payload.shipping.get("address", "")).strip()
    shipping_city = str(payload.shipping.get("city", "")).strip()
    shipping_phone = str(payload.customer.get("phone", "")).strip()

    if len(customer_name) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer name is required.")
    if len(shipping_address) < 6 or len(shipping_city) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Complete shipping details are required.")
    if len(shipping_phone) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid phone number is required.")

    # Generate stable order ID upfront before redemption
    order_id = f"TRD-{uuid.uuid4().hex[:8].upper()}"

    # 2. Order-Bound Coupon Validation & Redemption
    discount_amount = 0.0
    coupon_code = str(_extract_field(payload, "coupon_code", "") or "").strip().upper()
    fbt_token = _extract_field(payload, "fbt_token", None)
    offer_id = None
    redeemed_coupon = None
    newly_redeemed = False

    if coupon_code:
        today_iso = datetime.now(timezone.utc).date().isoformat()
        if coupon_code == "BUNDLE10":
            if not fbt_token:
                raise HTTPException(status_code=400, detail="BUNDLE10 coupon requires a valid FBT offer token.")
            try:
                fbt_qual = validate_fbt_bundle_qualification(fbt_token, items, prod_map)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            offer_id = fbt_qual["offer_id"]
            discount_amount = fbt_qual["discount_amount"]

        try:
            if offer_id is not None:
                redeemed_coupon = db.redeem_coupon(coupon_code, today_iso, order_id=order_id, offer_id=offer_id)
            else:
                redeemed_coupon = db.redeem_coupon(coupon_code, today_iso, order_id=order_id)
        except CouponConflictError as cce:
            raise HTTPException(status_code=400, detail=f"Coupon conflict: {cce}")

        if not redeemed_coupon:
            # Check reasons to give precise error detail matching client expectations
            coupon_res = db.read("coupons", {"code": coupon_code})
            if not coupon_res:
                raise HTTPException(status_code=400, detail="Invalid coupon code.")
            coupon = coupon_res[0]
            is_active = coupon.get("is_active")
            if is_active is False or str(is_active).lower() == "false":
                raise HTTPException(status_code=400, detail="Coupon is disabled.")
            now = datetime.now(timezone.utc).date()
            try:
                expiry_str = coupon.get("expires_at") or coupon.get("expiry") or "2099-01-01"
                expiry_date = datetime.fromisoformat(expiry_str).date()
            except Exception:
                expiry_date = now
            if expiry_date < now:
                raise HTTPException(status_code=400, detail="Coupon has expired.")
            usage_count = int(coupon.get("usage_count", 0))
            usage_limit = int(coupon.get("usage_limit", 9999))
            if usage_count >= usage_limit:
                raise HTTPException(status_code=400, detail="Coupon usage limit reached.")
            raise HTTPException(status_code=400, detail="Coupon could not be applied.")

        newly_redeemed = not bool(redeemed_coupon.get("already_redeemed", False))
        if coupon_code != "BUNDLE10":
            raw_pct = redeemed_coupon.get("discount_pct") if redeemed_coupon.get("discount_pct") is not None else redeemed_coupon.get("discount")
            try:
                discount_pct = float(raw_pct if raw_pct is not None else 0.0)
            except (TypeError, ValueError):
                discount_pct = 0.0

            if math.isfinite(discount_pct) and (0.0 <= discount_pct <= 100.0):
                discount_amount = round(subtotal * discount_pct / 100, 2)
                discount_amount = min(discount_amount, subtotal)
            else:
                if newly_redeemed:
                    (db.release_coupon(coupon_code, order_id=order_id, offer_id=offer_id) if offer_id is not None else db.release_coupon(coupon_code, order_id=order_id))
                redeemed_coupon = None
                discount_amount = 0.0

    total = max(0.0, round(subtotal - discount_amount, 2))

    new_order = {
        "order_id": order_id,
        "customer": {
            "user_id": session_user["id"] if session_user else None,
            "name": customer_name,
            "email": customer_email,
            "phone": shipping_phone
        },
        "shipping": {
            "address": shipping_address,
            "city": shipping_city,
            "pincode": str(payload.shipping.get("pincode", "")).strip()
        },
        "items": items,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "coupon_code": coupon_code or None,
        "coupon_status": "redeemed" if redeemed_coupon else "none",
        "fbt_offer_id": offer_id,
        "total": total,
        "payment_method": getattr(payload, "payment_method", "cod"),
        "status": "placed",
        "payment_status": "cod_pending" if getattr(payload, "payment_method", "cod") == "cod" else "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "test_mode": bool(getattr(payload, "test_mode", False)),
        "created_at": now_iso(),
    }
    
    # 3. Save order (isolated insertion with coupon compensation if insert fails)
    try:
        inserted = db.insert("orders", new_order)
    except Exception as e:
        if newly_redeemed:
            try:
                (db.release_coupon(coupon_code, order_id=order_id, offer_id=offer_id) if offer_id is not None else db.release_coupon(coupon_code, order_id=order_id))
            except Exception as rel_err:
                app_logger.error(f"[CRITICAL_COMPENSATION_FAILED] Failed to release coupon '{coupon_code}': {rel_err}")
        raise HTTPException(status_code=500, detail=f"Failed to place order: {e}")

    # 4. Stock deduction (order is safely persisted; do NOT release coupon if stock fails)
    if not inserted.get("test_mode"):
        try:
            deduct_stock(items, order_id=inserted["order_id"])
            db.update("orders", {"id": inserted["id"]}, {"stock_status": "deducted"})
            inserted["stock_status"] = "deducted"
        except InsufficientStockError as is_err:
            app_logger.error(f"[STOCK_SHORTAGE_COD_ORDER] Order {inserted.get('order_id')}: {is_err}")
            db.update("orders", {"id": inserted["id"]}, {
                "stock_status": "failed_insufficient_stock",
                "fulfillment_status": "manual_review_required"
            })
            inserted["stock_status"] = "failed_insufficient_stock"
            inserted["fulfillment_status"] = "manual_review_required"
        except Exception as stock_err:
            app_logger.error(f"[STOCK_DEDUCTION_FAILED] Order {inserted.get('order_id')}: {stock_err}")

    # 5. Customer email dispatch
    try:
        send_order_email(inserted)
        db.update("orders", {"id": inserted["id"]}, {"email_status": "sent"})
        inserted["email_status"] = "sent"
    except Exception:
        pass
        
    return {"success": True, "message": "Order placed successfully.", "order_id": inserted["order_id"]}

def get_user_orders_data(request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in to view orders.")
    orders = load_orders()
    user_orders = []
    for o in orders:
        cust = o.get("customer") or {}
        uid = cust.get("user_id") if isinstance(cust, dict) else None
        if uid is None:
            uid = o.get("user_id")
        if uid is not None and int(uid) == int(user["id"]):
            user_orders.append(o)
            
    user_orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"success": True, "orders": user_orders}

def cancel_order_logic(order_id: str, request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in.")

    res = db.read("orders", {"order_id": order_id})
    if not res:
        raise HTTPException(status_code=404, detail="Order not found.")
    order = res[0]

    cust = order.get("customer") or {}
    uid = cust.get("user_id") if isinstance(cust, dict) else None
    if uid is None:
        uid = order.get("user_id")

    if int(uid or 0) != int(user["id"]):
        raise HTTPException(status_code=403, detail="Forbidden.")

    # Idempotent return if already cancelled
    if order.get("status") == "cancelled":
        return {"success": True, "message": "Order is already cancelled."}

    # Prohibit customer cancellation of shipped / delivered orders
    if order.get("status") in ("shipped", "delivered"):
        raise HTTPException(status_code=400, detail="Cannot cancel a shipped order.")

    # Prohibit customer cancellation of paid orders
    if order.get("payment_status") == "paid":
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel an order that has already been paid. Please contact customer support for returns or refunds."
        )

    current_status = order.get("status")
    current_payment_status = order.get("payment_status") or "pending"

    # Atomic CAS claim: verify order is still in the observed status and payment_status is still non-paid
    claim_filter = {
        "order_id": order_id,
        "payment_status": current_payment_status,
    }
    if current_status is not None:
        claim_filter["status"] = current_status

    claimed = db.update("orders", claim_filter, {"status": "cancelled", "updated_at": now_iso()})
    if not claimed:
        # Re-read authoritative order state to determine race outcome
        fresh = db.read("orders", {"order_id": order_id})
        if not fresh:
            raise HTTPException(status_code=404, detail="Order not found.")
        raced = fresh[0]
        if raced.get("status") == "cancelled":
            return {"success": True, "message": "Order is already cancelled."}
        if raced.get("payment_status") == "paid":
            raise HTTPException(
                status_code=400,
                detail="Cannot cancel an order that has already been paid. Please contact customer support."
            )
        raise HTTPException(
            status_code=409,
            detail=f"Order state changed concurrently to status '{raced.get('status')}'; cancellation aborted."
        )

    # Release ONLY a reserved coupon / FBT offer; NEVER release an already redeemed coupon
    coupon_code = order.get("coupon_code")
    offer_id = order.get("fbt_offer_id")
    coupon_status = order.get("coupon_status")
    if coupon_code and coupon_status == "reserved" and offer_id:
        try:
            db.release_coupon_offer(coupon_code, order_id=order_id, offer_id=offer_id)
            db.update("orders", {"order_id": order_id, "status": "cancelled"}, {"coupon_status": "released"})
        except Exception as e:
            app_logger.error(f"[COUPON_RELEASE_FAILED] Order {order_id}: {e}")

    return {"success": True, "message": "Order cancelled."}

def track_order_logic(order_id: str) -> Dict[str, Any]:
    orders = load_orders()
    for o in orders:
        if o.get("order_id") == order_id:
            if o.get("tracking_id"):
                return {
                    "status": "In Transit" if o.get("status") == "shipped" else o.get("status", "Unknown").title(),
                    "courier": o.get("courier", "Standard Courier"),
                    "tracking_id": o.get("tracking_id"),
                    "estimated_delivery": o.get("estimated_delivery", "TBD")
                }
            return {
                "status": o.get("status", "pending").title(),
                "courier": "Pending Allocation",
                "tracking_id": None,
                "estimated_delivery": "Tracking will be updated soon"
            }
    raise HTTPException(status_code=404, detail="Order not found.")

def create_shiprocket_shipment(order: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "shipped",
        "tracking_id": f"SR{uuid.uuid4().hex[:8].upper()}",
        "courier": "Delhivery (Shiprocket)",
        "estimated_delivery": (datetime.now(timezone.utc) + timedelta(days=4)).date().isoformat()
    }

def get_all_orders_data() -> List[Dict[str, Any]]:
    return load_orders()

def normalize_order_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in ORDER_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Order status must be one of: {', '.join(sorted(ORDER_STATUSES))}.")
    return normalized

def normalize_payment_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in PAYMENT_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Payment status must be one of: {', '.join(sorted(PAYMENT_STATUSES))}.")
    return normalized

def update_order_status_logic(order_id: str, payload: Any) -> Dict[str, Any]:
    changes = payload if isinstance(payload, dict) else {"status": payload}
    payload_status = normalize_order_status(changes.get("status"))
    
    res = db.read("orders", {"order_id": order_id})
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    order = res[0]
    
    updates = {
        "status": payload_status,
        "updated_at": now_iso()
    }
    if changes.get("payment_status"):
        updates["payment_status"] = normalize_payment_status(changes["payment_status"])
    for field in ("tracking_id", "courier", "estimated_delivery", "shipment_notes"):
        if changes.get(field) is not None:
            updates[field] = str(changes[field]).strip()
            
    if payload_status == "shipped" and not order.get("tracking_id") and not updates.get("tracking_id"):
        try:
            shipment = create_shiprocket_shipment(order)
            updates["tracking_id"] = shipment["tracking_id"]
            updates["courier"] = shipment["courier"]
            updates["estimated_delivery"] = shipment["estimated_delivery"]
        except Exception:
            pass
            
    updated_list = db.update("orders", {"order_id": order_id}, updates)
    if not updated_list:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return {"success": True, "message": "Order status updated.", "order": updated_list[0]}

def create_pending_payment_order(order_data: Dict[str, Any], currency: str = "INR", request: Request = None) -> Dict[str, Any]:
    """
    Establishes and persists a server-validated pending order before payment initiation.
    Does NOT deduct stock, does NOT send confirmation email, and does NOT increment coupon counters.
    Calculates authoritative subtotal and total from catalog prices and coupon data.
    """
    if currency != "INR":
        raise HTTPException(status_code=400, detail="Only INR currency is supported.")

    raw_items = order_data.get("items")
    if not raw_items or not isinstance(raw_items, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your cart is empty.")

    products = load_products()
    prod_map = {p["id"]: p for p in products}

    aggregated_qtys: Dict[int, int] = {}
    validated_items_temp = []

    for item in raw_items:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Invalid item format.")
        try:
            pid = int(item.get("id") or item.get("product_id") or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid product ID.")

        if pid <= 0 or pid not in prod_map:
            raise HTTPException(status_code=400, detail=f"Product with ID {pid} not found.")

        try:
            qty = int(item.get("qty", 1))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid item quantity.")

        if qty < 1 or qty > 50:
            raise HTTPException(status_code=400, detail="Item quantity must be between 1 and 50.")

        aggregated_qtys[pid] = aggregated_qtys.get(pid, 0) + qty
        validated_items_temp.append((pid, qty, str(item.get("size", "")).strip().upper()))

    # Check aggregate stock availability per product ID
    for pid, total_qty in aggregated_qtys.items():
        if total_qty > 50:
            raise HTTPException(status_code=400, detail=f"Total quantity for product ID {pid} exceeds maximum limit of 50.")
        db_product = prod_map[pid]
        if int(db_product.get("stock", 0)) < total_qty:
            raise HTTPException(status_code=400, detail=f"Insufficient aggregate stock for {db_product['name']}.")

    # Build final items list and compute authoritative subtotal
    items = []
    subtotal = 0.0
    for pid, qty, size in validated_items_temp:
        db_product = prod_map[pid]
        items.append({
            "id": pid,
            "name": db_product["name"],
            "price": float(db_product["price"]),
            "image": normalize_image_path(db_product.get("image", "")),
            "qty": qty,
            "size": size,
        })
        subtotal += float(db_product["price"]) * qty

    # Customer validation
    customer = dict(order_data.get("customer") or {})
    customer_name = str(customer.get("name", "")).strip()
    if len(customer_name) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer name is required.")

    customer_email = validate_email(str(customer.get("email", "") or "guest@trident.local"))
    shipping_phone = str(customer.get("phone", "")).strip()
    if len(shipping_phone) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid phone number is required.")

    if request is not None:
        session_user = get_session_user(request)
        if session_user:
            customer["user_id"] = session_user["id"]

    customer["name"] = customer_name
    customer["email"] = customer_email
    customer["phone"] = shipping_phone

    # Shipping validation
    shipping = dict(order_data.get("shipping") or {})
    shipping_address = str(shipping.get("address", "")).strip()
    shipping_city = str(shipping.get("city", "")).strip()
    if len(shipping_address) < 6 or len(shipping_city) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Complete shipping details are required.")

    # Coupon validation (authoritative check without decrementing usage count)
    discount_amount = 0.0
    coupon_code = str(order_data.get("coupon_code", "") or "").strip().upper()
    fbt_token = order_data.get("fbt_token")
    offer_id = None
    if coupon_code:
        if coupon_code == "BUNDLE10":
            if not fbt_token:
                raise HTTPException(status_code=400, detail="BUNDLE10 coupon requires a valid FBT offer token.")
            try:
                fbt_qual = validate_fbt_bundle_qualification(fbt_token, items, prod_map)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            discount_amount = fbt_qual["discount_amount"]
            offer_id = fbt_qual["offer_id"]

        coupon_res = db.read("coupons", {"code": coupon_code})
        if not coupon_res:
            raise HTTPException(status_code=400, detail="Invalid coupon code.")
        coupon = coupon_res[0]

        is_active = coupon.get("is_active")
        if is_active is False or str(is_active).lower() == "false":
            raise HTTPException(status_code=400, detail="Coupon is disabled.")

        now_date = datetime.now(timezone.utc).date()
        try:
            expiry_str = str(coupon.get("expires_at") or coupon.get("expiry") or "2099-01-01").strip()
            expiry_date = datetime.fromisoformat(expiry_str).date()
        except Exception:
            expiry_date = now_date
        if expiry_date < now_date:
            raise HTTPException(status_code=400, detail="Coupon has expired.")

        usage_count = int(coupon.get("usage_count", 0))
        usage_limit = int(coupon.get("usage_limit", 9999))
        if usage_count >= usage_limit:
            raise HTTPException(status_code=400, detail="Coupon usage limit reached.")

        if coupon_code != "BUNDLE10":
            raw_pct = coupon.get("discount_pct") if coupon.get("discount_pct") is not None else coupon.get("discount")
            try:
                discount_pct = float(raw_pct if raw_pct is not None else 0.0)
            except (TypeError, ValueError):
                discount_pct = 0.0

            if math.isfinite(discount_pct) and (0.0 <= discount_pct <= 100.0):
                discount_amount = round(subtotal * discount_pct / 100, 2)
                discount_amount = min(discount_amount, subtotal)
            else:
                coupon_code = ""

    total = max(0.0, round(subtotal - discount_amount, 2))
    amount_paise = int(round(total * 100))

    order_id = f"TRD-{uuid.uuid4().hex[:8].upper()}"
    razorpay_order_id = str(order_data.get("razorpay_order_id") or f"order_{uuid.uuid4().hex[:14]}")

    reserved_coupon = None
    if coupon_code == "BUNDLE10" and offer_id:
        today_iso = datetime.now(timezone.utc).date().isoformat()
        try:
            reserved_coupon = db.reserve_coupon_offer(coupon_code, today_iso, order_id=order_id, offer_id=offer_id)
        except CouponConflictError as cce:
            raise HTTPException(status_code=400, detail=f"Coupon reservation conflict: {cce}")
        if not reserved_coupon:
            raise HTTPException(status_code=400, detail="Coupon offer could not be reserved.")

    pending_order = {
        "order_id": order_id,
        "razorpay_order_id": razorpay_order_id,
        "status": "initiated",
        "payment_method": "razorpay",
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "coupon_status": "reserved" if reserved_coupon else "none",
        "coupon_code": coupon_code or None,
        "fbt_offer_id": offer_id,
        "fbt_token": fbt_token if coupon_code == "BUNDLE10" else None,
        "items": items,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "total": total,
        "customer": customer,
        "shipping": shipping,
        "test_mode": bool(order_data.get("test_mode", False)),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    try:
        inserted = db.insert("orders", pending_order)
    except Exception as ins_err:
        if reserved_coupon and offer_id:
            try:
                db.release_coupon_offer(coupon_code, order_id=order_id, offer_id=offer_id)
            except Exception as rel_err:
                app_logger.error(f"[RESERVATION_RELEASE_FAILED] Order {order_id}: {rel_err}")
        raise
    return {
        "order": inserted,
        "order_id": order_id,
        "razorpay_order_id": razorpay_order_id,
        "amount_paise": amount_paise,
        "currency": "INR",
    }

def create_payment_order_record(order_data: Dict[str, Any]) -> Dict[str, Any]:
    if order_data.get("razorpay_order_id"):
        existing = db.read("orders", {"razorpay_order_id": order_data["razorpay_order_id"]})
        if existing:
            return existing[0]
    if order_data.get("razorpay_payment_id"):
        existing = db.read("orders", {"razorpay_payment_id": order_data["razorpay_payment_id"]})
        if existing:
            return existing[0]
    if order_data.get("idempotency_key"):
        existing = db.read("orders", {"idempotency_key": order_data["idempotency_key"]})
        if existing:
            return existing[0]

    # Generate or resolve canonical order_id upfront before any coupon redemption or compensation
    order_id = str(order_data.get("order_id") or "").strip() or f"TRD-{uuid.uuid4().hex[:8].upper()}"

    products = load_products()
    prod_map = {p["id"]: p for p in products}
    
    items = []
    subtotal = 0.0
    for item in order_data.get("items", []):
        pid = int(item.get("id") or item.get("product_id") or 0)
        qty = max(int(item.get("qty", 1)), 1)
        if pid not in prod_map:
            raise HTTPException(status_code=400, detail=f"Product with ID {pid} not found.")
        db_product = prod_map[pid]
        items.append({
            "id": pid,
            "name": db_product["name"],
            "price": db_product["price"],
            "image": normalize_image_path(db_product.get("image", "")),
            "qty": qty,
            "size": str(item.get("size", "")).strip().upper(),
        })
        subtotal += db_product["price"] * qty

    discount_amount = 0.0
    coupon_code = str(order_data.get("coupon_code", "") or "").strip().upper()
    fbt_token = order_data.get("fbt_token")
    offer_id = None
    redeemed_coupon = None
    newly_redeemed = False
    if coupon_code:
        today_iso = datetime.now(timezone.utc).date().isoformat()
        if coupon_code == "BUNDLE10":
            if not fbt_token:
                raise HTTPException(status_code=400, detail="BUNDLE10 coupon requires a valid FBT offer token.")
            try:
                fbt_qual = validate_fbt_bundle_qualification(fbt_token, items, prod_map)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            offer_id = fbt_qual["offer_id"]
            discount_amount = fbt_qual["discount_amount"]

        if offer_id is not None:
            redeemed_coupon = db.redeem_coupon(coupon_code, today_iso, order_id=order_id, offer_id=offer_id)
        else:
            redeemed_coupon = db.redeem_coupon(coupon_code, today_iso, order_id=order_id)

        if redeemed_coupon:
            newly_redeemed = not bool(redeemed_coupon.get("already_redeemed", False))
            if coupon_code != "BUNDLE10":
                raw_pct = redeemed_coupon.get("discount_pct") if redeemed_coupon.get("discount_pct") is not None else redeemed_coupon.get("discount")
                try:
                    discount_pct = float(raw_pct if raw_pct is not None else 0.0)
                except (TypeError, ValueError):
                    discount_pct = 0.0

                if math.isfinite(discount_pct) and (0.0 <= discount_pct <= 100.0):
                    discount_amount = round(subtotal * discount_pct / 100, 2)
                    discount_amount = min(discount_amount, subtotal)
                else:
                    if newly_redeemed:
                        (db.release_coupon(coupon_code, order_id=order_id, offer_id=offer_id) if offer_id is not None else db.release_coupon(coupon_code, order_id=order_id))
                    redeemed_coupon = None
                    discount_amount = 0.0

    total = max(0.0, round(subtotal - discount_amount, 2))

    new_order = {
        "order_id": order_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "payment_status": order_data.get("payment_status", "pending"),
        "stock_status": "pending",
        "email_status": "pending",
        "tracking_id": order_data.get("tracking_id"),
        "courier": order_data.get("courier"),
        "estimated_delivery": order_data.get("estimated_delivery"),
        "test_mode": bool(order_data.get("test_mode", False)),
        **order_data,
        "items": items,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "total": total,
        "coupon_status": "redeemed" if redeemed_coupon else "none",
        "fbt_offer_id": offer_id,
    }
    try:
        inserted = db.insert("orders", new_order)
        # If an idempotent insert returned an existing prior order, release the extra acquired coupon if newly redeemed
        if inserted and inserted.get("order_id") != order_id and newly_redeemed:
            try:
                (db.release_coupon(coupon_code, order_id=order_id, offer_id=offer_id) if offer_id is not None else db.release_coupon(coupon_code, order_id=order_id))
            except Exception:
                pass
    except Exception as e:
        if newly_redeemed:
            try:
                (db.release_coupon(coupon_code, order_id=order_id, offer_id=offer_id) if offer_id is not None else db.release_coupon(coupon_code, order_id=order_id))
            except Exception as rel_err:
                app_logger.error(f"[CRITICAL_COMPENSATION_FAILED] Failed to release coupon '{coupon_code}' after order insert error: {rel_err}")
        raise e

    if inserted and not inserted.get("test_mode") and inserted.get("order_id") == order_id:
        try:
            deduct_stock(items, order_id=inserted["order_id"])
            db.update("orders", {"id": inserted["id"]}, {"stock_status": "deducted"})
            inserted["stock_status"] = "deducted"
        except Exception as stock_err:
            app_logger.error(f"[STOCK_DEDUCTION_FAILED] Order {inserted.get('order_id')}: {stock_err}")
        
    try:
        if inserted and inserted.get("order_id") == order_id:
            send_order_email(inserted)
            db.update("orders", {"id": inserted["id"]}, {"email_status": "sent"})
            inserted["email_status"] = "sent"
    except Exception:
        pass
        
    return inserted
