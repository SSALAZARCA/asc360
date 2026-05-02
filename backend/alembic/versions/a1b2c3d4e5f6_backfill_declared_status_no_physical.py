"""backfill DECLARED status for items received without physical inspection

Revision ID: a1b2c3d4e5f6
Revises: z9a0b1c2d3e4
Create Date: 2026-05-02

Items reconciliados con código anterior quedaron en RECEIVED aunque nunca
tuvieron inspección física (qty_physical IS NULL). El nuevo flujo los marca
DECLARED hasta que se confirme el inventario físico. Esta migración corrige
los datos existentes sin tocar items que ya pasaron por inspección física.
"""
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = 'z9a0b1c2d3e4'
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
