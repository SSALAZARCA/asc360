"""caso detractor responsable backfill

Revision ID: a7c3e91d5b20
Revises: f2a6d83b9e14
Create Date: 2026-09-30 12:00:00.000000

Business rule: the "Responsable" (`caso_detractor.asignado_a`) of a detractor
case is the first USER who records anything in its history. Until now it was
only set when moving to EN_GESTION, so cases with a manual action but no
"Tomar caso" still show "Sin asignar". This backfills those cases with the
author of their earliest user-authored history entry (system entries, with
usuario_id NULL, never count).

Data-only and idempotent: it only touches rows where `asignado_a IS NULL`, so
a second run (or a run after the application already assigns) changes nothing.
The append-only trigger guards `caso_detractor_accion`, which is only read
here; the UPDATE targets `caso_detractor`.

Downgrade: documented no-op. After the fact there is no way to tell which
assignments came from this backfill and which were made by users, and clearing
them would destroy real data.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7c3e91d5b20'
down_revision: Union[str, None] = 'f2a6d83b9e14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BACKFILL = """
UPDATE caso_detractor c
SET asignado_a = (
    SELECT a.usuario_id FROM caso_detractor_accion a
    WHERE a.caso_id = c.id AND a.usuario_id IS NOT NULL
    ORDER BY a.created_at, a.id
    LIMIT 1
)
WHERE c.asignado_a IS NULL
  AND EXISTS (
    SELECT 1 FROM caso_detractor_accion a
    WHERE a.caso_id = c.id AND a.usuario_id IS NOT NULL
  )
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(_BACKFILL)


def downgrade() -> None:
    # Intentional no-op: see the module docstring.
    pass
