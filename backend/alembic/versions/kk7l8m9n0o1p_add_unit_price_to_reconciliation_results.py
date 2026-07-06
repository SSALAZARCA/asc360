"""add unit_price to reconciliation_results

Revision ID: kk7l8m9n0o1p
Revises: jj6k7l8m9n0o
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'kk7l8m9n0o1p'
down_revision = 'jj6k7l8m9n0o'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reconciliation_results',
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=True))


def downgrade():
    op.drop_column('reconciliation_results', 'unit_price')
