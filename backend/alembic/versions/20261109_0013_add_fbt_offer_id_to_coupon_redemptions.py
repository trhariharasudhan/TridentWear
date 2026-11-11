"""add fbt offer_id to coupon_redemptions

Revision ID: 20261109_0013
Revises: 20261028_0012
Create Date: 2026-11-09

Description:
Adds unique, nullable 'offer_id' column to 'coupon_redemptions' table
for replay protection of single-use FBT offer tokens across orders.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261109_0013"
down_revision = "20261028_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("coupon_redemptions"):
        raise RuntimeError("Table 'coupon_redemptions' does not exist. Cannot add offer_id column.")

    cols = {c["name"] for c in insp.get_columns("coupon_redemptions")}

    with op.batch_alter_table("coupon_redemptions") as batch_op:
        if "offer_id" not in cols:
            batch_op.add_column(sa.Column("offer_id", sa.String(), nullable=True))
            batch_op.create_index("ix_coupon_redemptions_offer_id", ["offer_id"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("coupon_redemptions"):
        return

    cols = {c["name"] for c in insp.get_columns("coupon_redemptions")}
    indexes = {ix["name"] for ix in insp.get_indexes("coupon_redemptions")}

    with op.batch_alter_table("coupon_redemptions") as batch_op:
        if "ix_coupon_redemptions_offer_id" in indexes:
            batch_op.drop_index("ix_coupon_redemptions_offer_id")
        if "offer_id" in cols:
            batch_op.drop_column("offer_id")
