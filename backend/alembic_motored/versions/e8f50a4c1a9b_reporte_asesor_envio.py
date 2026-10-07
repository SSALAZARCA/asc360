"""reporte_asesor_envio: ledger of the daily asesor report messages

Revision ID: e8f50a4c1a9b
Revises: 86b1df9d3d5f
Create Date: 2026-10-08 12:00:00.000000

odd/motored-reporte-diario-asesor, T3b. Lore sends each asesor, once per
data date, a message with their personal report link.

- One row per attempt: `estado` is 'enviado', 'fallido' or 'bloqueado'.
- `uq_reporte_asesor_envio_diario`: at most one automatic 'enviado' row per
  (usuario_id, fecha_datos). ADMIN resends (`reenvio`) are not limited.
- `usuario_id` cascades on delete; `solicitado_por` is set to NULL.
- `detalle` never holds the token or the URL.

Purely additive; downgrade drops the table (and its indexes).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e8f50a4c1a9b'
down_revision: Union[str, None] = '86b1df9d3d5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLA = 'reporte_asesor_envio'


def upgrade() -> None:
    op.create_table(
        TABLA,
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'usuario_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('usuario.id', ondelete='CASCADE'),
            nullable=False),
        sa.Column('cedula', sa.String(20), nullable=False),
        sa.Column('fecha_datos', sa.Date(), nullable=False),
        sa.Column(
            'enviado_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('estado', sa.String(12), nullable=False),
        sa.Column('detalle', sa.String(80), nullable=True),
        sa.Column(
            'reenvio', sa.Boolean(), nullable=False,
            server_default=sa.text('false')),
        sa.Column(
            'solicitado_por', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('usuario.id', ondelete='SET NULL'),
            nullable=True),
        sa.CheckConstraint(
            "estado IN ('enviado', 'fallido', 'bloqueado')",
            name='ck_reporte_asesor_envio_estado'),
    )
    op.create_index(
        'uq_reporte_asesor_envio_diario', TABLA,
        ['usuario_id', 'fecha_datos'], unique=True,
        postgresql_where=sa.text("NOT reenvio AND estado = 'enviado'"))
    op.create_index(
        'ix_reporte_asesor_envio_fecha', TABLA, ['fecha_datos'])


def downgrade() -> None:
    op.drop_index('ix_reporte_asesor_envio_fecha', table_name=TABLA)
    op.drop_index('uq_reporte_asesor_envio_diario', table_name=TABLA)
    op.drop_table(TABLA)
