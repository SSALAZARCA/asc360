"""add moto_observations table and observation_id to shipment_moto_units

Revision ID: dd6e7f8a9b0c
Revises: cc5d6e7f8a9b
Create Date: 2026-05-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'dd6e7f8a9b0c'
down_revision = 'cc5d6e7f8a9b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'moto_observations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.execute("""
        INSERT INTO moto_observations (id, name) VALUES
        (gen_random_uuid(), 'VIN NO PERMITIDO'),
        (gen_random_uuid(), 'VIN REPETIDO'),
        (gen_random_uuid(), 'ERROR REFERENCIA'),
        (gen_random_uuid(), 'ERROR COLOR'),
        (gen_random_uuid(), 'CONSIGNACIÓN')
    """)
    op.add_column('shipment_moto_units', sa.Column('observation_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_moto_unit_observation',
        'shipment_moto_units', 'moto_observations',
        ['observation_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint('fk_moto_unit_observation', 'shipment_moto_units', type_='foreignkey')
    op.drop_column('shipment_moto_units', 'observation_id')
    op.drop_table('moto_observations')
