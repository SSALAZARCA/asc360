"""encuesta satisfaccion schema

Revision ID: c4e81a7d3f26
Revises: 7be41d9c0a26
Create Date: 2026-09-29 15:00:00.000000

Motored satisfaction survey, slice T2. Five NEW tables (no change to any
existing table, so it is safe on the production DB):

- `encuesta_carga`: one uploaded customer-base batch.
- `encuesta_registro`: one customer/service row to survey; unique per
  (carga, cedula, placa, tipo), indexed by cedula for the public lookup.
- `encuesta_respuesta`: the customer's answer, at most one per registro. The
  six matrix answers are nullable (NULL = NS/NR).
- `caso_detractor`: one case per detractor response. `numero` is an identity
  column (human-friendly case number); `resultado` is set iff `estado` is
  CERRADO (`ck_caso_detractor_resultado_iff_cerrado`).
- `caso_detractor_accion`: APPEND-ONLY action log. A PL/pgSQL trigger raises on
  any UPDATE or DELETE, so corrections must be new rows.

Downgrade drops the trigger and function first, then every table in reverse
dependency order. Note: the trigger also blocks `DELETE`, which is why the
downgrade uses `DROP TABLE` (DDL, not row deletes).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e81a7d3f26'
down_revision: Union[str, None] = '7be41d9c0a26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MATRIX_COLUMNS = (
    'p_explicacion_tecnica',
    'p_confianza_reparacion',
    'p_servicio_taller',
    'p_calidad_mecanicos',
    'p_claridad_cobros',
    'p_originalidad_repuestos',
)

_APPEND_ONLY_FUNCTION = 'caso_detractor_accion_append_only'
_APPEND_ONLY_TRIGGER = 'trg_caso_detractor_accion_append_only'


def _create_encuesta_carga() -> None:
    op.create_table(
        'encuesta_carga',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('nombre_archivo', sa.String(length=255), nullable=False),
        sa.Column('total_registros', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def _create_encuesta_registro() -> None:
    op.create_table(
        'encuesta_registro',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('carga_id', sa.UUID(), nullable=False),
        sa.Column('tipo', sa.String(length=16), nullable=False),
        sa.Column('nombre', sa.String(length=255), nullable=False),
        sa.Column('cedula', sa.String(length=32), nullable=False),
        sa.Column('celular', sa.String(length=32), nullable=True),
        sa.Column('linea', sa.String(length=100), nullable=True),
        sa.Column('placa', sa.String(length=16), nullable=False),
        sa.Column('sic', sa.String(length=32), nullable=True),
        sa.Column('centro_servicio', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['encuesta_carga.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'carga_id', 'cedula', 'placa', 'tipo',
            name='uq_encuesta_registro_carga_cedula_placa_tipo',
        ),
        sa.CheckConstraint(
            "tipo IN ('SERVICIO_TALLER', 'VENTA')", name='ck_encuesta_registro_tipo',
        ),
    )
    op.create_index('ix_encuesta_registro_cedula', 'encuesta_registro', ['cedula'])


def _create_encuesta_respuesta() -> None:
    op.create_table(
        'encuesta_respuesta',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('registro_id', sa.UUID(), nullable=False),
        sa.Column('satisfaccion_general', sa.SmallInteger(), nullable=False),
        *(sa.Column(col, sa.SmallInteger(), nullable=True) for col in _MATRIX_COLUMNS),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('autoriza_datos', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['registro_id'], ['encuesta_registro.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('registro_id', name='uq_encuesta_respuesta_registro_id'),
        sa.CheckConstraint(
            'satisfaccion_general BETWEEN 1 AND 5',
            name='ck_encuesta_respuesta_satisfaccion_general',
        ),
        *(
            sa.CheckConstraint(
                f'{col} IS NULL OR {col} BETWEEN 1 AND 5',
                name=f'ck_encuesta_respuesta_{col}',
            )
            for col in _MATRIX_COLUMNS
        ),
    )


def _create_caso_detractor() -> None:
    op.create_table(
        'caso_detractor',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('respuesta_id', sa.UUID(), nullable=False),
        sa.Column('numero', sa.Integer(), sa.Identity(), nullable=False),
        sa.Column('estado', sa.String(length=16), nullable=False, server_default='ABIERTO'),
        sa.Column('resultado', sa.String(length=16), nullable=True),
        sa.Column('asignado_a', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('cerrado_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['respuesta_id'], ['encuesta_respuesta.id']),
        sa.ForeignKeyConstraint(['asignado_a'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('respuesta_id', name='uq_caso_detractor_respuesta_id'),
        sa.UniqueConstraint('numero', name='uq_caso_detractor_numero'),
        sa.CheckConstraint(
            "estado IN ('ABIERTO', 'EN_GESTION', 'CERRADO')",
            name='ck_caso_detractor_estado',
        ),
        sa.CheckConstraint(
            "resultado IN ('RECUPERADO', 'NO_RECUPERADO', 'NO_CONTACTABLE')",
            name='ck_caso_detractor_resultado',
        ),
        sa.CheckConstraint(
            "(estado = 'CERRADO' AND resultado IS NOT NULL) "
            "OR (estado <> 'CERRADO' AND resultado IS NULL)",
            name='ck_caso_detractor_resultado_iff_cerrado',
        ),
    )


def _create_caso_detractor_accion() -> None:
    op.create_table(
        'caso_detractor_accion',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('caso_id', sa.UUID(), nullable=False),
        sa.Column('usuario_id', sa.UUID(), nullable=True),
        sa.Column('tipo', sa.String(length=16), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('estado_anterior', sa.String(length=16), nullable=True),
        sa.Column('estado_nuevo', sa.String(length=16), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['caso_id'], ['caso_detractor.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "tipo IN ('APERTURA', 'LLAMADA', 'WHATSAPP', 'NOTA', "
            "'CAMBIO_ESTADO', 'COMPENSACION', 'CORRECCION')",
            name='ck_caso_detractor_accion_tipo',
        ),
    )
    op.create_index(
        'ix_caso_detractor_accion_caso_id_created_at',
        'caso_detractor_accion',
        ['caso_id', 'created_at'],
    )


def _create_append_only_trigger() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_APPEND_ONLY_FUNCTION}() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'caso_detractor_accion is append-only: % is not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_APPEND_ONLY_TRIGGER}
        BEFORE UPDATE OR DELETE ON caso_detractor_accion
        FOR EACH ROW EXECUTE FUNCTION {_APPEND_ONLY_FUNCTION}()
        """
    )


def upgrade() -> None:
    _create_encuesta_carga()
    _create_encuesta_registro()
    _create_encuesta_respuesta()
    _create_caso_detractor()
    _create_caso_detractor_accion()
    _create_append_only_trigger()


def downgrade() -> None:
    op.execute(f'DROP TRIGGER IF EXISTS {_APPEND_ONLY_TRIGGER} ON caso_detractor_accion')
    op.execute(f'DROP FUNCTION IF EXISTS {_APPEND_ONLY_FUNCTION}()')
    op.drop_index(
        'ix_caso_detractor_accion_caso_id_created_at', table_name='caso_detractor_accion',
    )
    op.drop_table('caso_detractor_accion')
    op.drop_table('caso_detractor')
    op.drop_table('encuesta_respuesta')
    op.drop_index('ix_encuesta_registro_cedula', table_name='encuesta_registro')
    op.drop_table('encuesta_registro')
    op.drop_table('encuesta_carga')
