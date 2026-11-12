"""site_settings table (admin-editable storefront)

Revision ID: 20261112_0018
Revises: 20261112_0017
Create Date: 2026-11-12
"""

from alembic import op
import sqlalchemy as sa

revision = "20261112_0018"
down_revision = "20261112_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("site_settings")
