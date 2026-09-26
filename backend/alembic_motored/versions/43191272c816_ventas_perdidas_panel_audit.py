"""ventas perdidas panel audit

Revision ID: 43191272c816
Revises: 8611c3e463ac
Create Date: 2026-09-26 00:00:00.000000

Phase 1 "Migration + model" (sdd/motored-ventas-perdidas-panel, design D1).
Additive and nullable: adds who/when audit columns to `demanda_perdida_bot_
linea` for the new ADMIN panel's edit/anular actions, mirroring `usuario.
resuelto_por`/`resuelto_en` (8611c3e463ac). No `ondelete` is set on either FK
because usuarios are never hard-deleted.

Also adds an index on `fecha`: the panel's listing endpoint filters primarily
by date range, and neither existing composite index
(`ix_demanda_perdida_bot_linea_usuario_id_fecha`,
`ix_demanda_perdida_bot_linea_sucursal_id_fecha`) serves a date-only range
since both lead with a different column.

Downgrade drops the index, then the foreign keys, then the columns. Purely
additive migration -- nothing to preserve, downgrade loses only audit data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '43191272c816'
down_revision: Union[str, None] = '8611c3e463ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'demanda_perdida_bot_linea', sa.Column('editado_por', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_demanda_perdida_bot_linea_editado_por_usuario',
        'demanda_perdida_bot_linea', 'usuario', ['editado_por'], ['id'],
    )
    op.add_column(
        'demanda_perdida_bot_linea',
        sa.Column('editado_en', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'demanda_perdida_bot_linea', sa.Column('anulado_por', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_demanda_perdida_bot_linea_anulado_por_usuario',
        'demanda_perdida_bot_linea', 'usuario', ['anulado_por'], ['id'],
    )
    op.add_column(
        'demanda_perdida_bot_linea',
        sa.Column('anulado_en', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_demanda_perdida_bot_linea_fecha',
        'demanda_perdida_bot_linea', ['fecha'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_demanda_perdida_bot_linea_fecha', table_name='demanda_perdida_bot_linea',
    )
    op.drop_constraint(
        'fk_demanda_perdida_bot_linea_anulado_por_usuario',
        'demanda_perdida_bot_linea', type_='foreignkey',
    )
    op.drop_constraint(
        'fk_demanda_perdida_bot_linea_editado_por_usuario',
        'demanda_perdida_bot_linea', type_='foreignkey',
    )
    op.drop_column('demanda_perdida_bot_linea', 'anulado_en')
    op.drop_column('demanda_perdida_bot_linea', 'anulado_por')
    op.drop_column('demanda_perdida_bot_linea', 'editado_en')
    op.drop_column('demanda_perdida_bot_linea', 'editado_por')
