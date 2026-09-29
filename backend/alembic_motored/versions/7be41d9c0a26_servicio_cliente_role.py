"""servicio cliente role

Revision ID: 7be41d9c0a26
Revises: a3f7c91d2e58
Create Date: 2026-09-29 12:00:00.000000

Motored satisfaction survey, slice T1. Adds the `SERVICIO_CLIENTE` value to
the existing `motored_role` Postgres enum (customer-service agents who manage
the survey and detractor cases). Split into its own revision because
PostgreSQL requires `ALTER TYPE ... ADD VALUE` to be committed before the new
value can be used in the same transaction -- same `autocommit_block()`
precedent as `d0f33eb07f78_lore_role_enum.py`. `IF NOT EXISTS` keeps it
idempotent.

Downgrade is a documented no-op: PostgreSQL cannot drop a single enum value
without recreating the whole type. `SERVICIO_CLIENTE` remains in the enum,
unused, after a downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7be41d9c0a26'
down_revision: Union[str, None] = 'a3f7c91d2e58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE motored_role ADD VALUE IF NOT EXISTS 'SERVICIO_CLIENTE'"))


def downgrade() -> None:
    # PostgreSQL no permite remover valores de un enum sin recrear el tipo.
    # 'SERVICIO_CLIENTE' permanece en el enum, sin uso, tras el downgrade.
    pass
