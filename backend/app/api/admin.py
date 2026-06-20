from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.core.db_switch import db
from app.services.auth_service import require_admin, serialize_user, find_user_by_id, update_user
from app.services.product_service import process_create_product, process_update_product, process_delete_product
from app.services.order_service import get_all_orders_data, update_order_status_logic
from app.services.admin_service import get_analytics_data
from app.services.review_service import delete_review, get_admin_reviews, moderate_review

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

class OrderStatusUpdate(BaseModel):
    status: str
    payment_status: Optional[str] = None
    tracking_id: Optional[str] = None
    courier: Optional[str] = None
    estimated_delivery: Optional[str] = None
    shipment_notes: Optional[str] = None

class ReviewModerationUpdate(BaseModel):
    status: str
    moderation_notes: Optional[str] = None

@router.post("/products")
async def create_product(
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    price: str = Form(...),
    description: str = Form(""),
    tag: str = Form(""),
    sizes: str = Form("S, M, L, XL"),
    stock: str = Form("0"),
    featured: str = Form("false"),
    fabric: str = Form("100% Cotton"),
    gsm: str = Form("150"),
    fit_type: str = Form("Unisex"),
    neck_type: str = Form("Round Neck"),
    print_method: str = Form("DTG, Embroidery"),
    wash_care_label: str = Form("true"),
    image: Optional[UploadFile] = File(None),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    return await process_create_product(
        name, category, price, description, tag, sizes, stock, featured, image,
        fabric, gsm, fit_type, neck_type, print_method, wash_care_label,
    )

@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    price: str = Form(...),
    description: str = Form(""),
    tag: str = Form(""),
    sizes: str = Form("S, M, L, XL"),
    stock: str = Form("0"),
    featured: str = Form("false"),
    fabric: str = Form("100% Cotton"),
    gsm: str = Form("150"),
    fit_type: str = Form("Unisex"),
    neck_type: str = Form("Round Neck"),
    print_method: str = Form("DTG, Embroidery"),
    wash_care_label: str = Form("true"),
    image: Optional[UploadFile] = File(None),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    return await process_update_product(
        product_id, name, category, price, description, tag, sizes, stock, featured, image,
        fabric, gsm, fit_type, neck_type, print_method, wash_care_label,
    )

@router.delete("/products/{product_id}")
def delete_product(product_id: int, _: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return process_delete_product(product_id)

@router.get("/orders")
def get_all_orders(_: Dict[str, Any] = Depends(require_admin)) -> List[Dict[str, Any]]:
    return get_all_orders_data()

@router.put("/orders/{order_id}")
def update_order_status(order_id: str, payload: OrderStatusUpdate, _: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return update_order_status_logic(order_id, payload.model_dump(exclude_none=True))

@router.get("/reviews")
def list_reviews(status: Optional[str] = None, _: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return get_admin_reviews(status)

@router.put("/reviews/{review_id}")
def update_review(review_id: int, payload: ReviewModerationUpdate, admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return moderate_review(review_id, payload.status, payload.moderation_notes, admin)

@router.delete("/reviews/{review_id}")
def remove_review(review_id: int, _: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return delete_review(review_id)

@router.get("/analytics")
def get_analytics(_: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return get_analytics_data()

class UserStatusUpdate(BaseModel):
    is_active: bool

class UserRoleUpdate(BaseModel):
    role: str

@router.get("/users")
def list_users(admin: Dict[str, Any] = Depends(require_admin)) -> List[Dict[str, Any]]:
    all_users = db.read("users", {})
    return [serialize_user(u) for u in all_users]

@router.put("/users/{id}/status")
def update_user_status(id: int, payload: UserStatusUpdate, admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    if admin.get("id") == id:
        raise HTTPException(status_code=400, detail="Admins cannot block themselves.")
    user = find_user_by_id(id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    updated = update_user(id, {"is_active": payload.is_active})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update user status.")
    return {"success": True, "user": serialize_user(updated)}

@router.put("/users/{id}/role")
def update_user_role(id: int, payload: UserRoleUpdate, admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    if payload.role not in ["admin", "customer"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'customer'.")
    if admin.get("id") == id and payload.role != "admin":
        raise HTTPException(status_code=400, detail="Admins cannot remove their own admin role.")
    user = find_user_by_id(id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    updated = update_user(id, {"role": payload.role})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update user role.")
    return {"success": True, "user": serialize_user(updated)}

@router.get("/users/{id}/orders")
def get_user_orders(id: int, _: Dict[str, Any] = Depends(require_admin)) -> List[Dict[str, Any]]:
    user_orders = db.read("orders", {"user_id": id})
    return user_orders
