"""align coupons schema

Revision ID: 20261028_0007
Revises: 20260623_0006
Create Date: 2026-10-28

Description:
Aligns the 'coupons' table with the canonical application schema:
- Renames 'discount' to 'discount_pct' (Float) or creates 'discount_pct' if missing.
- Renames 'expiry' to 'expires_at' (String) or creates 'expires_at' if missing.
- Adds 'is_active' (Boolean, default True) if missing.

Downgrade Limitations:
Downgrade reverts 'discount_pct' back to 'discount' and 'expires_at' back to 'expiry'.
The 'is_active' column is dropped because the historical migration 20260613_0004
did not support an active flag; any coupons marked as inactive will lose their
inactive status and become active again under the legacy schema.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261028_0007"
down_revision = "20260623_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("coupons"):
        raise RuntimeError("Table 'coupons' does not exist. Migration 20260613_0004 must be applied first before aligning schema.")

    cols = {c["name"] for c in insp.get_columns("coupons")}

    with op.batch_alter_table("coupons") as batch_op:
        if "discount" in cols and "discount_pct" not in cols:
            batch_op.alter_column("discount", new_column_name="discount_pct", existing_type=sa.Float())
        elif "discount_pct" not in cols:
            batch_op.add_column(sa.Column("discount_pct", sa.Float(), nullable=False, server_default="0.0"))

        if "expiry" in cols and "expires_at" not in cols:
            batch_op.alter_column("expiry", new_column_name="expires_at", existing_type=sa.String())
        elif "expires_at" not in cols:
            batch_op.add_column(sa.Column("expires_at", sa.String(), nullable=False, server_default="2099-12-31"))

        if "is_active" not in cols:
            batch_op.add_column(sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("coupons"):
        return

    cols = {c["name"] for c in insp.get_columns("coupons")}

    with op.batch_alter_table("coupons") as batch_op:
        if "discount_pct" in cols and "discount" not in cols:
            batch_op.alter_column("discount_pct", new_column_name="discount", existing_type=sa.Float())
        if "expires_at" in cols and "expiry" not in cols:
            batch_op.alter_column("expires_at", new_column_name="expiry", existing_type=sa.String())
        if "is_active" in cols:
            batch_op.drop_column("is_active")
