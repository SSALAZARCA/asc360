"""
Motored satisfaction survey (slice T5) -- detractor case management service.

Cases are opened by the public survey (T4); this module lists them, shows the
detail with the append-only action log, appends actions and moves a case
through ABIERTO -> EN_GESTION -> CERRADO. The action table is append-only (a DB
trigger rejects UPDATE/DELETE), so nothing here ever edits or deletes an action.
Concurrency: every write path locks the case row (`SELECT ... FOR UPDATE`) and
validates against the LOCKED state, so two agents acting at once serialize.
"""
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.caso_detractor import CasoDetractor
from app.motored.models.caso_detractor_accion import CasoDetractorAccion
from app.motored.models.encuesta_carga import EncuestaCarga
from app.motored.models.encuesta_registro import EncuestaRegistro
from app.motored.models.encuesta_respuesta import MATRIX_COLUMNS, EncuestaRespuesta
from app.motored.models.usuario import Usuario
from app.motored.services.referencias_busqueda import _condicion_texto

ESTADOS = ("ABIERTO", "EN_GESTION", "CERRADO")
# CERRADO is terminal for now (no reopening).
TRANSICIONES = {"ABIERTO": {"EN_GESTION", "CERRADO"}, "EN_GESTION": {"CERRADO"}}
TIPOS_CIERRE_PERMITIDOS = {"NOTA", "CORRECCION"}


class CasoError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _asignado(user_id, nombre) -> Optional[dict]:
    return {"id": user_id, "nombre": nombre} if user_id is not None else None


def _resumen(row) -> Dict[str, Any]:
    return {
        "id": row.id,
        "numero": row.numero,
        "estado": row.estado,
        "resultado": row.resultado,
        "created_at": row.created_at,
        "cerrado_at": row.cerrado_at,
        "asignado_a": _asignado(row.asignado_id, row.asignado_nombre),
        "cliente": {
            "nombre": row.nombre, "cedula": row.cedula, "celular": row.celular,
            "placa": row.placa, "linea": row.linea, "centro_servicio": row.centro_servicio,
        },
        "satisfaccion_general": row.satisfaccion_general,
        "autoriza_datos": row.autoriza_datos,
        "ultima_accion_at": row.ultima_accion_at,
    }


def _base_select(*extra):
    ultima_accion = (
        select(func.max(CasoDetractorAccion.created_at))
        .where(CasoDetractorAccion.caso_id == CasoDetractor.id)
        .correlate(CasoDetractor)
        .scalar_subquery()
    )
    return (
        select(
            CasoDetractor.id, CasoDetractor.numero, CasoDetractor.estado,
            CasoDetractor.resultado, CasoDetractor.created_at, CasoDetractor.cerrado_at,
            Usuario.id.label("asignado_id"), Usuario.nombre.label("asignado_nombre"),
            EncuestaRegistro.nombre, EncuestaRegistro.cedula, EncuestaRegistro.celular,
            EncuestaRegistro.placa, EncuestaRegistro.linea, EncuestaRegistro.centro_servicio,
            EncuestaRespuesta.satisfaccion_general, EncuestaRespuesta.autoriza_datos,
            ultima_accion.label("ultima_accion_at"),
            *extra,
        )
        .select_from(CasoDetractor)
        .join(EncuestaRespuesta, EncuestaRespuesta.id == CasoDetractor.respuesta_id)
        .join(EncuestaRegistro, EncuestaRegistro.id == EncuestaRespuesta.registro_id)
        .outerjoin(Usuario, Usuario.id == CasoDetractor.asignado_a)
    )


def _condiciones(estado, centro_servicio, autoriza_datos, desde: Optional[date], hasta: Optional[date], q) -> list:
    conds = _condicion_texto(
        q, EncuestaRegistro.nombre, EncuestaRegistro.cedula, EncuestaRegistro.placa
    )
    if estado:
        conds.append(CasoDetractor.estado == estado)
    if centro_servicio:
        conds.append(EncuestaRegistro.centro_servicio == centro_servicio)
    if autoriza_datos is not None:
        conds.append(EncuestaRespuesta.autoriza_datos.is_(autoriza_datos))
    if desde:
        conds.append(CasoDetractor.created_at >= datetime.combine(desde, time.min))
    if hasta:  # inclusive day: strictly before the next midnight
        conds.append(CasoDetractor.created_at < datetime.combine(hasta + timedelta(days=1), time.min))
    return conds


async def listar(
    db: AsyncSession, *, page: int, page_size: int, estado=None, centro_servicio=None,
    autoriza_datos=None, desde=None, hasta=None, q=None,
) -> Dict[str, Any]:
    conds = _condiciones(estado, centro_servicio, autoriza_datos, desde, hasta, q)
    joins = (
        select(func.count(CasoDetractor.id))
        .select_from(CasoDetractor)
        .join(EncuestaRespuesta, EncuestaRespuesta.id == CasoDetractor.respuesta_id)
        .join(EncuestaRegistro, EncuestaRegistro.id == EncuestaRespuesta.registro_id)
        .where(*conds)
    )
    total = (await db.execute(joins)).first()[0]
    page_stmt = (
        _base_select().where(*conds)
        .order_by(CasoDetractor.created_at.desc(), CasoDetractor.id)
        .limit(page_size).offset((page - 1) * page_size)
    )
    rows = (await db.execute(page_stmt)).all()
    counts_stmt = select(CasoDetractor.estado, func.count(CasoDetractor.id)).group_by(CasoDetractor.estado)
    conteo = {e: 0 for e in ESTADOS}
    for est, n in (await db.execute(counts_stmt)).all():
        conteo[est] = n
    return {
        "items": [_resumen(r) for r in rows],
        "total": total, "page": page, "page_size": page_size, "conteo_por_estado": conteo,
    }


def _accion_dict(row) -> Dict[str, Any]:
    return {
        "id": row.id, "tipo": row.tipo, "descripcion": row.descripcion,
        "estado_anterior": row.estado_anterior, "estado_nuevo": row.estado_nuevo,
        "created_at": row.created_at, "usuario": _asignado(row.usuario_id, row.usuario_nombre),
    }


async def detalle(db: AsyncSession, caso_id: uuid.UUID) -> Dict[str, Any]:
    stmt = (
        _base_select(
            EncuestaRegistro.sic, EncuestaRegistro.tipo,
            EncuestaRespuesta.created_at.label("respuesta_created_at"),
            EncuestaRespuesta.observaciones,
            *(getattr(EncuestaRespuesta, col) for col in MATRIX_COLUMNS),
            EncuestaCarga.nombre_archivo.label("carga_nombre_archivo"),
            EncuestaCarga.created_at.label("carga_created_at"),
        )
        .join(EncuestaCarga, EncuestaCarga.id == EncuestaRegistro.carga_id)
        .where(CasoDetractor.id == caso_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise CasoError(404, "Caso no encontrado")
    log_stmt = (
        select(
            CasoDetractorAccion.id, CasoDetractorAccion.tipo, CasoDetractorAccion.descripcion,
            CasoDetractorAccion.estado_anterior, CasoDetractorAccion.estado_nuevo,
            CasoDetractorAccion.created_at, CasoDetractorAccion.usuario_id,
            Usuario.nombre.label("usuario_nombre"),
        )
        .outerjoin(Usuario, Usuario.id == CasoDetractorAccion.usuario_id)
        .where(CasoDetractorAccion.caso_id == caso_id)
        .order_by(CasoDetractorAccion.created_at.asc(), CasoDetractorAccion.id)
    )
    acciones = (await db.execute(log_stmt)).all()
    detail = _resumen(row)
    detail["registro"] = {
        "nombre": row.nombre, "cedula": row.cedula, "celular": row.celular, "linea": row.linea,
        "placa": row.placa, "sic": row.sic, "centro_servicio": row.centro_servicio,
        "tipo": row.tipo,
        "carga": {"nombre_archivo": row.carga_nombre_archivo, "fecha": row.carga_created_at},
    }
    detail["respuesta"] = {
        "satisfaccion_general": row.satisfaccion_general,
        **{col: getattr(row, col) for col in MATRIX_COLUMNS},
        "observaciones": row.observaciones,
        "autoriza_datos": row.autoriza_datos,
        "created_at": row.respuesta_created_at,
    }
    detail["acciones"] = [_accion_dict(a) for a in acciones]
    return detail


async def _bloquear_caso(db: AsyncSession, caso_id: uuid.UUID) -> CasoDetractor:
    """Row lock: the caller validates against the state as it is NOW, not as it
    was when the page was rendered (two agents clicking at once serialize)."""
    result = await db.execute(
        select(CasoDetractor).where(CasoDetractor.id == caso_id).with_for_update()
    )
    caso = result.scalars().first()
    if caso is None:
        raise CasoError(404, "Caso no encontrado")
    return caso


async def agregar_accion(
    db: AsyncSession, caso_id: uuid.UUID, *, usuario_id: str, tipo: str, descripcion: str
) -> Dict[str, Any]:
    caso = await _bloquear_caso(db, caso_id)
    if caso.estado == "CERRADO" and tipo not in TIPOS_CIERRE_PERMITIDOS:
        raise CasoError(
            409, "El caso está cerrado: solo se pueden agregar notas o correcciones."
        )
    actor = uuid.UUID(usuario_id)
    nombre_row = (await db.execute(select(Usuario.nombre).where(Usuario.id == actor))).first()
    accion = CasoDetractorAccion(
        id=uuid.uuid4(), caso_id=caso_id, usuario_id=actor, tipo=tipo, descripcion=descripcion,
    )
    db.add(accion)
    await db.commit()
    return _accion_dict(SimpleAccion(accion, nombre_row.nombre if nombre_row else None))


class SimpleAccion:
    """Adapter so the created action serializes like a log row."""

    def __init__(self, accion: CasoDetractorAccion, nombre: Optional[str]):
        self.id, self.tipo, self.descripcion = accion.id, accion.tipo, accion.descripcion
        self.estado_anterior, self.estado_nuevo = accion.estado_anterior, accion.estado_nuevo
        self.created_at, self.usuario_id, self.usuario_nombre = accion.created_at, accion.usuario_id, nombre


async def cambiar_estado(
    db: AsyncSession, caso_id: uuid.UUID, *, usuario_id: str, estado: str,
    resultado: Optional[str], comentario: str,
) -> Dict[str, Any]:
    caso = await _bloquear_caso(db, caso_id)
    actual = caso.estado
    if actual == "CERRADO":
        raise CasoError(409, "El caso ya está cerrado y no se puede reabrir ni modificar su estado.")
    if actual == estado:
        raise CasoError(409, f"El caso ya está en estado {estado}.")
    if estado not in TRANSICIONES.get(actual, set()):
        raise CasoError(409, f"Transición no permitida: {actual} -> {estado}.")

    actor = uuid.UUID(usuario_id)
    ahora = datetime.utcnow()
    caso.estado = estado
    caso.resultado = resultado
    caso.updated_at = ahora
    if estado == "CERRADO":
        caso.cerrado_at = ahora
    if estado == "EN_GESTION" and caso.asignado_a is None:
        caso.asignado_a = actor
    descripcion = comentario if resultado is None else f"{comentario} (Resultado: {resultado})"
    db.add(CasoDetractorAccion(
        id=uuid.uuid4(), caso_id=caso_id, usuario_id=actor, tipo="CAMBIO_ESTADO",
        descripcion=descripcion, estado_anterior=actual, estado_nuevo=estado,
    ))
    await db.commit()
    return await detalle(db, caso_id)
