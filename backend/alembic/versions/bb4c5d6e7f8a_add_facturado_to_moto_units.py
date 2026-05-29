"""add facturado to shipment_moto_units

Revision ID: bb4c5d6e7f8a
Revises: aa3b4c5d6e7f
Create Date: 2026-05-29

"""
from alembic import op
import sqlalchemy as sa

revision = 'bb4c5d6e7f8a'
down_revision = 'aa3b4c5d6e7f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'shipment_moto_units',
        sa.Column('facturado', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade():
    op.drop_column('shipment_moto_units', 'facturado')
