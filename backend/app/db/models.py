from sqlalchemy import (
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    JSON,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.sql import func

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String, unique=True, index=True),
    Column("name", String),
    Column("email", String, unique=True, index=True),
    Column("phone", String, unique=True, index=True),
    Column("password_hash", String),
    Column("role", String, default="customer", index=True),
    Column("gender", String),
    Column("otp_verification_status", Boolean, default=False),
    Column("profile_completed_status", Boolean, default=False),
    Column("is_active", Boolean, default=True),
    Column("last_login_at", DateTime(timezone=True)),
    Column("password_reset_token", String, nullable=True),
    Column("password_reset_expires_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), onupdate=func.now()),
)

products = Table(
    "products",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String),
    Column("category", String, index=True),
    Column("price", Float),
    Column("stock", Integer),
    Column("image", String),
    Column("description", Text),
    Column("tag", String),
    Column("sizes", JSON),
    Column("featured", Boolean, default=False, index=True),
    Column("cloth_type", String),
    Column("base_color", String),
    Column("fabric", String),
    Column("material", String),
    Column("gsm", Integer),
    Column("fit_type", String),
    Column("neck_type", String),
    Column("design_type", String),
    Column("design_color", String),
    Column("print_method", JSON),
    Column("wash_care_label", Boolean, default=True),
    Column("wash_care", JSON),
    Column("size_quantities", JSON),
    Column("tag_metadata", JSON),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), onupdate=func.now()),
)

orders = Table(
    "orders",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("order_id", String, unique=True, index=True),
    Column("user_id", Integer, ForeignKey("users.id"), index=True, nullable=True),
    Column("items", JSON),
    Column("total", Float),
    Column("subtotal", Float),
    Column("discount_amount", Float, default=0),
    Column("coupon_code", String),
    Column("customer", JSON),
    Column("shipping", JSON),
    Column("status", String, default="placed", index=True),
    Column("payment_method", String),
    Column("payment_status", String, default="pending", index=True),
    Column("tracking_id", String),
    Column("courier", String),
    Column("estimated_delivery", String),
    Column("test_mode", Boolean, default=False, index=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), onupdate=func.now()),
)

order_items = Table(
    "order_items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("order_id", Integer, ForeignKey("orders.id"), index=True, nullable=False),
    Column("product_id", Integer, ForeignKey("products.id"), index=True, nullable=True),
    Column("name", String),
    Column("sku", String),
    Column("size", String),
    Column("qty", Integer, nullable=False),
    Column("unit_price", Float, nullable=False),
    Column("image", String),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

addresses = Table(
    "addresses",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("address_id", String, unique=True, index=True),
    Column("user_id", Integer, ForeignKey("users.id"), index=True, nullable=False),
    Column("label", String),
    Column("street", String),
    Column("area", String),
    Column("city", String),
    Column("state", String),
    Column("pin", String),
    Column("country", String, default="India"),
    Column("is_default", Boolean, default=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now())
)

wishlist = Table(
    "wishlist",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), index=True, nullable=False),
    Column("product_id", Integer, ForeignKey("products.id"), index=True, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    UniqueConstraint("user_id", "product_id", name="uq_wishlist_user_product"),
)

recently_viewed = Table(
    "recently_viewed",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), index=True, nullable=True),
    Column("session_id", String, index=True, nullable=True),
    Column("product_id", Integer, ForeignKey("products.id"), index=True, nullable=False),
    Column("viewed_at", DateTime(timezone=True), server_default=func.now()),
)

reviews = Table(
    "reviews",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("product_id", Integer, ForeignKey("products.id"), index=True, nullable=False),
    Column("user_id", Integer, ForeignKey("users.id"), index=True, nullable=False),
    Column("user_name", String),
    Column("rating", Integer, nullable=False),
    Column("review", Text),
    Column("verified_purchase", Boolean, default=False),
    Column("status", String, default="pending_moderation"),
    Column("moderation_notes", Text),
    Column("moderated_by", Integer, ForeignKey("users.id"), nullable=True),
    Column("moderated_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), onupdate=func.now()),
)

notifications = Table(
    "notifications",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), index=True, nullable=True),
    Column("type", String, index=True),
    Column("message", String),
    Column("payload", JSON),
    Column("read", Boolean, default=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now())
)

otp_sessions = Table(
    "otp_sessions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("phone", String, index=True, nullable=False),
    Column("country_code", String),
    Column("otp_hash", String, nullable=False),
    Column("purpose", String, default="login", index=True),
    Column("attempts", Integer, default=0),
    Column("send_count", Integer, default=1),
    Column("ip_address", String, index=True),
    Column("last_sent_at", DateTime(timezone=True)),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("blocked_until", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

chat_messages = Table(
    "chat_messages",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("thread_id", String, index=True),
    Column("author", String),
    Column("message", String),
    Column("role", String),
    Column("timestamp", String),
    Column("read", Boolean, default=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now())
)

contacts = Table(
    "contacts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("email", String, nullable=False),
    Column("message", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

coupons = Table(
    "coupons",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String, unique=True, index=True),
    Column("discount", Float, nullable=False),
    Column("expiry", String, nullable=False),
    Column("usage_limit", Integer, default=1000),
    Column("usage_count", Integer, default=0),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

payment_events = Table(
    "payment_events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("event_id", String, unique=True, index=True),
    Column("payment_id", String, index=True, nullable=True),
    Column("order_id", String, index=True, nullable=True),
    Column("status", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


