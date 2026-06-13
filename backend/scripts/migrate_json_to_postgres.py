import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = BACKEND_DIR.parent
DB_DIR = BASE_DIR / "db"
LOG_DIR = BACKEND_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
sys.path.append(str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import (
    addresses,
    metadata,
    notifications,
    order_items,
    orders,
    otp_sessions,
    products,
    recently_viewed,
    reviews,
    users,
    wishlist,
    contacts,
    chat_messages,
)

PG_DSN = os.getenv("DATABASE_URL") or os.getenv("PG_DSN", "postgresql://user:password@localhost/tridentwear")


def load_json(filename: str) -> List[Dict[str, Any]]:
    path = DB_DIR / filename
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        return [{"__migration_error__": f"{filename}: {exc}"}]


def pick(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if data.get(key) is not None:
            return data.get(key)
    return default


def normalize_user_ids(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    clean_rows = [dict(row) for row in rows if not row.get("__migration_error__")]
    max_id = max([int(row.get("id", 0) or 0) for row in clean_rows] or [0])
    seen = set()
    notes = []
    for row in clean_rows:
        user_pk = int(row.get("id", 0) or 0)
        if user_pk <= 0 or user_pk in seen:
            max_id += 1
            notes.append(f"Reassigned duplicate/missing user id {row.get('id')} -> {max_id} for {row.get('email')}")
            row["id"] = max_id
            user_pk = max_id
        seen.add(user_pk)
    return clean_rows, notes


def map_users(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "user_id": row.get("user_id"),
            "name": row.get("name"),
            "email": row.get("email"),
            "phone": row.get("phone"),
            "password_hash": row.get("password_hash") or row.get("password"),
            "role": row.get("role", "customer"),
            "gender": row.get("gender"),
            "otp_verification_status": bool(row.get("otp_verification_status", False)),
            "profile_completed_status": bool(row.get("profile_completed_status", False)),
            "is_active": row.get("is_active", True),
            "created_at": row.get("created_at"),
        }
        for row in rows
        if not row.get("__migration_error__")
    ]


def map_products(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "category": row.get("category", "tshirt"),
            "price": row.get("price"),
            "stock": row.get("stock"),
            "image": row.get("image"),
            "description": row.get("description"),
            "tag": row.get("tag"),
            "sizes": row.get("sizes", []),
            "featured": bool(row.get("featured", False)),
            "cloth_type": row.get("cloth_type"),
            "base_color": row.get("base_color"),
            "fabric": row.get("fabric") or row.get("material"),
            "material": row.get("material") or row.get("fabric"),
            "gsm": row.get("gsm"),
            "fit_type": row.get("fit_type"),
            "neck_type": row.get("neck_type"),
            "design_type": row.get("design_type"),
            "design_color": row.get("design_color"),
            "print_method": row.get("print_method", []),
            "wash_care_label": bool(row.get("wash_care_label", True)),
            "wash_care": row.get("wash_care", []),
            "size_quantities": row.get("size_quantities", {}),
            "tag_metadata": row.get("tag_metadata", {}),
            "created_at": row.get("created_at"),
        }
        for row in rows
        if not row.get("__migration_error__")
    ]


def map_orders(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    mapped = []
    for row in rows:
        if row.get("__migration_error__"):
            continue
        subtotal = float(pick(row, "subtotal", "total", default=0) or 0)
        mapped.append(
            {
                "id": row.get("id"),
                "order_id": row.get("order_id"),
                "user_id": row.get("customer", {}).get("user_id"),
                "items": row.get("items", []),
                "total": row.get("total", subtotal),
                "subtotal": subtotal,
                "discount_amount": float(row.get("discount_amount", 0) or 0),
                "coupon_code": row.get("coupon_code"),
                "customer": row.get("customer", {}),
                "shipping": row.get("shipping", {}),
                "status": row.get("status", "placed"),
                "payment_method": row.get("payment_method") or row.get("method"),
                "payment_status": row.get("payment_status", "pending"),
                "tracking_id": row.get("tracking_id"),
                "courier": row.get("courier"),
                "estimated_delivery": row.get("estimated_delivery"),
                "test_mode": bool(row.get("test_mode", False)),
                "created_at": row.get("created_at"),
            }
        )
    return mapped


def map_order_items(order_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    mapped = []
    next_id = 1
    for order in order_rows:
        order_pk = order.get("id")
        if not order_pk:
            continue
        for item in order.get("items", []) or []:
            mapped.append(
                {
                    "id": next_id,
                    "order_id": order_pk,
                    "product_id": item.get("id"),
                    "name": item.get("name"),
                    "size": item.get("size"),
                    "qty": int(item.get("qty", 1) or 1),
                    "unit_price": float(item.get("price", 0) or 0),
                    "image": item.get("image"),
                }
            )
            next_id += 1
    return mapped


def map_reviews(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "product_id": row.get("product_id"),
            "user_id": row.get("user_id"),
            "user_name": row.get("user_name"),
            "rating": row.get("rating"),
            "review": row.get("review"),
            "verified_purchase": bool(row.get("verified_purchase", False)),
            "status": str(row.get("status", "pending")).replace("_moderation", ""),
            "moderation_notes": row.get("moderation_notes"),
            "moderated_by": row.get("moderated_by"),
            "moderated_at": row.get("moderated_at"),
            "created_at": row.get("created_at"),
        }
        for row in rows
        if not row.get("__migration_error__")
    ]


def map_contacts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "email": row.get("email"),
            "message": row.get("message"),
            "created_at": row.get("created_at"),
        }
        for row in rows
        if not row.get("__migration_error__")
    ]


def map_chat_messages(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "thread_id": row.get("thread_id"),
            "author": row.get("author"),
            "message": row.get("message"),
            "role": row.get("role"),
            "timestamp": row.get("timestamp"),
            "read": bool(row.get("read", False)),
            "created_at": row.get("created_at") or row.get("timestamp"),
        }
        for row in rows
        if not row.get("__migration_error__")
    ]


def build_migration_payload() -> Dict[str, List[Dict[str, Any]]]:
    users_data = load_json("users.json")
    products_data = load_json("products.json")
    orders_data = load_json("orders.json")
    reviews_data = load_json("reviews.json")
    otp_data = load_json("otp_sessions.json")
    wishlist_data = load_json("wishlist.json")
    contacts_data = load_json("contacts.json")
    chat_data = load_json("chat.json")

    normalized_users, notes = normalize_user_ids(users_data)
    mapped_orders = map_orders(orders_data)
    return {
        "_notes": [{"message": note} for note in notes],
        "users": map_users(normalized_users),
        "products": map_products(products_data),
        "orders": mapped_orders,
        "order_items": map_order_items(mapped_orders),
        "addresses": [],
        "reviews": map_reviews(reviews_data),
        "wishlist": wishlist_data,
        "recently_viewed": [],
        "notifications": [],
        "otp_sessions": otp_data,
        "contacts": map_contacts(contacts_data),
        "chat_messages": map_chat_messages(chat_data),
    }


TABLES = {
    "users": users,
    "products": products,
    "orders": orders,
    "order_items": order_items,
    "addresses": addresses,
    "reviews": reviews,
    "wishlist": wishlist,
    "recently_viewed": recently_viewed,
    "notifications": notifications,
    "otp_sessions": otp_sessions,
    "contacts": contacts,
    "chat_messages": chat_messages,
}


def validate_payload(payload: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    errors = []
    product_ids = {row.get("id") for row in payload["products"]}
    user_ids = {row.get("id") for row in payload["users"]}
    for table_name in ("users", "products", "orders", "reviews", "contacts", "chat_messages"):
        ids = [row.get("id") for row in payload.get(table_name, []) if row.get("id") is not None]
        duplicate_ids = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
        for item_id in duplicate_ids:
            errors.append(f"Duplicate id {item_id} in {table_name}")
    for order in payload["orders"]:
        if not order.get("order_id"):
            errors.append(f"Order row missing order_id: {order}")
        if order.get("user_id") and order["user_id"] not in user_ids:
            errors.append(f"Order {order.get('order_id')} references missing user {order.get('user_id')}")
    for item in payload["order_items"]:
        if item.get("product_id") and item["product_id"] not in product_ids:
            errors.append(f"Order item references missing product {item.get('product_id')}")
    for review in payload["reviews"]:
        if review.get("product_id") not in product_ids:
            errors.append(f"Review {review.get('id')} references missing product {review.get('product_id')}")
        if review.get("user_id") not in user_ids:
            errors.append(f"Review {review.get('id')} references missing user {review.get('user_id')}")
    return errors


def migrate(dry_run: bool = False) -> None:
    started = time.time()
    payload = build_migration_payload()
    errors = validate_payload(payload)
    report = {
        "dry_run": dry_run,
        "database_url_configured": bool(PG_DSN),
        "record_counts": {name: len(rows) for name, rows in payload.items() if not name.startswith("_")},
        "notes": [row["message"] for row in payload.get("_notes", [])],
        "errors": errors,
        "execution_time_ms": 0,
    }

    if dry_run or errors:
        print("=== JSON TO POSTGRES DRY RUN ===" if dry_run else "=== JSON TO POSTGRES VALIDATION FAILED ===")
        print(json.dumps(report, indent=2, default=str))
        (LOG_DIR / "migration_dry_run_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        return

    print("--- WARNING: Starting database migration. Ensure backups of your JSON database are secured. ---")
    engine = create_engine(PG_DSN)
    metadata.create_all(engine)
    try:
        with engine.begin() as conn:
            for name, rows in payload.items():
                if name.startswith("_"):
                    continue
                if not rows:
                    continue
                table = TABLES[name]
                statement = pg_insert(table).values(rows)
                update_columns = {
                    column.name: statement.excluded[column.name]
                    for column in table.columns
                    if not column.primary_key
                }
                conn.execute(statement.on_conflict_do_update(index_elements=["id"], set_=update_columns))
    except SQLAlchemyError as exc:
        report["errors"].append(str(exc))
        print("Migration failed and rolled back.")
        print(json.dumps(report, indent=2, default=str))
        return

    report["execution_time_ms"] = round((time.time() - started) * 1000, 2)
    (LOG_DIR / "migration_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("Migration completed.")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the planned migration without writing to Postgres.")
    args = parser.parse_args()
    migrate(args.dry_run)
