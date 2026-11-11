from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.review_service import create_product_review, get_product_reviews


router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


class ReviewPayload(BaseModel):
    product_id: int
    rating: int
    review: str
    images: Optional[List[str]] = None


@router.get("/{product_id}")
def product_reviews(product_id: int) -> Dict[str, Any]:
    return get_product_reviews(product_id)


@router.post("")
def add_review(payload: ReviewPayload, request: Request) -> Dict[str, Any]:
    return create_product_review(payload, request)
