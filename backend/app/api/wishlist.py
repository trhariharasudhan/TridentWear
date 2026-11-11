from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone

from app.services.auth_service import get_session_user
from app.core.db_switch import get_db

router = APIRouter(prefix="/api/v1/wishlist", tags=["wishlist"])


class WishlistPayload(BaseModel):
    product_id: int


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_products_map() -> Dict[int, Dict[str, Any]]:
    from app.services.product_service import load_products
    return {p["id"]: p for p in load_products()}


@router.get("")
@router.get("/")
def get_user_wishlist(request: Request) -> List[Dict[str, Any]]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to view your wishlist.")
    db = get_db()
    user_items = db.read("wishlist", {"user_id": user["id"]})
    products = load_products_map()
    enriched = []
    for w in user_items:
        if w["product_id"] in products:
            enriched.append({
                "id": w["id"],
                "product_id": w["product_id"],
                "product": products[w["product_id"]]
            })
    return enriched


@router.post("/add")
def add_to_wishlist(payload: WishlistPayload, request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to manage your wishlist.")
    db = get_db()
    existing = db.read("wishlist", {"user_id": user["id"], "product_id": payload.product_id})
    if existing:
        return {"success": True, "message": "Already in wishlist"}
    products = load_products_map()
    if payload.product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found.")

    db.insert("wishlist", {
        "user_id": user["id"],
        "product_id": payload.product_id,
        "created_at": now_iso(),
    })
    return {"success": True, "message": "Added to wishlist."}


@router.delete("/remove")
@router.post("/remove")
def remove_from_wishlist(payload: WishlistPayload, request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to manage your wishlist.")
    db = get_db()
    existing = db.read("wishlist", {"user_id": user["id"], "product_id": payload.product_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Item not in wishlist.")
    db.delete("wishlist", {"user_id": user["id"], "product_id": payload.product_id})
    return {"success": True, "message": "Removed from wishlist."}
