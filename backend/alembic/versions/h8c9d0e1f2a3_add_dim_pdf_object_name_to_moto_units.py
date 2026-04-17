"""add dim_pdf_object_name to shipment_moto_units

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-04-14

"""
from alembic import op
import sqlalchemy as sa

revision = 'h8c9d0e1f2a3'
down_revision = 'g7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'shipment_moto_units',
        sa.Column('dim_pdf_object_name', sa.String(500), nullable=True)
    )


def downgrade():
    op.drop_column('shipment_moto_units', 'dim_pdf_object_name')
