"""
Motored budgets -- database side (odd/motored-presupuestos-gerencia, T2):
dry-run, apply, manual edits and the reads. Parsing and row validation are pure
and live in `presupuestos_archivo.py`.

Versioning: every upload (once per month in the file) and every manual edit
INSERTS a new `presupuesto_version` for that month, carrying ALL the month's
lines; nothing already stored is ever modified, so the headers are the audit
trail. The latest version (max `version`) of a month is the effective one.

Concurrency: the next version number is taken under a per-month transaction
advisory lock (`pg_advisory_xact_lock`), so concurrent writers of the same
month queue up and get consecutive numbers. `UNIQUE(mes, version)` stays as the
backstop: a violation that gets past the lock surfaces as `PresupuestoConflicto`.

Like the rest of Motored (ADR-5), these functions only `flush`: the caller
commits, or rolls back on any exception.
"""
import datetime
import uuid
from typing import Any, Dict, List, NamedTuple, Optional

from sqlalchemy import and_, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.presupuesto import ORIGEN_EXCEL, ORIGEN_MANUAL, PresupuestoLinea, PresupuestoVersion
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import Usuario
from app.motored.models.vendedor import Vendedor
from app.motored.schemas.vendedor import limpiar_cedula
from app.motored.services.fechas_utc import a_utc_iso
from app.motored.services.presupuestos_archivo import (
    Catalogos,
    LineaValida,
    mes_de_fila,
    resumir,
    validar_filas,
)
from app.motored.services.sucursal_texto import sucursal_id_por_texto

_LOCK_BASE = 7_100_000_000  # advisory-lock key space of this module (+ month ordinal)


class PresupuestoInvalido(Exception):
    """The upload or the edit breaks a rule; `errores` lists each one."""

    def __init__(self, errores: List[Dict[str, Any]]):
        super().__init__("Presupuesto inválido")
        self.errores = errores


class PresupuestoConflicto(Exception):
    """Two writers raced for the same month version."""


class PresupuestoNoEncontrado(Exception):
    pass


class LineaPresupuesto(NamedTuple):
    sucursal_id: uuid.UUID
    monto: int


def _mes_texto(mes: datetime.date) -> str:
    return f"{mes:%Y-%m}"


def _error(columna: str, mensaje: str, fila: int = 1) -> Dict[str, Any]:
    return {"fila": fila, "columna": columna, "mensaje": mensaje}


# --- lookups ----------------------------------------------------------------


async def _cargar_catalogos(db: AsyncSession, filas: List[Dict[str, Any]]) -> Catalogos:
    cedulas, meses = set(), set()
    for fila in filas:
        try:
            cedulas.add(limpiar_cedula(fila.get("cedula")))
        except ValueError:
            pass
        try:
            meses.add(mes_de_fila(fila))
        except ValueError:
            pass
    cedula_activa = await _cedulas_activas(db, cedulas)
    sucursales = (await db.execute(select(Sucursal.id, Sucursal.nombre, Sucursal.activa))).all()
    versiones = {}
    if meses:
        consulta = (
            select(PresupuestoVersion.mes, func.max(PresupuestoVersion.version))
            .where(PresupuestoVersion.mes.in_(meses)).group_by(PresupuestoVersion.mes))
        versiones = dict((await db.execute(consulta)).all())
    return Catalogos(
        cedula_activa=cedula_activa,
        sucursal_por_texto=await sucursal_id_por_texto(db),
        sucursal_activa={sid: bool(activa) for sid, _, activa in sucursales},
        sucursal_nombre={sid: nombre for sid, nombre, _ in sucursales},
        version_actual=versiones,
    )


async def _cedulas_activas(db: AsyncSession, cedulas) -> Dict[str, bool]:
    """cedula -> True if at least one ACTIVE vendedor row has it (the cedula
    is not unique: one person can have several ERP names)."""
    if not cedulas:
        return {}
    consulta = (
        select(Vendedor.cedula, func.bool_or(Vendedor.activo))
        .where(Vendedor.cedula.in_(cedulas)).group_by(Vendedor.cedula))
    return {cedula: bool(activo) for cedula, activo in (await db.execute(consulta)).all()}


async def _nombres_asesores(db: AsyncSession, cedulas) -> Dict[str, str]:
    """Display name per cedula: the name of an active vendedor row, else of any."""
    if not cedulas:
        return {}
    filas = (await db.execute(
        select(Vendedor.cedula, Vendedor.nombre, Vendedor.activo).where(Vendedor.cedula.in_(cedulas))
    )).all()
    nombres: Dict[str, str] = {}
    for cedula, nombre, _ in sorted(filas, key=lambda f: (not f[2], f[1])):
        nombres.setdefault(cedula, nombre)
    return nombres


# --- dry-run and apply ------------------------------------------------------


async def validar_archivo(db: AsyncSession, filas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Dry-run: the summary of what `aplicar_archivo` would do. Writes nothing."""
    catalogos = await _cargar_catalogos(db, filas)
    return resumir(validar_filas(filas, catalogos), catalogos)


async def _bloquear_mes(db: AsyncSession, mes: datetime.date) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(:clave)"), {"clave": _LOCK_BASE + mes.toordinal()})


async def _siguiente_version(db: AsyncSession, mes: datetime.date) -> int:
    await _bloquear_mes(db, mes)
    actual = (await db.execute(
        select(func.max(PresupuestoVersion.version)).where(PresupuestoVersion.mes == mes))).scalar()
    return (actual or 0) + 1


async def _crear_version(
    db: AsyncSession,
    mes: datetime.date,
    origen: str,
    archivo_nombre: Optional[str],
    nota: Optional[str],
    usuario_id: Optional[uuid.UUID],
    lineas: Dict[str, LineaPresupuesto],
) -> PresupuestoVersion:
    cabecera = PresupuestoVersion(
        id=uuid.uuid4(), mes=mes, version=await _siguiente_version(db, mes), origen=origen,
        archivo_nombre=archivo_nombre, nota=nota, created_by=usuario_id)
    try:
        async with db.begin_nested():
            db.add(cabecera)
            await db.flush()
    except IntegrityError as exc:
        raise PresupuestoConflicto(
            f"Otra persona está modificando el presupuesto de {_mes_texto(mes)}. Intente de nuevo.") from exc
    db.add_all([
        PresupuestoLinea(
            id=uuid.uuid4(), version_id=cabecera.id, cedula=cedula,
            sucursal_id=linea.sucursal_id, monto=linea.monto)
        for cedula, linea in lineas.items()
    ])
    await db.flush()
    return cabecera


async def aplicar_archivo(
    db: AsyncSession, filas: List[Dict[str, Any]], archivo_nombre: Optional[str], usuario_id: Optional[uuid.UUID]
) -> Dict[str, Any]:
    """Re-validates the whole file (never trusts a previous dry-run) and, when
    valid, creates ONE new version for EACH month in it: the month is replaced
    (an asesor missing from the file has no budget that month). Months not in
    the file are untouched."""
    resultado = validar_filas(filas, await _cargar_catalogos(db, filas))
    if resultado.errores:
        raise PresupuestoInvalido(resultado.errores)
    if not resultado.lineas:
        raise PresupuestoInvalido([_error("", "El archivo no tiene filas con presupuesto", fila=0)])

    por_mes: Dict[datetime.date, List[LineaValida]] = {}
    for linea in resultado.lineas:
        por_mes.setdefault(linea.mes, []).append(linea)

    creadas = []
    for mes in sorted(por_mes):  # fixed order: concurrent multi-month uploads cannot deadlock
        lineas = {v.cedula: LineaPresupuesto(v.sucursal_id, v.monto) for v in por_mes[mes]}
        cabecera = await _crear_version(db, mes, ORIGEN_EXCEL, archivo_nombre, None, usuario_id, lineas)
        creadas.append({
            "mes": _mes_texto(mes), "version": cabecera.version,
            "asesores": len(lineas), "total": sum(linea.monto for linea in lineas.values()),
        })
    return {"meses": creadas}


# --- manual edits -----------------------------------------------------------


async def _ultima_cabecera(db: AsyncSession, mes: datetime.date) -> Optional[PresupuestoVersion]:
    consulta = (
        select(PresupuestoVersion).where(PresupuestoVersion.mes == mes)
        .order_by(PresupuestoVersion.version.desc()).limit(1))
    return (await db.execute(consulta)).scalars().first()


async def _lineas_de(db: AsyncSession, version_id: uuid.UUID) -> Dict[str, LineaPresupuesto]:
    filas = (await db.execute(
        select(PresupuestoLinea.cedula, PresupuestoLinea.sucursal_id, PresupuestoLinea.monto)
        .where(PresupuestoLinea.version_id == version_id))).all()
    return {cedula: LineaPresupuesto(sucursal_id, monto) for cedula, sucursal_id, monto in filas}


async def _lineas_vigentes(db: AsyncSession, mes: datetime.date) -> Dict[str, LineaPresupuesto]:
    cabecera = await _ultima_cabecera(db, mes)
    return await _lineas_de(db, cabecera.id) if cabecera else {}


def _cedula_o_invalido(cedula: Any) -> str:
    try:
        return limpiar_cedula(cedula)
    except ValueError as exc:
        raise PresupuestoInvalido([_error("Cédula", str(exc))])


async def _validar_edicion(db: AsyncSession, cedula: str, sucursal_id: uuid.UUID, monto: int) -> None:
    errores = []
    if cedula not in await _cedulas_activas(db, {cedula}):
        errores.append(_error("Cédula", f"La cédula {cedula} no corresponde a ningún vendedor"))
    activa = (await db.execute(select(Sucursal.activa).where(Sucursal.id == sucursal_id))).scalar()
    if activa is None:
        errores.append(_error("Tienda", "La tienda elegida no existe"))
    elif not activa:
        errores.append(_error("Tienda", "La tienda elegida está inactiva"))
    if monto <= 0:
        errores.append(_error("Presupuesto", "El presupuesto debe ser un número entero de pesos mayor a 0"))
    if errores:
        raise PresupuestoInvalido(errores)


async def editar_asesor(
    db: AsyncSession, mes: datetime.date, cedula: str, sucursal_id: uuid.UUID, monto: int,
    nota: Optional[str], usuario_id: Optional[uuid.UUID],
) -> Dict[str, Any]:
    """Adds or changes ONE asesor's line for `mes`: a new MANUAL version that
    clones the latest one with the change applied (version 1 if the month had
    no budget)."""
    cedula = _cedula_o_invalido(cedula)
    await _validar_edicion(db, cedula, sucursal_id, monto)
    await _bloquear_mes(db, mes)
    lineas = await _lineas_vigentes(db, mes)
    lineas[cedula] = LineaPresupuesto(sucursal_id, monto)
    cabecera = await _crear_version(db, mes, ORIGEN_MANUAL, None, nota, usuario_id, lineas)
    return {"mes": _mes_texto(mes), "version": cabecera.version}


async def quitar_asesor(
    db: AsyncSession, mes: datetime.date, cedula: str, nota: Optional[str], usuario_id: Optional[uuid.UUID],
) -> Dict[str, Any]:
    """Removes ONE asesor from `mes`: a new MANUAL version without him.
    Removing the last asesor is allowed (an empty version: the month then has
    no budget). `PresupuestoNoEncontrado` if he had none that month."""
    cedula = _cedula_o_invalido(cedula)
    await _bloquear_mes(db, mes)
    lineas = await _lineas_vigentes(db, mes)
    if cedula not in lineas:
        raise PresupuestoNoEncontrado(f"La cédula {cedula} no tiene presupuesto en {_mes_texto(mes)}")
    del lineas[cedula]
    cabecera = await _crear_version(db, mes, ORIGEN_MANUAL, None, nota, usuario_id, lineas)
    return {"mes": _mes_texto(mes), "version": cabecera.version}


# --- reads ------------------------------------------------------------------


def _ultimas_versiones():
    """Subquery: (mes, latest version number) per month."""
    return (
        select(PresupuestoVersion.mes.label("mes"), func.max(PresupuestoVersion.version).label("version"))
        .group_by(PresupuestoVersion.mes).subquery())


def _es_la_ultima(ultimas):
    return and_(PresupuestoVersion.mes == ultimas.c.mes, PresupuestoVersion.version == ultimas.c.version)


def _con_totales(consulta):
    return (
        consulta.outerjoin(PresupuestoLinea, PresupuestoLinea.version_id == PresupuestoVersion.id)
        .add_columns(func.count(PresupuestoLinea.id), func.coalesce(func.sum(PresupuestoLinea.monto), 0)))


async def listar_meses(db: AsyncSession) -> List[Dict[str, Any]]:
    """Every month with a budget, newest first, with its latest version."""
    ultimas = _ultimas_versiones()
    consulta = _con_totales(
        select(PresupuestoVersion.mes, PresupuestoVersion.version, PresupuestoVersion.origen,
               PresupuestoVersion.created_at)
        .join(ultimas, _es_la_ultima(ultimas))
    ).group_by(PresupuestoVersion.id).order_by(PresupuestoVersion.mes.desc())
    return [
        {"mes": _mes_texto(mes), "version": version, "origen": origen,
         "created_at": a_utc_iso(creada), "asesores": asesores, "total": int(total)}
        for mes, version, origen, creada, asesores, total in (await db.execute(consulta)).all()
    ]


async def _detalle(db: AsyncSession, cabecera: PresupuestoVersion) -> Dict[str, Any]:
    filas = (await db.execute(
        select(PresupuestoLinea.cedula, PresupuestoLinea.sucursal_id, Sucursal.nombre, PresupuestoLinea.monto)
        .join(Sucursal, Sucursal.id == PresupuestoLinea.sucursal_id)
        .where(PresupuestoLinea.version_id == cabecera.id))).all()
    nombres = await _nombres_asesores(db, {f[0] for f in filas})
    lineas = sorted(
        ({"cedula": cedula, "asesor": nombres.get(cedula, ""), "sucursal_id": str(sucursal_id),
          "tienda": tienda, "monto": monto} for cedula, sucursal_id, tienda, monto in filas),
        key=lambda linea: (linea["tienda"], linea["asesor"], linea["cedula"]))
    por_tienda: Dict[str, Dict[str, Any]] = {}
    for linea in lineas:
        grupo = por_tienda.setdefault(linea["sucursal_id"], {
            "sucursal_id": linea["sucursal_id"], "tienda": linea["tienda"], "asesores": 0, "total": 0})
        grupo["asesores"] += 1
        grupo["total"] += linea["monto"]
    return {
        "id": str(cabecera.id), "mes": _mes_texto(cabecera.mes), "version": cabecera.version,
        "origen": cabecera.origen, "archivo_nombre": cabecera.archivo_nombre, "nota": cabecera.nota,
        "created_at": a_utc_iso(cabecera.created_at),
        "asesores": len(lineas), "total": sum(linea["monto"] for linea in lineas),
        "lineas": lineas, "por_tienda": list(por_tienda.values()),
    }


async def detalle_mes(db: AsyncSession, mes: datetime.date) -> Dict[str, Any]:
    """The latest version of `mes` with its lines and the totals per store."""
    cabecera = await _ultima_cabecera(db, mes)
    if cabecera is None:
        raise PresupuestoNoEncontrado(f"No hay presupuesto cargado para {_mes_texto(mes)}")
    return await _detalle(db, cabecera)


async def detalle_version(db: AsyncSession, version_id: uuid.UUID) -> Dict[str, Any]:
    cabecera = await db.get(PresupuestoVersion, version_id)
    if cabecera is None:
        raise PresupuestoNoEncontrado("Versión no encontrada")
    return await _detalle(db, cabecera)


async def historial_mes(db: AsyncSession, mes: datetime.date) -> List[Dict[str, Any]]:
    """Every version of `mes`, newest first (empty list if none)."""
    consulta = _con_totales(
        select(PresupuestoVersion, Usuario.nombre)
        .outerjoin(Usuario, Usuario.id == PresupuestoVersion.created_by)
        .where(PresupuestoVersion.mes == mes)
    ).group_by(PresupuestoVersion.id, Usuario.nombre).order_by(PresupuestoVersion.version.desc())
    return [
        {"id": str(c.id), "version": c.version, "origen": c.origen, "archivo_nombre": c.archivo_nombre,
         "nota": c.nota, "created_at": a_utc_iso(c.created_at), "created_by_nombre": autor,
         "lineas": lineas, "total": int(total)}
        for c, autor, lineas, total in (await db.execute(consulta)).all()
    ]


async def presupuesto_por_asesor(
    db: AsyncSession, mes_desde: datetime.date, mes_hasta: datetime.date
) -> Dict[tuple, LineaPresupuesto]:
    """KPI read: (mes, cedula) -> latest budget, for the months in the range."""
    ultimas = _ultimas_versiones()
    consulta = (
        select(PresupuestoVersion.mes, PresupuestoLinea.cedula, PresupuestoLinea.sucursal_id, PresupuestoLinea.monto)
        .join(ultimas, _es_la_ultima(ultimas))
        .join(PresupuestoLinea, PresupuestoLinea.version_id == PresupuestoVersion.id)
        .where(PresupuestoVersion.mes.between(mes_desde, mes_hasta)))
    return {
        (mes, cedula): LineaPresupuesto(sucursal_id, monto)
        for mes, cedula, sucursal_id, monto in (await db.execute(consulta)).all()
    }


async def presupuesto_por_sucursal(
    db: AsyncSession, mes_desde: datetime.date, mes_hasta: datetime.date
) -> Dict[tuple, int]:
    """KPI read: (mes, sucursal_id) -> sum of the latest budgets of its asesores."""
    ultimas = _ultimas_versiones()
    consulta = (
        select(PresupuestoVersion.mes, PresupuestoLinea.sucursal_id, func.sum(PresupuestoLinea.monto))
        .join(ultimas, _es_la_ultima(ultimas))
        .join(PresupuestoLinea, PresupuestoLinea.version_id == PresupuestoVersion.id)
        .where(PresupuestoVersion.mes.between(mes_desde, mes_hasta))
        .group_by(PresupuestoVersion.mes, PresupuestoLinea.sucursal_id))
    return {(mes, sucursal_id): int(total) for mes, sucursal_id, total in (await db.execute(consulta)).all()}


async def listar_tiendas(db: AsyncSession) -> List[Dict[str, str]]:
    """Active sucursales (id, name): the store options of the manual edit, readable by GERENCIA."""
    consulta = select(Sucursal.id, Sucursal.nombre).where(Sucursal.activa.is_(True)).order_by(Sucursal.nombre)
    return [{"id": str(id_), "nombre": nombre} for id_, nombre in (await db.execute(consulta)).all()]
