"""add moto_locations table and location_id to shipment_moto_units

Revision ID: aa3b4c5d6e7f
Revises: bb3c4d5e6f7a
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid as _uuid

revision = 'aa3b4c5d6e7f'
down_revision = 'bb3c4d5e6f7a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'moto_locations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # Seed the two existing locations
    op.execute("INSERT INTO moto_locations (id, name) VALUES (gen_random_uuid(), 'STRONG'), (gen_random_uuid(), 'MCA')")

    op.add_column('shipment_moto_units', sa.Column('location_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_moto_unit_location',
        'shipment_moto_units', 'moto_locations',
        ['location_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint('fk_moto_unit_location', 'shipment_moto_units', type_='foreignkey')
    op.drop_column('shipment_moto_units', 'location_id')
    op.drop_table('moto_locations')
