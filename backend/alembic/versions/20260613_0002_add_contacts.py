"""add contacts and chat columns

Revision ID: 20260613_0002
Revises: 20260510_0001
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260613_0002"
down_revision = "20260510_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Create contacts table ───────────────────────────────────────────
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # ── Add columns to chat_messages ───────────────────────────────────
    op.add_column("chat_messages", sa.Column("author", sa.String(), nullable=True))
    op.add_column("chat_messages", sa.Column("timestamp", sa.String(), nullable=True))


def downgrade() -> None:
    # ── Drop columns from chat_messages ───────────────────────────────
    op.drop_column("chat_messages", "timestamp")
    op.drop_column("chat_messages", "author")
    
    # ── Drop contacts table ───────────────────────────────────────────
    op.drop_table("contacts")
