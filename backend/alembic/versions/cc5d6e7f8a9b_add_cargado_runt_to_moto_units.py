"""add cargado_runt to shipment_moto_units

Revision ID: cc5d6e7f8a9b
Revises: bb4c5d6e7f8a
Create Date: 2026-05-29

"""
from alembic import op
import sqlalchemy as sa

revision = 'cc5d6e7f8a9b'
down_revision = 'bb4c5d6e7f8a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'shipment_moto_units',
        sa.Column('cargado_runt', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade():
    op.drop_column('shipment_moto_units', 'cargado_runt')
