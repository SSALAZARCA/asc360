"""add original_quantity to part_order_decisions

Revision ID: ii5j6k7l8m9n
Revises: hh4i5j6k7l8m
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'ii5j6k7l8m9n'
down_revision = 'hh4i5j6k7l8m'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('part_order_decisions', sa.Column('original_quantity', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('part_order_decisions', 'original_quantity')
