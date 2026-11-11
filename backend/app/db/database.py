from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import os
import math
import json
from datetime import datetime, timezone, timedelta
import uuid
from pathlib import Path

from sqlalchemy import create_engine, select, update as sql_update, delete as sql_delete, insert as sql_insert, func
from sqlalchemy.exc import IntegrityError

from app.db.json_manager import read_json, update_json
from app.core.logger import app_logger

class DatabaseInterface(ABC):
    @abstractmethod
    def read(self, table: str, filters: dict) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def insert(self, table: str, data: dict) -> Dict[str, Any]:
        pass

    @abstractmethod
    def update(self, table: str, filters: dict, data: dict) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete(self, table: str, filters: dict) -> int:
        pass

    @abstractmethod
    def reserve_coupon_offer(self, code: str, today_iso: str, order_id: str, offer_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def release_coupon_offer(self, code: str, order_id: str, offer_id: str) -> bool:
        pass

    @abstractmethod
    def redeem_coupon(self, code: str, today_iso: str, order_id: Optional[str] = None, offer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def release_coupon(self, code: str, order_id: Optional[str] = None, offer_id: Optional[str] = None) -> bool:
        pass

    def deduct_order_stock(self, order_id: str, items: List[Dict[str, Any]]) -> bool:
        pass

    @abstractmethod
    def bind_payment_id(self, order_id: str, razorpay_payment_id: str) -> bool:
        pass

    @abstractmethod
    def acquire_claim(
        self,
        order_id: str,
        claim_token: Optional[str] = None,
        lease_seconds: int = 30,
        claim_owner: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def renew_claim(self, order_id: str, claim_token: str, lease_seconds: int = 30) -> bool:
        pass

    @abstractmethod
    def release_claim(self, order_id: str, claim_token: str) -> bool:
        pass

    @abstractmethod
    def finalize_order(self, order_id: str, claim_token: str) -> bool:
        pass


class InsufficientStockError(Exception):
    """Raised when one or more products do not have sufficient stock to fulfill an order."""
    pass


class InconsistentAllocationError(Exception):
    """Raised when an order allocation record is malformed or partially applied."""
    pass


class CouponConflictError(Exception):
    """Raised when an order attempts to redeem a different coupon after already redeeming one, or when concurrent redemption conflicts."""
    pass


class PaymentBindingConflictError(Exception):
    """Raised when an order or payment ID binding conflicts with existing records."""
    pass


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DB_DIR = BASE_DIR / "db"

class JsonDatabaseAdapter(DatabaseInterface):
    """Wraps json_manager.py to map tables to json files."""

    def __init__(self, db_dir: Optional[Any] = None):
        if db_dir is not None:
            self._explicit_db_dir = Path(db_dir).resolve()
        else:
            self._explicit_db_dir = None

    @property
    def db_dir(self) -> Path:
        if self._explicit_db_dir is not None:
            return self._explicit_db_dir
        from app.core.db_switch import get_db_dir
        return get_db_dir()

    def _get_path(self, table: str) -> str:
        return str(self.db_dir / f"{table}.json")
        
    def _match(self, item: dict, filters: dict) -> bool:
        for k, v in filters.items():
            if item.get(k) != v:
                return False
        return True

    def read(self, table: str, filters: dict) -> List[Dict[str, Any]]:
        items = read_json(self._get_path(table)) or []
        if not filters:
            return items
        return [item for item in items if self._match(item, filters)]

    def insert(self, table: str, data: dict) -> Dict[str, Any]:
        inserted_item = None
        def _insert_fn(items):
            nonlocal inserted_item
            if not items: items = []
            
            if "id" not in data:
                data["id"] = max([int(i.get("id", 0)) for i in items] + [0]) + 1
                
            items.append(data)
            inserted_item = data
            return items
            
        update_json(self._get_path(table), _insert_fn)
        return inserted_item

    def update(self, table: str, filters: dict, data: dict) -> List[Dict[str, Any]]:
        updated_items = []
        def _update_fn(items):
            if not items: return []
            for item in items:
                if self._match(item, filters):
                    item.update(data)
                    updated_items.append(item)
            return items
            
        update_json(self._get_path(table), _update_fn)
        return updated_items

    def delete(self, table: str, filters: dict) -> int:
        deleted_count = 0
        def _delete_fn(items):
            nonlocal deleted_count
            if not items: return []
            new_items = []
            for item in items:
                if self._match(item, filters):
                    deleted_count += 1
                else:
                    new_items.append(item)
            return new_items
            
        update_json(self._get_path(table), _delete_fn)
        return deleted_count

    def reserve_coupon_offer(self, code: str, today_iso: str, order_id: str, offer_id: str) -> Optional[Dict[str, Any]]:
        today_date = datetime.fromisoformat(today_iso).date()
        order_str = str(order_id).strip() if order_id and str(order_id).strip() else None
        offer_str = str(offer_id).strip() if offer_id and str(offer_id).strip() else None

        if not order_str:
            raise ValueError("order_id is required for coupon offer reservation")
        if not offer_str:
            raise ValueError("offer_id is required for coupon offer reservation")

        reserved_item = None
        conflict_error = None

        def _reserve_fn(items):
            nonlocal reserved_item, conflict_error
            if not items: return []

            # 0. Check if offer is already redeemed or reserved
            for item in items:
                offers = item.get("redeemed_offers")
                if isinstance(offers, dict) and offer_str in offers:
                    o_rec = offers[offer_str]
                    o_ord = o_rec.get("order_id") if isinstance(o_rec, dict) else str(o_rec)
                    conflict_error = CouponConflictError(
                        f"FBT offer {offer_str} has already been redeemed by order {o_ord}. Reservation rejected."
                    )
                    return items

                res_offers = item.get("reserved_offers")
                if isinstance(res_offers, dict) and offer_str in res_offers:
                    r_rec = res_offers[offer_str]
                    r_ord = r_rec.get("order_id") if isinstance(r_rec, dict) else str(r_rec)
                    if r_ord == order_str:
                        # Idempotent reservation for the same order
                        reserved_item = item.copy()
                        reserved_item["already_reserved"] = True
                        return items
                    else:
                        conflict_error = CouponConflictError(
                            f"FBT offer {offer_str} is currently reserved by order {r_ord}. Reservation rejected."
                        )
                        return items

            # 1. Check if order already redeemed a different coupon
            for item in items:
                allocs = item.get("redeemed_orders")
                if isinstance(allocs, dict) and order_str in allocs:
                    if item.get("code") != code:
                        conflict_error = CouponConflictError(
                            f"Order {order_str} has already claimed coupon {item.get('code')}."
                        )
                        return items

            # 2. Find target coupon and validate eligibility
            for item in items:
                if item.get("code") == code:
                    if not item.get("is_active", True):
                        break
                    expiry_date = datetime.fromisoformat(item["expires_at"]).date()
                    if today_date > expiry_date:
                        break
                    usage_limit = int(item.get("usage_limit", 1000))
                    usage_count = int(item.get("usage_count", 0))
                    if usage_count >= usage_limit:
                        break

                    # Record reservation without incrementing usage_count
                    if not isinstance(item.get("reserved_offers"), dict):
                        item["reserved_offers"] = {}
                    item["reserved_offers"][offer_str] = {
                        "order_id": order_str,
                        "reserved_at": datetime.now(timezone.utc).isoformat(),
                    }
                    reserved_item = item.copy()
                    reserved_item["already_reserved"] = False
                    break
            return items

        update_json(self._get_path("coupons"), _reserve_fn)
        if conflict_error:
            raise conflict_error
        return reserved_item

    def release_coupon_offer(self, code: str, order_id: str, offer_id: str) -> bool:
        released = False
        order_str = str(order_id).strip() if order_id and str(order_id).strip() else None
        offer_str = str(offer_id).strip() if offer_id and str(offer_id).strip() else None

        if not order_str or not offer_str:
            return False

        def _release_offer_fn(items):
            nonlocal released
            if not items: return []
            for item in items:
                if item.get("code") == code:
                    res_offers = item.get("reserved_offers")
                    if isinstance(res_offers, dict) and offer_str in res_offers:
                        r_rec = res_offers[offer_str]
                        r_ord = r_rec.get("order_id") if isinstance(r_rec, dict) else str(r_rec)
                        if r_ord == order_str:
                            del res_offers[offer_str]
                            released = True
            return items

        update_json(self._get_path("coupons"), _release_offer_fn)
        return released

    def redeem_coupon(self, code: str, today_iso: str, order_id: Optional[str] = None, offer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        today_date = datetime.fromisoformat(today_iso).date()
        order_str = str(order_id).strip() if order_id and str(order_id).strip() else None
        offer_str = str(offer_id).strip() if offer_id and str(offer_id).strip() else None
        redeemed_item = None
        conflict_error = None

        def _redeem_fn(items):
            nonlocal redeemed_item, conflict_error
            if not items: return []

            # 0. If offer_str provided, check if this FBT offer was already redeemed or reserved
            if offer_str:
                for item in items:
                    offers = item.get("redeemed_offers")
                    if isinstance(offers, dict) and offer_str in offers:
                        o_rec = offers[offer_str]
                        o_ord = o_rec.get("order_id") if isinstance(o_rec, dict) else str(o_rec)
                        if order_str and o_ord == order_str:
                            pass
                        else:
                            conflict_error = CouponConflictError(
                                f"FBT offer {offer_str} has already been redeemed by order {o_ord}. Replay rejected."
                            )
                            return items

                    res_offers = item.get("reserved_offers")
                    if isinstance(res_offers, dict) and offer_str in res_offers:
                        r_rec = res_offers[offer_str]
                        r_ord = r_rec.get("order_id") if isinstance(r_rec, dict) else str(r_rec)
                        if order_str and r_ord == order_str:
                            # Reserved by this order: finalize redemption below
                            pass
                        else:
                            conflict_error = CouponConflictError(
                                f"FBT offer {offer_str} is currently reserved by order {r_ord}. Replay rejected."
                            )
                            return items

            # 1. If order_str provided, check if this order already redeemed any coupon
            if order_str:
                for item in items:
                    allocs = item.get("redeemed_orders")
                    if allocs is not None and not isinstance(allocs, dict):
                        raise InconsistentAllocationError(f"Malformed redeemed_orders in coupon {item.get('code')}.")
                    if isinstance(allocs, dict) and order_str in allocs:
                        if item.get("code") == code:
                            # Idempotent retry: return existing redemption without incrementing usage_count
                            redeemed_item = item.copy()
                            redeemed_item["already_redeemed"] = True
                            return items
                        else:
                            # Order already redeemed a DIFFERENT coupon!
                            conflict_error = CouponConflictError(
                                f"Order {order_str} has already redeemed coupon {item.get('code')}. Conflicting redemption rejected."
                            )
                            return items

            # 2. Find target coupon and validate eligibility
            for item in items:
                if item.get("code") == code:
                    if not item.get("is_active", True):
                        break
                    expiry_date = datetime.fromisoformat(item["expires_at"]).date()
                    if today_date > expiry_date:
                        break
                    usage_limit = int(item.get("usage_limit", 1000))
                    usage_count = int(item.get("usage_count", 0))
                    if usage_count >= usage_limit:
                        break

                    item["usage_count"] = usage_count + 1
                    if order_str:
                        if not isinstance(item.get("redeemed_orders"), dict):
                            item["redeemed_orders"] = {}
                        item["redeemed_orders"][order_str] = {
                            "redeemed_at": datetime.now(timezone.utc).isoformat()
                        }
                    if offer_str:
                        # Clean up reserved_offers if previously reserved
                        if isinstance(item.get("reserved_offers"), dict) and offer_str in item["reserved_offers"]:
                            del item["reserved_offers"][offer_str]

                        if not isinstance(item.get("redeemed_offers"), dict):
                            item["redeemed_offers"] = {}
                        item["redeemed_offers"][offer_str] = {
                            "order_id": order_str,
                            "redeemed_at": datetime.now(timezone.utc).isoformat()
                        }
                    redeemed_item = item.copy()
                    redeemed_item["already_redeemed"] = False
                    break
            return items

        update_json(self._get_path("coupons"), _redeem_fn)
        if conflict_error:
            raise conflict_error
        return redeemed_item

    def release_coupon(self, code: str, order_id: Optional[str] = None, offer_id: Optional[str] = None) -> bool:
        released = False
        order_str = str(order_id).strip() if order_id and str(order_id).strip() else None
        offer_str = str(offer_id).strip() if offer_id and str(offer_id).strip() else None

        def _release_fn(items):
            nonlocal released
            if not items: return []
            for item in items:
                if item.get("code") == code:
                    if order_str:
                        allocs = item.get("redeemed_orders")
                        if isinstance(allocs, dict) and order_str in allocs:
                            del allocs[order_str]
                            usage_count = int(item.get("usage_count", 0))
                            if usage_count > 0:
                                item["usage_count"] = usage_count - 1
                            released = True
                        else:
                            # Order did not redeem this coupon; do not decrement counter
                            released = False
                    else:
                        usage_count = int(item.get("usage_count", 0))
                        if usage_count > 0:
                            item["usage_count"] = usage_count - 1
                        released = True

                    offers = item.get("redeemed_offers")
                    if isinstance(offers, dict):
                        if offer_str and offer_str in offers:
                            del offers[offer_str]
                        elif order_str:
                            for o_id in list(offers.keys()):
                                o_rec = offers[o_id]
                                o_ord = o_rec.get("order_id") if isinstance(o_rec, dict) else str(o_rec)
                                if o_ord == order_str:
                                    del offers[o_id]

                    res_offers = item.get("reserved_offers")
                    if isinstance(res_offers, dict):
                        if offer_str and offer_str in res_offers:
                            del res_offers[offer_str]
                        elif order_str:
                            for o_id in list(res_offers.keys()):
                                r_rec = res_offers[o_id]
                                r_ord = r_rec.get("order_id") if isinstance(r_rec, dict) else str(r_rec)
                                if r_ord == order_str:
                                    del res_offers[o_id]
                    break
            return items

        update_json(self._get_path("coupons"), _release_fn)
        return released
    def deduct_order_stock(self, order_id: str, items: List[Dict[str, Any]]) -> bool:
        if not order_id or not str(order_id).strip():
            raise ValueError("Order ID is required for stock deduction.")
        if not items:
            return True

        # Validate and aggregate quantities by product ID
        qty_map: Dict[int, int] = {}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid item format in order.")
            try:
                pid = int(item.get("id") or item.get("product_id") or 0)
            except (TypeError, ValueError):
                raise ValueError("Invalid product ID in order.")
            if pid <= 0:
                raise ValueError(f"Product ID {pid} must be positive.")
            try:
                qty = int(item.get("qty", 1))
            except (TypeError, ValueError):
                raise ValueError(f"Invalid quantity for product {pid}.")
            if qty <= 0:
                raise ValueError(f"Quantity for product {pid} must be positive.")
            qty_map[pid] = qty_map.get(pid, 0) + qty

        orders_path = self._get_path("orders")
        products_path = self._get_path("products")
        allocations_path = self._get_path("stock_allocations")
        order_str = str(order_id).strip()

        # Execute atomic deduction & durable in-record allocation under CrossProcessLock
        already_allocated = False

        def _deduct_and_allocate_fn(prods):
            nonlocal already_allocated
            if not prods:
                prods = []

            prod_map = {}
            for p in prods:
                try:
                    prod_map[int(p.get("id", 0))] = p
                except (ValueError, TypeError):
                    pass

            # 1. Check legacy stock_allocations.json or orders.json fallback
            legacy_allocated = False
            if os.path.exists(allocations_path):
                try:
                    with open(allocations_path, "r", encoding="utf-8") as f:
                        allocs = json.load(f) or []
                        if any(str(a.get("order_id")) == order_str for a in allocs):
                            legacy_allocated = True
                except Exception:
                    pass

            if not legacy_allocated and os.path.exists(orders_path):
                try:
                    with open(orders_path, "r", encoding="utf-8") as f:
                        order_records = json.load(f) or []
                        for o in order_records:
                            if str(o.get("order_id")) == order_str or str(o.get("id")) == order_str:
                                if o.get("stock_status") == "deducted":
                                    legacy_allocated = True
                                break
                except Exception:
                    pass

            # 2. Check allocation status inside products.json
            allocated_count = 0
            for pid in qty_map:
                if pid not in prod_map:
                    raise InsufficientStockError(f"Product with ID {pid} not found.")
                p = prod_map[pid]
                allocs = p.get("allocated_orders")
                if allocs is not None and not isinstance(allocs, dict):
                    raise InconsistentAllocationError(
                        f"Malformed allocation record in product {pid} for order {order_str}."
                    )
                if isinstance(allocs, dict) and order_str in allocs:
                    allocated_count += 1

            # Inconsistent partial allocation detection
            if 0 < allocated_count < len(qty_map):
                raise InconsistentAllocationError(
                    f"Partial allocation detected for order {order_str}: "
                    f"{allocated_count} of {len(qty_map)} products recorded. Refusing second deduction."
                )

            # If already fully allocated or recognized by legacy record:
            if allocated_count == len(qty_map) or legacy_allocated:
                already_allocated = True
                # If legacy allocated but not yet recorded in products.json, backfill without decrementing stock
                if legacy_allocated and allocated_count == 0:
                    now_str = datetime.now(timezone.utc).isoformat()
                    for pid, needed_qty in qty_map.items():
                        p = prod_map[pid]
                        if not isinstance(p.get("allocated_orders"), dict):
                            p["allocated_orders"] = {}
                        p["allocated_orders"][order_str] = {
                            "quantity": needed_qty,
                            "allocated_at": now_str
                        }
                    return prods
                return prods

            # 3. Validation: Verify all products have sufficient stock
            for pid, needed_qty in qty_map.items():
                p = prod_map[pid]
                try:
                    available = int(p.get("stock", 0))
                except (ValueError, TypeError):
                    available = 0
                if available < needed_qty:
                    raise InsufficientStockError(
                        f"Insufficient stock for {p.get('name', f'product {pid}')}: available {available}, needed {needed_qty}."
                    )

            # 4. Atomic Mutation: Decrement stock AND record allocation in the same pass
            now_str = datetime.now(timezone.utc).isoformat()
            for pid, needed_qty in qty_map.items():
                p = prod_map[pid]
                p["stock"] = int(p.get("stock", 0)) - needed_qty
                if not isinstance(p.get("allocated_orders"), dict):
                    p["allocated_orders"] = {}
                p["allocated_orders"][order_str] = {
                    "quantity": needed_qty,
                    "allocated_at": now_str
                }

            return prods

        update_json(products_path, _deduct_and_allocate_fn)

        # 5. Update orders.json with stock_status = 'deducted'
        if os.path.exists(orders_path):
            def _mark_order_fn(orders):
                if not orders:
                    return []
                for o in orders:
                    if str(o.get("order_id")) == order_str or str(o.get("id")) == order_str:
                        o["stock_status"] = "deducted"
                        o["updated_at"] = datetime.now(timezone.utc).isoformat()
                return orders

            update_json(orders_path, _mark_order_fn)

        return True
    def bind_payment_id(self, order_id: str, razorpay_payment_id: str) -> bool:
        if not order_id or not str(order_id).strip():
            raise ValueError("Order ID is required.")
        if not razorpay_payment_id or not str(razorpay_payment_id).strip():
            raise ValueError("Payment ID is required.")

        order_str = str(order_id).strip()
        pay_id_str = str(razorpay_payment_id).strip()
        orders_path = self._get_path("orders")

        conflict_err = None
        not_found = False

        def _bind_fn(orders):
            nonlocal conflict_err, not_found
            if not orders:
                orders = []

            target = None
            for o in orders:
                if str(o.get("order_id")) == order_str or str(o.get("id")) == order_str:
                    target = o
                    break

            if not target:
                not_found = True
                return orders

            # Idempotent retry: same order already bound to same payment ID
            if target.get("razorpay_payment_id") == pay_id_str:
                return orders

            # Target order already bound to a different payment ID
            if target.get("razorpay_payment_id") and target.get("razorpay_payment_id") != pay_id_str:
                conflict_err = PaymentBindingConflictError(
                    f"Order '{order_str}' already has payment ID '{target.get('razorpay_payment_id')}' bound. Cannot rebind to '{pay_id_str}'."
                )
                return orders

            # Check if another order already has this payment ID bound
            for o in orders:
                if str(o.get("order_id")) != order_str and str(o.get("id")) != order_str:
                    if o.get("razorpay_payment_id") == pay_id_str:
                        conflict_err = PaymentBindingConflictError(
                            f"Payment ID '{pay_id_str}' is already bound to order '{o.get('order_id') or o.get('id')}'."
                        )
                        return orders

            # Bind payment ID
            target["razorpay_payment_id"] = pay_id_str
            target["updated_at"] = datetime.now(timezone.utc).isoformat()
            return orders

        update_json(orders_path, _bind_fn)

        if not_found:
            raise ValueError(f"Order '{order_str}' not found.")
        if conflict_err:
            raise conflict_err
        return True

    def acquire_claim(
        self,
        order_id: str,
        claim_token: Optional[str] = None,
        lease_seconds: int = 30,
        claim_owner: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not order_id or not str(order_id).strip():
            return None

        order_str = str(order_id).strip()
        orders_path = self._get_path("orders")
        token = claim_token or uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=lease_seconds)
        expires_at_iso = expires_at.isoformat()

        acquired_record = None

        def _acquire_fn(orders):
            nonlocal acquired_record
            if not orders:
                return []

            for o in orders:
                if str(o.get("order_id")) == order_str or str(o.get("id")) == order_str:
                    # 1. Unpaid or non-paid orders cannot be claimed
                    if o.get("payment_status") != "paid":
                        return orders

                    # 2. Orders fulfilled or under manual review cannot be claimed
                    f_status = o.get("fulfillment_status") or "pending"
                    if f_status in ("fulfilled", "manual_review_required"):
                        return orders

                    # 3. Active lease check: must not overwrite valid active lease
                    existing_token = o.get("claim_token")
                    existing_expires = o.get("claim_expires_at")

                    is_active_lease = False
                    if existing_token and existing_expires:
                        try:
                            exp_dt = datetime.fromisoformat(existing_expires)
                            if exp_dt.tzinfo is None:
                                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                            if exp_dt >= now:
                                is_active_lease = True
                        except (ValueError, TypeError):
                            # Malformed timestamp defensively treated as expired/invalid
                            is_active_lease = False

                    if is_active_lease:
                        return orders

                    # Eligible: update claim fields atomically
                    o["claim_token"] = token
                    o["claim_expires_at"] = expires_at_iso
                    o["claim_owner"] = claim_owner
                    o["updated_at"] = now.isoformat()

                    acquired_record = {
                        "id": o.get("id"),
                        "order_id": o.get("order_id"),
                        "claim_token": token,
                        "claim_expires_at": expires_at_iso,
                        "claim_owner": claim_owner,
                    }
                    return orders
            return orders

        update_json(orders_path, _acquire_fn)
        return acquired_record

    def renew_claim(self, order_id: str, claim_token: str, lease_seconds: int = 30) -> bool:
        if not order_id or not claim_token:
            return False

        order_str = str(order_id).strip()
        orders_path = self._get_path("orders")
        now = datetime.now(timezone.utc)
        new_expires_at_iso = (now + timedelta(seconds=lease_seconds)).isoformat()
        renewed = False

        def _renew_fn(orders):
            nonlocal renewed
            if not orders:
                return []

            for o in orders:
                if str(o.get("order_id")) == order_str or str(o.get("id")) == order_str:
                    # Token must match exactly
                    if o.get("claim_token") != claim_token:
                        return orders

                    # Lease must be currently active (expired lease cannot be resurrected)
                    exp_str = o.get("claim_expires_at")
                    if not exp_str:
                        return orders
                    try:
                        exp_dt = datetime.fromisoformat(exp_str)
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        if exp_dt < now:
                            return orders
                    except (ValueError, TypeError):
                        return orders

                    o["claim_expires_at"] = new_expires_at_iso
                    o["updated_at"] = now.isoformat()
                    renewed = True
                    return orders
            return orders

        update_json(orders_path, _renew_fn)
        return renewed

    def release_claim(self, order_id: str, claim_token: str) -> bool:
        if not order_id or not claim_token:
            return False

        order_str = str(order_id).strip()
        orders_path = self._get_path("orders")
        now = datetime.now(timezone.utc)
        released = False

        def _release_fn(orders):
            nonlocal released
            if not orders:
                return []

            for o in orders:
                if str(o.get("order_id")) == order_str or str(o.get("id")) == order_str:
                    if o.get("claim_token") != claim_token:
                        return orders

                    o["claim_token"] = None
                    o["claim_expires_at"] = None
                    o["claim_owner"] = None
                    o["updated_at"] = now.isoformat()
                    released = True
                    return orders
            return orders

        update_json(orders_path, _release_fn)
        return released

    def finalize_order(self, order_id: str, claim_token: str) -> bool:
        if not order_id or not claim_token:
            return False

        order_str = str(order_id).strip()
        orders_path = self._get_path("orders")
        now = datetime.now(timezone.utc)
        finalized = False

        def _finalize_fn(orders):
            nonlocal finalized
            if not orders:
                return []

            for o in orders:
                if str(o.get("order_id")) == order_str or str(o.get("id")) == order_str:
                    # 1. Fencing token check
                    if o.get("claim_token") != claim_token:
                        return orders

                    # 2. Active lease check
                    exp_str = o.get("claim_expires_at")
                    if not exp_str:
                        return orders
                    try:
                        exp_dt = datetime.fromisoformat(exp_str)
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        if exp_dt < now:
                            return orders
                    except (ValueError, TypeError):
                        return orders

                    # 3. Prerequisites check: payment_status paid, stock deducted, email sent, no manual review
                    if o.get("payment_status") != "paid":
                        return orders
                    if o.get("stock_status") != "deducted":
                        return orders
                    if o.get("email_status") != "sent":
                        return orders
                    if (o.get("fulfillment_status") or "pending") == "manual_review_required":
                        return orders

                    # Commit finalization
                    o["fulfillment_status"] = "fulfilled"
                    o["claim_token"] = None
                    o["claim_expires_at"] = None
                    o["claim_owner"] = None
                    o["updated_at"] = now.isoformat()
                    finalized = True
                    return orders
            return orders

        update_json(orders_path, _finalize_fn)
        return finalized


class PostgresDatabaseAdapter(DatabaseInterface):
    """PostgreSQL adapter using SQLAlchemy Core."""
    
    def __init__(self, dsn: str):
        engine_kwargs = {"pool_pre_ping": True}
        if not dsn.startswith("sqlite"):
            engine_kwargs.update({"pool_size": 10, "max_overflow": 20})
        self.engine = create_engine(dsn, **engine_kwargs)
        from app.db.models import metadata
        self.metadata = metadata
        
    def _get_table(self, table_name: str):
        if table_name not in self.metadata.tables:
            raise ValueError(f"Table {table_name} not found in metadata")
        return self.metadata.tables[table_name]

    def _validate_filters(self, table_obj, filters: dict, table: str):
        if not filters:
            return
        for k in filters:
            if k not in table_obj.c:
                raise ValueError(f"Invalid filter column '{k}' for table '{table}'")

    def read(self, table: str, filters: dict) -> List[Dict[str, Any]]:
        table_obj = self._get_table(table)
        self._validate_filters(table_obj, filters, table)
        stmt = select(table_obj)
        for k, v in filters.items():
            stmt = stmt.where(getattr(table_obj.c, k) == v)
            
        with self.engine.connect() as conn:
            result = conn.execute(stmt)
            return [dict(row._mapping) for row in result]

    def insert(self, table: str, data: dict) -> Dict[str, Any]:
        table_obj = self._get_table(table)
        clean_data = {k: v for k, v in data.items() if k in table_obj.c}
        stmt = sql_insert(table_obj).values(**clean_data).returning(table_obj)
        
        try:
            with self.engine.begin() as conn:
                result = conn.execute(stmt)
                return dict(result.first()._mapping)
        except IntegrityError as e:
            if table == "orders":
                with self.engine.connect() as conn:
                    for unique_key in ("razorpay_order_id", "razorpay_payment_id", "idempotency_key"):
                        val = clean_data.get(unique_key)
                        if val and unique_key in table_obj.c:
                            existing = conn.execute(select(table_obj).where(getattr(table_obj.c, unique_key) == val)).first()
                            if existing:
                                return dict(existing._mapping)
            raise e

    def update(self, table: str, filters: dict, data: dict) -> List[Dict[str, Any]]:
        if not filters:
            raise ValueError(f"Empty filters not allowed for update on table '{table}'")
        table_obj = self._get_table(table)
        self._validate_filters(table_obj, filters, table)
        clean_data = {k: v for k, v in data.items() if k in table_obj.c}
        stmt = sql_update(table_obj).values(**clean_data).returning(table_obj)
        for k, v in filters.items():
            stmt = stmt.where(getattr(table_obj.c, k) == v)
            
        with self.engine.begin() as conn:
            result = conn.execute(stmt)
            return [dict(row._mapping) for row in result]

    def delete(self, table: str, filters: dict) -> int:
        if not filters:
            raise ValueError(f"Empty filters not allowed for delete on table '{table}'")
        table_obj = self._get_table(table)
        self._validate_filters(table_obj, filters, table)
        stmt = sql_delete(table_obj)
        for k, v in filters.items():
            stmt = stmt.where(getattr(table_obj.c, k) == v)
            
        with self.engine.begin() as conn:
            result = conn.execute(stmt)
            return result.rowcount

    def reserve_coupon_offer(self, code: str, today_iso: str, order_id: str, offer_id: str) -> Optional[Dict[str, Any]]:
        table_coupons = self._get_table("coupons")
        order_str = str(order_id).strip() if order_id and str(order_id).strip() else None
        offer_str = str(offer_id).strip() if offer_id and str(offer_id).strip() else None

        if not order_str:
            raise ValueError("order_id is required for coupon offer reservation")
        if not offer_str:
            raise ValueError("offer_id is required for coupon offer reservation")

        with self.engine.begin() as conn:
            if "coupon_redemptions" in self.metadata.tables:
                table_redemptions = self._get_table("coupon_redemptions")

                if "offer_id" in table_redemptions.c:
                    existing_offer = conn.execute(
                        select(table_redemptions).where(table_redemptions.c.offer_id == offer_str)
                    ).first()
                    if existing_offer:
                        if existing_offer.order_id == order_str:
                            # Idempotent reservation for same order
                            coupon_row = conn.execute(
                                select(table_coupons).where(table_coupons.c.code == code)
                            ).first()
                            if coupon_row:
                                res = dict(coupon_row._mapping)
                                res["already_reserved"] = True
                                return res
                            return None
                        else:
                            raise CouponConflictError(
                                f"FBT offer {offer_str} has already been reserved/redeemed by order {existing_offer.order_id}."
                            )

                existing_order = conn.execute(
                    select(table_redemptions).where(table_redemptions.c.order_id == order_str)
                ).first()
                if existing_order:
                    if existing_order.coupon_code != code:
                        raise CouponConflictError(
                            f"Order {order_str} has already claimed coupon {existing_order.coupon_code}."
                        )

            # Check eligibility without incrementing counter
            coupon_row = conn.execute(
                select(table_coupons).where(
                    (table_coupons.c.code == code)
                    & (table_coupons.c.is_active == True)
                    & (table_coupons.c.usage_count < table_coupons.c.usage_limit)
                    & (func.length(table_coupons.c.expires_at) == 10)
                    & (table_coupons.c.expires_at >= today_iso)
                    & (table_coupons.c.expires_at <= '2099-12-31')
                )
            ).first()
            if not coupon_row:
                return None

            coupon_data = dict(coupon_row._mapping)
            coupon_data["already_reserved"] = False

            if "coupon_redemptions" in self.metadata.tables:
                table_redemptions = self._get_table("coupon_redemptions")
                insert_vals = {
                    "order_id": order_str,
                    "coupon_code": code,
                    "status": "reserved",
                    "redeemed_at": func.now()
                }
                if "offer_id" in table_redemptions.c:
                    insert_vals["offer_id"] = offer_str

                try:
                    conn.execute(sql_insert(table_redemptions).values(**insert_vals))
                except IntegrityError as ie:
                    raise CouponConflictError(
                        f"Concurrent reservation conflict for order {order_str} or offer {offer_str}: {ie}"
                    )

            return coupon_data

    def release_coupon_offer(self, code: str, order_id: str, offer_id: str) -> bool:
        order_str = str(order_id).strip() if order_id and str(order_id).strip() else None
        offer_str = str(offer_id).strip() if offer_id and str(offer_id).strip() else None

        if not order_str or not offer_str:
            return False

        if "coupon_redemptions" not in self.metadata.tables:
            return False

        table_redemptions = self._get_table("coupon_redemptions")
        with self.engine.begin() as conn:
            del_stmt = (
                sql_delete(table_redemptions)
                .where(
                    (table_redemptions.c.order_id == order_str)
                    & (table_redemptions.c.coupon_code == code)
                    & (table_redemptions.c.offer_id == offer_str)
                    & (table_redemptions.c.status == "reserved")
                )
            )
            res = conn.execute(del_stmt)
            return bool(res.rowcount > 0)

    def redeem_coupon(self, code: str, today_iso: str, order_id: Optional[str] = None, offer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        table_coupons = self._get_table("coupons")
        order_str = str(order_id).strip() if order_id and str(order_id).strip() else None
        offer_str = str(offer_id).strip() if offer_id and str(offer_id).strip() else None

        with self.engine.begin() as conn:
            existing_row = None
            if "coupon_redemptions" in self.metadata.tables:
                table_redemptions = self._get_table("coupon_redemptions")
                if offer_str and "offer_id" in table_redemptions.c:
                    existing_offer = conn.execute(
                        select(table_redemptions).where(table_redemptions.c.offer_id == offer_str)
                    ).first()
                    if existing_offer:
                        if order_str and existing_offer.order_id == order_str:
                            existing_row = existing_offer
                        else:
                            raise CouponConflictError(
                                f"FBT offer {offer_str} has already been redeemed by order {existing_offer.order_id}. Replay rejected."
                            )

                if order_str and not existing_row:
                    existing_redemption = conn.execute(
                        select(table_redemptions).where(table_redemptions.c.order_id == order_str)
                    ).first()
                    if existing_redemption:
                        existing_row = existing_redemption

                if existing_row:
                    existing_code = existing_row.coupon_code
                    if existing_code != code:
                        raise CouponConflictError(
                            f"Order {order_str} has already redeemed coupon {existing_code}. Conflicting redemption rejected."
                        )

                    row_status = getattr(existing_row, "status", "redeemed")
                    if row_status == "redeemed":
                        # Idempotent retry: return existing redemption without incrementing usage_count
                        coupon_row = conn.execute(
                            select(table_coupons).where(table_coupons.c.code == code)
                        ).first()
                        if coupon_row:
                            res = dict(coupon_row._mapping)
                            res["already_redeemed"] = True
                            return res
                        return None
                    elif row_status == "reserved":
                        # Finalize reservation to redeemed: increment usage_count and update status
                        stmt = (
                            sql_update(table_coupons)
                            .where(
                                (table_coupons.c.code == code)
                                & (table_coupons.c.is_active == True)
                                & (table_coupons.c.usage_count < table_coupons.c.usage_limit)
                                & (func.length(table_coupons.c.expires_at) == 10)
                                & (table_coupons.c.expires_at >= today_iso)
                                & (table_coupons.c.expires_at <= '2099-12-31')
                                & (table_coupons.c.discount_pct >= 0.0)
                                & (table_coupons.c.discount_pct <= 100.0)
                            )
                            .values(usage_count=table_coupons.c.usage_count + 1)
                            .returning(table_coupons)
                        )
                        result = conn.execute(stmt)
                        row = result.first()
                        if not row:
                            return None

                        coupon_data = dict(row._mapping)
                        coupon_data["already_redeemed"] = False

                        update_vals = {
                            "status": "redeemed",
                            "redeemed_at": func.now(),
                        }
                        if offer_str and "offer_id" in table_redemptions.c:
                            update_vals["offer_id"] = offer_str

                        conn.execute(
                            sql_update(table_redemptions)
                            .where(table_redemptions.c.id == existing_row.id)
                            .values(**update_vals)
                        )
                        return coupon_data

            # 2. Concurrency-safe atomic check and update of usage_count on coupons table (direct redemption)
            stmt = (
                sql_update(table_coupons)
                .where(
                    (table_coupons.c.code == code)
                    & (table_coupons.c.is_active == True)
                    & (table_coupons.c.usage_count < table_coupons.c.usage_limit)
                    & (func.length(table_coupons.c.expires_at) == 10)
                    & (table_coupons.c.expires_at >= today_iso)
                    & (table_coupons.c.expires_at <= '2099-12-31')
                    & (table_coupons.c.discount_pct >= 0.0)
                    & (table_coupons.c.discount_pct <= 100.0)
                )
                .values(usage_count=table_coupons.c.usage_count + 1)
                .returning(table_coupons)
            )
            result = conn.execute(stmt)
            row = result.first()
            if not row:
                return None

            coupon_data = dict(row._mapping)
            coupon_data["already_redeemed"] = False

            # 3. If order_str is provided, insert durable redemption record
            if order_str and "coupon_redemptions" in self.metadata.tables:
                table_redemptions = self._get_table("coupon_redemptions")
                insert_vals = {
                    "order_id": order_str,
                    "coupon_code": code,
                    "status": "redeemed",
                    "redeemed_at": func.now()
                }
                if offer_str and "offer_id" in table_redemptions.c:
                    insert_vals["offer_id"] = offer_str
                try:
                    conn.execute(sql_insert(table_redemptions).values(**insert_vals))
                except IntegrityError as ie:
                    raise CouponConflictError(
                        f"Concurrent redemption conflict for order {order_str} or offer {offer_str}: {ie}"
                    )

            return coupon_data

    def release_coupon(self, code: str, order_id: Optional[str] = None, offer_id: Optional[str] = None) -> bool:
        table_coupons = self._get_table("coupons")
        order_str = str(order_id).strip() if order_id and str(order_id).strip() else None

        with self.engine.begin() as conn:
            should_decrement = True
            if order_str and "coupon_redemptions" in self.metadata.tables:
                table_redemptions = self._get_table("coupon_redemptions")
                existing_row = conn.execute(
                    select(table_redemptions).where(
                        (table_redemptions.c.order_id == order_str) & (table_redemptions.c.coupon_code == code)
                    )
                ).first()
                if not existing_row:
                    return False
                if getattr(existing_row, "status", "redeemed") == "reserved":
                    should_decrement = False

                del_stmt = (
                    sql_delete(table_redemptions)
                    .where((table_redemptions.c.order_id == order_str) & (table_redemptions.c.coupon_code == code))
                )
                res_del = conn.execute(del_stmt)
                if res_del.rowcount == 0:
                    return False

            if should_decrement:
                stmt = (
                    sql_update(table_coupons)
                    .where(
                        (table_coupons.c.code == code)
                        & (table_coupons.c.usage_count > 0)
                    )
                    .values(usage_count=table_coupons.c.usage_count - 1)
                    .returning(table_coupons.c.id)
                )
                result = conn.execute(stmt)
                return result.first() is not None
            return True
    def deduct_order_stock(self, order_id: str, items: List[Dict[str, Any]]) -> bool:
        if not order_id or not str(order_id).strip():
            raise ValueError("Order ID is required for stock deduction.")
        if not items:
            return True

        table_products = self._get_table("products")
        table_orders = self._get_table("orders")

        # Validate and aggregate quantities by product ID
        qty_map: Dict[int, int] = {}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid item format in order.")
            try:
                pid = int(item.get("id") or item.get("product_id") or 0)
            except (TypeError, ValueError):
                raise ValueError("Invalid product ID in order.")
            if pid <= 0:
                raise ValueError(f"Product ID {pid} must be positive.")
            try:
                qty = int(item.get("qty", 1))
            except (TypeError, ValueError):
                raise ValueError(f"Invalid quantity for product {pid}.")
            if qty <= 0:
                raise ValueError(f"Quantity for product {pid} must be positive.")
            qty_map[pid] = qty_map.get(pid, 0) + qty

        # Single atomic database transaction
        with self.engine.begin() as conn:
            stmt_order = select(table_orders.c.id, table_orders.c.stock_status)
            try:
                int_id = int(order_id)
                stmt_order = stmt_order.where((table_orders.c.order_id == str(order_id)) | (table_orders.c.id == int_id))
            except (ValueError, TypeError):
                stmt_order = stmt_order.where(table_orders.c.order_id == str(order_id))

            order_row = conn.execute(stmt_order.with_for_update()).first()
            if not order_row:
                raise ValueError(f"Order '{order_id}' not found.")

            # Idempotent fast-path: if already marked 'deducted', do not decrement again
            if getattr(order_row, "stock_status", None) == "deducted":
                return True

            # Deterministic row locking order (sorted by PID) to eliminate deadlocks
            sorted_pids = sorted(qty_map.keys())

            for pid in sorted_pids:
                needed_qty = qty_map[pid]
                stmt = (
                    sql_update(table_products)
                    .where((table_products.c.id == pid) & (table_products.c.stock >= needed_qty))
                    .values(stock=table_products.c.stock - needed_qty)
                    .returning(table_products.c.id, table_products.c.stock)
                )
                res = conn.execute(stmt).first()
                if not res:
                    # Insufficient stock or missing product: triggers automatic transaction rollback
                    raise InsufficientStockError(f"Insufficient stock for product ID {pid} (needed {needed_qty})")

            # Mark stock_status = 'deducted' in the same transaction
            conn.execute(
                sql_update(table_orders)
                .where(table_orders.c.id == order_row.id)
                .values(stock_status="deducted", updated_at=func.now())
            )
            return True
    def _order_predicate(self, table_orders, order_id: str):
        order_str = str(order_id).strip()
        try:
            int_id = int(order_str)
            return (table_orders.c.order_id == order_str) | (table_orders.c.id == int_id)
        except (ValueError, TypeError):
            return table_orders.c.order_id == order_str

    def bind_payment_id(self, order_id: str, razorpay_payment_id: str) -> bool:
        if not order_id or not str(order_id).strip():
            raise ValueError("Order ID is required.")
        if not razorpay_payment_id or not str(razorpay_payment_id).strip():
            raise ValueError("Payment ID is required.")

        pay_id_str = str(razorpay_payment_id).strip()
        table_orders = self._get_table("orders")
        pred = self._order_predicate(table_orders, order_id)

        with self.engine.begin() as conn:
            target_order = conn.execute(
                select(table_orders.c.id, table_orders.c.order_id, table_orders.c.razorpay_payment_id)
                .where(pred)
                .with_for_update()
            ).first()

            if not target_order:
                raise ValueError(f"Order '{order_id}' not found.")

            if target_order.razorpay_payment_id == pay_id_str:
                return True

            if target_order.razorpay_payment_id and target_order.razorpay_payment_id != pay_id_str:
                raise PaymentBindingConflictError(
                    f"Order '{order_id}' already has payment ID '{target_order.razorpay_payment_id}' bound. Cannot rebind to '{pay_id_str}'."
                )

            existing_pay = conn.execute(
                select(table_orders.c.id, table_orders.c.order_id)
                .where(table_orders.c.razorpay_payment_id == pay_id_str)
            ).first()

            if existing_pay and existing_pay.id != target_order.id:
                raise PaymentBindingConflictError(
                    f"Payment ID '{pay_id_str}' is already bound to order '{existing_pay.order_id or existing_pay.id}'."
                )

            try:
                conn.execute(
                    sql_update(table_orders)
                    .where(table_orders.c.id == target_order.id)
                    .values(razorpay_payment_id=pay_id_str, updated_at=func.now())
                )
            except IntegrityError as ie:
                raise PaymentBindingConflictError(
                    f"Concurrent binding conflict for payment ID '{pay_id_str}': {ie}"
                )

            return True

    def acquire_claim(
        self,
        order_id: str,
        claim_token: Optional[str] = None,
        lease_seconds: int = 30,
        claim_owner: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not order_id or not str(order_id).strip():
            return None

        table_orders = self._get_table("orders")
        pred = self._order_predicate(table_orders, order_id)
        token = claim_token or uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=lease_seconds)

        stmt = (
            sql_update(table_orders)
            .where(
                pred
                & (table_orders.c.payment_status == 'paid')
                & func.coalesce(table_orders.c.fulfillment_status, 'pending').notin_(['fulfilled', 'manual_review_required'])
                & (
                    table_orders.c.claim_token.is_(None)
                    | table_orders.c.claim_expires_at.is_(None)
                    | (table_orders.c.claim_expires_at < now)
                )
            )
            .values(
                claim_token=token,
                claim_expires_at=expires_at,
                claim_owner=claim_owner,
                updated_at=now
            )
            .returning(
                table_orders.c.id,
                table_orders.c.order_id,
                table_orders.c.claim_token,
                table_orders.c.claim_expires_at,
                table_orders.c.claim_owner
            )
        )

        with self.engine.begin() as conn:
            row = conn.execute(stmt).first()
            if not row:
                return None
            return {
                "id": row.id,
                "order_id": row.order_id,
                "claim_token": row.claim_token,
                "claim_expires_at": row.claim_expires_at.isoformat() if hasattr(row.claim_expires_at, "isoformat") else str(row.claim_expires_at),
                "claim_owner": row.claim_owner,
            }

    def renew_claim(self, order_id: str, claim_token: str, lease_seconds: int = 30) -> bool:
        if not order_id or not claim_token:
            return False

        table_orders = self._get_table("orders")
        pred = self._order_predicate(table_orders, order_id)
        now = datetime.now(timezone.utc)
        new_expires_at = now + timedelta(seconds=lease_seconds)

        stmt = (
            sql_update(table_orders)
            .where(
                pred
                & (table_orders.c.claim_token == claim_token)
                & table_orders.c.claim_expires_at.is_not(None)
                & (table_orders.c.claim_expires_at >= now)
            )
            .values(
                claim_expires_at=new_expires_at,
                updated_at=now
            )
            .returning(table_orders.c.id)
        )

        with self.engine.begin() as conn:
            res = conn.execute(stmt).first()
            return res is not None

    def release_claim(self, order_id: str, claim_token: str) -> bool:
        if not order_id or not claim_token:
            return False

        table_orders = self._get_table("orders")
        pred = self._order_predicate(table_orders, order_id)

        stmt = (
            sql_update(table_orders)
            .where(
                pred
                & (table_orders.c.claim_token == claim_token)
            )
            .values(
                claim_token=None,
                claim_expires_at=None,
                claim_owner=None,
                updated_at=func.now()
            )
            .returning(table_orders.c.id)
        )

        with self.engine.begin() as conn:
            res = conn.execute(stmt).first()
            return res is not None

    def finalize_order(self, order_id: str, claim_token: str) -> bool:
        if not order_id or not claim_token:
            return False

        table_orders = self._get_table("orders")
        pred = self._order_predicate(table_orders, order_id)
        now = datetime.now(timezone.utc)

        stmt = (
            sql_update(table_orders)
            .where(
                pred
                & (table_orders.c.claim_token == claim_token)
                & table_orders.c.claim_expires_at.is_not(None)
                & (table_orders.c.claim_expires_at >= now)
                & (table_orders.c.payment_status == 'paid')
                & (table_orders.c.stock_status == 'deducted')
                & (table_orders.c.email_status == 'sent')
                & (func.coalesce(table_orders.c.fulfillment_status, 'pending') != 'manual_review_required')
            )
            .values(
                fulfillment_status='fulfilled',
                claim_token=None,
                claim_expires_at=None,
                claim_owner=None,
                updated_at=now
            )
            .returning(table_orders.c.id)
        )

        with self.engine.begin() as conn:
            res = conn.execute(stmt).first()
            return res is not None


class DualWriteDatabaseAdapter(DatabaseInterface):
    """Zero Downtime Migration Adapter."""
    
    def __init__(self, old_db: DatabaseInterface, new_db: DatabaseInterface):
        self.old_db = old_db
        self.new_db = new_db
        self.replication_failures: List[Dict[str, Any]] = []

    def _record_failure(self, table: str, action: str, error: Exception):
        entry = {
            "table": table,
            "action": action,
            "error": str(error),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.replication_failures.append(entry)
        app_logger.error(f"[DUAL_WRITE_REPLICATION_FAILED] {action} on {table} failed: {error}")

    def read(self, table: str, filters: dict) -> List[Dict[str, Any]]:
        return self.old_db.read(table, filters)

    def insert(self, table: str, data: dict) -> Dict[str, Any]:
        result = self.old_db.insert(table, data)
        try:
            if "id" in result:
                data["id"] = result["id"]
            self.new_db.insert(table, data)
        except Exception as e:
            self._record_failure(table, "insert", e)
        return result

    def update(self, table: str, filters: dict, data: dict) -> List[Dict[str, Any]]:
        result = self.old_db.update(table, filters, data)
        try:
            self.new_db.update(table, filters, data)
        except Exception as e:
            self._record_failure(table, "update", e)
        return result

    def delete(self, table: str, filters: dict) -> int:
        result = self.old_db.delete(table, filters)
        try:
            self.new_db.delete(table, filters)
        except Exception as e:
            self._record_failure(table, "delete", e)
        return result

    def reserve_coupon_offer(self, code: str, today_iso: str, order_id: str, offer_id: str) -> Optional[Dict[str, Any]]:
        result = self.old_db.reserve_coupon_offer(code, today_iso, order_id=order_id, offer_id=offer_id)
        if result:
            try:
                self.new_db.reserve_coupon_offer(code, today_iso, order_id=order_id, offer_id=offer_id)
            except Exception as e:
                self._record_failure("coupons", "reserve_coupon_offer", e)
        return result

    def release_coupon_offer(self, code: str, order_id: str, offer_id: str) -> bool:
        result = self.old_db.release_coupon_offer(code, order_id=order_id, offer_id=offer_id)
        try:
            self.new_db.release_coupon_offer(code, order_id=order_id, offer_id=offer_id)
        except Exception as e:
            self._record_failure("coupons", "release_coupon_offer", e)
        return result

    def redeem_coupon(self, code: str, today_iso: str, order_id: Optional[str] = None, offer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        result = self.old_db.redeem_coupon(code, today_iso, order_id=order_id, offer_id=offer_id)
        if result:
            try:
                self.new_db.redeem_coupon(code, today_iso, order_id=order_id, offer_id=offer_id)
            except Exception as e:
                self._record_failure("coupons", "redeem_coupon", e)
        return result

    def release_coupon(self, code: str, order_id: Optional[str] = None, offer_id: Optional[str] = None) -> bool:
        result = self.old_db.release_coupon(code, order_id=order_id, offer_id=offer_id)
        try:
            self.new_db.release_coupon(code, order_id=order_id, offer_id=offer_id)
        except Exception as e:
            self._record_failure("coupons", "release_coupon", e)
        return result
    def deduct_order_stock(self, order_id: str, items: List[Dict[str, Any]]) -> bool:
        result = self.old_db.deduct_order_stock(order_id, items)
        if result:
            try:
                self.new_db.deduct_order_stock(order_id, items)
            except Exception as e:
                self._record_failure("products", "deduct_order_stock", e)
        return result
    def bind_payment_id(self, order_id: str, razorpay_payment_id: str) -> bool:
        result = self.old_db.bind_payment_id(order_id, razorpay_payment_id)
        if result:
            try:
                self.new_db.bind_payment_id(order_id, razorpay_payment_id)
            except Exception as e:
                self._record_failure("orders", "bind_payment_id", e)
        return result

    def acquire_claim(
        self,
        order_id: str,
        claim_token: Optional[str] = None,
        lease_seconds: int = 30,
        claim_owner: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        result = self.old_db.acquire_claim(
            order_id,
            claim_token=claim_token,
            lease_seconds=lease_seconds,
            claim_owner=claim_owner
        )
        if result:
            try:
                self.new_db.acquire_claim(
                    order_id,
                    claim_token=result["claim_token"],
                    lease_seconds=lease_seconds,
                    claim_owner=claim_owner
                )
            except Exception as e:
                self._record_failure("orders", "acquire_claim", e)
        return result

    def renew_claim(self, order_id: str, claim_token: str, lease_seconds: int = 30) -> bool:
        result = self.old_db.renew_claim(order_id, claim_token, lease_seconds=lease_seconds)
        if result:
            try:
                self.new_db.renew_claim(order_id, claim_token, lease_seconds=lease_seconds)
            except Exception as e:
                self._record_failure("orders", "renew_claim", e)
        return result

    def release_claim(self, order_id: str, claim_token: str) -> bool:
        result = self.old_db.release_claim(order_id, claim_token)
        try:
            self.new_db.release_claim(order_id, claim_token)
        except Exception as e:
            self._record_failure("orders", "release_claim", e)
        return result

    def finalize_order(self, order_id: str, claim_token: str) -> bool:
        result = self.old_db.finalize_order(order_id, claim_token)
        if result:
            try:
                self.new_db.finalize_order(order_id, claim_token)
            except Exception as e:
                self._record_failure("orders", "finalize_order", e)
        return result
