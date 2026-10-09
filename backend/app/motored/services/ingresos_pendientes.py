"""
Motored -- invoices pending ingreso (odd/tasks/motored-ingresos-pendientes.md).

A HMCL invoice (`factura_proveedor_linea`) is PENDING when:
- its date is on or after `verificable_desde` (the earliest loaded ingreso
  date: before it there is no ingreso data to compare with),
- its carga is not ANULADO,
- there is no live ingreso (`ingreso_factura`, carga not ANULADO) for the
  same `(prefijo_rh, numero_rh)`,
- its net units are positive (NRH credit notes carry negative quantities; a
  fully credited document is not pending).
One item per document and PRINCIPAL store (associated stores roll up). The
document date is the earliest line date. The asesores of the store confirm
"LLEGO" / "NO_HA_LLEGADO" (one shared state, with history).

`calcular_pendientes`, `resumen` and `por_tienda` are pure; the rest reads
and writes the database.
"""
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.factura_confirmacion_ingreso import (
    FacturaConfirmacionIngreso,
    FacturaConfirmacionIngresoHistorial,
)
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.services import sucursal_grupo
from app.motored.services.reloj import hoy_bogota

SIN_CONFIRMAR = "SIN_CONFIRMAR"
LLEGO = "LLEGO"
NO_HA_LLEGADO = "NO_HA_LLEGADO"
ESTADOS_CONFIRMABLES = (LLEGO, NO_HA_LLEGADO)
CANALES = ("web", "link")

MSG_FACTURA = "La factura no es válida."
MSG_ESTADO = "El estado debe ser «Llegó» o «No ha llegado»."
MSG_SIN_TIENDA = "No tienes una tienda asignada para confirmar facturas."
MSG_NO_PENDIENTE = "Esta factura ya no está pendiente de ingreso."

_FACTURA_RE = re.compile(r"^([A-Z]{2})\s*(\d+)$")

Clave = Tuple[str, int]


class PendienteError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class Actor:
    """Who confirms: the logged-in usuario, or the asesor behind a link."""
    nombre: str
    usuario_id: Optional[uuid.UUID] = None
    cedula: Optional[str] = None


def parsear_factura(factura: Any) -> Optional[Clave]:
    """`"RH 482915"` / `"rh482915"` -> `("RH", 482915)`; None when invalid."""
    if not isinstance(factura, str):
        return None
    m = _FACTURA_RE.match(factura.strip().upper())
    return (m.group(1), int(m.group(2))) if m else None


def nombre_factura(prefijo: str, numero: int) -> str:
    return f"{prefijo} {numero}"


def calcular_pendientes(
    lineas: Iterable[Any], ingresos: Set[Clave], verificable_desde: Optional[date],
    hoy: date, principal: Dict[uuid.UUID, uuid.UUID],
    nombres: Dict[uuid.UUID, str], confirmaciones: Dict[Tuple[str, int, uuid.UUID], Any],
) -> List[Dict[str, Any]]:
    """The pending documents, oldest first. `lineas` rows expose
    prefijo_rh, numero_rh, sucursal_id, fecha_factura, cantidad, valor_total
    (they may already be partial sums)."""
    if verificable_desde is None:
        return []
    docs: Dict[Tuple[str, int, uuid.UUID], Dict[str, Any]] = {}
    for linea in lineas:
        if (linea.prefijo_rh, linea.numero_rh) in ingresos:
            continue
        tienda = principal.get(linea.sucursal_id, linea.sucursal_id)
        clave = (linea.prefijo_rh, linea.numero_rh, tienda)
        doc = docs.get(clave)
        if doc is None:
            docs[clave] = {
                "fecha": linea.fecha_factura, "unidades": Decimal(linea.cantidad),
                "valor": Decimal(linea.valor_total)}
            continue
        doc["fecha"] = min(doc["fecha"], linea.fecha_factura)
        doc["unidades"] += Decimal(linea.cantidad)
        doc["valor"] += Decimal(linea.valor_total)

    items = []
    for (prefijo, numero, tienda), doc in docs.items():
        if doc["fecha"] < verificable_desde or doc["unidades"] <= 0:
            continue
        conf = confirmaciones.get((prefijo, numero, tienda))
        items.append({
            "prefijo_rh": prefijo, "numero_rh": numero,
            "factura": nombre_factura(prefijo, numero),
            "sucursal_id": tienda, "tienda": nombres.get(tienda, ""),
            "fecha": doc["fecha"], "dias": (hoy - doc["fecha"]).days,
            "unidades": float(doc["unidades"]), "valor": float(doc["valor"]),
            "estado": conf.estado if conf is not None else SIN_CONFIRMAR,
            "confirmado_por": conf.actualizado_por_nombre if conf is not None else None,
            "confirmado_en": conf.actualizado_en if conf is not None else None,
        })
    items.sort(key=lambda i: (i["fecha"], i["prefijo_rh"], i["numero_rh"]))
    return items


def resumen(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "pendientes": len(items),
        "llegaron_sin_ingresar": sum(1 for i in items if i["estado"] == LLEGO),
        "sin_confirmar": sum(1 for i in items if i["estado"] == SIN_CONFIRMAR),
        "aun_no_llegan": sum(1 for i in items if i["estado"] == NO_HA_LLEGADO),
        "mas_antigua": max((i["dias"] for i in items), default=None),
        "valor_pendiente": round(sum(i["valor"] for i in items), 2),
    }


def por_tienda(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per store: the resumen of its items; most pending first."""
    grupos: Dict[uuid.UUID, List[Dict[str, Any]]] = {}
    for item in items:
        grupos.setdefault(item["sucursal_id"], []).append(item)
    filas = [
        {"sucursal_id": sid, "tienda": grupo[0]["tienda"], **resumen(grupo)}
        for sid, grupo in grupos.items()]
    filas.sort(key=lambda f: (-f["pendientes"], f["tienda"]))
    return filas


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def _carga_viva():
    return CargaArchivo.estado != "ANULADO"


async def verificable_desde(db: AsyncSession) -> Optional[date]:
    stmt = (
        select(func.min(IngresoFactura.fecha_ingreso))
        .join(CargaArchivo, CargaArchivo.id == IngresoFactura.carga_id)
        .where(_carga_viva()))
    return (await db.execute(stmt)).scalar()


async def _ingresos_vivos(db: AsyncSession) -> Set[Clave]:
    stmt = (
        select(IngresoFactura.prefijo_rh, IngresoFactura.numero_rh)
        .join(CargaArchivo, CargaArchivo.id == IngresoFactura.carga_id)
        .where(_carga_viva()))
    return {(p, n) for p, n in (await db.execute(stmt)).all()}


async def _lineas_desde(db: AsyncSession, desde: date) -> List[Any]:
    stmt = (
        select(
            FacturaProveedorLinea.prefijo_rh, FacturaProveedorLinea.numero_rh,
            FacturaProveedorLinea.sucursal_id,
            func.min(FacturaProveedorLinea.fecha_factura).label("fecha_factura"),
            func.sum(FacturaProveedorLinea.cantidad).label("cantidad"),
            func.sum(FacturaProveedorLinea.valor_total).label("valor_total"))
        .join(CargaArchivo, CargaArchivo.id == FacturaProveedorLinea.carga_id)
        .where(_carga_viva())
        .group_by(
            FacturaProveedorLinea.prefijo_rh, FacturaProveedorLinea.numero_rh,
            FacturaProveedorLinea.sucursal_id))
    return list((await db.execute(stmt)).all())


async def _confirmaciones(db: AsyncSession) -> Dict[Tuple[str, int, uuid.UUID], Any]:
    filas = (await db.execute(select(FacturaConfirmacionIngreso))).scalars().all()
    return {(f.prefijo_rh, f.numero_rh, f.sucursal_id): f for f in filas}


async def pendientes(
    db: AsyncSession, sucursal_ids: Optional[Iterable[uuid.UUID]] = None,
    hoy: Optional[date] = None,
) -> List[Dict[str, Any]]:
    desde = await verificable_desde(db)
    if desde is None:
        return []
    principal = await sucursal_grupo.principal_de(db)
    nombres = {sid: nombre for sid, nombre in (
        await db.execute(select(Sucursal.id, Sucursal.nombre))).all()}
    items = calcular_pendientes(
        await _lineas_desde(db, desde), await _ingresos_vivos(db), desde,
        hoy or hoy_bogota(), principal, nombres, await _confirmaciones(db))
    if sucursal_ids is not None:
        permitidas = {principal.get(s, s) for s in sucursal_ids}
        items = [i for i in items if i["sucursal_id"] in permitidas]
    return items


async def historial(
    db: AsyncSession, factura: Clave, sucursal_id: uuid.UUID,
) -> List[Dict[str, Any]]:
    prefijo, numero = factura
    stmt = (
        select(FacturaConfirmacionIngresoHistorial)
        .where(
            FacturaConfirmacionIngresoHistorial.prefijo_rh == prefijo,
            FacturaConfirmacionIngresoHistorial.numero_rh == numero,
            FacturaConfirmacionIngresoHistorial.sucursal_id == sucursal_id)
        .order_by(FacturaConfirmacionIngresoHistorial.creado_en.desc(),
                  FacturaConfirmacionIngresoHistorial.id))
    return [
        {"estado": h.estado, "por": h.por_nombre, "canal": h.canal,
         "en": h.creado_en}
        for h in (await db.execute(stmt)).scalars().all()]


async def confirmar(
    db: AsyncSession, factura: Any, sucursal_id: uuid.UUID, estado: Any,
    actor: Actor, canal: str, ahora: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Sets the shared state of a document that is pending for the store and
    logs it. 422 for a malformed factura/estado, 409 when the document is
    not pending for that store (any more). Commits."""
    clave = parsear_factura(factura)
    if clave is None:
        raise PendienteError(422, MSG_FACTURA)
    if estado not in ESTADOS_CONFIRMABLES:
        raise PendienteError(422, MSG_ESTADO)
    principal = await sucursal_grupo.principal_de(db)
    tienda = principal.get(sucursal_id, sucursal_id)
    vigentes = await pendientes(db, [tienda])
    item = next(
        (i for i in vigentes
         if (i["prefijo_rh"], i["numero_rh"]) == clave), None)
    if item is None:
        raise PendienteError(409, MSG_NO_PENDIENTE)

    prefijo, numero = clave
    ahora = ahora or datetime.now().astimezone()
    existente = (await db.execute(
        select(FacturaConfirmacionIngreso).where(
            FacturaConfirmacionIngreso.prefijo_rh == prefijo,
            FacturaConfirmacionIngreso.numero_rh == numero,
            FacturaConfirmacionIngreso.sucursal_id == tienda,
        ).with_for_update())).scalar_one_or_none()
    if existente is None:
        existente = FacturaConfirmacionIngreso(
            id=uuid.uuid4(), prefijo_rh=prefijo, numero_rh=numero,
            sucursal_id=tienda)
        db.add(existente)
    existente.estado = estado
    existente.actualizado_por_usuario_id = actor.usuario_id
    existente.actualizado_por_nombre = actor.nombre
    existente.actualizado_por_cedula = actor.cedula
    existente.actualizado_en = ahora
    db.add(FacturaConfirmacionIngresoHistorial(
        id=uuid.uuid4(), prefijo_rh=prefijo, numero_rh=numero,
        sucursal_id=tienda, estado=estado, por_usuario_id=actor.usuario_id,
        por_nombre=actor.nombre, por_cedula=actor.cedula, canal=canal,
        creado_en=ahora))
    await db.commit()
    return {**item, "estado": estado, "confirmado_por": actor.nombre,
            "confirmado_en": ahora}


async def tiendas_de_asesor(
    db: AsyncSession, usuario_id: Optional[uuid.UUID], cedula: Optional[str],
) -> List[uuid.UUID]:
    """The principal stores of the active vendedor rows linked to the usuario
    (by `usuario_id`) or carrying the given (already approved) cédula.
    Sorted, without repeats."""
    cond = []
    if usuario_id is not None:
        cond.append(Vendedor.usuario_id == usuario_id)
    if cedula:
        cond.append(Vendedor.cedula == cedula)
    if not cond:
        return []
    stmt = select(Vendedor.sucursal_id).where(
        Vendedor.activo.is_(True), Vendedor.sucursal_id.is_not(None), or_(*cond))
    ids = {sid for (sid,) in (await db.execute(stmt)).all()}
    if not ids:
        return []
    principal = await sucursal_grupo.principal_de(db)
    return sorted({principal.get(s, s) for s in ids}, key=str)


async def confirmar_en_tiendas(
    db: AsyncSession, factura: Any, tiendas: List[uuid.UUID], estado: Any,
    actor: Actor, canal: str,
) -> Dict[str, Any]:
    """`confirmar` in the first of `tiendas` where the document is pending
    (an asesor may work for more than one store); 409 when in none."""
    ultimo: Optional[PendienteError] = None
    for tienda in tiendas:
        try:
            return await confirmar(db, factura, tienda, estado, actor, canal)
        except PendienteError as exc:
            if exc.status_code != 409:
                raise
            ultimo = exc
    raise ultimo or PendienteError(409, MSG_NO_PENDIENTE)


async def para_asesor(db: AsyncSession, tiendas: List[uuid.UUID]) -> Dict[str, Any]:
    """The `pendientes_ingreso` block of the asesor detail for the store(s)."""
    desde = await verificable_desde(db)
    items = await pendientes(db, tiendas) if (desde and tiendas) else []
    return {"verificable_desde": desde, "items": items, "resumen": resumen(items)}
