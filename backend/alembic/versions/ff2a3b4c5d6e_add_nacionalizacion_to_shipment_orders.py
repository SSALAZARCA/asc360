"""add nacionalizacion to shipment_orders

Revision ID: ff2a3b4c5d6e
Revises: ee8f9a0b1c2d
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa

revision = 'ff2a3b4c5d6e'
down_revision = 'ee8f9a0b1c2d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('shipment_orders',
        sa.Column('nacionalizacion_status', sa.String(20), nullable=True)
    )
    op.add_column('shipment_orders',
        sa.Column('nacionalizacion_fecha', sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('shipment_orders', 'nacionalizacion_fecha')
    op.drop_column('shipment_orders', 'nacionalizacion_status')
