from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.core.db_switch import db
from app.services.auth_service import require_admin, serialize_user, find_user_by_id, update_user
from app.services.product_service import process_create_product, process_update_product, process_delete_product
from app.services.order_service import get_all_orders_data, update_order_status_logic
from app.services.admin_service import get_analytics_data
from app.services.review_service import delete_review, get_admin_reviews, moderate_review
from app.services.audit_service import log_action

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
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    res = await process_create_product(
        name, category, price, description, tag, sizes, stock, featured, image,
        fabric, gsm, fit_type, neck_type, print_method, wash_care_label,
    )
    if res.get("success") and "product" in res:
        log_action(
            admin_id=admin.get("id"),
            action_type="product_create",
            target_entity="products",
            target_id=res["product"].get("id"),
            before_state=None,
            after_state=res["product"],
            request=request
        )
    return res

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
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    from app.services.product_service import get_single_product
    before_product = None
    try:
        before_res = get_single_product(product_id)
        if before_res.get("success"):
            before_product = before_res.get("product")
    except Exception:
        pass

    res = await process_update_product(
        product_id, name, category, price, description, tag, sizes, stock, featured, image,
        fabric, gsm, fit_type, neck_type, print_method, wash_care_label,
    )
    if res.get("success") and "product" in res:
        log_action(
            admin_id=admin.get("id"),
            action_type="product_update",
            target_entity="products",
            target_id=product_id,
            before_state=before_product,
            after_state=res["product"],
            request=request
        )
    return res

@router.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin)
) -> Dict[str, Any]:
    from app.services.product_service import get_single_product
    before_product = None
    try:
        before_res = get_single_product(product_id)
        if before_res.get("success"):
            before_product = before_res.get("product")
    except Exception:
        pass

    res = process_delete_product(product_id)
    if res.get("success"):
        log_action(
            admin_id=admin.get("id"),
            action_type="product_delete",
            target_entity="products",
            target_id=product_id,
            before_state=before_product,
            after_state=None,
            request=request
        )
    return res

@router.get("/orders")
def get_all_orders(_: Dict[str, Any] = Depends(require_admin)) -> List[Dict[str, Any]]:
    return get_all_orders_data()

@router.put("/orders/{order_id}")
def update_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin)
) -> Dict[str, Any]:
    before_order = None
    res_db = db.read("orders", {"order_id": order_id})
    if res_db:
        before_order = res_db[0]

    res = update_order_status_logic(order_id, payload.model_dump(exclude_none=True))
    if res.get("success"):
        after_order = None
        after_db = db.read("orders", {"order_id": order_id})
        if after_db:
            after_order = after_db[0]
        log_action(
            admin_id=admin.get("id"),
            action_type="order_status_update",
            target_entity="orders",
            target_id=order_id,
            before_state=before_order,
            after_state=after_order,
            request=request
        )
    return res

@router.get("/reviews")
def list_reviews(status: Optional[str] = None, _: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return get_admin_reviews(status)

@router.put("/reviews/{review_id}")
def update_review(
    review_id: int,
    payload: ReviewModerationUpdate,
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin)
) -> Dict[str, Any]:
    before_review = None
    res_db = db.read("reviews", {"id": review_id})
    if res_db:
        before_review = res_db[0]

    res = moderate_review(review_id, payload.status, payload.moderation_notes, admin)
    if res.get("success"):
        after_review = None
        after_db = db.read("reviews", {"id": review_id})
        if after_db:
            after_review = after_db[0]
        log_action(
            admin_id=admin.get("id"),
            action_type="review_moderation",
            target_entity="reviews",
            target_id=review_id,
            before_state=before_review,
            after_state=after_review,
            request=request
        )
    return res

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
def update_user_status(
    id: int,
    payload: UserStatusUpdate,
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin)
) -> Dict[str, Any]:
    if admin.get("id") == id:
        raise HTTPException(status_code=400, detail="Admins cannot block themselves.")
    user = find_user_by_id(id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    before_user = serialize_user(user)
    updated = update_user(id, {"is_active": payload.is_active})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update user status.")
    log_action(
        admin_id=admin.get("id"),
        action_type="user_status_update",
        target_entity="users",
        target_id=id,
        before_state=before_user,
        after_state=serialize_user(updated),
        request=request
    )
    return {"success": True, "user": serialize_user(updated)}

@router.put("/users/{id}/role")
def update_user_role(
    id: int,
    payload: UserRoleUpdate,
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin)
) -> Dict[str, Any]:
    if payload.role not in ["admin", "customer"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'customer'.")
    if admin.get("id") == id and payload.role != "admin":
        raise HTTPException(status_code=400, detail="Admins cannot remove their own admin role.")
    user = find_user_by_id(id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    before_user = serialize_user(user)
    updated = update_user(id, {"role": payload.role})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update user role.")
    log_action(
        admin_id=admin.get("id"),
        action_type="user_role_change",
        target_entity="users",
        target_id=id,
        before_state=before_user,
        after_state=serialize_user(updated),
        request=request
    )
    return {"success": True, "user": serialize_user(updated)}

@router.get("/users/{id}/orders")
def get_user_orders(id: int, _: Dict[str, Any] = Depends(require_admin)) -> List[Dict[str, Any]]:
    user_orders = db.read("orders", {"user_id": id})
    return user_orders
