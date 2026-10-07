"""usuario_cedula: link a usuario to the vendedor master by cédula

Revision ID: c6d2f8a41b97
Revises: e5c9b3d8f024
Create Date: 2026-10-07 18:00:00.000000

odd/motored-reporte-diario-asesor, T1. The daily asesor report goes out
only through an APPROVED link Telegram -> usuario -> cédula:

- `cedula`: digits only (same cleaning as the vendedor master), nullable.
- `cedula_aprobada`: false while a cédula typed in Lore waits for an ADMIN;
  an ADMIN entry is approved directly.
- `uq_usuario_cedula_aprobada`: one APPROVED usuario per cédula. Pending
  duplicates are allowed so an impostor can never block the real owner.

Purely additive: existing rows get `cedula = NULL`, `cedula_aprobada =
false`. Downgrade drops the index and both columns.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c6d2f8a41b97'
down_revision: Union[str, None] = 'e5c9b3d8f024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'usuario', sa.Column('cedula', sa.String(20), nullable=True))
    op.add_column(
        'usuario',
        sa.Column(
            'cedula_aprobada', sa.Boolean(), nullable=False,
            server_default=sa.text('false')))
    op.create_index(
        'uq_usuario_cedula_aprobada', 'usuario', ['cedula'],
        unique=True, postgresql_where=sa.text('cedula_aprobada'))


def downgrade() -> None:
    op.drop_index('uq_usuario_cedula_aprobada', table_name='usuario')
    op.drop_column('usuario', 'cedula_aprobada')
    op.drop_column('usuario', 'cedula')
