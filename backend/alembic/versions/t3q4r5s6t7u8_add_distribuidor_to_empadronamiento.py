"""add distribuidor fields to empadronamiento fisico

Revision ID: t3q4r5s6t7u8
Revises: s0o1p2q3r4s5
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 't3q4r5s6t7u8'
down_revision = 's0o1p2q3r4s5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'shipment_moto_units',
        sa.Column(
            'empadronamiento_fisico_distribuidor_id',
            UUID(as_uuid=True),
            nullable=True,
        )
    )
    op.create_foreign_key(
        'fk_moto_unit_distribuidor',
        'shipment_moto_units', 'tenants',
        ['empadronamiento_fisico_distribuidor_id'], ['id'],
        ondelete='SET NULL',
    )
    op.add_column(
        'shipment_moto_units',
        sa.Column('empadronamiento_fisico_distribuidor_nombre', sa.String(255), nullable=True)
    )


def downgrade():
    op.drop_constraint('fk_moto_unit_distribuidor', 'shipment_moto_units', type_='foreignkey')
    op.drop_column('shipment_moto_units', 'empadronamiento_fisico_distribuidor_nombre')
    op.drop_column('shipment_moto_units', 'empadronamiento_fisico_distribuidor_id')
