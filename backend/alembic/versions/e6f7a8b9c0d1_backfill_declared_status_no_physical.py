"""backfill DECLARED status for items received without physical inspection

Revision ID: e6f7a8b9c0d1
Revises: d3e4f5a6b7c8
Create Date: 2026-05-02

Items reconciliados con código anterior quedaron en RECEIVED aunque nunca
tuvieron inspección física (qty_physical IS NULL). El nuevo flujo los marca
DECLARED hasta que se confirme el inventario físico.
"""
from alembic import op

revision = 'e6f7a8b9c0d1'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE spare_part_items
        SET status = 'DECLARED'
        WHERE status = 'RECEIVED'
          AND qty_physical IS NULL
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE spare_part_items
        SET status = 'RECEIVED'
        WHERE status = 'DECLARED'
          AND qty_physical IS NULL
    """)
