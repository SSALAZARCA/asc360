"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S7, ADR-9): lecturas
de la API de corridas (lista, detalle, progreso, líneas).

Sólo SELECTs, nunca un commit. El alcance por sucursal (T19) se aplica acá,
en SQL, no en la API: `alcance` es `None` (ADMIN, COMPRAS, CONSULTA) o el
conjunto de sucursales del usuario de SUCURSAL, y restringe TODA lectura que
toque una sucursal (filas de `corrida_sucursal`, `corrida_resumen`,
`corrida_linea`); una corrida sin ninguna sucursal visible responde `None`
(la API la trata como 404: ni siquiera se confirma que existe). Armar las
respuestas es de `proyecciones.py` (puro).

Las líneas se devuelven como filas ORM; la API las serializa con sus
decimales exactos. Los conteos de la lista (`sucursales_total`,
`sucursales_procesadas`) son subconsultas sobre las sucursales visibles.
"""
from datetime import date
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_linea_historial import CorridaLineaHistorial
from app.motored.models.corrida_resumen import CorridaResumen
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import Usuario
from app.motored.services.corridas import (
    estados,
    lecturas_pedido,
    pedido_tienda,
    proyecciones,
    valores,
)

Alcance = Optional[FrozenSet[UUID]]


def _en_alcance(columna, alcance: Alcance) -> list:
    """Condición `columna IN (sucursales visibles)`; ninguna sin alcance."""
    return [] if alcance is None else [columna.in_(sorted(alcance))]


def _visible(alcance: Alcance) -> list:
    """La corrida tiene al menos una sucursal visible."""
    if alcance is None:
        return []
    return [exists().where(
        CorridaSucursal.corrida_id == Corrida.id,
        *_en_alcance(CorridaSucursal.sucursal_id, alcance))]


async def _corrida_visible(db, corrida_id: UUID, alcance: Alcance):
    resultado = await db.execute(
        select(Corrida).where(Corrida.id == corrida_id, *_visible(alcance)))
    return resultado.scalars().first()


async def _sucursales(db, corrida_id: UUID, alcance: Alcance) -> list:
    cs = CorridaSucursal
    resultado = await db.execute(
        select(
            cs.sucursal_id, cs.orden, cs.estado, cs.estado_pedido, cs.codigo,
            cs.mensaje,
            cs.lineas, cs.excluidas, cs.unidades, cs.valor,
            cs.fecha_apertura, cs.divisor, cs.dias_empaque,
            cs.dias_transito, cs.dias_seguridad, cs.dias_entre_pedidos,
            cs.intentos, cs.parametros, Sucursal.nombre)
        .join(Sucursal, Sucursal.id == cs.sucursal_id)
        .where(cs.corrida_id == corrida_id,
               *_en_alcance(cs.sucursal_id, alcance))
        .order_by(cs.orden))
    return resultado.all()


# --- Lista ------------------------------------------------------------------


def _tienda_en(alcance: Alcance, *estados_pedido: str):
    """EXISTS una tienda visible de la corrida con el pedido en alguno de
    esos estados."""
    condicion = (
        CorridaSucursal.estado_pedido == estados_pedido[0]
        if len(estados_pedido) == 1
        else CorridaSucursal.estado_pedido.in_(estados_pedido))
    return exists().where(
        CorridaSucursal.corrida_id == Corrida.id, condicion,
        *_en_alcance(CorridaSucursal.sucursal_id, alcance))


def _filtro_pedidos(alcance: Alcance, pedidos: str):
    """`abiertos`: alguna tienda en BORRADOR; `por_enviar`: alguna CERRADO;
    `enviados`: alguna ENVIADO y ninguna pendiente (BORRADOR o CERRADO)."""
    if pedidos == "abiertos":
        return _tienda_en(alcance, estados.PEDIDO_BORRADOR)
    if pedidos == "por_enviar":
        return _tienda_en(alcance, estados.PEDIDO_CERRADO)
    return and_(
        _tienda_en(alcance, estados.PEDIDO_ENVIADO),
        ~_tienda_en(
            alcance, estados.PEDIDO_BORRADOR, estados.PEDIDO_CERRADO))


def _filtros_lista(
    alcance: Alcance, proveedor_id: Optional[UUID], estado: Optional[str],
    desde: Optional[date], hasta: Optional[date], escenario: Optional[bool],
    pedidos: Optional[str] = None,
) -> list:
    filtros = _visible(alcance)
    if pedidos is not None:
        filtros.append(_filtro_pedidos(alcance, pedidos))
    if proveedor_id is not None:
        filtros.append(Corrida.proveedor_id == proveedor_id)
    if estado is not None:
        filtros.append(Corrida.estado == estado)
    if desde is not None:
        filtros.append(Corrida.fecha_corte >= desde)
    if hasta is not None:
        filtros.append(Corrida.fecha_corte <= hasta)
    if escenario is not None:
        filtros.append(Corrida.es_escenario.is_(escenario))
    return filtros


def _contar_sucursales(alcance: Alcance, solo_procesadas: bool):
    condiciones = [
        CorridaSucursal.corrida_id == Corrida.id,
        *_en_alcance(CorridaSucursal.sucursal_id, alcance)]
    if solo_procesadas:
        condiciones.append(
            CorridaSucursal.estado != estados.SUC_PENDIENTE)
    return (select(func.count()).select_from(CorridaSucursal)
            .where(*condiciones).scalar_subquery())


def _consulta_lista(alcance: Alcance):
    return select(
        Corrida.id, Corrida.codigo, Corrida.proveedor_id,
        Corrida.fecha_corte, Corrida.estado, Corrida.es_escenario,
        Corrida.alcance, Corrida.invalidada, Corrida.created_at,
        Corrida.terminado_en, Corrida.cerrada_en,
        Corrida.log[0]["nota"].astext.label("nota"),
        _contar_sucursales(alcance, False).label("sucursales_total"),
        _contar_sucursales(alcance, True).label("sucursales_procesadas"))


async def listar(
    db, *, alcance: Alcance, proveedor_id: Optional[UUID],
    estado: Optional[str], desde: Optional[date], hasta: Optional[date],
    escenario: Optional[bool], limite: int, offset: int,
    pedidos: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Página de corridas (la más reciente primero) y el total filtrado.
    `pedidos` (abiertos, por_enviar, enviados) deja las corridas que tienen
    una tienda en ese punto del ciclo; cada item trae su resumen de
    pedidos."""
    filtros = _filtros_lista(
        alcance, proveedor_id, estado, desde, hasta, escenario, pedidos)
    total = await db.execute(
        select(func.count()).select_from(Corrida).where(*filtros))
    filas = await db.execute(
        _consulta_lista(alcance).where(*filtros)
        .order_by(Corrida.created_at.desc(), Corrida.codigo.desc())
        .limit(limite).offset(offset))
    items = [proyecciones.item_de_fila(f) for f in filas.all()]
    resumen = await pedido_tienda.resumen_pedidos(
        db, [item["id"] for item in items], alcance)
    for item in items:
        item["pedidos"] = proyecciones.resumen_de_lista(
            resumen.get(item["id"]))
    return items, total.scalars().first() or 0


# --- Detalle y progreso -----------------------------------------------------


async def detalle(
    db, corrida_id: UUID, alcance: Alcance,
) -> Optional[Dict[str, Any]]:
    """Cabecera, cargas usadas, snapshot, estado por sucursal, resumen,
    avisos y antigüedades; `None` si no existe o no es visible."""
    corrida = await _corrida_visible(db, corrida_id, alcance)
    if corrida is None:
        return None
    sucursales = await _sucursales(db, corrida_id, alcance)
    resumen = await db.execute(
        select(CorridaResumen)
        .where(CorridaResumen.corrida_id == corrida_id,
               *_en_alcance(CorridaResumen.sucursal_id, alcance)))
    cargas = await db.execute(
        select(
            CorridaCarga.tipo, CargaArchivo.id, CargaArchivo.nombre_archivo,
            CargaArchivo.estado, CargaArchivo.periodo_desde,
            CargaArchivo.periodo_hasta)
        .join(CargaArchivo, CargaArchivo.id == CorridaCarga.carga_id)
        .where(CorridaCarga.corrida_id == corrida_id)
        .order_by(CorridaCarga.tipo, CargaArchivo.id))
    a_pedir = await _a_pedir(db, corrida_id, alcance)
    eventos = await lecturas_pedido.ultimos_eventos(
        db, corrida_id, alcance)
    return proyecciones.armar_detalle(
        corrida, sucursales, resumen.scalars().all(), cargas.all(), alcance,
        a_pedir, eventos)


async def _a_pedir(db, corrida_id: UUID, alcance: Alcance) -> list:
    """Unidades, referencias y valor de `pedido_final` por sucursal y clase
    (las líneas excluidas nunca cuentan)."""
    cl = CorridaLinea
    resultado = await db.execute(
        select(
            cl.sucursal_id, cl.clase,
            func.sum(cl.pedido_final).label("unidades"),
            func.count().label("referencias"),
            func.sum(cl.valor_pedido).label("valor"))
        .where(cl.corrida_id == corrida_id, cl.motivo_exclusion.is_(None),
               *_en_alcance(cl.sucursal_id, alcance))
        .group_by(cl.sucursal_id, cl.clase))
    return resultado.all()


async def progreso(
    db, corrida_id: UUID, alcance: Alcance,
) -> Optional[Dict[str, Any]]:
    """Avance de la corrida sobre las sucursales visibles."""
    corrida = await _corrida_visible(db, corrida_id, alcance)
    if corrida is None:
        return None
    sucursales = await _sucursales(db, corrida_id, alcance)
    return proyecciones.armar_progreso(corrida, sucursales, alcance)


# --- Líneas -----------------------------------------------------------------


def _filtros_edicion(
    q: Optional[str], solo_editadas: bool, solo_fuera_empaque: bool,
) -> list:
    """Filtros de F4: búsqueda por código o nombre (comodines escapados),
    líneas con historial y líneas cuya cantidad no es múltiplo del
    empaque."""
    filtros = []
    if q:
        patron = f"%{valores.escapar_like(q)}%"
        filtros.append(or_(
            CorridaLinea.codigo_referencia.ilike(patron, escape="\\"),
            CorridaLinea.nombre_parte.ilike(patron, escape="\\")))
    if solo_editadas:
        filtros.append(exists().where(
            CorridaLineaHistorial.linea_id == CorridaLinea.id))
    if solo_fuera_empaque:
        filtros.append(and_(
            CorridaLinea.pedido_final > 0, CorridaLinea.unidad_empaque > 0,
            CorridaLinea.pedido_final % CorridaLinea.unidad_empaque != 0))
    return filtros


def _filtros_lineas(
    corrida_id: UUID, alcance: Alcance, sucursal_id: Optional[UUID],
    incluir_excluidas: bool, clase: Optional[str],
    estado_quiebre: Optional[str], q: Optional[str] = None,
    solo_editadas: bool = False, solo_fuera_empaque: bool = False,
) -> list:
    filtros = [
        CorridaLinea.corrida_id == corrida_id,
        *_en_alcance(CorridaLinea.sucursal_id, alcance),
        *_filtros_edicion(q, solo_editadas, solo_fuera_empaque)]
    if sucursal_id is not None:
        filtros.append(CorridaLinea.sucursal_id == sucursal_id)
    if not incluir_excluidas:
        filtros.append(CorridaLinea.motivo_exclusion.is_(None))
    if clase is not None:
        filtros.append(CorridaLinea.clase == clase)
    if estado_quiebre is not None:
        filtros.append(CorridaLinea.estado_quiebre == estado_quiebre)
    return filtros


async def lineas(
    db, corrida_id: UUID, alcance: Alcance, *, sucursal_id: Optional[UUID],
    incluir_excluidas: bool, clase: Optional[str],
    estado_quiebre: Optional[str], limite: int, offset: int,
    q: Optional[str] = None, solo_editadas: bool = False,
    solo_fuera_empaque: bool = False,
) -> Optional[Tuple[list, int]]:
    """Página de líneas en el orden ABC de cada sucursal y el total
    filtrado; `None` si la corrida no existe o no es visible. Las líneas
    excluidas (SUSTITUIDA, INACTIVA_SIN_REEMPLAZO) sólo si se piden."""
    visible = await db.execute(
        select(Corrida.id).where(
            Corrida.id == corrida_id, *_visible(alcance)))
    if visible.scalars().first() is None:
        return None
    filtros = _filtros_lineas(
        corrida_id, alcance, sucursal_id, incluir_excluidas, clase,
        estado_quiebre, q, solo_editadas, solo_fuera_empaque)
    total = await db.execute(
        select(func.count()).select_from(CorridaLinea).where(*filtros))
    pagina = await db.execute(
        select(CorridaLinea).where(*filtros)
        .order_by(
            CorridaLinea.sucursal_id,
            CorridaLinea.orden_abc.asc().nulls_last(),
            CorridaLinea.codigo_referencia)
        .limit(limite).offset(offset))
    return pagina.scalars().all(), total.scalars().first() or 0


# --- Ediciones: última de cada línea e historial ----------------------------


async def ediciones_de(
    db, linea_ids: Iterable[int],
) -> Dict[int, proyecciones.UltimaEdicion]:
    """La última edición de cada línea (una sola consulta `DISTINCT ON`).
    Una línea nunca editada no aparece en el resultado."""
    ids = list(linea_ids)
    if not ids:
        return {}
    h = CorridaLineaHistorial
    resultado = await db.execute(
        select(h.linea_id, Usuario.nombre, h.creado_en, h.motivo)
        .join(Usuario, Usuario.id == h.usuario_id)
        .where(h.linea_id.in_(ids))
        .ext(distinct_on(h.linea_id))
        .order_by(h.linea_id, h.creado_en.desc(), h.id.desc()))
    return {
        fila[0]: proyecciones.UltimaEdicion(fila[1], fila[2], fila[3])
        for fila in resultado.all()}


async def historial_linea(
    db, corrida_id: UUID, linea_id: int,
) -> Optional[List[Dict[str, Any]]]:
    """El historial de una línea, el más antiguo primero; `None` si la línea
    no pertenece a la corrida."""
    existe = await db.execute(
        select(CorridaLinea.id).where(
            CorridaLinea.id == linea_id,
            CorridaLinea.corrida_id == corrida_id))
    if existe.scalars().first() is None:
        return None
    h = CorridaLineaHistorial
    filas = await db.execute(
        select(h.id, h.linea_id, h.campo, h.valor_anterior, h.valor_nuevo,
               h.motivo, h.detalle, h.usuario_id, Usuario.nombre,
               h.creado_en)
        .join(Usuario, Usuario.id == h.usuario_id)
        .where(h.linea_id == linea_id)
        .order_by(h.creado_en.asc(), h.id.asc()))
    claves = ("id", "linea_id", "campo", "valor_anterior", "valor_nuevo",
              "motivo", "detalle", "usuario_id", "usuario", "creado_en")
    return [dict(zip(claves, fila)) for fila in filas.all()]
