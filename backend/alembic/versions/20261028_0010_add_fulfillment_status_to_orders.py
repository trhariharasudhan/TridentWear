"""add fulfillment_status to orders

Revision ID: 20261028_0010
Revises: 20261028_0009
Create Date: 2026-10-28

Description:
Adds 'fulfillment_status' column to the 'orders' table:
- fulfillment_status (String, default 'pending', indexed, nullable=True)
"""

from alembic import op
import sqlalchemy as sa


revision = "20261028_0010"
down_revision = "20261028_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("orders"):
        raise RuntimeError("Table 'orders' does not exist. Cannot add fulfillment_status.")

    cols = {c["name"] for c in insp.get_columns("orders")}

    with op.batch_alter_table("orders") as batch_op:
        if "fulfillment_status" not in cols:
            batch_op.add_column(sa.Column("fulfillment_status", sa.String(), nullable=True, server_default="pending"))
            batch_op.create_index("ix_orders_fulfillment_status", ["fulfillment_status"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("orders"):
        return

    cols = {c["name"] for c in insp.get_columns("orders")}

    with op.batch_alter_table("orders") as batch_op:
        if "fulfillment_status" in cols:
            batch_op.drop_index("ix_orders_fulfillment_status")
            batch_op.drop_column("fulfillment_status")
