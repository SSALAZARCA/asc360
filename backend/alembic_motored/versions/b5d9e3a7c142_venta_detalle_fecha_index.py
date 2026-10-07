"""venta_detalle_fecha_index: index on venta_detalle(fecha)

Revision ID: b5d9e3a7c142
Revises: e8f50a4c1a9b
Create Date: 2026-10-08 13:00:00.000000

odd/motored-kpis-velocidad, S3. `ultima_fecha_venta` (the date of the latest loaded sale of a month, shown
as "fecha de datos" in the asesor detail and the daily report) now asks for the newest row of the month
(`ORDER BY fecha DESC LIMIT 1`). Without an index on `fecha` alone it had to read every sale of the month.

Built CONCURRENTLY, outside the migration's transaction (same `autocommit_block()` precedent as the enum
migrations), so loading sales is not blocked meanwhile. `IF NOT EXISTS` makes a retry after an interrupted
build safe (a failed concurrent build leaves an INVALID index that has to be dropped first).

Purely additive; downgrade drops the index.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b5d9e3a7c142'
down_revision: Union[str, None] = 'e8f50a4c1a9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDICE = 'ix_venta_detalle_fecha'


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDICE} ON venta_detalle (fecha)')


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {INDICE}')
