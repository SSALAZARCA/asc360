"""add model_year to shipment_moto_units

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-13

"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'shipment_moto_units',
        sa.Column('model_year', sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column('shipment_moto_units', 'model_year')
