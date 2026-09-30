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
from typing import Any, Dict, FrozenSet, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import exists, func, select

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_resumen import CorridaResumen
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.sucursal import Sucursal
from app.motored.services.corridas import estados, proyecciones

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
            cs.sucursal_id, cs.orden, cs.estado, cs.codigo, cs.mensaje,
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


def _filtros_lista(
    alcance: Alcance, proveedor_id: Optional[UUID], estado: Optional[str],
    desde: Optional[date], hasta: Optional[date], escenario: Optional[bool],
) -> list:
    filtros = _visible(alcance)
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
) -> Tuple[List[Dict[str, Any]], int]:
    """Página de corridas (la más reciente primero) y el total filtrado."""
    filtros = _filtros_lista(
        alcance, proveedor_id, estado, desde, hasta, escenario)
    total = await db.execute(
        select(func.count()).select_from(Corrida).where(*filtros))
    filas = await db.execute(
        _consulta_lista(alcance).where(*filtros)
        .order_by(Corrida.created_at.desc(), Corrida.codigo.desc())
        .limit(limite).offset(offset))
    items = [proyecciones.item_de_fila(f) for f in filas.all()]
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
    return proyecciones.armar_detalle(
        corrida, sucursales, resumen.scalars().all(), cargas.all(), alcance)


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


def _filtros_lineas(
    corrida_id: UUID, alcance: Alcance, sucursal_id: Optional[UUID],
    incluir_excluidas: bool, clase: Optional[str],
    estado_quiebre: Optional[str],
) -> list:
    filtros = [
        CorridaLinea.corrida_id == corrida_id,
        *_en_alcance(CorridaLinea.sucursal_id, alcance)]
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
        estado_quiebre)
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
