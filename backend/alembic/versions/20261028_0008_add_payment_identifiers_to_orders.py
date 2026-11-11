"""add payment identifiers to orders

Revision ID: 20261028_0008
Revises: 20261028_0007
Create Date: 2026-10-28

Description:
Adds payment identifier columns and idempotency constraints to the 'orders' table:
- razorpay_order_id (String, unique, indexed)
- razorpay_payment_id (String, unique, indexed)
- idempotency_key (String, unique, indexed)
- coupon_status (String, indexed)
"""

from alembic import op
import sqlalchemy as sa


revision = "20261028_0008"
down_revision = "20261028_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("orders"):
        raise RuntimeError("Table 'orders' does not exist. Cannot add payment identifiers.")

    cols = {c["name"] for c in insp.get_columns("orders")}

    with op.batch_alter_table("orders") as batch_op:
        if "razorpay_order_id" not in cols:
            batch_op.add_column(sa.Column("razorpay_order_id", sa.String(), nullable=True))
            batch_op.create_index("ix_orders_razorpay_order_id", ["razorpay_order_id"], unique=True)

        if "razorpay_payment_id" not in cols:
            batch_op.add_column(sa.Column("razorpay_payment_id", sa.String(), nullable=True))
            batch_op.create_index("ix_orders_razorpay_payment_id", ["razorpay_payment_id"], unique=True)

        if "idempotency_key" not in cols:
            batch_op.add_column(sa.Column("idempotency_key", sa.String(), nullable=True))
            batch_op.create_index("ix_orders_idempotency_key", ["idempotency_key"], unique=True)

        if "coupon_status" not in cols:
            batch_op.add_column(sa.Column("coupon_status", sa.String(), nullable=True, server_default="none"))
            batch_op.create_index("ix_orders_coupon_status", ["coupon_status"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("orders"):
        return

    cols = {c["name"] for c in insp.get_columns("orders")}

    with op.batch_alter_table("orders") as batch_op:
        if "coupon_status" in cols:
            batch_op.drop_index("ix_orders_coupon_status")
            batch_op.drop_column("coupon_status")

        if "idempotency_key" in cols:
            batch_op.drop_index("ix_orders_idempotency_key")
            batch_op.drop_column("idempotency_key")

        if "razorpay_payment_id" in cols:
            batch_op.drop_index("ix_orders_razorpay_payment_id")
            batch_op.drop_column("razorpay_payment_id")

        if "razorpay_order_id" in cols:
            batch_op.drop_index("ix_orders_razorpay_order_id")
            batch_op.drop_column("razorpay_order_id")
