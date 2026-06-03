"""add executed_at to part_order_decisions

Revision ID: ee8f9a0b1c2d
Revises: dd7e8f9a0b1c
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'ee8f9a0b1c2d'
down_revision = 'dd7e8f9a0b1c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('part_order_decisions',
        sa.Column('executed_at', sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('part_order_decisions', 'executed_at')
