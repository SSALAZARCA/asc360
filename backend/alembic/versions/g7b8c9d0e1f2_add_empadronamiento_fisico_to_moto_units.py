"""add empadronamiento_fisico columns to shipment_moto_units

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-14

"""
from alembic import op
import sqlalchemy as sa

revision = 'g7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'shipment_moto_units',
        sa.Column('empadronamiento_fisico_enviado', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column(
        'shipment_moto_units',
        sa.Column('empadronamiento_fisico_fecha', sa.DateTime(), nullable=True)
    )


def downgrade():
    op.drop_column('shipment_moto_units', 'empadronamiento_fisico_fecha')
    op.drop_column('shipment_moto_units', 'empadronamiento_fisico_enviado')
