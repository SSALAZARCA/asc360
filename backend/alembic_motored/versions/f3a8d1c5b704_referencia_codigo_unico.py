"""referencia: identidad por codigo (UNIQUE codigo)

Revision ID: f3a8d1c5b704
Revises: e8c2a5f17b93
Create Date: 2026-10-03 10:00:00.000000

Una referencia se identifica por su CODIGO: proveedores distintos siempre
traen codigos distintos (decision del usuario, 2026-10-01). Se cambia el unico
`uq_referencia_codigo_proveedor` (codigo, proveedor_id) por `uq_referencia_codigo`
(codigo), de modo que corregir el proveedor de una referencia la MUEVE (mismo
id, historial intacto) en vez de duplicarla.

Guarda previa: si hay codigos repetidos ignorando mayusculas y espacios
(`upper(trim(codigo))`), la migracion ABORTA listando hasta 50 de ellos. Nunca
fusiona filas por su cuenta: 11 tablas tienen FK a `referencia` y decidir cual
sobrevive es una decision de negocio.

Luego normaliza los codigos guardados con espacios sobrantes (`trim`); la
mayuscula/minuscula no se toca.

Downgrade: restaura el unico compuesto (siempre posible, es menos estricto).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3a8d1c5b704'
down_revision: Union[str, None] = 'e8c2a5f17b93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MAX_CODIGOS_EN_MENSAJE = 50


def _abortar_si_hay_duplicados() -> None:
    filas = op.get_bind().execute(sa.text(
        "SELECT upper(trim(codigo)) AS codigo, count(*) AS n FROM referencia "
        "GROUP BY 1 HAVING count(*) > 1 ORDER BY 1 LIMIT :limite"
    ), {"limite": _MAX_CODIGOS_EN_MENSAJE + 1}).all()
    if not filas:
        return
    mostradas = filas[:_MAX_CODIGOS_EN_MENSAJE]
    detalle = ", ".join(f"{codigo} (x{n})" for codigo, n in mostradas)
    resto = " y mas" if len(filas) > _MAX_CODIGOS_EN_MENSAJE else ""
    raise RuntimeError(
        "No se puede hacer unico el codigo de referencia: hay codigos repetidos "
        f"(ignorando mayusculas y espacios): {detalle}{resto}. Unifique o elimine "
        "los duplicados a mano (cada uno puede tener movimientos asociados) y vuelva a migrar."
    )


def upgrade() -> None:
    _abortar_si_hay_duplicados()
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("UPDATE referencia SET codigo = trim(codigo) WHERE codigo <> trim(codigo)")
    op.drop_constraint('uq_referencia_codigo_proveedor', 'referencia', type_='unique')
    op.create_unique_constraint('uq_referencia_codigo', 'referencia', ['codigo'])


def downgrade() -> None:
    op.drop_constraint('uq_referencia_codigo', 'referencia', type_='unique')
    op.create_unique_constraint(
        'uq_referencia_codigo_proveedor', 'referencia', ['codigo', 'proveedor_id'])
