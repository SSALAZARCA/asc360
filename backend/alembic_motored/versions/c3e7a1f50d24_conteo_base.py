"""conteo base: count header, frozen snapshot and store locations

Revision ID: c3e7a1f50d24
Revises: b4f9c2e6a813
Create Date: 2026-10-09 15:00:00.000000

Feature motored-conteos-inventario, WU2 (design §4.1-4.3, ADR-1, ADR-9).

- `conteo`: one physical store count. `lider_id` is the assigned
  LIDER_INVENTARIOS, required for TOTAL counts. The money thresholds are
  frozen at Iniciar. `uq_conteo_total_abierto` allows one running TOTAL
  count per store; several stores can count at the same time.
- `conteo_snapshot_linea`: the copied system side, ONE line per
  (conteo, referencia) with the store's total quantity; the per-bodega
  split is an informative JSON (owner decision: counts are per store).
- `ubicacion_inventario`: bin locations per store, with no bodega.

Purely additive; downgrade drops the three tables (and their indexes).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3e7a1f50d24'
down_revision: Union[str, None] = 'b4f9c2e6a813'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)
_TZ = sa.DateTime(timezone=True)
_ESTADOS = (
    "'PROGRAMADO', 'EN_CONTEO', 'EN_RECONTEO', 'CERRADO', 'ANULADO'")
_FUENTES = "'BODEGA', 'REFERENCIA', 'MEDIANA', 'PRECIO', 'SIN_COSTO'"


def _fk(tabla, ondelete=None):
    return sa.ForeignKey(f'{tabla}.id', ondelete=ondelete)


def _ahora(nombre):
    return sa.Column(
        nombre, _TZ, nullable=False, server_default=sa.text('now()'))


def _columnas_conteo():
    usuarios = ('creado_por', 'iniciado_por', 'cerrado_por', 'anulado_por')
    marcas = (
        'snapshot_aplicado_en', 'snapshot_tomado_en', 'codigo_rotado_en',
        'acceso_ventana_inicio', 'iniciado_en', 'ronda_terminada_en',
        'cerrado_en', 'anulado_en')
    return [
        sa.Column('id', _UUID, primary_key=True),
        sa.Column('tipo', sa.String(10), nullable=False),
        sa.Column(
            'sucursal_id', _UUID, _fk('sucursal', 'RESTRICT'),
            nullable=False),
        sa.Column('lider_id', _UUID, _fk('usuario', 'RESTRICT')),
        sa.Column('estado', sa.String(16), nullable=False),
        sa.Column('fecha_programada', sa.Date(), nullable=False),
        sa.Column('origen', sa.String(12), nullable=False),
        sa.Column('semana_iso', sa.String(8)),
        sa.Column('verifica_conteo_id', _UUID, _fk('conteo', 'RESTRICT')),
        sa.Column('arrastra_conteo_id', _UUID, _fk('conteo', 'RESTRICT')),
        *[sa.Column(n, _UUID, _fk('usuario')) for n in usuarios],
        sa.Column('motivo_anulacion', sa.Text()),
        sa.Column('motivo_cierre_forzado', sa.Text()),
        sa.Column(
            'snapshot_carga_id', _UUID, _fk('carga_archivo', 'SET NULL')),
        sa.Column('snapshot_fecha_corte', sa.Date()),
        sa.Column('snapshot_advertencias', postgresql.JSONB()),
        sa.Column('umbral_reconteo_pesos', sa.Numeric(16, 2)),
        sa.Column('umbral_critico_pesos', sa.Numeric(16, 2)),
        sa.Column('enlace_slug', sa.String(16)),
        sa.Column('codigo_hash', sa.String(64)),
        sa.Column(
            'acceso_fallidos_hora', sa.Integer(), nullable=False,
            server_default=sa.text('0')),
        *[sa.Column(n, _TZ) for n in marcas],
        sa.Column('refs_universo', sa.Integer()),
        sa.Column('refs_exactas', sa.Integer()),
        sa.Column('exactitud_pct', sa.Numeric(6, 2)),
        sa.Column('valor_sistema', sa.Numeric(18, 2)),
        sa.Column('valor_diferencia_neta', sa.Numeric(18, 2)),
        sa.Column('valor_diferencia_abs', sa.Numeric(18, 2)),
        _ahora('created_at'),
        _ahora('updated_at'),
    ]


def _restricciones_conteo():
    iniciado = "estado IN ('PROGRAMADO', 'ANULADO') OR "
    return [
        sa.CheckConstraint(
            "tipo IN ('TOTAL', 'SELECTIVO')", name='ck_conteo_tipo'),
        sa.CheckConstraint(
            f"estado IN ({_ESTADOS})", name='ck_conteo_estado'),
        sa.CheckConstraint(
            "origen IN ('MANUAL', 'AUTOMATICO')", name='ck_conteo_origen'),
        sa.CheckConstraint(
            "tipo <> 'TOTAL' OR lider_id IS NOT NULL",
            name='ck_conteo_lider_si_total'),
        sa.CheckConstraint(
            iniciado + 'snapshot_tomado_en IS NOT NULL',
            name='ck_conteo_snapshot_si_iniciado'),
        sa.CheckConstraint(
            iniciado + '(umbral_reconteo_pesos IS NOT NULL '
            'AND umbral_critico_pesos IS NOT NULL)',
            name='ck_conteo_umbrales_si_iniciado'),
        sa.CheckConstraint(
            "tipo = 'TOTAL' OR enlace_slug IS NULL",
            name='ck_conteo_slug_solo_total'),
        sa.UniqueConstraint('enlace_slug', name='uq_conteo_enlace_slug'),
    ]


def _indices_conteo():
    op.create_index(
        'uq_conteo_total_abierto', 'conteo', ['sucursal_id'], unique=True,
        postgresql_where=sa.text(
            "tipo = 'TOTAL' AND estado IN ('EN_CONTEO', 'EN_RECONTEO')"))
    op.create_index(
        'uq_conteo_selectivo_semana', 'conteo',
        ['sucursal_id', 'semana_iso'], unique=True,
        postgresql_where=sa.text(
            "tipo = 'SELECTIVO' AND origen = 'AUTOMATICO' "
            "AND verifica_conteo_id IS NULL "
            "AND arrastra_conteo_id IS NULL AND estado <> 'ANULADO'"))
    op.create_index(
        'ix_conteo_estado_fecha', 'conteo', ['estado', 'fecha_programada'])
    op.create_index(
        'ix_conteo_sucursal_cerrado', 'conteo',
        ['sucursal_id', sa.text('cerrado_en DESC')])
    op.create_index(
        'ix_conteo_lider', 'conteo', ['lider_id', 'fecha_programada'])


def _crear_snapshot_linea():
    op.create_table(
        'conteo_snapshot_linea',
        sa.Column('id', _UUID, primary_key=True),
        sa.Column(
            'conteo_id', _UUID, _fk('conteo', 'CASCADE'), nullable=False),
        sa.Column(
            'referencia_id', _UUID, _fk('referencia', 'RESTRICT'),
            nullable=False),
        sa.Column('existencia', sa.Numeric(14, 2), nullable=False),
        sa.Column(
            'existencia_por_bodega', postgresql.JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb")),
        sa.Column('costo_unitario', sa.Numeric(16, 2)),
        sa.Column('costo_fuente', sa.String(12), nullable=False),
        sa.UniqueConstraint(
            'conteo_id', 'referencia_id',
            name='uq_conteo_snapshot_linea_referencia'),
        sa.CheckConstraint(
            f'costo_fuente IN ({_FUENTES})',
            name='ck_conteo_snapshot_linea_costo_fuente'),
    )


def _crear_ubicacion():
    op.create_table(
        'ubicacion_inventario',
        sa.Column('id', _UUID, primary_key=True),
        sa.Column(
            'sucursal_id', _UUID, _fk('sucursal', 'RESTRICT'),
            nullable=False),
        sa.Column('codigo', sa.String(30), nullable=False),
        sa.Column('nombre', sa.String(60), nullable=False),
        sa.Column(
            'activa', sa.Boolean(), nullable=False,
            server_default=sa.text('true')),
        sa.Column('origen', sa.String(8), nullable=False),
        _ahora('created_at'),
        sa.Column('created_by', _UUID, _fk('usuario')),
        sa.UniqueConstraint(
            'sucursal_id', 'codigo', name='uq_ubicacion_inventario_codigo'),
        sa.CheckConstraint(
            "codigo = upper(btrim(codigo)) AND codigo <> ''",
            name='ck_ubicacion_inventario_codigo_normalizado'),
        sa.CheckConstraint(
            "origen IN ('LIDER', 'PAREJA')",
            name='ck_ubicacion_inventario_origen'),
    )


def upgrade() -> None:
    op.create_table(
        'conteo', *_columnas_conteo(), *_restricciones_conteo())
    _indices_conteo()
    _crear_snapshot_linea()
    _crear_ubicacion()


def downgrade() -> None:
    op.drop_table('ubicacion_inventario')
    op.drop_table('conteo_snapshot_linea')
    op.drop_table('conteo')
