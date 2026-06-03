"""cleanup preliminary_fob en partes sin spare_part_item

Revision ID: dd7e8f9a0b1c
Revises: cc6d7e8f9a0b
Create Date: 2026-06-02

El endpoint de importación FOB PI escribía preliminary_fob en parts_references
aunque no existiera ningún spare_part_item para esa referencia. Esta migración
limpia esos registros huérfanos.
"""
from alembic import op

revision = 'dd7e8f9a0b1c'
down_revision = 'cc6d7e8f9a0b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE parts_references
        SET preliminary_fob = NULL
        WHERE preliminary_fob IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM spare_part_items spi
              WHERE UPPER(TRIM(REPLACE(spi.part_number, ' ', '')))
                  = UPPER(TRIM(REPLACE(parts_references.factory_part_number, ' ', '')))
          )
    """)


def downgrade() -> None:
    pass
