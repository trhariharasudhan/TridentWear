"""add coupons table

Revision ID: 20260613_0004
Revises: 20260613_0003
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260613_0004"
down_revision = "20260613_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("discount", sa.Float(), nullable=False),
        sa.Column("expiry", sa.String(), nullable=False),
        sa.Column("usage_limit", sa.Integer(), server_default="1000", nullable=False),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_coupons_code", "coupons", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_coupons_code", table_name="coupons")
    op.drop_table("coupons")
