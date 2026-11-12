"""persist signup OTP, bundle offer id and simulated-payment flag

Revision ID: 20261111_0016
Revises: 20261111_0015
Create Date: 2026-11-11

Description:
In postgres mode the SQL adapter dropped keys without a column, which broke:
  * users.otp / users.otp_expiry      -> email signup could never be verified
  * orders.fbt_offer_id / fbt_token   -> cancelling never released a reserved BUNDLE10 offer
  * orders.payment_simulated          -> admins could not tell simulated payments from real ones
"""

from alembic import op
import sqlalchemy as sa

revision = "20261111_0016"
down_revision = "20261111_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("otp", sa.String(), nullable=True))
    op.add_column("users", sa.Column("otp_expiry", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("fbt_offer_id", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("fbt_token", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("payment_simulated", sa.Boolean(), nullable=True, server_default=sa.false()))
    op.create_index("ix_orders_fbt_offer_id", "orders", ["fbt_offer_id"])
    op.create_index("ix_orders_payment_simulated", "orders", ["payment_simulated"])


def downgrade() -> None:
    op.drop_index("ix_orders_payment_simulated", table_name="orders")
    op.drop_index("ix_orders_fbt_offer_id", table_name="orders")
    for col in ("payment_simulated", "fbt_token", "fbt_offer_id"):
        op.drop_column("orders", col)
    op.drop_column("users", "otp_expiry")
    op.drop_column("users", "otp")
