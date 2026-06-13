from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, Request, status

from app.core.db_switch import db
from app.services.auth_service import get_session_user
from app.services.product_service import load_products


def _load_reviews() -> List[Dict[str, Any]]:
    return db.read("reviews", {})


def _product_exists(product_id: int) -> bool:
    return any(int(product.get("id", 0)) == int(product_id) for product in load_products())


def get_product_reviews(product_id: int) -> Dict[str, Any]:
    all_reviews = db.read("reviews", {"product_id": product_id})
    reviews = [
        review for review in all_reviews
        if review.get("status", "approved") == "approved"
    ]
    counts = {star: 0 for star in range(1, 6)}
    for review in reviews:
        rating = int(review.get("rating", 0))
        if rating in counts:
            counts[rating] += 1
    average = round(sum(int(r.get("rating", 0)) for r in reviews) / len(reviews), 1) if reviews else 0
    return {
        "product_id": product_id,
        "count": len(reviews),
        "average": average,
        "bars": counts,
        "reviews": sorted(reviews, key=lambda item: item.get("created_at", ""), reverse=True),
    }


def create_product_review(payload: Any, request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in to review.")
    product_id = int(payload.product_id)
    rating = int(payload.rating)
    review_text = str(payload.review or "").strip()
    if not _product_exists(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rating must be between 1 and 5.")
    if len(review_text) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review must be at least 8 characters.")

    existing_reviews = db.read("reviews", {"user_id": user["id"], "product_id": product_id})
    if existing_reviews:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already reviewed this product.")

    created = {
        "product_id": product_id,
        "user_id": user["id"],
        "user_name": user.get("name", "Trident member"),
        "rating": rating,
        "review": review_text,
        "verified_purchase": False,
        "status": "pending_moderation",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    inserted = db.insert("reviews", created)
    return {"success": True, "message": "Review submitted for moderation.", "review": inserted}


def get_admin_reviews(status_filter: Optional[str] = None) -> Dict[str, Any]:
    reviews = _load_reviews()
    if status_filter:
        normalized = normalize_review_status(status_filter)
        reviews = [review for review in reviews if normalize_review_status(review.get("status", "pending")) == normalized]

    counts = {"pending": 0, "approved": 0, "rejected": 0}
    for review in _load_reviews():
        status_value = normalize_review_status(review.get("status", "pending"))
        if status_value in counts:
            counts[status_value] += 1

    return {
        "success": True,
        "counts": counts,
        "reviews": sorted(reviews, key=lambda item: item.get("created_at", ""), reverse=True),
    }


def normalize_review_status(value: Any) -> str:
    status_value = str(value or "pending").strip().lower().replace("_moderation", "")
    if status_value in {"pending", "approved", "rejected"}:
        return status_value
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review status must be pending, approved, or rejected.")


def moderate_review(review_id: int, status_value: str, notes: Optional[str], admin: Dict[str, Any]) -> Dict[str, Any]:
    normalized_status = normalize_review_status(status_value)
    
    res = db.read("reviews", {"id": review_id})
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")
        
    updates = {
        "status": normalized_status,
        "moderation_notes": str(notes or "").strip(),
        "moderated_by": admin.get("id"),
        "moderated_at": datetime.now(timezone.utc).isoformat()
    }
    updated = db.update("reviews", {"id": review_id}, updates)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")
    return {"success": True, "message": f"Review {normalized_status}.", "review": updated[0]}


def delete_review(review_id: int) -> Dict[str, Any]:
    count = db.delete("reviews", {"id": review_id})
    if count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")
    return {"success": True, "message": "Review deleted."}
