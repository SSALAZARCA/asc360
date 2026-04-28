"""add qty_physical to reconciliation_results and source/already_charged to backorders

Revision ID: a0b1c2d3e4f5
Revises: z9a0b1c2d3e4
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'a0b1c2d3e4f5'
down_revision = 'z9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reconciliation_results',
        sa.Column('qty_physical', sa.Integer(), nullable=True))

    op.add_column('backorders',
        sa.Column('source', sa.String(30), nullable=False, server_default='reconciliation'))
    op.add_column('backorders',
        sa.Column('already_charged', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    op.drop_column('reconciliation_results', 'qty_physical')
    op.drop_column('backorders', 'already_charged')
    op.drop_column('backorders', 'source')
