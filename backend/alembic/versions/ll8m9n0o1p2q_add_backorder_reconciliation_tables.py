"""add backorder reconciliation tables

Revision ID: ll8m9n0o1p2q
Revises: kk7l8m9n0o1p
Create Date: 2026-07-07 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = 'll8m9n0o1p2q'
down_revision = 'kk7l8m9n0o1p'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. backorder_reconciliations (header)
    op.create_table(
        'backorder_reconciliations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('lot_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_lots.id'), nullable=False),
        sa.Column('uploaded_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('file_name', sa.String(500), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('minio_object_name', sa.String(1000), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('is_invoice', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('uploaded_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('confirmed_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_br_lot_status', 'backorder_reconciliations', ['lot_id', 'status'])
    op.create_index('ix_br_lot_content_hash', 'backorder_reconciliations', ['lot_id', 'content_hash'])

    # 2. backorder_reconciliation_results (lines)
    op.create_table(
        'backorder_reconciliation_results',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('reconciliation_id', UUID(as_uuid=True),
                  sa.ForeignKey('backorder_reconciliations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('backorder_id', UUID(as_uuid=True), sa.ForeignKey('backorders.id'), nullable=True),
        sa.Column('spare_part_item_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_items.id'), nullable=True),
        sa.Column('part_number', sa.String(100), nullable=False),
        sa.Column('model_applicable', sa.String(255), nullable=True),
        sa.Column('qty_pending_snapshot', sa.Integer, nullable=True),
        sa.Column('qty_in_packing', sa.Integer, nullable=True),
        sa.Column('qty_applied', sa.Integer, nullable=True),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('result', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_brr_reconciliation', 'backorder_reconciliation_results', ['reconciliation_id'])
    op.create_index('ix_brr_backorder', 'backorder_reconciliation_results', ['backorder_id'])
    op.create_index('ix_brr_result', 'backorder_reconciliation_results', ['result'])


def downgrade() -> None:
    # Drop tables in reverse FK order
    op.drop_index('ix_brr_result', table_name='backorder_reconciliation_results')
    op.drop_index('ix_brr_backorder', table_name='backorder_reconciliation_results')
    op.drop_index('ix_brr_reconciliation', table_name='backorder_reconciliation_results')
    op.drop_table('backorder_reconciliation_results')

    op.drop_index('ix_br_lot_content_hash', table_name='backorder_reconciliations')
    op.drop_index('ix_br_lot_status', table_name='backorder_reconciliations')
    op.drop_table('backorder_reconciliations')
