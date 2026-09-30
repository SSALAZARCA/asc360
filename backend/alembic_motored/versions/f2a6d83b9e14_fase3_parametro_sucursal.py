"""fase3 parametro sucursal

Revision ID: f2a6d83b9e14
Revises: e5b19c47a3d8
Create Date: 2026-09-29 22:05:00.000000

Fase 3 "Motor" (sdd/motored-pedidos-motor, S4a, design ADR-7): agrega
`parametro_metodologia.sucursal_id`, un alcance por sucursal para claves
como `dias_entre_pedidos`. NULL = alcance global, por lo que todas las
filas existentes quedan globales y ninguna lectura actual cambia.

Aditiva: una columna NULLABLE sin default (en Postgres es solo un cambio de
catálogo, no reescribe la tabla) más un índice sobre una tabla de pocas
filas. La FK a `sucursal` valida contra una columna sin datos, así que el
escaneo es trivial. `parametro_metodologia` es leída por el flujo de F2 en
producción: el `SET LOCAL lock_timeout` evita encolarse detrás de una
lectura larga (mismo patrón que `5c2e8a1f9b47`).

Downgrade: borra el índice y la columna. Antes de bajar, las filas con
`sucursal_id` no nulo pasarían a leerse como globales, por eso el downgrade
las BORRA primero: dejarlas cambiaría el valor global de la clave.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a6d83b9e14'
down_revision: Union[str, None] = 'e5b19c47a3d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDICE = 'ix_parametro_metodologia_clave_sucursal_vigente'


def upgrade() -> None:
    # SET LOCAL vale solo para la transacción de esta migración (env.py).
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column(
        'parametro_metodologia',
        sa.Column(
            'sucursal_id',
            sa.UUID(),
            sa.ForeignKey('sucursal.id'),
            nullable=True,
        ),
    )
    op.create_index(
        _INDICE,
        'parametro_metodologia',
        ['clave', 'sucursal_id', 'vigente_desde'],
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "DELETE FROM parametro_metodologia WHERE sucursal_id IS NOT NULL"
    )
    op.drop_index(_INDICE, table_name='parametro_metodologia')
    op.drop_column('parametro_metodologia', 'sucursal_id')
