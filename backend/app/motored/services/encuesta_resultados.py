"""
Motored satisfaction survey -- per-carga results (detail and Excel sources).

The survey scale is 1-5 (`satisfaccion_general`). The only classification the
app has is the detractor rule of `encuesta_publica` (score <= DETRACTOR_MAX_SCORE),
so a respondent is DETRACTOR or SATISFECHO; there is no promotor/pasivo split.
Send status is not tracked, so a row is RESPONDIDA when it has an answer and
SIN_RESPONDER otherwise. The send date is the carga's `created_at`.
"""
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.encuesta_carga import EncuestaCarga
from app.motored.models.caso_detractor import CasoDetractor
from app.motored.models.caso_detractor_accion import CasoDetractorAccion
from app.motored.models.encuesta_registro import EncuestaRegistro
from app.motored.models.encuesta_respuesta import EncuestaRespuesta
from app.motored.models.usuario import Usuario
from app.motored.services.encuesta_publica import DETRACTOR_MAX_SCORE
from app.motored.services.fechas_utc import a_utc_iso
from app.motored.services.reloj import BOGOTA_OFFSET

Filtro = Literal["todas", "respondidas", "sin_responder", "detractores"]
Por = Literal["envio", "respuesta"]
MAX_RANGO_DIAS = 366


def clasificar(nota: Optional[int]) -> Optional[str]:
    if nota is None:
        return None
    return "DETRACTOR" if nota <= DETRACTOR_MAX_SCORE else "SATISFECHO"


def fila_de(row: Any) -> Dict[str, Any]:
    nota = row.satisfaccion_general
    return {
        "cliente": row.nombre,
        "cedula": row.cedula,
        "telefono": row.celular,
        "tienda": row.centro_servicio,
        "estado": "RESPONDIDA" if nota is not None else "SIN_RESPONDER",
        "nota": nota,
        "categoria": clasificar(nota),
        "comentario": row.observaciones,
        "fecha_respuesta": a_utc_iso(row.respuesta_created_at),
    }


def filtrar(filas: List[Dict[str, Any]], filtro: str) -> List[Dict[str, Any]]:
    if filtro == "respondidas":
        return [f for f in filas if f["estado"] == "RESPONDIDA"]
    if filtro == "sin_responder":
        return [f for f in filas if f["estado"] == "SIN_RESPONDER"]
    if filtro == "detractores":
        return [f for f in filas if f["categoria"] == "DETRACTOR"]
    return list(filas)


def limites_utc(desde: date, hasta: date) -> Tuple[datetime, datetime]:
    """Naive-UTC [inicio, fin) covering the Bogota days desde..hasta inclusive."""
    def _medianoche(dia: date) -> datetime:
        return datetime(dia.year, dia.month, dia.day) - BOGOTA_OFFSET.utcoffset(None)

    return _medianoche(desde), _medianoche(hasta + timedelta(days=1))


def _seleccion():
    return (
        select(
            EncuestaCarga.nombre_archivo,
            EncuestaCarga.created_at.label("carga_created_at"),
            EncuestaRegistro.id.label("registro_id"),
            EncuestaRespuesta.id.label("respuesta_id"),
            EncuestaRegistro.nombre,
            EncuestaRegistro.cedula,
            EncuestaRegistro.celular,
            EncuestaRegistro.centro_servicio,
            EncuestaRegistro.placa,
            EncuestaRegistro.linea,
            EncuestaRegistro.sic,
            EncuestaRespuesta.satisfaccion_general,
            EncuestaRespuesta.p_explicacion_tecnica,
            EncuestaRespuesta.p_confianza_reparacion,
            EncuestaRespuesta.p_servicio_taller,
            EncuestaRespuesta.p_calidad_mecanicos,
            EncuestaRespuesta.p_claridad_cobros,
            EncuestaRespuesta.p_originalidad_repuestos,
            EncuestaRespuesta.observaciones,
            EncuestaRespuesta.autoriza_datos,
            EncuestaRespuesta.created_at.label("respuesta_created_at"),
        )
        .select_from(EncuestaCarga)
        .join(EncuestaRegistro, EncuestaRegistro.carga_id == EncuestaCarga.id)
        .outerjoin(EncuestaRespuesta, EncuestaRespuesta.registro_id == EncuestaRegistro.id)
    )


async def filas_de_carga(db: AsyncSession, carga_id: uuid.UUID) -> List[Any]:
    stmt = _seleccion().where(EncuestaRegistro.carga_id == carga_id).order_by(EncuestaRegistro.nombre)
    return list((await db.execute(stmt)).all())


async def filas_de_rango(db: AsyncSession, desde: date, hasta: date, por: str) -> List[Any]:
    inicio, fin = limites_utc(desde, hasta)
    columna = EncuestaRespuesta.created_at if por == "respuesta" else EncuestaCarga.created_at
    stmt = (
        _seleccion()
        .where(columna >= inicio, columna < fin)
        .order_by(EncuestaCarga.created_at, EncuestaRegistro.nombre)
    )
    return list((await db.execute(stmt)).all())


async def casos_y_acciones(db: AsyncSession, rows: List[Any]) -> Tuple[List[Any], List[Any]]:
    """Detractor cases (with the assignee's name) and their action log for the
    answered surveys in `rows`, actions oldest first."""
    respuestas = [r.respuesta_id for r in rows if r.respuesta_id is not None]
    if not respuestas:
        return [], []
    stmt = (
        select(
            CasoDetractor.id.label("caso_id"),
            CasoDetractor.numero,
            CasoDetractor.respuesta_id,
            CasoDetractor.estado,
            CasoDetractor.resultado,
            Usuario.nombre.label("asignado_nombre"),
            CasoDetractor.created_at,
            CasoDetractor.updated_at,
            CasoDetractor.cerrado_at,
        )
        .outerjoin(Usuario, Usuario.id == CasoDetractor.asignado_a)
        .where(CasoDetractor.respuesta_id.in_(respuestas))
    )
    casos = list((await db.execute(stmt)).all())
    if not casos:
        return [], []
    stmt = (
        select(
            CasoDetractorAccion.id.label("accion_id"),
            CasoDetractorAccion.caso_id,
            Usuario.nombre.label("usuario_nombre"),
            CasoDetractorAccion.tipo,
            CasoDetractorAccion.descripcion,
            CasoDetractorAccion.estado_anterior,
            CasoDetractorAccion.estado_nuevo,
            CasoDetractorAccion.created_at,
        )
        .outerjoin(Usuario, Usuario.id == CasoDetractorAccion.usuario_id)
        .where(CasoDetractorAccion.caso_id.in_([c.caso_id for c in casos]))
        .order_by(CasoDetractorAccion.created_at, CasoDetractorAccion.id)
    )
    return casos, list((await db.execute(stmt)).all())
