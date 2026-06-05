from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime, timezone

from app.db.json_manager import read_json, write_json

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DB_DIR = BASE_DIR / "db"
COUPONS_PATH = str(DB_DIR / "coupons.json")

router = APIRouter(prefix="/api/v1", tags=["coupons"])


DEFAULT_COUPONS = [
    {"code": "TRIDENTFIRST", "discount": 20, "expiry": "2027-12-31", "usage_limit": 1000, "usage_count": 0},
    {"code": "TRIDENT10", "discount": 10, "expiry": "2027-12-31", "usage_limit": 5000, "usage_count": 0},
]


def load_coupons():
    data = read_json(COUPONS_PATH)
    if not data:
        write_json(COUPONS_PATH, DEFAULT_COUPONS)
        return DEFAULT_COUPONS
    return data


def round_currency(value: float) -> float:
    return round(value, 2)


class ApplyCouponPayload(BaseModel):
    code: str
    subtotal: float


@router.post("/coupons/apply")
def apply_coupon(payload: ApplyCouponPayload) -> Dict[str, Any]:
    coupons = load_coupons()
    code = payload.code.strip().upper()
    subtotal = float(payload.subtotal)
    now = datetime.now(timezone.utc).date()

    for coupon in coupons:
        if coupon.get("code", "").upper() == code:
            # Check expiry
            try:
                expiry_date = datetime.fromisoformat(coupon.get("expiry", "2099-01-01")).date()
            except Exception:
                expiry_date = now
            if expiry_date < now:
                raise HTTPException(status_code=400, detail="Coupon has expired.")
            if coupon.get("usage_count", 0) >= coupon.get("usage_limit", 9999):
                raise HTTPException(status_code=400, detail="Coupon usage limit reached.")

            discount_pct = float(coupon.get("discount", 0))
            discount_amount = round_currency(subtotal * discount_pct / 100)
            return {
                "success": True,
                "code": coupon["code"],
                "discount_pct": discount_pct,
                "discount_amount": discount_amount,
                "final_total": round_currency(subtotal - discount_amount),
            }

    raise HTTPException(status_code=404, detail="Invalid coupon code.")
