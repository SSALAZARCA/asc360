"""add separada_nacionalizacion to shipment_moto_units

Revision ID: ee7f8a9b0c1d
Revises: dd6e7f8a9b0c
Create Date: 2026-05-29

"""
from alembic import op
import sqlalchemy as sa

revision = 'ee7f8a9b0c1d'
down_revision = 'dd6e7f8a9b0c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'shipment_moto_units',
        sa.Column('separada_nacionalizacion', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade():
    op.drop_column('shipment_moto_units', 'separada_nacionalizacion')
