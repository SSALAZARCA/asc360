"""add avg_fob_cost to parts_references, part_cost_history table, and pricing SystemConfig keys

Revision ID: aa1b2c3d4e5f
Revises: z9a0b1c2d3e4
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'aa1b2c3d4e5f'
down_revision = 'z9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('parts_references',
        sa.Column('avg_fob_cost', sa.Numeric(12, 4), nullable=True))
    op.add_column('parts_references',
        sa.Column('total_fob_qty', sa.Integer(), nullable=True))
    op.add_column('parts_references',
        sa.Column('last_cost_updated', sa.DateTime(), nullable=True))

    op.create_table(
        'part_cost_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('factory_part_number', sa.String(100),
                  sa.ForeignKey('parts_references.factory_part_number', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('lot_identifier', sa.String(100), nullable=False),
        sa.Column('part_number_used', sa.String(100), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 4), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_pch_factory_part', 'part_cost_history', ['factory_part_number'])
    op.create_index('ix_pch_recorded_at',  'part_cost_history', ['recorded_at'])

    op.execute("""
        INSERT INTO system_config (key, value, updated_at)
        VALUES
            ('pricing.import_factor',      '1.42', NOW()),
            ('pricing.provider_margin',    '0.35', NOW()),
            ('pricing.distributor_margin', '0.35', NOW()),
            ('pricing.iva_rate',           '0.19', NOW())
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade():
    op.execute("""
        DELETE FROM system_config
        WHERE key IN (
            'pricing.import_factor', 'pricing.provider_margin',
            'pricing.distributor_margin', 'pricing.iva_rate'
        )
    """)
    op.drop_index('ix_pch_recorded_at',  table_name='part_cost_history')
    op.drop_index('ix_pch_factory_part', table_name='part_cost_history')
    op.drop_table('part_cost_history')
    op.drop_column('parts_references', 'last_cost_updated')
    op.drop_column('parts_references', 'total_fob_qty')
    op.drop_column('parts_references', 'avg_fob_cost')
