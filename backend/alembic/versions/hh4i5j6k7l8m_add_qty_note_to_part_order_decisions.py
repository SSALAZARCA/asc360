"""add new_quantity and change_note to part_order_decisions

Revision ID: hh4i5j6k7l8m
Revises: gg3h4i5j6k7l
Create Date: 2026-06-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'hh4i5j6k7l8m'
down_revision = 'gg3h4i5j6k7l'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('part_order_decisions', sa.Column('new_quantity', sa.Integer(), nullable=True))
    op.add_column('part_order_decisions', sa.Column('change_note',  sa.String(500), nullable=True))


def downgrade():
    op.drop_column('part_order_decisions', 'change_note')
    op.drop_column('part_order_decisions', 'new_quantity')
