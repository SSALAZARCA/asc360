"""normalize parts: add parts_references, remove duplicate columns from items

Revision ID: x7y8z9a0b1c2
Revises: w6x7y8z9a0b1
Create Date: 2026-04-26

"""
from alembic import op
import sqlalchemy as sa

revision = 'x7y8z9a0b1c2'
down_revision = 'w6x7y8z9a0b1'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Tabla de referencias únicas de partes
    op.create_table(
        'parts_references',
        sa.Column('factory_part_number', sa.String(100), primary_key=True),
        sa.Column('um_part_number',      sa.String(100), nullable=False),
        sa.Column('description',         sa.String(255), nullable=False),
        sa.Column('unit',                sa.String(20),  nullable=True),
    )
    op.create_index('ix_parts_references_um_part_number', 'parts_references', ['um_part_number'])

    # 2. Limpiar índices y columnas redundantes de parts_manual_items
    op.drop_index('ix_parts_manual_items_factory_part_number', table_name='parts_manual_items')
    op.drop_index('ix_parts_manual_items_um_part_number',      table_name='parts_manual_items')
    op.drop_column('parts_manual_items', 'um_part_number')
    op.drop_column('parts_manual_items', 'description')
    op.drop_column('parts_manual_items', 'unit')
    op.drop_column('parts_manual_items', 'qty')

    # 3. Agregar FK en factory_part_number
    op.create_foreign_key(
        'fk_parts_items_reference',
        'parts_manual_items', 'parts_references',
        ['factory_part_number'], ['factory_part_number'],
        ondelete='RESTRICT',
    )


def downgrade():
    op.drop_constraint('fk_parts_items_reference', 'parts_manual_items', type_='foreignkey')
    op.add_column('parts_manual_items', sa.Column('qty',          sa.Integer,     nullable=True))
    op.add_column('parts_manual_items', sa.Column('unit',         sa.String(20),  nullable=True))
    op.add_column('parts_manual_items', sa.Column('description',  sa.String(255), nullable=False, server_default=''))
    op.add_column('parts_manual_items', sa.Column('um_part_number', sa.String(100), nullable=False, server_default=''))
    op.create_index('ix_parts_manual_items_um_part_number',      'parts_manual_items', ['um_part_number'])
    op.create_index('ix_parts_manual_items_factory_part_number', 'parts_manual_items', ['factory_part_number'])
    op.drop_table('parts_references')
