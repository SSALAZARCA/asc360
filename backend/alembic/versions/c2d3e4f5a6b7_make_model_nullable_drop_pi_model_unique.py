"""make model nullable and drop uq_shipment_pi_model constraint

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('uq_shipment_pi_model', 'shipment_orders', type_='unique')
    op.alter_column('shipment_orders', 'model',
                    existing_type=sa.String(255),
                    nullable=True)


def downgrade():
    op.alter_column('shipment_orders', 'model',
                    existing_type=sa.String(255),
                    nullable=False)
    op.create_unique_constraint('uq_shipment_pi_model', 'shipment_orders', ['pi_number', 'model'])
