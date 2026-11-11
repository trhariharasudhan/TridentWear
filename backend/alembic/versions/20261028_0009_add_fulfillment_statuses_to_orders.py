"""add fulfillment statuses to orders

Revision ID: 20261028_0009
Revises: 20261028_0008
Create Date: 2026-10-28

Description:
Adds fulfillment tracking columns to the 'orders' table:
- stock_status (String, default 'pending', indexed)
- email_status (String, default 'pending', indexed)
"""

from alembic import op
import sqlalchemy as sa


revision = "20261028_0009"
down_revision = "20261028_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("orders"):
        raise RuntimeError("Table 'orders' does not exist. Cannot add fulfillment statuses.")

    cols = {c["name"] for c in insp.get_columns("orders")}

    with op.batch_alter_table("orders") as batch_op:
        if "stock_status" not in cols:
            batch_op.add_column(sa.Column("stock_status", sa.String(), nullable=True, server_default="pending"))
            batch_op.create_index("ix_orders_stock_status", ["stock_status"])

        if "email_status" not in cols:
            batch_op.add_column(sa.Column("email_status", sa.String(), nullable=True, server_default="pending"))
            batch_op.create_index("ix_orders_email_status", ["email_status"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("orders"):
        return

    cols = {c["name"] for c in insp.get_columns("orders")}

    with op.batch_alter_table("orders") as batch_op:
        if "email_status" in cols:
            batch_op.drop_index("ix_orders_email_status")
            batch_op.drop_column("email_status")

        if "stock_status" in cols:
            batch_op.drop_index("ix_orders_stock_status")
            batch_op.drop_column("stock_status")
