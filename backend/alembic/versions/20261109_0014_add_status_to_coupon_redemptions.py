"""add status column to coupon_redemptions

Revision ID: 20261109_0014
Revises: 20261109_0013
Create Date: 2026-11-09

Description:
Adds indexed 'status' column to 'coupon_redemptions' table
to represent reservation vs permanent redemption lifecycle for FBT offers.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261109_0014"
down_revision = "20261109_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("coupon_redemptions"):
        raise RuntimeError("Table 'coupon_redemptions' does not exist. Cannot add status column.")

    cols = {c["name"] for c in insp.get_columns("coupon_redemptions")}

    with op.batch_alter_table("coupon_redemptions") as batch_op:
        if "status" not in cols:
            batch_op.add_column(sa.Column("status", sa.String(), nullable=False, server_default="redeemed"))
            batch_op.create_index("ix_coupon_redemptions_status", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("coupon_redemptions"):
        return

    cols = {c["name"] for c in insp.get_columns("coupon_redemptions")}
    indexes = {ix["name"] for ix in insp.get_indexes("coupon_redemptions")}

    with op.batch_alter_table("coupon_redemptions") as batch_op:
        if "ix_coupon_redemptions_status" in indexes:
            batch_op.drop_index("ix_coupon_redemptions_status")
        if "status" in cols:
            batch_op.drop_column("status")
