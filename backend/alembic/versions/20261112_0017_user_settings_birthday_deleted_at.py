"""user settings, birthday and deleted_at

Revision ID: 20261112_0017
Revises: 20261111_0016
Create Date: 2026-11-12

Description:
Notification preferences (`settings`) were accepted by the profile API but had no
column, so they were silently dropped in postgres mode. Also adds `birthday` and
`deleted_at` for the account-deletion (anonymise) flow.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261112_0017"
down_revision = "20261111_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("settings", sa.JSON(), nullable=True))
    op.add_column("users", sa.Column("birthday", sa.String(), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for col in ("deleted_at", "birthday", "settings"):
        op.drop_column("users", col)
