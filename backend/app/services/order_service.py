import os
import json
import uuid
import smtplib
import ssl
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from fastapi import HTTPException, status, Request

from app.core.db_switch import db
from app.services.product_service import load_products, deduct_stock, normalize_image_path
from app.services.auth_service import get_session_user, validate_email

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

    # 2. Coupon Validation
    discount_amount = 0
    coupon_code = str(getattr(payload, "coupon_code", "") or "").strip().upper()
    if coupon_code:
        coupon_res = db.read("coupons", {"code": coupon_code})
        if not coupon_res:
            raise HTTPException(status_code=400, detail="Invalid coupon code.")
        coupon = coupon_res[0]
        
        # Check expiry
        now = datetime.now(timezone.utc).date()
        try:
            expiry_date = datetime.fromisoformat(coupon.get("expiry", "2099-01-01")).date()
        except Exception:
            expiry_date = now
        if expiry_date < now:
            raise HTTPException(status_code=400, detail="Coupon has expired.")
            
        usage_count = int(coupon.get("usage_count", 0))
        usage_limit = int(coupon.get("usage_limit", 9999))
        if usage_count >= usage_limit:
            raise HTTPException(status_code=400, detail="Coupon usage limit reached.")
            
        discount_pct = float(coupon.get("discount", 0))
        discount_amount = round(subtotal * discount_pct / 100, 2)
        
    total = round(subtotal - discount_amount, 2)
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

    order_id = f"TRD-{uuid.uuid4().hex[:8].upper()}"
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
        "total": total,
        "payment_method": getattr(payload, "payment_method", "cod"),
        "status": "placed",
        "payment_status": "cod_pending" if getattr(payload, "payment_method", "cod") == "cod" else "pending",
        "test_mode": bool(getattr(payload, "test_mode", False)),
        "created_at": now_iso(),
    }
    
    # 3. Atomically update coupon usage, save order, and deduct stock
    try:
        if coupon_code:
            db.update("coupons", {"code": coupon_code}, {"usage_count": int(coupon.get("usage_count", 0)) + 1})
            
        inserted = db.insert("orders", new_order)
        
        if not inserted.get("test_mode"):
            deduct_stock(items)
            
    except Exception as e:
        # Rollback coupon count on failure
        if coupon_code:
            db.update("coupons", {"code": coupon_code}, {"usage_count": int(coupon.get("usage_count", 0))})
        raise HTTPException(status_code=500, detail=f"Failed to place order: {e}")

    try:
        send_order_email(inserted)
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
        
    if order.get("status") in ("shipped", "delivered"):
        raise HTTPException(status_code=400, detail="Cannot cancel a shipped order.")
        
    db.update("orders", {"order_id": order_id}, {"status": "cancelled"})
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

def create_payment_order_record(order_data: Dict[str, Any]) -> Dict[str, Any]:
    if order_data.get("razorpay_order_id"):
        existing = db.read("orders", {"razorpay_order_id": order_data["razorpay_order_id"]})
        if existing:
            return existing[0]

    products = load_products()
    prod_map = {p["id"]: p for p in products}
    
    items = []
    subtotal = 0
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

    discount_amount = 0
    coupon_code = str(order_data.get("coupon_code", "") or "").strip().upper()
    if coupon_code:
        coupon_res = db.read("coupons", {"code": coupon_code})
        if coupon_res:
            coupon = coupon_res[0]
            discount_pct = float(coupon.get("discount", 0))
            discount_amount = round(subtotal * discount_pct / 100, 2)
            db.update("coupons", {"code": coupon_code}, {"usage_count": int(coupon.get("usage_count", 0)) + 1})

    total = round(subtotal - discount_amount, 2)

    order_id = f"TRD-{uuid.uuid4().hex[:8].upper()}"
    new_order = {
        "order_id": order_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "payment_status": order_data.get("payment_status", "pending"),
        "tracking_id": order_data.get("tracking_id"),
        "courier": order_data.get("courier"),
        "estimated_delivery": order_data.get("estimated_delivery"),
        "test_mode": bool(order_data.get("test_mode", False)),
        **order_data,
        "items": items,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "total": total,
    }
    inserted = db.insert("orders", new_order)
    if inserted and not inserted.get("test_mode"):
        deduct_stock(items)
        
    try:
        send_order_email(inserted)
    except Exception:
        pass
        
    return inserted
