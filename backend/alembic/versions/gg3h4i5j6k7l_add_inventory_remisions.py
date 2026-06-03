"""add inventory remisions module

Revision ID: gg3h4i5j6k7l
Revises: ff2a3b4c5d6e
Create Date: 2026-06-03 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = 'gg3h4i5j6k7l'
down_revision = 'ff2a3b4c5d6e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. inventory_remisions (header)
    op.create_table(
        'inventory_remisions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='BORRADOR'),
        sa.Column('reference_lot_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_lots.id'), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('remision_number', sa.String(20), nullable=True, unique=True),
        sa.Column('dispatched_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('dispatched_at', sa.DateTime, nullable=True),
        sa.Column('cancelled_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('cancelled_at', sa.DateTime, nullable=True),
        sa.Column('cancellation_reason', sa.Text, nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_ir_status', 'inventory_remisions', ['status'])
    op.create_index('ix_ir_type', 'inventory_remisions', ['type'])
    op.create_index('ix_ir_created_at', 'inventory_remisions', ['created_at'])
    op.create_index('ix_ir_reference_lot', 'inventory_remisions', ['reference_lot_id'])

    # 2. inventory_remision_items (line items, mutable only while BORRADOR)
    op.create_table(
        'inventory_remision_items',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('remision_id', UUID(as_uuid=True), sa.ForeignKey('inventory_remisions.id'), nullable=False),
        sa.Column('spare_part_item_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_items.id'), nullable=False),
        sa.Column('part_number', sa.String(100), nullable=False),
        sa.Column('qty_dispatched', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('remision_id', 'spare_part_item_id', name='uq_remision_item'),
    )
    op.create_index('ix_iri_remision', 'inventory_remision_items', ['remision_id'])
    op.create_index('ix_iri_spare_part_item', 'inventory_remision_items', ['spare_part_item_id'])

    # 3. inventory_remision_movements (immutable ledger, no updated_at)
    op.create_table(
        'inventory_remision_movements',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('remision_id', UUID(as_uuid=True), sa.ForeignKey('inventory_remisions.id'), nullable=False),
        sa.Column('spare_part_item_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_items.id'), nullable=False),
        sa.Column('part_number', sa.String(100), nullable=False),
        sa.Column('delta', sa.Integer, nullable=False),
        sa.Column('movement_type', sa.String(20), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_irm_spare_part_item', 'inventory_remision_movements', ['spare_part_item_id'])
    op.create_index('ix_irm_remision', 'inventory_remision_movements', ['remision_id'])

    # 4. VIEW: spare_part_availability
    # qty_available = qty_physical + COALESCE(SUM(delta from movements), 0)
    # Filtered: only items with qty_physical IS NOT NULL (inspected items)
    op.execute("""
        CREATE OR REPLACE VIEW spare_part_availability AS
        SELECT
            spi.id,
            spi.part_number,
            spi.lot_id,
            spi.qty_physical + COALESCE(SUM(irm.delta), 0) AS qty_available
        FROM spare_part_items spi
        LEFT JOIN inventory_remision_movements irm ON irm.spare_part_item_id = spi.id
        WHERE spi.qty_physical IS NOT NULL
        GROUP BY spi.id, spi.part_number, spi.lot_id, spi.qty_physical
    """)


def downgrade() -> None:
    # Drop VIEW first (depends on the tables)
    op.execute("DROP VIEW IF EXISTS spare_part_availability")

    # Drop tables in reverse FK order
    op.drop_index('ix_irm_remision', table_name='inventory_remision_movements')
    op.drop_index('ix_irm_spare_part_item', table_name='inventory_remision_movements')
    op.drop_table('inventory_remision_movements')

    op.drop_index('ix_iri_spare_part_item', table_name='inventory_remision_items')
    op.drop_index('ix_iri_remision', table_name='inventory_remision_items')
    op.drop_table('inventory_remision_items')

    op.drop_index('ix_ir_reference_lot', table_name='inventory_remisions')
    op.drop_index('ix_ir_created_at', table_name='inventory_remisions')
    op.drop_index('ix_ir_type', table_name='inventory_remisions')
    op.drop_index('ix_ir_status', table_name='inventory_remisions')
    op.drop_table('inventory_remisions')
