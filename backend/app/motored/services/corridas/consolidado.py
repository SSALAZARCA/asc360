"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B6, ADR-8,
decisión F4-9, spec CO-01..CO-11): la matriz consolidada de una corrida.

Filas = referencias (código y nombre) con cantidad a pedir en alguna tienda;
columnas = las tiendas de la corrida (por nombre), cada una con el estado de
su pedido; celda = la cantidad a pedir (`pedido_final`) de esa referencia en
esa tienda. Totales por tienda (sobre TODAS las referencias, no sólo la
página), por referencia y general.

Pensada para 47 tiendas y miles de referencias: la respuesta está acotada
por la paginación de las REFERENCIAS (SQL, no en memoria) y la corrida se
lee en cuatro consultas, sin importar el tamaño:

1. la corrida (existe y cómo se llama);
2. las columnas: UNA agrupada por tienda, con sus totales;
3. la página de referencias: UNA agrupada por referencia, con `HAVING
   SUM > 0`, orden por código y `LIMIT/OFFSET`; el total de referencias va
   en la misma consulta (`count(*) OVER ()`), y sólo si la página queda vacía
   más allá del final se pregunta aparte;
4. las celdas de ESA página: sólo las de sus referencias, dispersas.

El total general es la suma de los totales de las columnas (idénticos por
construcción; una consulta menos sobre todas las líneas). Ninguna consulta
toca las líneas excluidas. Todo se apoya en los índices que ya tiene
`corrida_linea` (`corrida_id` + sucursal o referencia): no hay migración.

La búsqueda `q` y el filtro `estado_pedido` acotan las FILAS y las COLUMNAS
respectivamente: `q` nunca cambia los totales de las tiendas (CO-05);
`estado_pedido` deja sólo las tiendas con ese estado y las referencias se
suman sobre ellas. Las tiendas FALLIDA u OMITIDA salen como columnas
marcadas, sin números y sin celdas (CO-06). Sólo lectura: ningún commit.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.sucursal import Sucursal
from app.motored.services.corridas import estados, valores

CERO = Decimal("0.00")


def _c(valor: Any) -> Decimal:
    """Cantidad o valor con sus dos decimales (también el 0 de un SUM
    vacío), para que el JSON diga siempre `"0.00"` y nunca `"0"`."""
    return Decimal(valor).quantize(CERO)


# --- Consultas --------------------------------------------------------------


def _consulta_columnas(corrida_id: UUID, estado_pedido: Optional[str]):
    """Una fila por tienda de la corrida con lo que se pide en ella, sobre
    todas sus líneas no excluidas (una tienda fallida no tiene líneas)."""
    cs, cl = CorridaSucursal, CorridaLinea
    consulta = (
        select(
            cs.sucursal_id, Sucursal.nombre, cs.estado, cs.estado_pedido,
            cs.codigo, cs.mensaje,
            func.coalesce(func.sum(cl.pedido_final), 0),
            func.coalesce(func.sum(cl.valor_pedido), 0))
        .select_from(cs)
        .join(Sucursal, Sucursal.id == cs.sucursal_id)
        .outerjoin(cl, (cl.corrida_id == cs.corrida_id)
                   & (cl.sucursal_id == cs.sucursal_id)
                   & cl.motivo_exclusion.is_(None))
        .where(cs.corrida_id == corrida_id)
        .group_by(cs.sucursal_id, Sucursal.nombre, cs.estado,
                  cs.estado_pedido, cs.codigo, cs.mensaje)
        .order_by(Sucursal.nombre, cs.sucursal_id))
    if estado_pedido is not None:
        consulta = consulta.where(cs.estado_pedido == estado_pedido)
    return consulta


def _busqueda(q: Optional[str]) -> list:
    """Código o nombre que contiene `q` (comodines escapados)."""
    if not q:
        return []
    patron = f"%{valores.escapar_like(q)}%"
    return [or_(
        CorridaLinea.codigo_referencia.ilike(patron, escape="\\"),
        CorridaLinea.nombre_parte.ilike(patron, escape="\\"))]


def _por_referencia(
    corrida_id: UUID, sucursal_ids: Sequence[UUID], q: Optional[str],
):
    """Las referencias con algo que pedir en las tiendas dadas, con su
    total: agrupado, sin las líneas excluidas y sin orden ni página."""
    cl = CorridaLinea
    total = func.sum(cl.pedido_final)
    return (
        select(cl.referencia_id, cl.codigo_referencia,
               func.max(cl.nombre_parte), total)
        .where(cl.corrida_id == corrida_id,
               cl.motivo_exclusion.is_(None),
               cl.sucursal_id.in_(sorted(sucursal_ids)),
               *_busqueda(q))
        .group_by(cl.referencia_id, cl.codigo_referencia)
        .having(total > 0))


def _consulta_pagina(
    corrida_id: UUID, sucursal_ids: Sequence[UUID], q: Optional[str],
    limite: int, offset: int,
):
    """UNA página de referencias por código, más cuántas hay en total."""
    cl = CorridaLinea
    return (
        _por_referencia(corrida_id, sucursal_ids, q)
        .add_columns(func.count().over())
        .order_by(cl.codigo_referencia, cl.referencia_id)
        .limit(limite).offset(offset))


def _consulta_celdas(
    corrida_id: UUID, sucursal_ids: Sequence[UUID],
    referencia_ids: Sequence[UUID],
):
    """Las cantidades mayores que 0 de las referencias de la página."""
    cl = CorridaLinea
    return (
        select(cl.referencia_id, cl.sucursal_id, cl.pedido_final)
        .where(cl.corrida_id == corrida_id,
               cl.motivo_exclusion.is_(None),
               cl.pedido_final > 0,
               cl.referencia_id.in_(sorted(referencia_ids)),
               cl.sucursal_id.in_(sorted(sucursal_ids))))


# --- Armado de la respuesta -------------------------------------------------


def _tienda(fila: Sequence[Any]) -> Dict[str, Any]:
    """La columna de una tienda; sin números si su cálculo no fue OK."""
    (sucursal_id, nombre, estado, estado_pedido, codigo, mensaje,
     unidades, valor) = fila
    ok = estado == estados.SUC_OK
    return {
        "sucursal_id": sucursal_id, "nombre": nombre, "estado": estado,
        "estado_pedido": estado_pedido, "codigo": codigo,
        "mensaje": mensaje,
        "unidades": _c(unidades) if ok else None,
        "valor": _c(valor) if ok else None,
    }


def _filas(
    pagina: Sequence[Any], celdas: Sequence[Any],
) -> List[Dict[str, Any]]:
    """Cada referencia de la página con sus celdas (una por tienda con
    cantidad), por el texto del id de la tienda."""
    por_referencia: Dict[UUID, Dict[str, Decimal]] = {}
    for referencia_id, sucursal_id, cantidad in celdas:
        por_referencia.setdefault(referencia_id, {})[
            str(sucursal_id)] = _c(cantidad)
    return [
        {"referencia_id": fila[0], "codigo": fila[1], "nombre": fila[2],
         "total": _c(fila[3]),
         "celdas": por_referencia.get(fila[0], {})}
        for fila in pagina]


def _totales(tiendas: Sequence[Dict[str, Any]]) -> Dict[str, Decimal]:
    """La suma de lo que se pide en las tiendas calculadas."""
    return {
        "unidades": sum((t["unidades"] for t in tiendas if t["unidades"]
                         is not None), CERO),
        "valor": sum((t["valor"] for t in tiendas if t["valor"]
                      is not None), CERO),
    }


# --- Lectura ----------------------------------------------------------------


async def _pagina(
    db, corrida_id: UUID, sucursal_ids: Sequence[UUID], q: Optional[str],
    limite: int, offset: int,
) -> Tuple[list, int]:
    """La página de referencias y el total. Una página vacía más allá del
    final no trae el total en sus filas: se cuenta aparte."""
    filas = (await db.execute(_consulta_pagina(
        corrida_id, sucursal_ids, q, limite, offset))).all()
    if filas:
        return filas, int(filas[0][4])
    if offset == 0:
        return filas, 0
    agrupada = _por_referencia(corrida_id, sucursal_ids, q).subquery()
    total = (await db.execute(
        select(func.count()).select_from(agrupada))).first()
    return filas, int(total[0])


async def consolidado(
    db, corrida_id: UUID, q: Optional[str] = None,
    estado_pedido: Optional[str] = None, limite: int = 100, offset: int = 0,
) -> Optional[Dict[str, Any]]:
    """La matriz de la corrida (ver el docstring del módulo) o `None` si no
    existe. Una corrida sin tiendas calculadas (PENDIENTE, CALCULANDO) da la
    matriz vacía, sin error (CO-10)."""
    corrida = (await db.execute(
        select(Corrida.id, Corrida.codigo, Corrida.estado,
               Corrida.es_escenario)
        .where(Corrida.id == corrida_id))).first()
    if corrida is None:
        return None
    columnas = (await db.execute(
        _consulta_columnas(corrida_id, estado_pedido))).all()
    tiendas = [_tienda(fila) for fila in columnas]
    visibles = [t["sucursal_id"] for t in tiendas if t["unidades"] is not None]
    filas, total = [], 0
    if visibles:
        pagina, total = await _pagina(
            db, corrida_id, visibles, q, limite, offset)
        celdas = [] if not pagina else (await db.execute(_consulta_celdas(
            corrida_id, visibles, [f[0] for f in pagina]))).all()
        filas = _filas(pagina, celdas)
    return {
        "corrida_id": corrida[0], "codigo": corrida[1], "estado": corrida[2],
        "es_escenario": corrida[3], "tiendas": tiendas, "filas": filas,
        "totales": _totales(tiendas), "total": total, "limite": limite,
        "offset": offset,
    }
