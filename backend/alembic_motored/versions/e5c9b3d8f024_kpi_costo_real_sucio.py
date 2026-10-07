"""kpi_costo_real_sucio: rebuild the KPI summaries with the real sale cost

Revision ID: e5c9b3d8f024
Revises: d2b7a94e5c61
Create Date: 2026-10-07 10:00:00.000000

The KPI margin now prices each sales line with `venta_detalle.costo` (the real
ERP cost) when it has one. The summaries store the priced cost per line, so
they must be derived again with the new rule: this marks the state row dirty and
the supervisor loop rebuilds them. A summary that was never built has no state
row and is left alone (the UPDATE touches nothing).

Downgrade: nothing to undo (a dirty summary only triggers one more rebuild).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5c9b3d8f024'
down_revision: Union[str, None] = 'd2b7a94e5c61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE kpi_resumen_estado SET sucio = true WHERE id = 1")


def downgrade() -> None:
    pass
