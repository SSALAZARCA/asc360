"""fase3 corridas

Revision ID: e5b19c47a3d8
Revises: c4e81a7d3f26
Create Date: 2026-09-29 22:00:00.000000

Fase 3 "Motor" (sdd/motored-pedidos-motor, S4a, design ADR-3): crea las 5
tablas de corrida -- `corrida`, `corrida_sucursal`, `corrida_linea`,
`corrida_resumen` y `corrida_carga`.

Estrictamente ADITIVA: solo `CREATE TABLE` y `CREATE INDEX` sobre tablas
nuevas, sin tocar ninguna tabla existente (las FK solo APUNTAN a
`proveedor`, `usuario`, `sucursal`, `referencia` y `carga_archivo`). Como
las tablas son nuevas, no hay `ACCESS EXCLUSIVE` sobre tablas con tráfico;
el `SET LOCAL lock_timeout` cubre el `SHARE ROW EXCLUSIVE` que toma cada
`FOREIGN KEY` sobre la tabla referenciada, para fallar rápido en vez de
hacer cola detrás de una lectura larga.

Nada usa estas tablas todavía (el job llega en S6b). No siembra parámetros.
Downgrade: borra las 5 tablas, hijas primero.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e5b19c47a3d8'
down_revision: Union[str, None] = 'c4e81a7d3f26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MESES_CERRADOS = (6, 5, 4, 3, 2, 1)
_ESTADOS = (
    'PENDIENTE', 'CALCULANDO', 'FALLIDA', 'BORRADOR',
    'EN_REVISION', 'CERRADA', 'ENVIADA', 'ANULADA',
)


def _lista_sql(valores) -> str:
    return ', '.join(f"'{v}'" for v in valores)


def _uuid(nombre: str, nullable: bool = True) -> sa.Column:
    return sa.Column(nombre, sa.UUID(), nullable=nullable)


def _tz(nombre: str) -> sa.Column:
    return sa.Column(nombre, sa.DateTime(timezone=True), nullable=True)


def _entero(nombre: str) -> sa.Column:
    return sa.Column(
        nombre, sa.Integer(), nullable=False, server_default='0',
    )


def _create_corrida() -> None:
    op.create_table(
        'corrida',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('codigo', sa.String(length=30), nullable=False),
        _uuid('proveedor_id', nullable=False),
        sa.Column('fecha_corte', sa.Date(), nullable=False),
        sa.Column(
            'estado', sa.String(length=16), nullable=False,
            server_default='PENDIENTE',
        ),
        sa.Column(
            'es_escenario', sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
        sa.Column('overrides', postgresql.JSONB(), nullable=True),
        sa.Column(
            'alcance', sa.String(length=12), nullable=False,
            server_default='TODAS',
        ),
        sa.Column('parametros_en_fecha', sa.Date(), nullable=True),
        sa.Column('parametros_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('maestro_sustitucion', postgresql.JSONB(), nullable=True),
        sa.Column('seleccion_datos', postgresql.JSONB(), nullable=True),
        sa.Column(
            'invalidada', sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
        sa.Column('motivo_invalidacion', postgresql.JSONB(), nullable=True),
        _entero('sucursales_total'),
        _entero('sucursales_procesadas'),
        _tz('latido_en'),
        _entero('intentos'),
        _tz('reintentar_despues_de'),
        sa.Column('log', postgresql.JSONB(), nullable=True),
        _uuid('usuario_id'),
        _tz('iniciado_en'),
        _tz('terminado_en'),
        _tz('cerrada_en'),
        _uuid('cerrada_por'),
        _tz('anulada_en'),
        _uuid('anulada_por'),
        sa.Column('motivo_anulacion', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['proveedor_id'], ['proveedor.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['cerrada_por'], ['usuario.id']),
        sa.ForeignKeyConstraint(['anulada_por'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('codigo'),
        sa.CheckConstraint(
            f'estado IN ({_lista_sql(_ESTADOS)})', name='ck_corrida_estado',
        ),
        sa.CheckConstraint(
            "alcance IN ('TODAS', 'SELECCION')", name='ck_corrida_alcance',
        ),
    )
    op.create_index(
        'ix_corrida_proveedor_fecha_corte', 'corrida',
        ['proveedor_id', sa.text('fecha_corte DESC')],
    )
    op.create_index(
        'ix_corrida_estado_created_at', 'corrida', ['estado', 'created_at'],
    )
    op.create_index(
        'ix_corrida_estado_latido_en', 'corrida', ['estado', 'latido_en'],
        postgresql_where=sa.text('latido_en IS NOT NULL'),
    )


def _create_corrida_sucursal() -> None:
    op.create_table(
        'corrida_sucursal',
        _uuid('corrida_id', nullable=False),
        _uuid('sucursal_id', nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column(
            'estado', sa.String(length=12), nullable=False,
            server_default='PENDIENTE',
        ),
        sa.Column('codigo', sa.String(length=20), nullable=True),
        sa.Column('mensaje', sa.Text(), nullable=True),
        sa.Column('fecha_apertura', sa.Date(), nullable=True),
        sa.Column('divisor', sa.SmallInteger(), nullable=True),
        sa.Column('buckets_operados', sa.SmallInteger(), nullable=True),
        sa.Column('dias_empaque', sa.Numeric(6, 2), nullable=True),
        sa.Column('dias_transito', sa.Numeric(6, 2), nullable=True),
        sa.Column('dias_seguridad', sa.Numeric(6, 2), nullable=True),
        sa.Column('dias_entre_pedidos', sa.Numeric(6, 2), nullable=True),
        sa.Column('parametros', postgresql.JSONB(), nullable=True),
        sa.Column('coberturas', postgresql.JSONB(), nullable=True),
        _entero('lineas'),
        _entero('excluidas'),
        sa.Column('unidades', sa.Numeric(14, 2), nullable=True),
        sa.Column('valor', sa.Numeric(16, 2), nullable=True),
        _entero('intentos'),
        _tz('iniciado_en'),
        _tz('terminado_en'),
        sa.ForeignKeyConstraint(
            ['corrida_id'], ['corrida.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('corrida_id', 'sucursal_id'),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'OK', 'OMITIDA', 'FALLIDA')",
            name='ck_corrida_sucursal_estado',
        ),
    )
    op.create_index(
        'ix_corrida_sucursal_corrida_estado', 'corrida_sucursal',
        ['corrida_id', 'estado'],
    )


def _columnas_linea_entradas() -> list:
    """Entradas crudas propias: meses, precio, U, V, W, X y Z."""
    def entrada(nombre, nullable=False):
        return sa.Column(nombre, sa.Numeric(14, 2), nullable=nullable)

    columnas = [entrada(f'venta_m{i}') for i in _MESES_CERRADOS]
    columnas += [entrada(f'perdida_m{i}') for i in _MESES_CERRADOS]
    columnas += [entrada('venta_m0', True), entrada('perdida_m0', True)]
    columnas += [entrada('precio', True)]
    columnas += [sa.Column('unidad_empaque', sa.Integer(), nullable=False)]
    columnas += [entrada(n) for n in (
        'inventario', 'transito', 'backorder', 'ajuste',
    )]
    return columnas


def _columnas_linea_salidas() -> list:
    """Salidas del motor: K, L, M, N, clases, cobertura, pedido y quiebre."""
    def calculo(nombre):
        return sa.Column(nombre, sa.Numeric(18, 6), nullable=True)

    def num(nombre, precision, escala):
        return sa.Column(nombre, sa.Numeric(precision, escala), nullable=True)

    return [
        calculo('demanda_perdida'),
        calculo('demanda_perdida_mensualizada'),
        calculo('demanda_prom_simple'),
        calculo('venta_m0_proyectada'),
        calculo('demanda_ponderada'),
        num('peso_pct', 14, 10),
        num('peso_acum_pct', 14, 10),
        sa.Column('orden_abc', sa.Integer(), nullable=True),
        sa.Column('clase_abc', sa.String(length=1), nullable=True),
        sa.Column('clase_fms', sa.String(length=1), nullable=True),
        sa.Column('clase', sa.String(length=2), nullable=True),
        sa.Column('meses_con_venta', sa.SmallInteger(), nullable=True),
        num('meses_cobertura', 12, 6),
        num('inventario_final', 14, 2),
        num('y_recibido', 14, 2),
        calculo('stock_objetivo'),
        num('pedido_sugerido', 14, 2),
        num('pedido_final', 14, 2),
        num('valor_pedido', 16, 2),
        num('cobertura_final', 12, 6),
        num('cobertura_actual', 12, 6),
        calculo('punto_minimo'),
        calculo('punto_maximo'),
        sa.Column('estado_quiebre', sa.String(length=24), nullable=True),
    ]


def _create_corrida_linea() -> None:
    op.create_table(
        'corrida_linea',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        _uuid('corrida_id', nullable=False),
        _uuid('sucursal_id', nullable=False),
        _uuid('referencia_id', nullable=False),
        sa.Column('codigo_referencia', sa.String(length=100), nullable=False),
        sa.Column('nombre_parte', sa.String(length=255), nullable=True),
        sa.Column('linea_comercial', sa.String(length=60), nullable=True),
        sa.Column('ultima_fecha_entrada', sa.Date(), nullable=True),
        *_columnas_linea_entradas(),
        *_columnas_linea_salidas(),
        sa.Column('motivo_exclusion', sa.String(length=30), nullable=True),
        _uuid('sustituta_final_id'),
        sa.Column(
            'banderas', postgresql.ARRAY(sa.String(length=30)),
            nullable=False, server_default=sa.text("'{}'"),
        ),
        sa.Column('detalle_consolidacion', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ['corrida_id'], ['corrida.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.ForeignKeyConstraint(['sustituta_final_id'], ['referencia.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'corrida_id', 'sucursal_id', 'referencia_id',
            name='uq_corrida_linea_corrida_sucursal_referencia',
        ),
    )
    op.create_index(
        'ix_corrida_linea_corrida_sucursal_orden_abc', 'corrida_linea',
        ['corrida_id', 'sucursal_id', 'orden_abc'],
    )
    op.create_index(
        'ix_corrida_linea_corrida_referencia', 'corrida_linea',
        ['corrida_id', 'referencia_id'],
    )
    op.create_index(
        'ix_corrida_linea_corrida_estado_quiebre', 'corrida_linea',
        ['corrida_id', 'estado_quiebre'],
    )


def _create_corrida_resumen() -> None:
    op.create_table(
        'corrida_resumen',
        _uuid('corrida_id', nullable=False),
        _uuid('sucursal_id', nullable=False),
        sa.Column('clase', sa.String(length=8), nullable=False),
        sa.Column(
            'unidades', sa.Numeric(14, 2), nullable=False,
            server_default='0',
        ),
        _entero('referencias'),
        sa.Column(
            'valor', sa.Numeric(16, 2), nullable=False, server_default='0',
        ),
        sa.Column('porcentaje_peso', sa.Numeric(12, 6), nullable=True),
        sa.ForeignKeyConstraint(
            ['corrida_id'], ['corrida.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('corrida_id', 'sucursal_id', 'clase'),
    )


def _create_corrida_carga() -> None:
    op.create_table(
        'corrida_carga',
        _uuid('corrida_id', nullable=False),
        _uuid('carga_id', nullable=False),
        sa.Column('tipo', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ['corrida_id'], ['corrida.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.PrimaryKeyConstraint('corrida_id', 'carga_id'),
    )
    op.create_index(
        'ix_corrida_carga_carga_id', 'corrida_carga', ['carga_id'],
    )


def upgrade() -> None:
    # `env.py` corre cada migración dentro de `context.begin_transaction()`,
    # así que SET LOCAL vale solo para esta transacción: si una FK no logra
    # su lock sobre la tabla referenciada en 5 s, falla rápido en vez de
    # encolarse detrás de lecturas largas y bloquear los requests.
    op.execute("SET LOCAL lock_timeout = '5s'")
    _create_corrida()
    _create_corrida_sucursal()
    _create_corrida_linea()
    _create_corrida_resumen()
    _create_corrida_carga()


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    for tabla in (
        'corrida_carga', 'corrida_resumen', 'corrida_linea',
        'corrida_sucursal', 'corrida',
    ):
        op.drop_table(tabla)
