"""add invoiced flag to inventory_remisions

Revision ID: b3c4d5e6f7a8
Revises: p2q3r4s5t6u7
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'b3c4d5e6f7a8'
down_revision = 'p2q3r4s5t6u7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('inventory_remisions',
        sa.Column('invoiced', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('inventory_remisions', 'invoiced')
