"""
Motored -- transfers between stores still alive in the ERP
(odd/tasks/motored-traslados-pendientes.md, T2).

A TRASLADOS load is a FULL snapshot of the transfers still alive in the ERP.
The current snapshot is the latest non-ANULADO APLICADO TRASLADOS carga; a
transfer is PENDING while it is in that snapshot, and it leaves the list on
its own when a newer load no longer has it (received in the ERP). A transfer
is the group `(nro_documento, bodega_salida)` (the document number repeats
across origin bodegas); its receiving store is the principal store of the
destination bodega (associated stores roll up). The receiving store certifies
"RECIBIDO" / "NO_HA_LLEGADO" (one shared state, with history); a transfer
marked RECIBIDO that is still in the snapshot carries `aviso_erp` = true: the
store must also receive it in the ERP.

`calcular_traslados`, `resumen` and `por_tienda` are pure; the rest reads and
writes the database.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.sucursal import Sucursal
from app.motored.models.traslado import (
    TrasladoConfirmacion,
    TrasladoConfirmacionHistorial,
    TrasladoLinea,
)
from app.motored.services import sucursal_grupo
from app.motored.services.ingresos_pendientes import Actor, PendienteError
from app.motored.services.reloj import hoy_bogota

SIN_CONFIRMAR = "SIN_CONFIRMAR"
RECIBIDO = "RECIBIDO"
NO_HA_LLEGADO = "NO_HA_LLEGADO"
ESTADOS_CONFIRMABLES = (RECIBIDO, NO_HA_LLEGADO)

MSG_TRASLADO = "El traslado no es válido."
MSG_ESTADO = "El estado debe ser «Recibido» o «No ha llegado»."
MSG_NO_PENDIENTE = "Este traslado ya no está pendiente."

Clave = Tuple[str, str]


def _texto(valor: Any) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _nombre_origen(
    linea: Any, principal: Dict[uuid.UUID, uuid.UUID],
    nombres: Dict[uuid.UUID, str],
) -> str:
    """Origin store name; the bodega description (else its code) when the
    origin bodega has no store."""
    if linea.sucursal_salida_id is not None:
        tienda = principal.get(linea.sucursal_salida_id, linea.sucursal_salida_id)
        if nombres.get(tienda):
            return nombres[tienda]
    return _texto(linea.descripcion_bodega_salida) or linea.bodega_salida


def _grupos(lineas: Iterable[Any]) -> Dict[Clave, List[Any]]:
    grupos: Dict[Clave, List[Any]] = {}
    for linea in lineas:
        grupos.setdefault(
            (linea.nro_documento, linea.bodega_salida), []).append(linea)
    return grupos


def _detalle(grupo: List[Any]) -> List[Dict[str, Any]]:
    """The group's lines, one per reference (quantities summed), by code."""
    por_ref: Dict[str, Dict[str, Any]] = {}
    for linea in grupo:
        fila = por_ref.setdefault(linea.referencia_codigo, {
            "referencia": linea.referencia_codigo,
            "descripcion": linea.descripcion, "cantidad": Decimal(0)})
        fila["cantidad"] += Decimal(linea.cantidad)
        fila["descripcion"] = fila["descripcion"] or linea.descripcion
    return [{**por_ref[ref], "cantidad": float(por_ref[ref]["cantidad"])}
            for ref in sorted(por_ref)]


def calcular_traslados(
    lineas: Iterable[Any], hoy: date, principal: Dict[uuid.UUID, uuid.UUID],
    nombres: Dict[uuid.UUID, str], confirmaciones: Dict[Clave, Any],
) -> List[Dict[str, Any]]:
    """The pending transfers of a snapshot, oldest first. `lineas` rows expose
    nro_documento, fecha, bodega_salida, descripcion_bodega_salida,
    sucursal_salida_id, sucursal_entrada_id, referencia_codigo, descripcion
    and cantidad. The receiving store is the one of the group's first line."""
    items = []
    for (documento, bodega), grupo in _grupos(lineas).items():
        grupo = sorted(grupo, key=lambda linea: linea.fecha)
        fecha = grupo[0].fecha
        tienda = principal.get(
            grupo[0].sucursal_entrada_id, grupo[0].sucursal_entrada_id)
        detalle = _detalle(grupo)
        conf = confirmaciones.get((documento, bodega))
        estado = conf.estado if conf is not None else SIN_CONFIRMAR
        items.append({
            "documento": documento, "bodega_salida": bodega,
            "sale": _nombre_origen(grupo[0], principal, nombres),
            "sucursal_id": tienda, "llega": nombres.get(tienda, ""),
            "tienda": nombres.get(tienda, ""),
            "fecha": fecha, "dias": (hoy - fecha).days,
            "refs": len(detalle), "unidades": sum(d["cantidad"] for d in detalle),
            "num_lineas": len(grupo), "lineas": detalle, "estado": estado,
            "aviso_erp": estado == RECIBIDO,
            "confirmado_por": conf.actualizado_por_nombre if conf is not None else None,
            "confirmado_en": conf.actualizado_en if conf is not None else None,
        })
    items.sort(key=lambda i: (i["fecha"], i["documento"], i["bodega_salida"]))
    return items


def resumen(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    viejo = max(items, key=lambda i: (i["dias"], i["documento"]), default=None)
    return {
        "pendientes": len(items),
        "recibidos_sin_erp": sum(1 for i in items if i["estado"] == RECIBIDO),
        "sin_confirmar": sum(1 for i in items if i["estado"] == SIN_CONFIRMAR),
        "aun_no_llegan": sum(1 for i in items if i["estado"] == NO_HA_LLEGADO),
        "mas_antiguo": None if viejo is None else {
            "documento": viejo["documento"], "tienda": viejo["tienda"],
            "dias": viejo["dias"]},
        "lineas": sum(i["num_lineas"] for i in items),
    }


def por_tienda(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per receiving store; most received-not-in-ERP first."""
    grupos: Dict[uuid.UUID, List[Dict[str, Any]]] = {}
    for item in items:
        grupos.setdefault(item["sucursal_id"], []).append(item)
    filas = [{
        "sucursal_id": sid, "tienda": g[0]["tienda"], "pendientes": len(g),
        "recibidos": sum(1 for i in g if i["estado"] == RECIBIDO),
        "sin_confirmar": sum(1 for i in g if i["estado"] == SIN_CONFIRMAR),
        "no": sum(1 for i in g if i["estado"] == NO_HA_LLEGADO),
        "mas_antiguo_dias": max(i["dias"] for i in g),
        "unidades": sum(i["unidades"] for i in g),
    } for sid, g in grupos.items()]
    filas.sort(key=lambda f: (-f["recibidos"], -f["pendientes"], f["tienda"]))
    return filas


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

async def carga_vigente(db: AsyncSession) -> Optional[Tuple[uuid.UUID, Optional[datetime]]]:
    """`(id, aplicado_en)` of the current snapshot: the latest APLICADO,
    non-ANULADO TRASLADOS carga; None when there is none."""
    stmt = (
        select(CargaArchivo.id, CargaArchivo.aplicado_en)
        .where(CargaArchivo.tipo == "TRASLADOS",
               CargaArchivo.estado == "APLICADO")
        .order_by(CargaArchivo.aplicado_en.desc().nulls_last(),
                  CargaArchivo.created_at.desc())
        .limit(1))
    fila = (await db.execute(stmt)).first()
    return None if fila is None else (fila[0], fila[1])


async def _lineas_de(db: AsyncSession, carga_id: uuid.UUID) -> List[Any]:
    stmt = select(
        TrasladoLinea.nro_documento, TrasladoLinea.fecha,
        TrasladoLinea.bodega_salida, TrasladoLinea.descripcion_bodega_salida,
        TrasladoLinea.sucursal_salida_id, TrasladoLinea.sucursal_entrada_id,
        TrasladoLinea.referencia_codigo, TrasladoLinea.descripcion,
        TrasladoLinea.cantidad,
    ).where(TrasladoLinea.carga_id == carga_id)
    return list((await db.execute(stmt)).all())


async def _confirmaciones(db: AsyncSession) -> Dict[Clave, Any]:
    filas = (await db.execute(select(TrasladoConfirmacion))).scalars().all()
    return {(f.nro_documento, f.bodega_salida): f for f in filas}


async def pendientes(
    db: AsyncSession, sucursal_ids: Optional[Iterable[uuid.UUID]] = None,
    hoy: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """The pending transfers (all, or those received by the given stores)."""
    vigente = await carga_vigente(db)
    if vigente is None:
        return []
    principal = await sucursal_grupo.principal_de(db)
    nombres = {sid: nombre for sid, nombre in (
        await db.execute(select(Sucursal.id, Sucursal.nombre))).all()}
    items = calcular_traslados(
        await _lineas_de(db, vigente[0]), hoy or hoy_bogota(), principal,
        nombres, await _confirmaciones(db))
    if sucursal_ids is not None:
        permitidas = {principal.get(s, s) for s in sucursal_ids}
        items = [i for i in items if i["sucursal_id"] in permitidas]
    return items


async def ultima_carga(db: AsyncSession) -> Optional[datetime]:
    vigente = await carga_vigente(db)
    return None if vigente is None else vigente[1]


async def historial(
    db: AsyncSession, documento: str, bodega_salida: str,
) -> List[Dict[str, Any]]:
    h = TrasladoConfirmacionHistorial
    stmt = (
        select(h)
        .where(h.nro_documento == documento.strip(),
               h.bodega_salida == bodega_salida.strip())
        .order_by(h.creado_en.desc(), h.id))
    return [
        {"estado": r.estado, "por": r.por_nombre, "canal": r.canal,
         "en": r.creado_en}
        for r in (await db.execute(stmt)).scalars().all()]


async def confirmar(
    db: AsyncSession, documento: Any, bodega_salida: Any, estado: Any,
    actor: Actor, canal: str, tiendas: Optional[List[uuid.UUID]] = None,
    ahora: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Sets the shared state of a transfer of the current snapshot and logs
    it. 422 for a malformed document/estado; 404 when the transfer is not in
    the current snapshot (or, with `tiendas`, is not received by one of
    them). Commits."""
    documento, bodega_salida = _texto(documento), _texto(bodega_salida)
    if not documento or not bodega_salida:
        raise PendienteError(422, MSG_TRASLADO)
    if estado not in ESTADOS_CONFIRMABLES:
        raise PendienteError(422, MSG_ESTADO)
    vigentes = await pendientes(db, tiendas)
    item = next((i for i in vigentes if i["documento"] == documento
                 and i["bodega_salida"] == bodega_salida), None)
    if item is None:
        raise PendienteError(404, MSG_NO_PENDIENTE)

    ahora = ahora or datetime.now().astimezone()
    # One atomic upsert: two confirmations racing on a brand-new transfer both
    # reach the unique key, and the loser updates instead of failing.
    valores = {
        "estado": estado, "actualizado_por_usuario_id": actor.usuario_id,
        "actualizado_por_nombre": actor.nombre,
        "actualizado_por_cedula": actor.cedula, "actualizado_en": ahora,
    }
    await db.execute(
        pg_insert(TrasladoConfirmacion)
        .values(id=uuid.uuid4(), nro_documento=documento,
                bodega_salida=bodega_salida, **valores)
        .on_conflict_do_update(
            index_elements=["nro_documento", "bodega_salida"], set_=valores))
    db.add(TrasladoConfirmacionHistorial(
        id=uuid.uuid4(), nro_documento=documento, bodega_salida=bodega_salida,
        estado=estado, por_usuario_id=actor.usuario_id,
        por_nombre=actor.nombre, por_cedula=actor.cedula, canal=canal,
        creado_en=ahora))
    await db.commit()
    return {**item, "estado": estado, "aviso_erp": estado == RECIBIDO,
            "confirmado_por": actor.nombre, "confirmado_en": ahora}


async def para_asesor(db: AsyncSession, tiendas: List[uuid.UUID]) -> Dict[str, Any]:
    """The `traslados` block of the asesor card for the store(s)."""
    items = await pendientes(db, tiendas) if tiendas else []
    cargada = await ultima_carga(db)
    return {"ultima_carga": cargada, "items": items,
            "resumen": resumen(items)}

