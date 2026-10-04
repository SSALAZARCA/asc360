"""gerencia role

Revision ID: c4e8a1f6d903
Revises: b5d91e3a7c42
Create Date: 2026-10-04 12:00:00.000000

Motored budgets/management, task T1. Adds the `GERENCIA` value to the existing
`motored_role` Postgres enum (management users who load sales budgets and read
the advisor dashboard). Split into its own revision because PostgreSQL requires
`ALTER TYPE ... ADD VALUE` to be committed before the new value can be used in
the same transaction -- same `autocommit_block()` precedent as
`7be41d9c0a26_servicio_cliente_role.py`. `IF NOT EXISTS` keeps it idempotent.

Downgrade is a documented no-op: PostgreSQL cannot drop a single enum value
without recreating the whole type. `GERENCIA` remains in the enum, unused,
after a downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1f6d903'
down_revision: Union[str, None] = 'b5d91e3a7c42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE motored_role ADD VALUE IF NOT EXISTS 'GERENCIA'"))


def downgrade() -> None:
    # PostgreSQL no permite remover valores de un enum sin recrear el tipo.
    # 'GERENCIA' permanece en el enum, sin uso, tras el downgrade.
    pass
