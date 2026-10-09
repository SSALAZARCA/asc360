"""
Inventory counts -- the leader API's reads and its scoping
(odd/motored-conteos-inventario, WU6; design §6.1).

Owner decision on scoping: ADMIN and GERENCIA see every conteo; a
leader (LIDER_INVENTARIOS or, owner decision 2026-10-09,
COORDINADOR_REPUESTOS; `snapshot.ROLES_LIDER_CONTEO`) sees ONLY the
conteos assigned to it (`lider_id`).
Another leader's conteo is "not found" (404 at the API, never 403), so
ids never leak; the list filters them out in SQL.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, NamedTuple, Optional, Tuple

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.conteo import Conteo
from app.motored.models.conteo_snapshot_linea import ConteoSnapshotLinea
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import Usuario
from app.motored.services.auth import MotoredUser
from app.motored.services.conteos import errores, snapshot
from app.motored.services.reloj import hoy_bogota

LIMITE_LISTA = 200

_SQL_ULTIMO_INVENTARIO = text("""
SELECT s.id, s.nombre, u.carga_id, u.fecha_corte, u.aplicado_en
FROM sucursal s
LEFT JOIN LATERAL (
    SELECT d.carga_id, d.fecha_corte, c.aplicado_en
    FROM inventario_detalle d
    JOIN carga_archivo c ON c.id = d.carga_id
    WHERE d.sucursal_id = s.id AND c.estado <> 'ANULADO'
    ORDER BY d.fecha_corte DESC, c.aplicado_en DESC NULLS LAST
    LIMIT 1
) u ON true
WHERE s.activa
ORDER BY s.nombre
""")


class ResumenSnapshot(NamedTuple):
    """The frozen copy, summed: what the leader sees at Iniciar."""

    nombre_archivo: Optional[str]
    lineas: int
    valor_sistema: Optional[Decimal]
    sin_costo: int


class DatosConteo(NamedTuple):
    """Names and totals a conteo response needs beyond its own row."""

    sucursal: str
    lider: Optional[str]
    snapshot: Optional[ResumenSnapshot]


class OpcionLider(NamedTuple):
    id: uuid.UUID
    nombre: str
    email: Optional[str]
    rol: str


# Role values of a count leader, as `MotoredUser.role` carries them.
ROLES_LIDER = tuple(r.value for r in snapshot.ROLES_LIDER_CONTEO)


def es_lider(usuario: MotoredUser) -> bool:
    return usuario.role in ROLES_LIDER


def ve_lider(
        usuario: MotoredUser, lider_id: Optional[uuid.UUID]) -> bool:
    """ADMIN and GERENCIA see all; a leader only the conteos it leads."""
    if not es_lider(usuario):
        return True
    return str(lider_id) == str(usuario.user_id)


def ve_conteo(usuario: MotoredUser, conteo: Conteo) -> bool:
    return ve_lider(usuario, conteo.lider_id)


async def conteo_visible(
        db: AsyncSession, conteo_id: uuid.UUID,
        usuario: MotoredUser) -> Conteo:
    """The conteo, or ConteoNoEncontrado when it is missing or belongs
    to another leader (both look the same)."""
    conteo = await db.get(Conteo, conteo_id)
    if conteo is None or not ve_conteo(usuario, conteo):
        raise errores.ConteoNoEncontrado()
    return conteo


async def listar(
        db: AsyncSession, *, estado: Optional[str],
        sucursal_id: Optional[uuid.UUID], tipo: Optional[str],
        lider_id: Optional[uuid.UUID],
) -> List[Tuple[Conteo, str, Optional[str]]]:
    """(conteo, store name, leader name), newest date first."""
    lider = aliased(Usuario)
    consulta = (
        select(Conteo, Sucursal.nombre, lider.nombre)
        .join(Sucursal, Sucursal.id == Conteo.sucursal_id)
        .outerjoin(lider, lider.id == Conteo.lider_id)
        .order_by(Conteo.fecha_programada.desc(), Conteo.created_at.desc())
        .limit(LIMITE_LISTA))
    if estado is not None:
        consulta = consulta.where(Conteo.estado == estado)
    if sucursal_id is not None:
        consulta = consulta.where(Conteo.sucursal_id == sucursal_id)
    if tipo is not None:
        consulta = consulta.where(Conteo.tipo == tipo)
    if lider_id is not None:
        consulta = consulta.where(Conteo.lider_id == lider_id)
    filas = (await db.execute(consulta)).all()
    return [(f[0], f[1], f[2]) for f in filas]


async def _resumen_snapshot(
        db: AsyncSession, conteo: Conteo) -> Optional[ResumenSnapshot]:
    if conteo.snapshot_tomado_en is None:
        return None
    linea = ConteoSnapshotLinea
    fila = (await db.execute(
        select(
            func.count(linea.id),
            func.sum(linea.existencia * linea.costo_unitario),
            func.sum(case((linea.costo_fuente == "SIN_COSTO", 1), else_=0)),
        ).where(linea.conteo_id == conteo.id))).first()
    nombre = None
    if conteo.snapshot_carga_id is not None:
        nombre = (await db.execute(
            select(CargaArchivo.nombre_archivo).where(
                CargaArchivo.id == conteo.snapshot_carga_id))).scalar()
    valor = None if fila[1] is None else Decimal(fila[1]).quantize(
        Decimal("0.01"))
    return ResumenSnapshot(nombre, int(fila[0] or 0), valor, int(fila[2] or 0))


async def datos_conteo(db: AsyncSession, conteo: Conteo) -> DatosConteo:
    """Store and leader names, plus the snapshot totals once started."""
    sucursal = await db.get(Sucursal, conteo.sucursal_id)
    lider = None
    if conteo.lider_id is not None:
        lider = await db.get(Usuario, conteo.lider_id)
    return DatosConteo(
        sucursal.nombre if sucursal else "",
        lider.nombre if lider else None,
        await _resumen_snapshot(db, conteo))


async def lideres_activos(db: AsyncSession) -> List[OpcionLider]:
    """Active, approved users of a leader role (the schedule form)."""
    filas = (await db.execute(
        select(Usuario.id, Usuario.nombre, Usuario.email, Usuario.role)
        .where(Usuario.role.in_(snapshot.ROLES_LIDER_CONTEO),
               Usuario.activo.is_(True), Usuario.status == "approved")
        .order_by(Usuario.nombre))).all()
    return [OpcionLider(f[0], f[1], f[2], _valor_rol(f[3])) for f in filas]


def _valor_rol(rol) -> str:
    return getattr(rol, "value", rol)


async def _vigencia_horas(db: AsyncSession, ahora: datetime):
    try:
        umbrales = await snapshot.leer_umbrales(db, hoy_bogota(ahora))
    except errores.UmbralesInvalidos:
        return None
    return umbrales.vigencia_horas


async def sucursales(
        db: AsyncSession, ahora: Optional[datetime] = None) -> List[dict]:
    """Active stores with their latest non-annulled inventory carga and
    its age, so the leader sees a stale inventory before Iniciar."""
    ahora = ahora or datetime.now(timezone.utc)
    vigencia = await _vigencia_horas(db, ahora)
    salida = []
    for fila in (await db.execute(_SQL_ULTIMO_INVENTARIO)).all():
        inventario = None
        if fila.carga_id is not None:
            fuente = snapshot.FuenteSnapshot(
                fila.carga_id, fila.fecha_corte, fila.aplicado_en, 0)
            inventario = {
                "carga_id": fila.carga_id, "fecha_corte": fila.fecha_corte,
                "aplicado_en": fila.aplicado_en,
                "antiguedad_horas": snapshot.antiguedad_horas(
                    fuente, ahora)}
        salida.append({
            "id": fila.id, "nombre": fila.nombre,
            "inventario": inventario, "vigencia_horas": vigencia})
    return salida
