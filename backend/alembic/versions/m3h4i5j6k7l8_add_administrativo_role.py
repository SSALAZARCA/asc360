"""add administrativo role

Revision ID: m3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'm3h4i5j6k7l8'
down_revision = 'l2g3h4i5j6k7'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE role ADD VALUE IF NOT EXISTS 'administrativo'"))


def downgrade():
    pass
