"""add description_es_manual to parts_references for manual overrides

Revision ID: z9a0b1c2d3e4
Revises: y8z9a0b1c2d3
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'z9a0b1c2d3e4'
down_revision = 'y8z9a0b1c2d3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('parts_references',
        sa.Column('description_es_manual', sa.String(500), nullable=True))


def downgrade():
    op.drop_column('parts_references', 'description_es_manual')
