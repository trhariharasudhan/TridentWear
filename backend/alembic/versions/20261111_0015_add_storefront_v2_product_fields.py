"""add storefront v2 product fields

Revision ID: 20261111_0015
Revises: 20261109_0014
Create Date: 2026-11-11

Description:
The v2 storefront uses slug / style_code / mrp / color_hex / gallery / tryon on
products. Without these columns the SQL adapter silently drops them on insert,
so MRP, galleries and AI Fit Check anchors vanished in postgres mode.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261111_0015"
down_revision = "20261109_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("slug", sa.String(), nullable=True))
    op.add_column("products", sa.Column("style_code", sa.String(), nullable=True))
    op.add_column("products", sa.Column("mrp", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("color_hex", sa.String(), nullable=True))
    op.add_column("products", sa.Column("gallery", sa.JSON(), nullable=True))
    op.add_column("products", sa.Column("tryon", sa.JSON(), nullable=True))
    op.create_index("ix_products_slug", "products", ["slug"])
    op.create_index("ix_products_style_code", "products", ["style_code"])


def downgrade() -> None:
    op.drop_index("ix_products_style_code", table_name="products")
    op.drop_index("ix_products_slug", table_name="products")
    for col in ("tryon", "gallery", "color_hex", "mrp", "style_code", "slug"):
        op.drop_column("products", col)
