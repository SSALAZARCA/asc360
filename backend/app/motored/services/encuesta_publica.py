"""
Motored satisfaction survey (slice T4) -- business logic of the PUBLIC survey
API. Nothing here authenticates the caller, so it only ever returns the minimum
the survey screens need (registro id, placa, linea, first name) and never
distinguishes "unknown registro" from "registro of another cedula".
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.caso_detractor import CasoDetractor
from app.motored.models.caso_detractor_accion import CasoDetractorAccion
from app.motored.models.encuesta_carga import EncuestaCarga
from app.motored.models.encuesta_registro import EncuestaRegistro
from app.motored.models.encuesta_respuesta import EncuestaRespuesta
from app.motored.services.encuesta_carga import (
    CEDULA_MAX_LENGTH,
    TIPO_SERVICIO_TALLER,
    normalize_cedula,
)

logger = logging.getLogger(__name__)

DETRACTOR_MAX_SCORE = 3
NOT_FOUND_MESSAGE = (
    "No encontramos esa cédula. Recuerda ingresar la cédula de la persona a cuyo nombre "
    "está registrada la motocicleta. Revísala e intenta de nuevo."
)


class RegistroNoEncontrado(Exception):
    """Unknown registro, wrong cedula or not surveyable: one indistinguishable outcome."""


class RespuestaYaRegistrada(Exception):
    """The registro already has its (single) response."""


@dataclass
class IdentificacionResultado:
    estado: str
    primer_nombre: Optional[str] = None
    registros: Optional[List[dict]] = None
    respondida_at: Optional[datetime] = None


@dataclass
class EnvioResultado:
    clasificacion: str
    caso_numero: Optional[int]
    primer_nombre: str


def primer_nombre_de(nombre: Any) -> str:
    words = str(nombre or "").split()
    return words[0].title() if words else ""


async def identificar(db: AsyncSession, cedula_raw: str) -> IdentificacionResultado:
    cedula = normalize_cedula(cedula_raw)
    if not cedula or len(cedula) > CEDULA_MAX_LENGTH:
        return IdentificacionResultado(estado="NO_ENCONTRADA")

    stmt = (
        select(
            EncuestaRegistro.id,
            EncuestaRegistro.placa,
            EncuestaRegistro.linea,
            EncuestaRegistro.nombre,
            EncuestaCarga.created_at.label("carga_created_at"),
            EncuestaRespuesta.created_at.label("respuesta_created_at"),
        )
        .join(EncuestaCarga, EncuestaCarga.id == EncuestaRegistro.carga_id)
        .outerjoin(EncuestaRespuesta, EncuestaRespuesta.registro_id == EncuestaRegistro.id)
        .where(
            EncuestaRegistro.cedula == cedula,
            EncuestaRegistro.tipo == TIPO_SERVICIO_TALLER,
        )
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return IdentificacionResultado(estado="NO_ENCONTRADA")

    # One row per placa: the newest batch decides. A placa already answered in
    # its latest batch is not asked again because of a stale older batch.
    latest_by_placa: dict = {}
    for row in sorted(rows, key=lambda r: r.carga_created_at or datetime.min, reverse=True):
        latest_by_placa.setdefault(row.placa, row)
    pending = [r for r in latest_by_placa.values() if r.respuesta_created_at is None]

    if not pending:
        answered = [r.respuesta_created_at for r in rows if r.respuesta_created_at is not None]
        return IdentificacionResultado(estado="YA_RESPONDIDA", respondida_at=max(answered) if answered else None)

    return IdentificacionResultado(
        estado="PENDIENTE",
        primer_nombre=primer_nombre_de(pending[0].nombre),
        registros=[{"registro_id": r.id, "placa": r.placa, "linea": r.linea} for r in pending],
    )


async def registrar_respuesta(
    db: AsyncSession,
    *,
    cedula_raw: str,
    registro_id: uuid.UUID,
    datos: dict,
) -> EnvioResultado:
    """`datos` holds satisfaccion_general, the six matrix answers,
    observaciones and autoriza_datos (already validated by the schema)."""
    cedula = normalize_cedula(cedula_raw)
    stmt = (
        select(
            EncuestaRegistro.id,
            EncuestaRegistro.cedula,
            EncuestaRegistro.tipo,
            EncuestaRegistro.nombre,
            EncuestaRespuesta.id.label("respuesta_id"),
        )
        .outerjoin(EncuestaRespuesta, EncuestaRespuesta.registro_id == EncuestaRegistro.id)
        .where(EncuestaRegistro.id == registro_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None or row.cedula != cedula or row.tipo != TIPO_SERVICIO_TALLER:
        raise RegistroNoEncontrado()
    if row.respuesta_id is not None:
        raise RespuestaYaRegistrada()

    respuesta = EncuestaRespuesta(id=uuid.uuid4(), registro_id=registro_id, **datos)
    db.add(respuesta)
    caso: Optional[CasoDetractor] = None
    score = datos["satisfaccion_general"]
    try:
        if score <= DETRACTOR_MAX_SCORE:
            caso = CasoDetractor(id=uuid.uuid4(), respuesta_id=respuesta.id, estado="ABIERTO")
            db.add(caso)
            descripcion = f"Caso abierto automáticamente: satisfacción general {score}/5"
            if not datos["autoriza_datos"]:
                descripcion += " — el cliente NO autorizó tratamiento de datos"
            db.add(CasoDetractorAccion(
                id=uuid.uuid4(), caso_id=caso.id, usuario_id=None, tipo="APERTURA", descripcion=descripcion,
            ))
        await db.flush()
        if caso is not None:
            await db.refresh(caso, attribute_names=["numero"])  # Identity value
        await db.commit()
    except IntegrityError:
        # UNIQUE(registro_id) is the source of truth for the double-submit race.
        await db.rollback()
        logger.debug("encuesta response race: registro already answered")
        raise RespuestaYaRegistrada()

    return EnvioResultado(
        clasificacion="DETRACTOR" if caso is not None else "SATISFECHO",
        caso_numero=caso.numero if caso is not None else None,
        primer_nombre=primer_nombre_de(row.nombre),
    )
