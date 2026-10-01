"""fase4 pedido por tienda

Revision ID: a3f7c1d9e642
Revises: d9a2b6e04f71
Create Date: 2026-09-30 21:00:00.000000

Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B1, design ADR-2):
el estado del pedido de cada (corrida, sucursal) y sus tablas de auditoria.
Es la UNICA migracion del cambio; las demas rebanadas son solo codigo.

- `corrida_sucursal.estado_pedido` varchar(10) NULL con su CHECK
  (BORRADOR, CERRADO, ENVIADO). NULL significa "sin pedido" (sucursal
  FALLIDA u OMITIDA, escenario, o corrida no calculada).
- `corrida_linea_historial`: auditoria de cada cambio de `pedido_final`.
- `pedido_evento`: linea de tiempo del pedido por tienda (CERRADO,
  REABIERTO, ENVIADO y ENVIO_CORREGIDO, F4-15).
- `corrida_envio`: un envio por tienda, con la UNIQUE de F4-13.

Estrictamente ADITIVA: una columna nullable (solo metadatos), un CHECK y
tres tablas nuevas. El backfill llena UNICAMENTE la columna nueva (ningun
valor existente cambia) y, para las corridas que F3 dejo CERRADA, inserta un
evento CERRADO `migrado_f3` sin usuario (quien cerro queda en `detalle`).
`SET LOCAL lock_timeout` cubre los bloqueos de las FK y del ALTER para
fallar rapido en vez de hacer cola detras de una lectura larga.

Downgrade: borra las tres tablas, el CHECK y la columna. Se pierden el
estado por tienda y los envios: correrlo solo antes del uso en produccion o
despues de exportar `corrida_envio`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a3f7c1d9e642'
down_revision: Union[str, None] = 'd9a2b6e04f71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CK_ESTADO_PEDIDO = 'ck_corrida_sucursal_estado_pedido'

_BACKFILL_BORRADOR = """
UPDATE corrida_sucursal cs SET estado_pedido = 'BORRADOR'
FROM corrida c
WHERE cs.corrida_id = c.id AND NOT c.es_escenario
  AND c.estado = 'BORRADOR' AND cs.estado = 'OK'
"""
_BACKFILL_CERRADO = """
UPDATE corrida_sucursal cs SET estado_pedido = 'CERRADO'
FROM corrida c
WHERE cs.corrida_id = c.id AND NOT c.es_escenario
  AND c.estado = 'CERRADA' AND cs.estado = 'OK'
"""
_EVENTOS_MIGRADOS = """
INSERT INTO pedido_evento
    (corrida_id, sucursal_id, evento, detalle, usuario_id, creado_en)
SELECT cs.corrida_id, cs.sucursal_id, 'CERRADO',
       jsonb_strip_nulls(jsonb_build_object(
           'migrado_f3', true, 'cerrada_por', c.cerrada_por)),
       NULL, COALESCE(c.cerrada_en, now())
FROM corrida_sucursal cs JOIN corrida c ON c.id = cs.corrida_id
WHERE NOT c.es_escenario AND c.estado = 'CERRADA' AND cs.estado = 'OK'
"""


def _lista_sql(valores) -> str:
    return ', '.join(f"'{v}'" for v in valores)


def _uuid(nombre: str, nullable: bool = False) -> sa.Column:
    return sa.Column(nombre, sa.UUID(), nullable=nullable)


def _creado_en(nombre: str) -> sa.Column:
    return sa.Column(
        nombre, sa.DateTime(timezone=True), nullable=False,
        server_default=sa.text('now()'),
    )


def _fk_corrida(ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ['corrida_id'], ['corrida.id'], ondelete=ondelete,
    )


def _create_historial() -> None:
    op.create_table(
        'corrida_linea_historial',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        _uuid('corrida_id'),
        sa.Column('linea_id', sa.BigInteger(), nullable=False),
        _uuid('sucursal_id'),
        sa.Column(
            'campo', sa.String(length=30), nullable=False,
            server_default='pedido_final',
        ),
        sa.Column('valor_anterior', sa.Numeric(14, 2), nullable=False),
        sa.Column('valor_nuevo', sa.Numeric(14, 2), nullable=False),
        sa.Column('motivo', sa.String(length=24), nullable=False),
        sa.Column('detalle', postgresql.JSONB(), nullable=True),
        _uuid('usuario_id'),
        _creado_en('creado_en'),
        sa.PrimaryKeyConstraint('id'),
        _fk_corrida('CASCADE'),
        sa.ForeignKeyConstraint(
            ['linea_id'], ['corrida_linea.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.CheckConstraint(
            "campo IN ('pedido_final')",
            name='ck_corrida_linea_historial_campo',
        ),
        sa.CheckConstraint(
            "motivo IN ('MANUAL', 'RECORTE_PRESUPUESTO')",
            name='ck_corrida_linea_historial_motivo',
        ),
    )
    op.create_index(
        'ix_corrida_linea_historial_linea_creado', 'corrida_linea_historial',
        ['linea_id', sa.text('creado_en DESC')],
    )
    op.create_index(
        'ix_corrida_linea_historial_corrida_sucursal',
        'corrida_linea_historial', ['corrida_id', 'sucursal_id'],
    )


def _create_evento() -> None:
    op.create_table(
        'pedido_evento',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        _uuid('corrida_id'),
        _uuid('sucursal_id'),
        sa.Column('evento', sa.String(length=20), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('detalle', postgresql.JSONB(), nullable=True),
        _uuid('usuario_id', nullable=True),
        _creado_en('creado_en'),
        sa.PrimaryKeyConstraint('id'),
        _fk_corrida('CASCADE'),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.CheckConstraint(
            'evento IN (' + _lista_sql((
                'CERRADO', 'REABIERTO', 'ENVIADO', 'ENVIO_CORREGIDO',
            )) + ')',
            name='ck_pedido_evento_evento',
        ),
        sa.CheckConstraint(
            "evento <> 'REABIERTO' OR "
            "(motivo IS NOT NULL AND length(btrim(motivo)) > 0)",
            name='ck_pedido_evento_reabierto_motivo',
        ),
    )
    op.create_index(
        'ix_pedido_evento_corrida_sucursal_creado', 'pedido_evento',
        ['corrida_id', 'sucursal_id', 'creado_en'],
    )


def _create_envio() -> None:
    op.create_table(
        'corrida_envio',
        _uuid('corrida_id'),
        _uuid('sucursal_id'),
        _uuid('proveedor_id'),
        sa.Column('fecha_corte', sa.Date(), nullable=False),
        sa.Column(
            'numero_pedido_proveedor', sa.String(length=50), nullable=False,
        ),
        sa.Column('fecha_envio', sa.Date(), nullable=False),
        _uuid('enviada_por'),
        _creado_en('enviada_en'),
        sa.PrimaryKeyConstraint('corrida_id', 'sucursal_id'),
        _fk_corrida('RESTRICT'),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.ForeignKeyConstraint(['proveedor_id'], ['proveedor.id']),
        sa.ForeignKeyConstraint(['enviada_por'], ['usuario.id']),
        sa.UniqueConstraint(
            'proveedor_id', 'fecha_corte', 'sucursal_id',
            name='uq_corrida_envio_corte_sucursal',
        ),
        sa.CheckConstraint(
            'length(btrim(numero_pedido_proveedor)) > 0',
            name='ck_corrida_envio_numero',
        ),
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column(
        'corrida_sucursal',
        sa.Column('estado_pedido', sa.String(length=10), nullable=True),
    )
    op.create_check_constraint(
        _CK_ESTADO_PEDIDO, 'corrida_sucursal',
        'estado_pedido IN (' + _lista_sql(
            ('BORRADOR', 'CERRADO', 'ENVIADO')) + ')',
    )
    _create_historial()
    _create_evento()
    _create_envio()
    op.execute(_BACKFILL_BORRADOR)
    op.execute(_BACKFILL_CERRADO)
    op.execute(_EVENTOS_MIGRADOS)


def downgrade() -> None:
    op.drop_table('corrida_envio')
    op.drop_table('pedido_evento')
    op.drop_table('corrida_linea_historial')
    op.drop_constraint(
        _CK_ESTADO_PEDIDO, 'corrida_sucursal', type_='check',
    )
    op.drop_column('corrida_sucursal', 'estado_pedido')
