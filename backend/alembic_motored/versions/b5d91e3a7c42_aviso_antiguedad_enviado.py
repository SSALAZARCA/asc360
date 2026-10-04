"""aviso_antiguedad_enviado: ledger de avisos de antiguedad enviados

Revision ID: b5d91e3a7c42
Revises: f3a8d1c5b704
Create Date: 2026-10-03 18:00:00.000000

Registra cada aviso de antiguedad de datos ya enviado por Telegram. La clave
unica (dataset, umbral, fecha_vencimiento) hace el envio idempotente ante
reinicios y varias replicas.

Estrictamente ADITIVA: una tabla nueva, sin tocar ninguna existente.

Downgrade: borra la tabla (en el peor caso un aviso se manda otra vez).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b5d91e3a7c42'
down_revision: Union[str, None] = 'f3a8d1c5b704'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'aviso_antiguedad_enviado',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('dataset', sa.String(length=32), nullable=False),
        sa.Column('umbral', sa.String(length=16), nullable=False),
        sa.Column('fecha_vencimiento', sa.Date(), nullable=False),
        sa.Column('enviado_en', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'dataset', 'umbral', 'fecha_vencimiento',
            name='uq_aviso_antiguedad_dataset_umbral_vence'),
    )


def downgrade() -> None:
    op.drop_table('aviso_antiguedad_enviado')
