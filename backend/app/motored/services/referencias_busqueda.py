"""
Motored Pedidos — lectura paginada de referencias
(`odd/tasks/motored-referencias-paginacion.md`, T1).

El listado genérico `GET /maestros/referencias` trae TODAS las filas (~11.7k
y creciendo). Este módulo arma las consultas para leer una página a la vez:
todo filtro va en SQL (nunca en memoria), con un COUNT y una consulta de
página que comparten exactamente el mismo `WHERE`.

Búsqueda `q`: `ILIKE '%q%'` sobre `codigo` o `nombre` (insensible a
mayúsculas). NO es insensible a tildes: la extensión `unaccent` no se usa en
ningún lado de la base de Motored, así que no se agrega acá.
"""
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia

SUSTITUTAS_LIMITE = 20
_ORDEN_ESTABLE = (Referencia.codigo, Referencia.id)


@dataclass(frozen=True)
class FiltrosReferencia:
    q: Optional[str] = None
    linea_comercial: Optional[str] = None
    activa: Optional[bool] = None
    proveedor_id: Optional[uuid.UUID] = None


def _patron_like(texto: str) -> str:
    """`%texto%` con `\\`, `%` y `_` escapados para que se busquen
    literales."""
    escapado = (
        texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_"))
    return f"%{escapado}%"


def _condicion_texto(q: Optional[str], *columnas) -> list:
    texto = (q or "").strip()
    if not texto:
        return []
    patron = _patron_like(texto)
    return [or_(*(columna.ilike(patron, escape="\\") for columna in columnas))]


def condiciones(filtros: FiltrosReferencia) -> list:
    resultado = _condicion_texto(
        filtros.q, Referencia.codigo, Referencia.nombre)
    if filtros.linea_comercial:
        resultado.append(Referencia.linea_comercial == filtros.linea_comercial)
    if filtros.activa is not None:
        resultado.append(Referencia.activa == filtros.activa)
    if filtros.proveedor_id is not None:
        resultado.append(Referencia.proveedor_id == filtros.proveedor_id)
    return resultado


async def contar_referencias(
    db: AsyncSession, filtros: FiltrosReferencia
) -> int:
    stmt = (
        select(func.count())
        .select_from(Referencia)
        .where(*condiciones(filtros))
    )
    total = (await db.execute(stmt)).scalars().first()
    return int(total or 0)


async def pagina_referencias(
    db: AsyncSession, filtros: FiltrosReferencia, page: int, page_size: int
) -> List[Tuple[Referencia, Optional[str]]]:
    """Filas `(referencia, codigo_de_su_sustituta_o_None)`. La sustituta se
    resuelve con un self-join en la MISMA consulta: con paginación, la
    sustituta casi nunca está en la página actual."""
    sustituta = aliased(Referencia)
    stmt = (
        select(Referencia, sustituta.codigo)
        .outerjoin(sustituta, Referencia.sustituida_por == sustituta.id)
        .where(*condiciones(filtros))
        .order_by(*_ORDEN_ESTABLE)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return [tuple(fila) for fila in (await db.execute(stmt)).all()]


async def filas_exportacion(
    db: AsyncSession, filtros: FiltrosReferencia
) -> List[tuple]:
    """Every row matching `filtros` (no paging) for the Excel download,
    with the SAME `WHERE` as `/buscar`. One query: the proveedor and the
    sustituta codes come from joins, never one lookup per row. Column
    order is `referencias_excel.COLUMNAS` minus the header text."""
    sustituta = aliased(Referencia)
    stmt = (
        select(
            Referencia.codigo, Proveedor.codigo, Referencia.nombre,
            Referencia.linea_comercial, Referencia.unidad_empaque,
            Referencia.precio_normal, Referencia.precio_publico,
            sustituta.codigo, Referencia.homologados, Referencia.activa,
        )
        .join(Proveedor, Referencia.proveedor_id == Proveedor.id)
        .outerjoin(sustituta, Referencia.sustituida_por == sustituta.id)
        .where(*condiciones(filtros))
        .order_by(*_ORDEN_ESTABLE)
    )
    return [tuple(fila) for fila in (await db.execute(stmt)).all()]


async def lineas_comerciales(db: AsyncSession) -> List[str]:
    columna = Referencia.linea_comercial
    stmt = (
        select(columna)
        .distinct()
        .where(columna.is_not(None), columna != "")
        .order_by(columna)
    )
    return list((await db.execute(stmt)).scalars().all())


async def buscar_sustitutas(
    db: AsyncSession,
    proveedor_id: uuid.UUID,
    q: Optional[str],
    exclude_id: Optional[uuid.UUID],
) -> List[Referencia]:
    """Candidatas a sustituta: MISMO proveedor (regla de negocio, también
    validada al guardar), SOLO activas (decisión de negocio) y nunca la
    referencia misma. Filtra únicamente las sugerencias: una sustituta ya
    asignada que después quedó inactiva (cadena A->B->C) se sigue mostrando
    por su código, porque `pagina_referencias` la resuelve sin mirar
    `activa`."""
    filtros = [
        Referencia.proveedor_id == proveedor_id,
        Referencia.activa == True,  # noqa: E712 (SQL, not Python)
    ]
    filtros += _condicion_texto(q, Referencia.codigo, Referencia.nombre)
    if exclude_id is not None:
        filtros.append(Referencia.id != exclude_id)
    stmt = (
        select(Referencia)
        .where(*filtros)
        .order_by(*_ORDEN_ESTABLE)
        .limit(SUSTITUTAS_LIMITE)
    )
    return list((await db.execute(stmt)).scalars().all())
