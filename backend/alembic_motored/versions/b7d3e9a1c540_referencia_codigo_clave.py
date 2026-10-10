"""referencia: functional index on the code's match key

Revision ID: b7d3e9a1c540
Revises: f4b8d2a6c917
Create Date: 2026-10-10 18:00:00.000000

odd/tasks/motored-conteo-codigo-sin-guiones.md. A count reading whose
code misses the master by `upper(btrim)` is matched by its key: upper
case with every character outside `A-Z0-9` removed, so `9410912000S`
finds `94109-12000S` (`services/conteos/lecturas.py::resolver`). The
index keeps that lookup off a sequential scan of `referencia`. Its
expression must stay byte-for-byte equal to `lecturas._CLAVE_SQL`.

Not unique: two master codes may share a key; the count treats that
key as ambiguous. Downgrade drops the index.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7d3e9a1c540'
down_revision: Union[str, None] = 'f4b8d2a6c917'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDICE = 'ix_referencia_codigo_clave'
CLAVE = "regexp_replace(upper(codigo), '[^A-Z0-9]', '', 'g')"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"CREATE INDEX {_INDICE} ON referencia (({CLAVE}))")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"DROP INDEX IF EXISTS {_INDICE}")
