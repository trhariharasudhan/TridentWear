from typing import Any, Dict, List
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from app.services.auth_service import get_session_user
from app.db.json_manager import read_json, write_json, update_json
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DB_DIR = BASE_DIR / "db"
WISHLIST_PATH = str(DB_DIR / "wishlist.json")

router = APIRouter(prefix="/api/v1/wishlist", tags=["wishlist"])


class WishlistPayload(BaseModel):
    product_id: int


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_wishlist() -> List[Dict[str, Any]]:
    data = read_json(WISHLIST_PATH)
    return data if isinstance(data, list) else []


def next_id(items: List[Dict[str, Any]]) -> int:
    if not items:
        return 1
    return max(int(item.get("id", 0)) for item in items) + 1


def load_products_map() -> Dict[int, Dict[str, Any]]:
    from app.services.product_service import load_products
    return {p["id"]: p for p in load_products()}


@router.get("")
@router.get("/")
def get_user_wishlist(request: Request) -> List[Dict[str, Any]]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to view your wishlist.")
    wishlists = load_wishlist()
    user_items = [w for w in wishlists if w.get("user_id") == user["id"]]
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
    wishlists = load_wishlist()
    if any(w.get("user_id") == user["id"] and w.get("product_id") == payload.product_id for w in wishlists):
        return {"success": True, "message": "Already in wishlist"}
    products = load_products_map()
    if payload.product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found.")

    def _add(items: list):
        items = items if isinstance(items, list) else []
        items.append({
            "id": next_id(items),
            "user_id": user["id"],
            "product_id": payload.product_id,
            "created_at": now_iso(),
        })
        return items

    update_json(WISHLIST_PATH, _add)
    return {"success": True, "message": "Added to wishlist."}


@router.delete("/remove")
@router.post("/remove")
def remove_from_wishlist(payload: WishlistPayload, request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to manage your wishlist.")
    wishlists = load_wishlist()
    initial_len = len(wishlists)
    remaining = [
        w for w in wishlists
        if not (w.get("user_id") == user["id"] and w.get("product_id") == payload.product_id)
    ]
    if len(remaining) == initial_len:
        raise HTTPException(status_code=404, detail="Item not in wishlist.")
    write_json(WISHLIST_PATH, remaining)
    return {"success": True, "message": "Removed from wishlist."}
