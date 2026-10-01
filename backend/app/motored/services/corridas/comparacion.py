"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B6, ADR-9,
decisión F4-8, spec SC-07..SC-13): comparar un escenario (una corrida con
parámetros alternativos) con la corrida real de la misma semana.

Compara el SUGERIDO del motor de los dos lados (`pedido_sugerido`), que es lo
que aísla el efecto de los overrides; el `pedido_final` real (lo que COMPRAS
ajustó) va sólo como contexto. Por (tienda, referencia): lo sugerido en la
real, lo sugerido en la prueba y su delta (prueba - real); lo que existe de
un solo lado vale 0 en el otro (SC-08).

Emparejamiento (E-CORRIDA-063, SC-10/SC-11, siempre antes de leer líneas): el
primero debe ser un escenario; el segundo, una corrida real que existe y ya
se calculó (BORRADOR o la CERRADA que dejó F3; el estado de sus pedidos no
importa) con la MISMA fecha de corte y el MISMO proveedor.

Sólo se comparan las tiendas calculadas (OK) en las dos corridas; las demás
se listan como no comparables, con su estado de cada lado (SC-13).

Cuatro consultas, sin importar el tamaño: las dos corridas, sus tiendas, UN
`FULL OUTER JOIN` de las líneas no excluidas de los dos lados, paginado en SQL
(el total de filas viaja con la página; sólo si ésta queda vacía más allá del
final se cuenta aparte), y los totales por tienda y por lado en una agrupada.
Los totales cubren siempre todas las tiendas comparables, con o sin el filtro
de tienda y de `solo_diferencias`. Sólo lectura: ningún commit.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.sucursal import Sucursal
from app.motored.services.corridas import codigos, estados
from app.motored.services.corridas.codigos import ErrorCorrida

CERO = Decimal("0.00")


def _c(valor: Any) -> Decimal:
    """Cantidad o valor con sus dos decimales (también lo que falta de un
    lado, que sale como 0 del SQL), para que el JSON sea uniforme."""
    return Decimal(valor).quantize(CERO)


# --- El emparejamiento ------------------------------------------------------


def _invalida(detalle: str) -> ErrorCorrida:
    codigo = codigos.E_CORRIDA_COMPARACION_INVALIDA
    return ErrorCorrida(codigo, codigos.mensaje(codigo, detalle=detalle))


def _validar_pareja(escenario: Sequence[Any], real: Optional[Sequence[Any]]):
    """E-CORRIDA-063 si no son un escenario y su corrida real de la misma
    semana. Las filas son `(id, codigo, estado, es_escenario, fecha_corte,
    proveedor_id)`."""
    if not escenario[3]:
        raise _invalida("la corrida indicada no es un escenario")
    if real is None:
        raise _invalida("la corrida real no existe")
    if real[3]:
        raise _invalida("la corrida con la que se compara es otro escenario")
    if real[2] not in estados.CALCULADAS:
        raise _invalida(
            f"la corrida real {real[1]} no está calculada (está {real[2]})")
    if real[4] != escenario[4]:
        raise _invalida(
            "las dos corridas deben ser de la misma fecha de corte")
    if real[5] != escenario[5]:
        raise _invalida("las dos corridas deben ser del mismo proveedor")


# --- Consultas --------------------------------------------------------------


def _consulta_corridas(corridas: Sequence[UUID]):
    return select(
        Corrida.id, Corrida.codigo, Corrida.estado, Corrida.es_escenario,
        Corrida.fecha_corte, Corrida.proveedor_id,
    ).where(Corrida.id.in_(list(corridas)))


def _consulta_tiendas(corridas: Sequence[UUID]):
    cs = CorridaSucursal
    return (
        select(cs.corrida_id, cs.sucursal_id, Sucursal.nombre, cs.estado)
        .join(Sucursal, Sucursal.id == cs.sucursal_id)
        .where(cs.corrida_id.in_(list(corridas))))


def _lado(corrida_id: UUID, sucursal_ids: Sequence[UUID], nombre: str):
    """Las líneas no excluidas de UNA corrida en las tiendas dadas."""
    cl = CorridaLinea
    return (
        select(cl.sucursal_id, cl.referencia_id, cl.codigo_referencia,
               cl.nombre_parte, cl.clase, cl.pedido_sugerido,
               cl.pedido_final)
        .where(cl.corrida_id == corrida_id,
               cl.motivo_exclusion.is_(None),
               cl.sucursal_id.in_(sorted(sucursal_ids)))
        .subquery(nombre))


def _consulta_filas(
    escenario_id: UUID, real_id: UUID, sucursal_ids: Sequence[UUID],
    solo_diferencias: bool,
):
    """`(consulta, orden)`: el FULL OUTER JOIN por (tienda, referencia) con
    lo sugerido de cada lado (0 si falta), sin página."""
    real = _lado(real_id, sucursal_ids, "real")
    prueba = _lado(escenario_id, sucursal_ids, "prueba")
    sucursal = func.coalesce(real.c.sucursal_id, prueba.c.sucursal_id)
    referencia = func.coalesce(real.c.referencia_id, prueba.c.referencia_id)
    codigo = func.coalesce(
        real.c.codigo_referencia, prueba.c.codigo_referencia)
    sug_real = func.coalesce(real.c.pedido_sugerido, 0)
    sug_prueba = func.coalesce(prueba.c.pedido_sugerido, 0)
    unidas = real.join(prueba, and_(
        real.c.sucursal_id == prueba.c.sucursal_id,
        real.c.referencia_id == prueba.c.referencia_id), full=True)
    consulta = (
        select(sucursal, Sucursal.nombre, referencia, codigo,
               func.coalesce(real.c.nombre_parte, prueba.c.nombre_parte),
               real.c.clase, prueba.c.clase, sug_real, sug_prueba,
               func.coalesce(real.c.pedido_final, 0))
        .select_from(unidas.join(Sucursal, Sucursal.id == sucursal)))
    if solo_diferencias:
        consulta = consulta.where(sug_prueba != sug_real)
    return consulta, (Sucursal.nombre, codigo, sucursal, referencia)


def _consulta_totales(
    corridas: Sequence[UUID], sucursal_ids: Sequence[UUID],
):
    """Unidades y valor SUGERIDOS por corrida y tienda, en una agrupada."""
    cl = CorridaLinea
    valor = func.round(cl.pedido_sugerido * func.coalesce(cl.precio, 0), 2)
    return (
        select(cl.corrida_id, cl.sucursal_id,
               func.coalesce(func.sum(cl.pedido_sugerido), 0),
               func.coalesce(func.sum(valor), 0))
        .where(cl.corrida_id.in_(list(corridas)),
               cl.motivo_exclusion.is_(None),
               cl.sucursal_id.in_(sorted(sucursal_ids)))
        .group_by(cl.corrida_id, cl.sucursal_id))


# --- Tiendas ----------------------------------------------------------------


def _motivo(estado_real: Optional[str], estado_prueba: Optional[str]) -> str:
    if estado_prueba is None:
        return "La tienda no está en el escenario."
    if estado_real is None:
        return "La tienda no está en la corrida real."
    if estado_real != estados.SUC_OK:
        return f"La corrida real no tiene pedido de la tienda ({estado_real})."
    return f"El escenario no calculó la tienda ({estado_prueba})."


def _clasificar(
    filas: Sequence[Any], escenario_id: UUID, real_id: UUID,
) -> Tuple[Dict[UUID, str], List[Dict[str, Any]]]:
    """`(comparables, no_comparables)`: las tiendas OK en las dos corridas
    (id -> nombre, por nombre) y las demás con el estado de cada lado."""
    nombres: Dict[UUID, str] = {}
    por_lado: Dict[UUID, Dict[UUID, str]] = {escenario_id: {}, real_id: {}}
    for corrida_id, sucursal_id, nombre, estado in filas:
        nombres[sucursal_id] = nombre
        por_lado[corrida_id][sucursal_id] = estado
    comparables: Dict[UUID, str] = {}
    no_comparables = []
    for sucursal_id in sorted(nombres, key=lambda s: (nombres[s], s)):
        real = por_lado[real_id].get(sucursal_id)
        prueba = por_lado[escenario_id].get(sucursal_id)
        if real == estados.SUC_OK and prueba == estados.SUC_OK:
            comparables[sucursal_id] = nombres[sucursal_id]
            continue
        no_comparables.append({
            "sucursal_id": sucursal_id, "nombre": nombres[sucursal_id],
            "estado_real": real, "estado_prueba": prueba,
            "motivo": _motivo(real, prueba)})
    return comparables, no_comparables


def _totales_por_sucursal(
    filas: Sequence[Any], comparables: Dict[UUID, str], escenario_id: UUID,
    real_id: UUID,
) -> List[Dict[str, Any]]:
    """Por tienda comparable, lo sugerido de cada lado y su diferencia."""
    lados = {
        (corrida_id, sucursal_id): (_c(unidades), _c(valor))
        for corrida_id, sucursal_id, unidades, valor in filas}
    totales = []
    for sucursal_id, nombre in comparables.items():
        u_real, v_real = lados.get((real_id, sucursal_id), (CERO, CERO))
        u_prueba, v_prueba = lados.get(
            (escenario_id, sucursal_id), (CERO, CERO))
        totales.append({
            "sucursal_id": sucursal_id, "nombre": nombre,
            "unidades_real": u_real, "unidades_prueba": u_prueba,
            "diferencia_unidades": u_prueba - u_real,
            "valor_real": v_real, "valor_prueba": v_prueba,
            "diferencia_valor": v_prueba - v_real})
    return totales


# --- Filas ------------------------------------------------------------------


def _fila(fila: Sequence[Any]) -> Dict[str, Any]:
    (sucursal_id, sucursal, referencia_id, codigo, nombre, clase_real,
     clase_prueba, sug_real, sug_prueba, final_real) = fila[:10]
    return {
        "sucursal_id": sucursal_id, "sucursal": sucursal,
        "referencia_id": referencia_id, "codigo": codigo, "nombre": nombre,
        "clase_real": clase_real, "clase_prueba": clase_prueba,
        "sugerido_real": _c(sug_real), "sugerido_prueba": _c(sug_prueba),
        "delta": _c(sug_prueba) - _c(sug_real),
        "pedido_final_real": _c(final_real)}


async def _leer_filas(
    db, escenario_id: UUID, real_id: UUID, sucursal_ids: Sequence[UUID],
    solo_diferencias: bool, limite: int, offset: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """Una página de filas y el total. Una página vacía más allá del final
    no trae el total en sus filas: se cuenta aparte."""
    base, orden = _consulta_filas(
        escenario_id, real_id, sucursal_ids, solo_diferencias)
    pagina = (await db.execute(
        base.add_columns(func.count().over())
        .order_by(*orden).limit(limite).offset(offset))).all()
    if pagina:
        return [_fila(f) for f in pagina], int(pagina[0][10])
    if offset == 0:
        return [], 0
    total = (await db.execute(
        select(func.count()).select_from(base.subquery()))).first()
    return [], int(total[0])


# --- Lectura ----------------------------------------------------------------


def _tiendas_de_filas(
    comparables: Dict[UUID, str], sucursal_id: Optional[UUID],
) -> List[UUID]:
    """Las tiendas de las filas: todas las comparables o, con filtro, esa
    sola (ninguna si no es comparable)."""
    if sucursal_id is None:
        return list(comparables)
    return [sucursal_id] if sucursal_id in comparables else []


def _ref(fila: Sequence[Any]) -> Dict[str, Any]:
    return {"id": fila[0], "codigo": fila[1], "estado": fila[2],
            "es_escenario": fila[3]}


async def comparar(
    db, escenario_id: UUID, real_id: UUID,
    sucursal_id: Optional[UUID] = None, solo_diferencias: bool = False,
    limite: int = 100, offset: int = 0,
) -> Optional[Dict[str, Any]]:
    """El escenario contra su corrida real (ver el docstring del módulo) o
    `None` si el escenario no existe. `ErrorCorrida` E-CORRIDA-063 si el
    emparejamiento no es válido. `sucursal_id` acota las filas a una tienda
    comparable (otra da ninguna fila)."""
    corridas = {f[0]: f for f in (await db.execute(
        _consulta_corridas([escenario_id, real_id]))).all()}
    escenario = corridas.get(escenario_id)
    if escenario is None:
        return None
    real = corridas.get(real_id)
    _validar_pareja(escenario, real)
    tiendas = (await db.execute(
        _consulta_tiendas([escenario_id, real_id]))).all()
    comparables, no_comparables = _clasificar(tiendas, escenario_id, real_id)
    filas, total, totales = [], 0, []
    if comparables:
        en_filas = _tiendas_de_filas(comparables, sucursal_id)
        if en_filas:
            filas, total = await _leer_filas(
                db, escenario_id, real_id, en_filas, solo_diferencias,
                limite, offset)
        totales = _totales_por_sucursal(
            (await db.execute(_consulta_totales(
                [escenario_id, real_id], list(comparables)))).all(),
            comparables, escenario_id, real_id)
    return {
        "escenario": _ref(escenario), "real": _ref(real),
        "fecha_corte": escenario[4], "filas": filas, "total": total,
        "limite": limite, "offset": offset,
        "totales_por_sucursal": totales, "no_comparables": no_comparables}
