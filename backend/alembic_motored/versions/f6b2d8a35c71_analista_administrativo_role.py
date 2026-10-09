"""analista administrativo role

Revision ID: f6b2d8a35c71
Revises: e3a7c1d94b52
Create Date: 2026-10-09 15:05:00.000000

Feature motored-ingresos-responsable-plantilla, T1. Adds the
`ANALISTA_ADMINISTRATIVO` value to the existing `motored_role` Postgres enum
(enters the big supplier invoices into the ERP). Its own revision because
PostgreSQL requires `ALTER TYPE ... ADD VALUE` to be committed before the
new value can be used in the same transaction -- same `autocommit_block()`
precedent as `b4f9c2e6a813_lider_inventarios_role.py`. `IF NOT EXISTS`
keeps it idempotent.

Downgrade is a documented no-op: PostgreSQL cannot drop a single enum value
without recreating the whole type.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6b2d8a35c71'
down_revision: Union[str, None] = 'e3a7c1d94b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text(
            "ALTER TYPE motored_role "
            "ADD VALUE IF NOT EXISTS 'ANALISTA_ADMINISTRATIVO'"
        ))


def downgrade() -> None:
    # PostgreSQL cannot remove a value from an enum without recreating the
    # type: 'ANALISTA_ADMINISTRATIVO' stays in the enum, unused.
    pass
