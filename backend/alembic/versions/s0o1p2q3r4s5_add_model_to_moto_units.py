"""add model column to shipment_moto_units

Revision ID: s0o1p2q3r4s5
Revises: r8n0o1p2q3r4
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        "shipment_moto_units",
        sa.Column("model", sa.String(255), nullable=True),
    )


def downgrade():
    op.drop_column("shipment_moto_units", "model")
