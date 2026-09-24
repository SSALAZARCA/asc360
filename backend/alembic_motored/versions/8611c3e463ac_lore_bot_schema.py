"""lore bot schema

Revision ID: 8611c3e463ac
Revises: d0f33eb07f78
Create Date: 2026-09-24 14:00:56.421449

Phase 1 "Schema" (sdd/motored-ventas-perdidas-bot, design D2). Additive and
backward-compatible for every existing EXCEL-only row: `origen` columns are
added with a `server_default` so no existing row changes meaning, and the
Excel upsert's key columns keep exactly the same 3-column semantics plus the
literal `origen='EXCEL'` (Phase 2's concern, not touched by this migration).
Split into one helper per table, mirroring `fase2_movimientos`/`fase2_
staging`'s gga-driven precedent so the review stays scannable table-by-table.

- `usuario`: bot self-registration fields (`telegram_id`, `phone`, `status`,
  approval resolution) plus `ck_usuario_credenciales_web`, which relaxes
  `email`/`hashed_password` to nullable ONLY for `ASESOR_MOSTRADOR` rows --
  every other role still requires both, enforced by the DB, not just the app.
- `carga_archivo`: `origen` discriminator (`EXCEL`|`BOT`) and nullable file
  columns for BOT rows (design D1's volume/isolation fix), with checks that
  keep EXCEL rows exactly as strict as before.
- `demanda_perdida`: `origen` discriminator and the unique key widened from
  `(fecha, sucursal_id, referencia_id)` to `(fecha, sucursal_id,
  referencia_id, origen)`, so a BOT-origin row never collides with the
  EXCEL-origin row for the same key (design D2/D3 additive-vs-replace split).
- `demanda_perdida_bot_linea`: new per-reference ledger (design D1) used to
  reverse today-only edits/cancels precisely, independent of whatever
  `demanda_perdida.carga_id` currently points to.

Deviation from design D2's literal text: `ck_usuario_credenciales_web` uses
`role = 'ASESOR_MOSTRADOR'`, not `role::text = 'ASESOR_MOSTRADOR'`. Postgres
resolves an unknown-typed string literal against the enum's own equality
operator without an explicit cast, so the cast was redundant in production --
and it actively breaks the SQLite-backed model tests
(`tests/motored/test_bootstrap_admin.py`, `test_database.py`) that run
`MotoredBase.metadata.create_all()` against `aiosqlite`, since SQLite has no
`::` cast syntax and CheckConstraint text is embedded verbatim, dialect-
agnostic. Flagged here per apply-phase convention rather than silently
diverging from the design doc.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8611c3e463ac'
down_revision: Union[str, None] = 'd0f33eb07f78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _alter_usuario() -> None:
    op.add_column('usuario', sa.Column('telegram_id', sa.BigInteger(), nullable=True))
    op.create_unique_constraint('uq_usuario_telegram_id', 'usuario', ['telegram_id'])
    op.add_column('usuario', sa.Column('phone', sa.String(length=20), nullable=True))
    op.add_column(
        'usuario',
        sa.Column('status', sa.String(length=16), nullable=False, server_default='approved'),
    )
    op.create_check_constraint(
        'ck_usuario_status', 'usuario', "status IN ('pending', 'approved', 'rejected')",
    )
    op.add_column('usuario', sa.Column('resuelto_por', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_usuario_resuelto_por_usuario', 'usuario', 'usuario', ['resuelto_por'], ['id'],
    )
    op.add_column('usuario', sa.Column('resuelto_en', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'usuario', sa.Column('codigo_vinculacion_hash', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'usuario',
        sa.Column('codigo_vinculacion_expira', sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column('usuario', 'email', nullable=True)
    op.alter_column('usuario', 'hashed_password', nullable=True)
    op.create_check_constraint(
        'ck_usuario_credenciales_web',
        'usuario',
        "role = 'ASESOR_MOSTRADOR' OR "
        "(email IS NOT NULL AND hashed_password IS NOT NULL)",
    )


def _alter_carga_archivo() -> None:
    op.add_column(
        'carga_archivo',
        sa.Column('origen', sa.String(length=8), nullable=False, server_default='EXCEL'),
    )
    op.create_check_constraint(
        'ck_carga_archivo_origen', 'carga_archivo', "origen IN ('EXCEL', 'BOT')",
    )
    op.alter_column('carga_archivo', 'nombre_archivo', nullable=True)
    op.alter_column('carga_archivo', 'hash_sha256', nullable=True)
    op.alter_column('carga_archivo', 'ruta_objeto', nullable=True)
    op.alter_column('carga_archivo', 'bytes', nullable=True)
    op.create_check_constraint(
        'ck_carga_archivo_archivo_por_origen',
        'carga_archivo',
        "origen = 'BOT' OR (nombre_archivo IS NOT NULL AND hash_sha256 IS NOT NULL "
        "AND ruta_objeto IS NOT NULL AND bytes IS NOT NULL)",
    )
    op.create_check_constraint(
        'ck_carga_archivo_bot_tipo', 'carga_archivo', "origen = 'EXCEL' OR tipo = 'DEMANDA_PERDIDA'",
    )
    op.create_index(
        'ix_carga_archivo_origen_tipo_created_at',
        'carga_archivo', ['origen', 'tipo', 'created_at'], unique=False,
    )


def _alter_demanda_perdida() -> None:
    op.add_column(
        'demanda_perdida',
        sa.Column('origen', sa.String(length=8), nullable=False, server_default='EXCEL'),
    )
    op.create_check_constraint(
        'ck_demanda_perdida_origen', 'demanda_perdida', "origen IN ('EXCEL', 'BOT')",
    )
    op.drop_constraint(
        'uq_demanda_perdida_fecha_sucursal_referencia', 'demanda_perdida', type_='unique',
    )
    op.create_unique_constraint(
        'uq_demanda_perdida_fecha_sucursal_referencia_origen',
        'demanda_perdida', ['fecha', 'sucursal_id', 'referencia_id', 'origen'],
    )


def _create_demanda_perdida_bot_linea() -> None:
    op.create_table(
        'demanda_perdida_bot_linea',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('carga_id', sa.UUID(), nullable=False),
        sa.Column('usuario_id', sa.UUID(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('cantidad', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('estado', sa.String(length=16), nullable=False, server_default='ACTIVA'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'carga_id', 'referencia_id', name='uq_demanda_perdida_bot_linea_carga_referencia',
        ),
        sa.CheckConstraint('cantidad > 0', name='ck_demanda_perdida_bot_linea_cantidad_positiva'),
        sa.CheckConstraint(
            "estado IN ('ACTIVA', 'ANULADA')", name='ck_demanda_perdida_bot_linea_estado',
        ),
    )
    op.create_index(
        'ix_demanda_perdida_bot_linea_usuario_id_fecha',
        'demanda_perdida_bot_linea', ['usuario_id', 'fecha'], unique=False,
    )
    op.create_index(
        'ix_demanda_perdida_bot_linea_sucursal_id_fecha',
        'demanda_perdida_bot_linea', ['sucursal_id', 'fecha'], unique=False,
    )


def upgrade() -> None:
    _alter_usuario()
    _alter_carga_archivo()
    _alter_demanda_perdida()
    _create_demanda_perdida_bot_linea()


def _delete_bot_data() -> None:
    # *** DATA LOSS WARNING ***
    # This downgrade permanently deletes every BOT-origin row (demanda_
    # perdida, the per-reference ledger, carga_archivo headers) and every
    # advisor account created through bot self-registration (they have no
    # web credentials and cannot survive once `email`/`hashed_password`
    # become NOT NULL again). There is no reversible way to keep BOT data
    # once the schema that models it is removed -- this mirrors design D2's
    # own explicit downgrade caveat. Deletes go in FK-dependency order:
    # demanda_perdida (BOT rows) -> the ledger -> carga_archivo (BOT rows)
    # -> advisor usuario_sucursal rows -> advisor usuario rows.
    op.execute(sa.text("DELETE FROM demanda_perdida WHERE origen = 'BOT'"))
    op.execute(sa.text("DELETE FROM demanda_perdida_bot_linea"))
    op.execute(sa.text("DELETE FROM carga_archivo WHERE origen = 'BOT'"))
    op.execute(
        sa.text(
            "DELETE FROM usuario_sucursal WHERE usuario_id IN "
            "(SELECT id FROM usuario WHERE role = 'ASESOR_MOSTRADOR')"
        )
    )
    op.execute(sa.text("DELETE FROM usuario WHERE role = 'ASESOR_MOSTRADOR'"))


def _restore_demanda_perdida() -> None:
    op.drop_constraint(
        'uq_demanda_perdida_fecha_sucursal_referencia_origen', 'demanda_perdida', type_='unique',
    )
    op.create_unique_constraint(
        'uq_demanda_perdida_fecha_sucursal_referencia',
        'demanda_perdida', ['fecha', 'sucursal_id', 'referencia_id'],
    )
    op.drop_constraint('ck_demanda_perdida_origen', 'demanda_perdida', type_='check')
    op.drop_column('demanda_perdida', 'origen')


def _restore_carga_archivo() -> None:
    op.drop_index('ix_carga_archivo_origen_tipo_created_at', table_name='carga_archivo')
    op.drop_constraint('ck_carga_archivo_bot_tipo', 'carga_archivo', type_='check')
    op.drop_constraint('ck_carga_archivo_archivo_por_origen', 'carga_archivo', type_='check')
    op.alter_column('carga_archivo', 'bytes', nullable=False)
    op.alter_column('carga_archivo', 'ruta_objeto', nullable=False)
    op.alter_column('carga_archivo', 'hash_sha256', nullable=False)
    op.alter_column('carga_archivo', 'nombre_archivo', nullable=False)
    op.drop_constraint('ck_carga_archivo_origen', 'carga_archivo', type_='check')
    op.drop_column('carga_archivo', 'origen')


def _restore_usuario() -> None:
    op.drop_constraint('ck_usuario_credenciales_web', 'usuario', type_='check')
    op.alter_column('usuario', 'hashed_password', nullable=False)
    op.alter_column('usuario', 'email', nullable=False)
    op.drop_column('usuario', 'codigo_vinculacion_expira')
    op.drop_column('usuario', 'codigo_vinculacion_hash')
    op.drop_column('usuario', 'resuelto_en')
    op.drop_constraint('fk_usuario_resuelto_por_usuario', 'usuario', type_='foreignkey')
    op.drop_column('usuario', 'resuelto_por')
    op.drop_constraint('ck_usuario_status', 'usuario', type_='check')
    op.drop_column('usuario', 'status')
    op.drop_column('usuario', 'phone')
    op.drop_constraint('uq_usuario_telegram_id', 'usuario', type_='unique')
    op.drop_column('usuario', 'telegram_id')


def downgrade() -> None:
    _delete_bot_data()
    op.drop_index(
        'ix_demanda_perdida_bot_linea_sucursal_id_fecha',
        table_name='demanda_perdida_bot_linea',
    )
    op.drop_index(
        'ix_demanda_perdida_bot_linea_usuario_id_fecha',
        table_name='demanda_perdida_bot_linea',
    )
    op.drop_table('demanda_perdida_bot_linea')
    _restore_demanda_perdida()
    _restore_carga_archivo()
    _restore_usuario()
