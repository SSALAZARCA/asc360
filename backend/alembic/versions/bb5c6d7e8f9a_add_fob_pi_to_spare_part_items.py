"""add fob_pi to spare_part_items

Revision ID: bb5c6d7e8f9a
Revises: aa4b5c6d7e8f
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'bb5c6d7e8f9a'
down_revision = 'aa4b5c6d7e8f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('spare_part_items',
        sa.Column('fob_pi', sa.Numeric(12, 4), nullable=True))


def downgrade():
    op.drop_column('spare_part_items', 'fob_pi')
