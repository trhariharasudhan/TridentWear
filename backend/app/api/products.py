from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, Optional

from app.services.product_service import get_all_products, get_single_product, load_products
from app.services.fbt_service import issue_fbt_offer

router = APIRouter(prefix="/api/v1/products", tags=["products"])

@router.get("")
def get_products(category: Optional[str] = None, featured: Optional[bool] = None) -> Dict[str, Any]:
    return get_all_products(category, featured)

@router.get("/{product_id}/fbt-offer")
def get_product_fbt_offer(product_id: int) -> Dict[str, Any]:
    all_prods = load_products()
    if not any(int(p.get("id", 0)) == product_id for p in all_prods):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    try:
        offer = issue_fbt_offer(product_id, all_prods)
        return {"success": True, "offer": offer}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/{product_id}")
def get_product(product_id: int) -> Dict[str, Any]:
    return get_single_product(product_id)
