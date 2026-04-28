"""add description_es and model_applicable to reconciliation_results

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reconciliation_results',
        sa.Column('description_es', sa.Text(), nullable=True))
    op.add_column('reconciliation_results',
        sa.Column('model_applicable', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('reconciliation_results', 'model_applicable')
    op.drop_column('reconciliation_results', 'description_es')
