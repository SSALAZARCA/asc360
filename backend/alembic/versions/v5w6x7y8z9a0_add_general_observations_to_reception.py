"""add general_observations to service_order_receptions

Revision ID: v5w6x7y8z9a0
Revises: u4v5w6x7y8z9
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa

revision = 'v5w6x7y8z9a0'
down_revision = 'u4v5w6x7y8z9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'service_order_receptions',
        sa.Column('general_observations', sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column('service_order_receptions', 'general_observations')
