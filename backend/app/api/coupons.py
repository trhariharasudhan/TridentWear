from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.db_switch import db

router = APIRouter(prefix="/api/v1", tags=["coupons"])

DEFAULT_COUPONS = [
    {"code": "TRIDENTFIRST", "discount": 20, "expiry": "2027-12-31", "usage_limit": 1000, "usage_count": 0},
    {"code": "TRIDENT10", "discount": 10, "expiry": "2027-12-31", "usage_limit": 5000, "usage_count": 0},
]

def round_currency(value: float) -> float:
    return round(value, 2)

class ApplyCouponPayload(BaseModel):
    code: str
    subtotal: float

@router.post("/coupons/apply")
def apply_coupon(payload: ApplyCouponPayload) -> Dict[str, Any]:
    code = payload.code.strip().upper()
    subtotal = float(payload.subtotal)

    if subtotal <= 0 or subtotal > 1_000_000:
        raise HTTPException(status_code=400, detail="Invalid order subtotal.")

    res = db.read("coupons", {"code": code})
    if not res:
        # Seed default coupons if DB is empty
        all_coupons = db.read("coupons", {})
        if not all_coupons:
            for c in DEFAULT_COUPONS:
                db.insert("coupons", c)
            res = db.read("coupons", {"code": code})

    if not res:
        raise HTTPException(status_code=404, detail="Invalid coupon code.")

    coupon = res[0]
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
    discount_amount = round_currency(subtotal * discount_pct / 100)

    # Note: Usage count is incremented in order_service during checkout, not on apply.
    return {
        "success": True,
        "code": coupon["code"],
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "final_total": round_currency(subtotal - discount_amount),
    }
