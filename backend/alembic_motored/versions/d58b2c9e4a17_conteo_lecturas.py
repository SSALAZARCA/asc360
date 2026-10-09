"""conteo lecturas: sessions, people, readings, reconteo and results

Revision ID: d58b2c9e4a17
Revises: c3e7a1f50d24
Create Date: 2026-10-09 15:30:00.000000

Feature motored-conteos-inventario, WU3 (design §4.4-4.8, ADR-3..5).

- `conteo_sesion` + `conteo_integrante`: one counting device and its 1-3
  people. The cédula is stored for the "different pair" rule only and
  is never returned by any endpoint (§8.3).
- `conteo_reconteo`: one live reconteo per (conteo, codigo).
- `conteo_lectura`: client-generated id (idempotent retries) and a server
  identity `seq` for the live panel's version.
- `conteo_acceso_intento`: brute-force counter per (conteo, client hash).
- `conteo_resultado`: one line per (conteo, codigo) at close, with the
  store's principal bodega as the single adjustment bodega.

Every child row cascades from `conteo`. Purely additive; downgrade drops
the six tables in reverse order.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd58b2c9e4a17'
down_revision: Union[str, None] = 'c3e7a1f50d24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)
_TZ = sa.DateTime(timezone=True)
_FUENTES = "'BODEGA', 'REFERENCIA', 'MEDIANA', 'PRECIO', 'SIN_COSTO'"
_SIN_ANULAR = sa.text('anulada_en IS NULL')
_TABLAS = (
    'conteo_sesion', 'conteo_integrante', 'conteo_reconteo',
    'conteo_lectura', 'conteo_acceso_intento', 'conteo_resultado',
)


def _fk(tabla, ondelete=None):
    return sa.ForeignKey(f'{tabla}.id', ondelete=ondelete)


def _ahora(nombre):
    return sa.Column(
        nombre, _TZ, nullable=False, server_default=sa.text('now()'))


def _del_conteo():
    return sa.Column(
        'conteo_id', _UUID, _fk('conteo', 'CASCADE'), nullable=False)


def _crear_sesion():
    op.create_table(
        'conteo_sesion',
        sa.Column('id', _UUID, primary_key=True),
        _del_conteo(),
        sa.Column('tipo', sa.String(8), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('estado', sa.String(14), nullable=False),
        sa.Column('dispositivo', sa.String(10), nullable=False),
        sa.Column(
            'ubicacion_actual_id', _UUID,
            _fk('ubicacion_inventario', 'SET NULL')),
        sa.Column('usuario_id', _UUID, _fk('usuario')),
        sa.Column('telegram_id', sa.BigInteger()),
        _ahora('conectada_en'),
        _ahora('ultima_actividad_en'),
        sa.Column('desconectada_en', _TZ),
        sa.Column('desconectada_por', _UUID, _fk('usuario')),
        sa.UniqueConstraint(
            'token_hash', name='uq_conteo_sesion_token_hash'),
        sa.CheckConstraint(
            "tipo IN ('PAREJA', 'ASESOR')", name='ck_conteo_sesion_tipo'),
        sa.CheckConstraint(
            "estado IN ('CONECTADA', 'DESCONECTADA', 'CERRADA')",
            name='ck_conteo_sesion_estado'),
        sa.CheckConstraint(
            "dispositivo IN ('ESCRITORIO', 'MOVIL', 'MINIAPP')",
            name='ck_conteo_sesion_dispositivo'),
        sa.CheckConstraint(
            "tipo = 'PAREJA' OR usuario_id IS NOT NULL",
            name='ck_conteo_sesion_asesor_usuario'),
    )
    op.create_index(
        'ix_conteo_sesion_conteo_estado', 'conteo_sesion',
        ['conteo_id', 'estado'])


def _crear_integrante():
    op.create_table(
        'conteo_integrante',
        sa.Column('id', _UUID, primary_key=True),
        sa.Column(
            'sesion_id', _UUID, _fk('conteo_sesion', 'CASCADE'),
            nullable=False),
        sa.Column('orden', sa.SmallInteger(), nullable=False),
        sa.Column('nombre', sa.String(120), nullable=False),
        sa.Column('cedula', sa.String(20), nullable=False),
        sa.UniqueConstraint(
            'sesion_id', 'orden', name='uq_conteo_integrante_orden'),
        sa.CheckConstraint(
            'orden BETWEEN 1 AND 3', name='ck_conteo_integrante_orden'),
    )
    op.create_index(
        'ix_conteo_integrante_sesion', 'conteo_integrante', ['sesion_id'])


def _crear_reconteo():
    op.create_table(
        'conteo_reconteo',
        sa.Column('id', _UUID, primary_key=True),
        _del_conteo(),
        sa.Column('referencia_id', _UUID, _fk('referencia', 'RESTRICT')),
        sa.Column('codigo', sa.String(100), nullable=False),
        sa.Column('estado', sa.String(10), nullable=False),
        sa.Column('origen', sa.String(8), nullable=False),
        sa.Column('diferencia_ronda1', sa.Numeric(14, 2)),
        sa.Column('valor_ronda1', sa.Numeric(18, 2)),
        sa.Column('sesion_id', _UUID, _fk('conteo_sesion')),
        sa.Column('asignado_por', _UUID, _fk('usuario')),
        sa.Column(
            'misma_pareja_autorizada', sa.Boolean(), nullable=False,
            server_default=sa.text('false')),
        sa.Column('motivo_autorizacion', sa.Text()),
        sa.Column('asignado_en', _TZ),
        sa.Column('terminado_en', _TZ),
        sa.Column('cancelado_en', _TZ),
        _ahora('created_at'),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'ASIGNADO', 'TERMINADO', 'CANCELADO')",
            name='ck_conteo_reconteo_estado'),
        sa.CheckConstraint(
            "origen IN ('UMBRAL', 'LIDER')",
            name='ck_conteo_reconteo_origen'),
        sa.CheckConstraint(
            "estado NOT IN ('ASIGNADO', 'TERMINADO') "
            "OR sesion_id IS NOT NULL",
            name='ck_conteo_reconteo_sesion_si_asignado'),
        sa.CheckConstraint(
            'NOT misma_pareja_autorizada '
            'OR motivo_autorizacion IS NOT NULL',
            name='ck_conteo_reconteo_motivo_si_autorizada'),
    )
    op.create_index(
        'uq_conteo_reconteo_codigo_activo', 'conteo_reconteo',
        ['conteo_id', 'codigo'], unique=True,
        postgresql_where=sa.text("estado <> 'CANCELADO'"))


def _crear_lectura():
    op.create_table(
        'conteo_lectura',
        sa.Column('id', _UUID, primary_key=True),
        sa.Column(
            'seq', sa.BigInteger(), sa.Identity(always=True),
            nullable=False),
        _del_conteo(),
        sa.Column(
            'sesion_id', _UUID, _fk('conteo_sesion', 'CASCADE'),
            nullable=False),
        sa.Column(
            'ubicacion_id', _UUID, _fk('ubicacion_inventario', 'RESTRICT'),
            nullable=False),
        sa.Column('referencia_id', _UUID, _fk('referencia', 'RESTRICT')),
        sa.Column('codigo_leido', sa.String(100), nullable=False),
        sa.Column('cantidad', sa.Numeric(12, 2), nullable=False),
        sa.Column('ronda', sa.SmallInteger(), nullable=False),
        sa.Column(
            'reconteo_id', _UUID, _fk('conteo_reconteo', 'CASCADE')),
        sa.Column('metodo', sa.String(8), nullable=False),
        sa.Column('leida_en', _TZ, nullable=False),
        _ahora('recibida_en'),
        sa.Column('anulada_en', _TZ),
        sa.UniqueConstraint('seq', name='uq_conteo_lectura_seq'),
        sa.CheckConstraint(
            'cantidad > 0 AND cantidad <= 99999',
            name='ck_conteo_lectura_cantidad'),
        sa.CheckConstraint(
            '(ronda = 1 AND reconteo_id IS NULL) '
            'OR (ronda = 2 AND reconteo_id IS NOT NULL)',
            name='ck_conteo_lectura_ronda_reconteo'),
        sa.CheckConstraint(
            "metodo IN ('ESCANER', 'CAMARA', 'MANUAL')",
            name='ck_conteo_lectura_metodo'),
    )
    _indices_lectura()


def _indices_lectura():
    op.create_index(
        'ix_conteo_lectura_agregado', 'conteo_lectura',
        ['conteo_id', 'ronda', 'referencia_id'],
        postgresql_include=['cantidad'], postgresql_where=_SIN_ANULAR)
    op.create_index(
        'ix_conteo_lectura_conteo_seq', 'conteo_lectura',
        ['conteo_id', sa.text('seq DESC')])
    op.create_index(
        'ix_conteo_lectura_sesion_seq', 'conteo_lectura',
        ['sesion_id', sa.text('seq DESC')])
    op.create_index(
        'ix_conteo_lectura_conteo_ubicacion', 'conteo_lectura',
        ['conteo_id', 'ubicacion_id'], postgresql_where=_SIN_ANULAR)


def _crear_acceso_intento():
    op.create_table(
        'conteo_acceso_intento',
        sa.Column(
            'conteo_id', _UUID, _fk('conteo', 'CASCADE'), primary_key=True),
        sa.Column('cliente', sa.String(64), primary_key=True),
        sa.Column(
            'fallidos', sa.Integer(), nullable=False,
            server_default=sa.text('0')),
        sa.Column('ventana_inicio', _TZ, nullable=False),
        sa.Column('bloqueado_hasta', _TZ),
    )


def _crear_resultado():
    op.create_table(
        'conteo_resultado',
        sa.Column('id', _UUID, primary_key=True),
        _del_conteo(),
        sa.Column(
            'sucursal_id', _UUID, _fk('sucursal', 'RESTRICT'),
            nullable=False),
        sa.Column('referencia_id', _UUID, _fk('referencia', 'RESTRICT')),
        sa.Column('codigo', sa.String(100), nullable=False),
        sa.Column(
            'bodega_ajuste_id', _UUID, _fk('bodega', 'RESTRICT'),
            nullable=False),
        sa.Column('existencia_sistema', sa.Numeric(14, 2), nullable=False),
        sa.Column('cantidad_contada', sa.Numeric(14, 2), nullable=False),
        sa.Column('diferencia', sa.Numeric(14, 2), nullable=False),
        sa.Column('costo_unitario', sa.Numeric(16, 2)),
        sa.Column('costo_fuente', sa.String(12), nullable=False),
        sa.Column('valor_diferencia', sa.Numeric(18, 2)),
        sa.Column(
            'ubicaciones', postgresql.ARRAY(sa.String(60)), nullable=False,
            server_default=sa.text("'{}'")),
        sa.Column('con_reconteo', sa.Boolean(), nullable=False),
        sa.Column('critico', sa.Boolean(), nullable=False),
        sa.Column('confirmada', sa.Boolean()),
        sa.Column('cerrado_en', _TZ, nullable=False),
        sa.UniqueConstraint(
            'conteo_id', 'codigo', name='uq_conteo_resultado_codigo'),
        sa.CheckConstraint(
            f'costo_fuente IN ({_FUENTES})',
            name='ck_conteo_resultado_costo_fuente'),
        sa.CheckConstraint(
            'diferencia = cantidad_contada - existencia_sistema',
            name='ck_conteo_resultado_diferencia'),
    )
    op.create_index(
        'ix_conteo_resultado_historial', 'conteo_resultado',
        ['sucursal_id', 'referencia_id', sa.text('cerrado_en DESC')])


def upgrade() -> None:
    _crear_sesion()
    _crear_integrante()
    _crear_reconteo()
    _crear_lectura()
    _crear_acceso_intento()
    _crear_resultado()


def downgrade() -> None:
    for tabla in reversed(_TABLAS):
        op.drop_table(tabla)
