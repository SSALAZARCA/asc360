"""conteo.es_prueba: test counts that never block a real one

Revision ID: f4b8d2a6c917
Revises: c4e8a2d6f931
Create Date: 2026-10-10 12:00:00.000000

odd/tasks/motored-conteo-prueba.md. ADMIN may schedule a count as a test
(`es_prueba`). The flag defaults to false, so every existing count stays
real. The one-open-TOTAL-count-per-store unique index is rebuilt with
`AND NOT es_prueba`, so an open test count never blocks a real one.

Downgrade restores the old index and drops the column. It fails if a store
still has a real and a test count open at the same time; delete the test
counts first.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4b8d2a6c917'
down_revision: Union[str, None] = 'c4e8a2d6f931'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDICE = 'uq_conteo_total_abierto'
_ABIERTO = "tipo = 'TOTAL' AND estado IN ('EN_CONTEO', 'EN_RECONTEO')"


def _indice(condicion: str) -> None:
    op.create_index(
        _INDICE, 'conteo', ['sucursal_id'], unique=True,
        postgresql_where=sa.text(condicion))


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column('conteo', sa.Column(
        'es_prueba', sa.Boolean(), nullable=False,
        server_default=sa.text('false')))
    op.drop_index(_INDICE, table_name='conteo')
    _indice(_ABIERTO + " AND NOT es_prueba")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_index(_INDICE, table_name='conteo')
    _indice(_ABIERTO)
    op.drop_column('conteo', 'es_prueba')
