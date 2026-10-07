"""reporte_asesor_link: one permanent secret report link per asesor

Revision ID: 86b1df9d3d5f
Revises: c6d2f8a41b97
Create Date: 2026-10-08 09:00:00.000000

odd/motored-reporte-diario-asesor, T3a. Lore sends each asesor a personal
link to their report; opening it also asks for the cédula.

- `token`: `secrets.token_urlsafe(32)`, unique. Never logged or audited.
- `uq_reporte_asesor_link_activo`: at most one link per usuario with
  `revocado_en IS NULL`. Revoked rows are kept as history.
- `intentos_fallidos`/`bloqueado_hasta`: the public endpoint's lock.
- `usuario_id` cascades on delete; `creado_por` is set to NULL.

The link is permanent: no month and no expiry column. Purely additive;
downgrade drops the table (and its indexes).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '86b1df9d3d5f'
down_revision: Union[str, None] = 'c6d2f8a41b97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reporte_asesor_link',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'usuario_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('usuario.id', ondelete='CASCADE'),
            nullable=False),
        sa.Column('cedula', sa.String(20), nullable=False),
        sa.Column('token', sa.String(64), nullable=False),
        sa.Column(
            'creado_en', sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text('now()')),
        sa.Column(
            'creado_por', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('usuario.id', ondelete='SET NULL'),
            nullable=True),
        sa.Column('revocado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('motivo_revocacion', sa.String(40), nullable=True),
        sa.Column(
            'ultimo_acceso_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'intentos_fallidos', sa.Integer(), nullable=False,
            server_default=sa.text('0')),
        sa.Column(
            'bloqueado_hasta', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('token', name='uq_reporte_asesor_link_token'),
    )
    op.create_index(
        'uq_reporte_asesor_link_activo', 'reporte_asesor_link',
        ['usuario_id'], unique=True,
        postgresql_where=sa.text('revocado_en IS NULL'))


def downgrade() -> None:
    op.drop_index(
        'uq_reporte_asesor_link_activo', table_name='reporte_asesor_link')
    op.drop_table('reporte_asesor_link')
