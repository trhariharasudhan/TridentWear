"""
TridentWear — Frequently Bought Together (FBT) Offer & Qualification Service

Provides cryptographically signed stateless offer tokens and authoritative
server-side bundle qualification for the BUNDLE10 promotion.
"""

import time
import secrets
import logging
from typing import Any, Dict, List, Optional, Set
import jwt

from app.core.config import get_fbt_secret, FBT_OFFER_EXPIRATION_HOURS

log = logging.getLogger(__name__)

FBT_ISSUER = "tridentwear-backend"
FBT_AUDIENCE = "tridentwear-storefront"
FBT_TOKEN_TYPE = "fbt_offer"
FBT_VERSION = 1
DEFAULT_MIN_DISTINCT_PRODUCTS = 2
DEFAULT_BUNDLE_DISCOUNT_PCT = 10.0


def issue_fbt_offer(
    primary_product_id: int,
    all_products: List[Dict[str, Any]],
    expiration_hours: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Issues a cryptographically signed FBT offer token for a given primary product.
    Selects up to 2 other products from the catalog as suggested bundle items.
    """
    primary_pid = int(primary_product_id)
    primary_prod = next((p for p in all_products if int(p.get("id", 0)) == primary_pid), None)
    if not primary_prod:
        raise ValueError(f"Primary product {primary_pid} not found in catalog")

    # Select up to 2 distinct suggested products excluding the primary and having available stock
    seen_pids = {primary_pid}
    suggestions = []
    for p in all_products:
        pid = int(p.get("id", 0))
        if pid not in seen_pids and int(p.get("stock", 0)) > 0:
            seen_pids.add(pid)
            suggestions.append(p)
            if len(suggestions) >= 2:
                break
    if not suggestions:
        raise ValueError("Insufficient products available to form an FBT bundle offer")

    suggested_pids = [int(p["id"]) for p in suggestions]
    qualifying_pids = sorted([primary_pid] + suggested_pids)

    now_ts = int(time.time())
    ttl_hours = expiration_hours if expiration_hours is not None else FBT_OFFER_EXPIRATION_HOURS
    exp_ts = now_ts + (ttl_hours * 3600)
    offer_id = secrets.token_hex(16)

    payload = {
        "iss": FBT_ISSUER,
        "aud": FBT_AUDIENCE,
        "typ": FBT_TOKEN_TYPE,
        "v": FBT_VERSION,
        "offer_id": offer_id,
        "primary_product_id": primary_pid,
        "suggested_product_ids": suggested_pids,
        "qualifying_product_ids": qualifying_pids,
        "min_distinct_count": DEFAULT_MIN_DISTINCT_PRODUCTS,
        "discount_pct": DEFAULT_BUNDLE_DISCOUNT_PCT,
        "iat": now_ts,
        "exp": exp_ts,
    }

    token = jwt.encode(payload, get_fbt_secret(), algorithm="HS256")

    return {
        "offer_id": offer_id,
        "primary_product_id": primary_pid,
        "suggested_product_ids": suggested_pids,
        "qualifying_product_ids": qualifying_pids,
        "min_distinct_count": DEFAULT_MIN_DISTINCT_PRODUCTS,
        "discount_pct": DEFAULT_BUNDLE_DISCOUNT_PCT,
        "expires_at": exp_ts,
        "token": token,
    }


def verify_fbt_token(token: str) -> Dict[str, Any]:
    """
    Verifies the cryptographic signature, expiration, and required claims of an FBT offer token.
    Raises ValueError on any tampering or invalid claim.
    """
    if not token or not isinstance(token, str):
        raise ValueError("FBT token must be a non-empty string")

    try:
        payload = jwt.decode(
            token.strip(),
            get_fbt_secret(),
            algorithms=["HS256"],
            audience=FBT_AUDIENCE,
            issuer=FBT_ISSUER,
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("FBT offer token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid FBT offer token signature or format: {e}")

    if payload.get("typ") != FBT_TOKEN_TYPE:
        raise ValueError(f"Invalid token type: expected '{FBT_TOKEN_TYPE}', got '{payload.get('typ')}'")

    offer_id = payload.get("offer_id")
    if not offer_id or not isinstance(offer_id, str) or len(offer_id.strip()) < 16:
        raise ValueError("Token missing or has invalid offer_id claim")

    qualifying_pids = payload.get("qualifying_product_ids")
    if not isinstance(qualifying_pids, list) or len(qualifying_pids) < 2:
        raise ValueError("Token missing or has invalid qualifying_product_ids claim")

    min_distinct = payload.get("min_distinct_count", DEFAULT_MIN_DISTINCT_PRODUCTS)
    if not isinstance(min_distinct, int) or min_distinct < 2:
        raise ValueError("Invalid min_distinct_count claim in token")

    discount_pct = payload.get("discount_pct", DEFAULT_BUNDLE_DISCOUNT_PCT)
    if not isinstance(discount_pct, (int, float)) or discount_pct <= 0:
        raise ValueError("Invalid discount_pct claim in token")

    return payload


def validate_fbt_bundle_qualification(
    fbt_token: str,
    items: List[Dict[str, Any]],
    product_map: Dict[int, Any],
) -> Dict[str, Any]:
    """
    Validates that the provided cart/order items satisfy the BUNDLE10 qualification rules:
    1. The FBT token is authentic, non-expired, and valid.
    2. The submitted items contain at least min_distinct_count (default 2) distinct product IDs
       belonging to the token's qualifying_product_ids.
       Multiple quantities or sizes of one product count as ONE distinct product.
    3. The discount amount is calculated ONLY from authoritative product prices of qualifying items.
       Unrelated cart items are strictly excluded from the discount calculation.

    Returns qualification details including:
      - is_qualified: True
      - offer_id: str
      - qualifying_product_ids: List[int]
      - qualifying_subtotal: float
      - discount_amount: float
      - discount_pct: float
    """
    claims = verify_fbt_token(fbt_token)
    offer_id = claims["offer_id"]
    qualifying_pids_set = set(int(pid) for pid in claims["qualifying_product_ids"])
    min_distinct = int(claims.get("min_distinct_count", DEFAULT_MIN_DISTINCT_PRODUCTS))
    discount_pct = float(claims.get("discount_pct", DEFAULT_BUNDLE_DISCOUNT_PCT))

    if not items or not isinstance(items, list):
        raise ValueError("Cart items must be a non-empty list for BUNDLE10 validation")

    distinct_qualifying_pids: Set[int] = set()
    qualifying_line_items: List[Dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid item format in bundle qualification: item must be a dictionary")
        raw_id = item.get("product_id") if item.get("product_id") is not None else item.get("id")
        if raw_id is None:
            raise ValueError("Invalid item format in bundle qualification: missing product id")
        try:
            pid = int(raw_id)
        except (ValueError, TypeError):
            raise ValueError("Invalid item format in bundle qualification: invalid product id")

        if pid in qualifying_pids_set:
            distinct_qualifying_pids.add(pid)
            try:
                qty = int(item.get("quantity") if item.get("quantity") is not None else item.get("qty", 1))
            except (ValueError, TypeError):
                raise ValueError("Invalid item format in bundle qualification: invalid quantity")
            if qty > 0:
                qualifying_line_items.append({"product_id": pid, "quantity": qty})

    if len(distinct_qualifying_pids) < min_distinct:
        raise ValueError(
            f"BUNDLE10 requires at least {min_distinct} distinct products from the FBT offer in cart (found {len(distinct_qualifying_pids)})"
        )

    # Compute qualifying subtotal using authoritative catalog prices ONLY
    qualifying_subtotal = 0.0
    for item in qualifying_line_items:
        pid = item["product_id"]
        qty = item["quantity"]
        prod = product_map.get(pid)
        if prod is None:
            raise ValueError(f"Product ID {pid} in bundle offer not found in catalog")
        
        if isinstance(prod, dict):
            price = float(prod.get("price", 0.0))
        else:
            price = float(getattr(prod, "price", 0.0))
            
        qualifying_subtotal += price * qty

    qualifying_subtotal = round(qualifying_subtotal, 2)
    discount_amount = round(qualifying_subtotal * (discount_pct / 100.0), 2)

    return {
        "is_qualified": True,
        "offer_id": offer_id,
        "qualifying_product_ids": sorted(list(distinct_qualifying_pids)),
        "qualifying_subtotal": qualifying_subtotal,
        "discount_amount": discount_amount,
        "discount_pct": discount_pct,
    }
