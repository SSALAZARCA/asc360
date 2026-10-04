"""presupuestos: monthly sales budgets per asesor, versioned

Revision ID: d7a2f4b8c915
Revises: c4e8a1f6d903
Create Date: 2026-10-04 12:00:00.000000

`presupuesto_version` is one version of one month (insert-only; the latest
`version` per `mes` is the one indicators read) and `presupuesto_linea` is one
asesor's budget (by cedula) in that version.

Strictly ADDITIVE: two new tables, nothing existing is touched.

Downgrade: drops both tables (all budgets and their history are lost; they are
recovered by re-uploading the files).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd7a2f4b8c915'
down_revision: Union[str, None] = 'c4e8a1f6d903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'presupuesto_version',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('mes', sa.Date(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('origen', sa.String(length=10), nullable=False),
        sa.Column('archivo_nombre', sa.String(length=255), nullable=True),
        sa.Column('nota', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mes', 'version', name='uq_presupuesto_version_mes_version'),
        sa.CheckConstraint('EXTRACT(DAY FROM mes) = 1', name='ck_presupuesto_version_mes_dia_1'),
        sa.CheckConstraint('version >= 1', name='ck_presupuesto_version_positiva'),
        sa.CheckConstraint("origen IN ('EXCEL', 'MANUAL')", name='ck_presupuesto_version_origen'),
    )
    op.create_table(
        'presupuesto_linea',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('version_id', sa.UUID(), nullable=False),
        sa.Column('cedula', sa.String(length=20), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('monto', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['version_id'], ['presupuesto_version.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('version_id', 'cedula', name='uq_presupuesto_linea_version_cedula'),
        sa.CheckConstraint('monto > 0', name='ck_presupuesto_linea_monto_positivo'),
    )


def downgrade() -> None:
    op.drop_table('presupuesto_linea')
    op.drop_table('presupuesto_version')
