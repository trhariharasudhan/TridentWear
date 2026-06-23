"""add admin_audit_logs table

Revision ID: 20260623_0006
Revises: 20260613_0005
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260623_0006"
down_revision = "20260613_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("target_entity", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admin_audit_logs_admin_id", "admin_audit_logs", ["admin_id"])
    op.create_index("ix_admin_audit_logs_action_type", "admin_audit_logs", ["action_type"])
    op.create_index("ix_admin_audit_logs_target_entity", "admin_audit_logs", ["target_entity"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_logs_target_entity", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_action_type", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_admin_id", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
