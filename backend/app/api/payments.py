from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from app.services.payment_service import process_cod_order, process_razorpay_create, process_razorpay_verify

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

class CODPayload(BaseModel):
    items: List[Dict[str, Any]]
    subtotal: float
    customer: Dict[str, Any]
    shipping: Dict[str, Any]
    coupon_code: Optional[str] = None
    discount_amount: float = 0
    test_mode: bool = False

class RazorpayCreatePayload(BaseModel):
    amount: int
    currency: str = "INR"

class RazorpayVerifyPayload(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    order_data: Dict[str, Any]

@router.post("/cod")
def place_cod_order(payload: CODPayload, request: Request) -> Dict[str, Any]:
    return process_cod_order(
        subtotal=payload.subtotal,
        customer=payload.customer,
        shipping=payload.shipping,
        items=payload.items,
        coupon_code=payload.coupon_code,
        test_mode=payload.test_mode,
        request=request,
    )

@router.post("/create-order")
def create_razorpay_order(payload: RazorpayCreatePayload) -> Dict[str, Any]:
    return process_razorpay_create(amount=payload.amount, currency=payload.currency)

@router.post("/verify")
def verify_razorpay_payment(payload: RazorpayVerifyPayload, request: Request) -> Dict[str, Any]:
    return process_razorpay_verify(
        razorpay_order_id=payload.razorpay_order_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        razorpay_signature=payload.razorpay_signature,
        order_data_payload=payload.order_data,
        request=request,
    )
