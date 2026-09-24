"""lore role enum

Revision ID: d0f33eb07f78
Revises: 3956c0ebd69c
Create Date: 2026-09-24 14:00:51.950535

Phase 1 "Schema" (sdd/motored-ventas-perdidas-bot, design D2). Adds the
`ASESOR_MOSTRADOR` value to the existing `motored_role` Postgres enum, ahead
of `lore_bot_schema` (which assigns that role to bot-registered advisors).
Split into its own revision because PostgreSQL requires `ALTER TYPE ... ADD
VALUE` to be committed before the new value can be used in the same
transaction -- same `autocommit_block()` precedent already established for
asc360's own `role` enum in `alembic/versions/c3d4e5f6a7b8_add_proveedor_
role.py`.

Downgrade is a documented no-op: PostgreSQL cannot drop a single enum value
without recreating the whole type. `ASESOR_MOSTRADOR` remains in the enum,
unused, after a downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0f33eb07f78'
down_revision: Union[str, None] = '3956c0ebd69c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE motored_role ADD VALUE IF NOT EXISTS 'ASESOR_MOSTRADOR'"))


def downgrade() -> None:
    # PostgreSQL no permite remover valores de un enum sin recrear el tipo.
    # 'ASESOR_MOSTRADOR' permanece en el enum, sin uso, tras el downgrade.
    pass
