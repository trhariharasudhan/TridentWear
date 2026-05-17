"""launch readiness schema

Revision ID: 20260510_0001
Revises:
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260510_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("gender", sa.String(), nullable=True),
        sa.Column("otp_verification_status", sa.Boolean(), nullable=True),
        sa.Column("profile_completed_status", sa.Boolean(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_user_id", "users", ["user_id"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=True),
        sa.Column("image", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tag", sa.String(), nullable=True),
        sa.Column("sizes", sa.JSON(), nullable=True),
        sa.Column("featured", sa.Boolean(), nullable=True),
        sa.Column("cloth_type", sa.String(), nullable=True),
        sa.Column("base_color", sa.String(), nullable=True),
        sa.Column("fabric", sa.String(), nullable=True),
        sa.Column("material", sa.String(), nullable=True),
        sa.Column("gsm", sa.Integer(), nullable=True),
        sa.Column("fit_type", sa.String(), nullable=True),
        sa.Column("neck_type", sa.String(), nullable=True),
        sa.Column("design_type", sa.String(), nullable=True),
        sa.Column("design_color", sa.String(), nullable=True),
        sa.Column("print_method", sa.JSON(), nullable=True),
        sa.Column("wash_care_label", sa.Boolean(), nullable=True),
        sa.Column("wash_care", sa.JSON(), nullable=True),
        sa.Column("size_quantities", sa.JSON(), nullable=True),
        sa.Column("tag_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_featured", "products", ["featured"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("items", sa.JSON(), nullable=True),
        sa.Column("total", sa.Float(), nullable=True),
        sa.Column("subtotal", sa.Float(), nullable=True),
        sa.Column("discount_amount", sa.Float(), nullable=True),
        sa.Column("coupon_code", sa.String(), nullable=True),
        sa.Column("customer", sa.JSON(), nullable=True),
        sa.Column("shipping", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("payment_method", sa.String(), nullable=True),
        sa.Column("payment_status", sa.String(), nullable=True),
        sa.Column("tracking_id", sa.String(), nullable=True),
        sa.Column("courier", sa.String(), nullable=True),
        sa.Column("estimated_delivery", sa.String(), nullable=True),
        sa.Column("test_mode", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_order_id", "orders", ["order_id"], unique=True)
    op.create_index("ix_orders_payment_status", "orders", ["payment_status"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_test_mode", "orders", ["test_mode"])
    op.create_index("ix_orders_user_id", "orders", ["user_id"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("sku", sa.String(), nullable=True),
        sa.Column("size", sa.String(), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("image", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"])

    op.create_table(
        "addresses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("address_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("street", sa.String(), nullable=True),
        sa.Column("area", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=True),
        sa.Column("pin", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_addresses_address_id", "addresses", ["address_id"], unique=True)
    op.create_index("ix_addresses_user_id", "addresses", ["user_id"])

    op.create_table(
        "wishlist",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "product_id", name="uq_wishlist_user_product"),
    )
    op.create_index("ix_wishlist_product_id", "wishlist", ["product_id"])
    op.create_index("ix_wishlist_user_id", "wishlist", ["user_id"])

    op.create_table(
        "recently_viewed",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_recently_viewed_product_id", "recently_viewed", ["product_id"])
    op.create_index("ix_recently_viewed_session_id", "recently_viewed", ["session_id"])
    op.create_index("ix_recently_viewed_user_id", "recently_viewed", ["user_id"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("user_name", sa.String(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review", sa.Text(), nullable=True),
        sa.Column("verified_purchase", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("moderation_notes", sa.Text(), nullable=True),
        sa.Column("moderated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reviews_product_id", "reviews", ["product_id"])
    op.create_index("ix_reviews_status", "reviews", ["status"])
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    op.create_table(
        "otp_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("country_code", sa.String(), nullable=True),
        sa.Column("otp_hash", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("send_count", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_otp_sessions_ip_address", "otp_sessions", ["ip_address"])
    op.create_index("ix_otp_sessions_phone", "otp_sessions", ["phone"])
    op.create_index("ix_otp_sessions_purpose", "otp_sessions", ["purpose"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_thread_id", "chat_messages", ["thread_id"])


def downgrade() -> None:
    for table_name in [
        "chat_messages",
        "otp_sessions",
        "notifications",
        "reviews",
        "recently_viewed",
        "wishlist",
        "addresses",
        "order_items",
        "orders",
        "products",
        "users",
    ]:
        op.drop_table(table_name)
