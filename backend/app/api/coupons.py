from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.db_switch import db
from app.services.auth_service import require_admin

router = APIRouter(prefix="/api/v1", tags=["coupons"])

DEFAULT_COUPONS = [
    {"code": "TRIDENTFIRST", "discount_pct": 20.0, "expires_at": "2027-12-31", "usage_limit": 1000, "usage_count": 0, "is_active": True},
    {"code": "TRIDENT10", "discount_pct": 10.0, "expires_at": "2027-12-31", "usage_limit": 5000, "usage_count": 0, "is_active": True},
]

def round_currency(value: float) -> float:
    return round(value, 2)

class ApplyCouponPayload(BaseModel):
    code: str
    subtotal: float

class CouponCreatePayload(BaseModel):
    code: str
    discount_pct: float
    expires_at: str
    usage_limit: int = 1000
    is_active: bool = True

class CouponUpdatePayload(BaseModel):
    discount_pct: Optional[float] = None
    expires_at: Optional[str] = None
    usage_limit: Optional[int] = None
    is_active: Optional[bool] = None

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
    
    # Check is_active (default True if missing)
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

    discount_pct = float(coupon.get("discount_pct") if coupon.get("discount_pct") is not None else coupon.get("discount", 0))
    discount_amount = round_currency(subtotal * discount_pct / 100)

    # Note: Usage count is incremented in order_service during checkout, not on apply.
    return {
        "success": True,
        "code": coupon["code"],
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "final_total": round_currency(subtotal - discount_amount),
    }

# ─── ADMIN CRUD ENDPOINTS ───────────────────────────────────────

@router.get("/admin/coupons")
def list_coupons(_: Dict[str, Any] = Depends(require_admin)) -> List[Dict[str, Any]]:
    # Seed default coupons if DB is empty
    all_coupons = db.read("coupons", {})
    if not all_coupons:
        for c in DEFAULT_COUPONS:
            db.insert("coupons", c)
        all_coupons = db.read("coupons", {})
        
    normalized = []
    for c in all_coupons:
        normalized.append({
            "id": c.get("id"),
            "code": c["code"],
            "discount_pct": float(c.get("discount_pct") if c.get("discount_pct") is not None else c.get("discount", 0)),
            "expires_at": c.get("expires_at") or c.get("expiry") or "2099-01-01",
            "usage_limit": int(c.get("usage_limit", 1000)),
            "usage_count": int(c.get("usage_count", 0)),
            "is_active": c.get("is_active") if c.get("is_active") is not None else True,
        })
    return normalized

@router.post("/admin/coupons")
def create_coupon(payload: CouponCreatePayload, _: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    code = payload.code.strip().upper()
    existing = db.read("coupons", {"code": code})
    if existing:
        raise HTTPException(status_code=400, detail="Coupon code already exists.")
        
    coupon_data = {
        "code": code,
        "discount_pct": float(payload.discount_pct),
        "expires_at": payload.expires_at,
        "usage_limit": int(payload.usage_limit),
        "usage_count": 0,
        "is_active": bool(payload.is_active),
        # Fallback fields for backward compatibility
        "discount": float(payload.discount_pct),
        "expiry": payload.expires_at,
    }
    
    inserted = db.insert("coupons", coupon_data)
    return {"success": True, "coupon": inserted}

@router.put("/admin/coupons/{code}")
def update_coupon(code: str, payload: CouponUpdatePayload, _: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    code = code.strip().upper()
    existing = db.read("coupons", {"code": code})
    if not existing:
        raise HTTPException(status_code=404, detail="Coupon not found.")
        
    coupon = existing[0]
    update_data = {}
    if payload.discount_pct is not None:
        update_data["discount_pct"] = float(payload.discount_pct)
        update_data["discount"] = float(payload.discount_pct)
    if payload.expires_at is not None:
        update_data["expires_at"] = payload.expires_at
        update_data["expiry"] = payload.expires_at
    if payload.usage_limit is not None:
        update_data["usage_limit"] = int(payload.usage_limit)
    if payload.is_active is not None:
        update_data["is_active"] = bool(payload.is_active)
        
    updated = db.update("coupons", {"code": code}, update_data)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update coupon.")
    return {"success": True, "coupon": updated[0]}

@router.delete("/admin/coupons/{code}")
def delete_coupon(code: str, _: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    code = code.strip().upper()
    deleted = db.delete("coupons", {"code": code})
    if not deleted:
        raise HTTPException(status_code=404, detail="Coupon not found.")
    return {"success": True}
