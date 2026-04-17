"""add_order_work_logs_and_parts

Revision ID: a1b2c3d4e5f6
Revises: e92c73f66541
Create Date: 2026-04-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e92c73f66541'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'order_work_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('service_orders.id'), nullable=False),
        sa.Column('history_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('order_history.id'), nullable=True),
        sa.Column('diagnosis', sa.String(2000), nullable=False),
        sa.Column('media_urls', postgresql.JSONB(), nullable=True),
        sa.Column('recorded_by_telegram_id', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_order_work_logs_order_id', 'order_work_logs', ['order_id'])

    op.create_table(
        'order_parts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('service_orders.id'), nullable=False),
        sa.Column('reference', sa.String(100), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('part_type', sa.Enum('warranty', 'paid', 'quote', name='orderparttype'), nullable=False, server_default='paid'),
        sa.Column('status', sa.Enum('pending', 'available', 'applied', name='orderpartstatus'), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_order_parts_order_id', 'order_parts', ['order_id'])


def downgrade() -> None:
    op.drop_index('ix_order_parts_order_id', table_name='order_parts')
    op.drop_table('order_parts')
    op.drop_index('ix_order_work_logs_order_id', table_name='order_work_logs')
    op.drop_table('order_work_logs')
    op.execute("DROP TYPE IF EXISTS orderparttype")
    op.execute("DROP TYPE IF EXISTS orderpartstatus")
