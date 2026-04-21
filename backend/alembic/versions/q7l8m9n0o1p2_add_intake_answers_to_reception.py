"""add intake_answers to service_order_receptions

Revision ID: q7l8m9n0o1p2
Revises: p6k7l8m9n0o1
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'q7l8m9n0o1p2'
down_revision = 'p6k7l8m9n0o1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('service_order_receptions',
        sa.Column('intake_answers', JSONB, nullable=True, server_default='[]'))


def downgrade():
    op.drop_column('service_order_receptions', 'intake_answers')
