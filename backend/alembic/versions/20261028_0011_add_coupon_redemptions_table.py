"""add coupon_redemptions table

Revision ID: 20261028_0011
Revises: 20261028_0010
Create Date: 2026-10-28

Description:
Creates 'coupon_redemptions' table with a unique constraint on 'order_id'
for durable, order-bound coupon redemption idempotency.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261028_0011"
down_revision = "20261028_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("coupons"):
        raise RuntimeError("Table 'coupons' does not exist. Migration 20260613_0004/20261028_0007 must be applied first.")

    if not insp.has_table("coupon_redemptions"):
        op.create_table(
            "coupon_redemptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_id", sa.String(), nullable=False),
            sa.Column("coupon_code", sa.String(), sa.ForeignKey("coupons.code"), nullable=False),
            sa.Column("redeemed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_coupon_redemptions_order_id", "coupon_redemptions", ["order_id"], unique=True)
        op.create_index("ix_coupon_redemptions_coupon_code", "coupon_redemptions", ["coupon_code"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if insp.has_table("coupon_redemptions"):
        op.drop_index("ix_coupon_redemptions_coupon_code", table_name="coupon_redemptions")
        op.drop_index("ix_coupon_redemptions_order_id", table_name="coupon_redemptions")
        op.drop_table("coupon_redemptions")
