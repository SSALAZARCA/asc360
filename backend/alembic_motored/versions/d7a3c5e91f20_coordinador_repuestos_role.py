"""coordinador repuestos role

Revision ID: d7a3c5e91f20
Revises: c7e1a4b92d36
Create Date: 2026-10-08 12:00:00.000000

Feature motored-coordinador-repuestos, task C1. Adds the
`COORDINADOR_REPUESTOS` value to the existing `motored_role` Postgres enum
(the parts coordinator: reads the KPI's and works the "Gestión repuestos"
section). Its own revision because PostgreSQL requires `ALTER TYPE ... ADD
VALUE` to be committed before the new value can be used in the same
transaction -- same `autocommit_block()` precedent as
`c4e8a1f6d903_gerencia_role.py`. `IF NOT EXISTS` keeps it idempotent.

Downgrade is a documented no-op: PostgreSQL cannot drop a single enum value
without recreating the whole type. `COORDINADOR_REPUESTOS` remains in the
enum, unused, after a downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a3c5e91f20'
down_revision: Union[str, None] = 'c7e1a4b92d36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text(
            "ALTER TYPE motored_role "
            "ADD VALUE IF NOT EXISTS 'COORDINADOR_REPUESTOS'"
        ))


def downgrade() -> None:
    # PostgreSQL cannot remove a value from an enum without recreating the
    # type: 'COORDINADOR_REPUESTOS' stays in the enum, unused.
    pass
