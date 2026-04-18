"""add order_date to shipment_orders

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-04-18

"""
from alembic import op
import sqlalchemy as sa

revision = 'i9d0e1f2a3b4'
down_revision = 'h8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('shipment_orders', sa.Column('order_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('shipment_orders', 'order_date')
