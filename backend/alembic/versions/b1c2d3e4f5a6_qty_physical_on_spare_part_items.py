"""add qty_physical to spare_part_items

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'b1c2d3e4f5a6'
down_revision = 'a0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('spare_part_items',
        sa.Column('qty_physical', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('spare_part_items', 'qty_physical')
