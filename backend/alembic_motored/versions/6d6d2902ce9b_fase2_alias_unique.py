"""fase2 alias unique

Revision ID: 6d6d2902ce9b
Revises: 890fe5b18174
Create Date: 2026-09-21 20:53:22.659095

Phase 1 "Staging Schema" (sdd/motored-pedidos-ingesta, Fase 2 "Ingesta").
Adds `UNIQUE(texto_normalizado)` to Fase 1's `sucursal_alias` table, which
shipped with NO constraint or index at all (verified against code). ADR-8
turns this column into a cache-first, hot resolution lookup (H11 prereq).
The `UNIQUE` constraint is backed by its own Postgres index -- no separate
`create_index` is needed.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6d6d2902ce9b'
down_revision: Union[str, None] = '890fe5b18174'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_sucursal_alias_texto_normalizado', 'sucursal_alias', ['texto_normalizado']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_sucursal_alias_texto_normalizado', 'sucursal_alias', type_='unique'
    )
