"""backfill BACKORDER_PARCIAL para ítems con inspección física parcial

Revision ID: cc6d7e8f9a0b
Revises: bb5c6d7e8f9a
Create Date: 2026-06-02

Ítems con status=BACKORDER que ya tienen qty_physical > 0 pero qty_physical < qty_ordered
corresponden a casos donde el proveedor cobró todo pero físicamente llegó parcial.
El nuevo status BACKORDER_PARCIAL los distingue del backorder total (nada llegó).
"""
from alembic import op

revision = 'cc6d7e8f9a0b'
down_revision = 'bb5c6d7e8f9a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE spare_part_items
        SET status = 'BACKORDER_PARCIAL'
        WHERE status = 'BACKORDER'
          AND qty_physical IS NOT NULL
          AND qty_physical > 0
          AND qty_physical < qty_ordered
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE spare_part_items
        SET status = 'BACKORDER'
        WHERE status = 'BACKORDER_PARCIAL'
    """)
