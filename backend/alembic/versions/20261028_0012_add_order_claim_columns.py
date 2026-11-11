"""add order claim columns to orders

Revision ID: 20261028_0012
Revises: 20261028_0011
Create Date: 2026-10-28

Description:
Adds fulfillment claim fields to the 'orders' table for worker lease coordination:
- claim_token (String, indexed, nullable=True): Unique token for active lease
- claim_expires_at (DateTime(timezone=True), indexed, nullable=True): Expiration of active lease
- claim_owner (String, nullable=True): Telemetry identifier of holding worker
"""

from alembic import op
import sqlalchemy as sa


revision = "20261028_0012"
down_revision = "20261028_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("orders"):
        raise RuntimeError("Table 'orders' does not exist. Cannot add order claim columns.")

    cols = {c["name"] for c in insp.get_columns("orders")}

    with op.batch_alter_table("orders") as batch_op:
        if "claim_token" not in cols:
            batch_op.add_column(sa.Column("claim_token", sa.String(), nullable=True))
            batch_op.create_index("ix_orders_claim_token", ["claim_token"])

        if "claim_expires_at" not in cols:
            batch_op.add_column(sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.create_index("ix_orders_claim_expires_at", ["claim_expires_at"])

        if "claim_owner" not in cols:
            batch_op.add_column(sa.Column("claim_owner", sa.String(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("orders"):
        return

    cols = {c["name"] for c in insp.get_columns("orders")}

    with op.batch_alter_table("orders") as batch_op:
        if "claim_owner" in cols:
            batch_op.drop_column("claim_owner")

        if "claim_expires_at" in cols:
            batch_op.drop_index("ix_orders_claim_expires_at")
            batch_op.drop_column("claim_expires_at")

        if "claim_token" in cols:
            batch_op.drop_index("ix_orders_claim_token")
            batch_op.drop_column("claim_token")
