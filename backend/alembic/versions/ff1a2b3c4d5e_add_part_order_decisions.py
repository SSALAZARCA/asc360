"""add part_order_decisions table

Revision ID: ff1a2b3c4d5e
Revises: ee7f8a9b0c1d
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'ff1a2b3c4d5e'
down_revision = 'ee7f8a9b0c1d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'part_order_decisions',
        sa.Column('factory_part_number', sa.String(100), nullable=False),
        sa.Column('lot_identifier',      sa.String(100), nullable=False),
        sa.Column('decision',            sa.String(20),  nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_by', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.PrimaryKeyConstraint('factory_part_number', 'lot_identifier'),
    )
    op.create_index('ix_pod_lot', 'part_order_decisions', ['lot_identifier'])


def downgrade():
    op.drop_index('ix_pod_lot', table_name='part_order_decisions')
    op.drop_table('part_order_decisions')
