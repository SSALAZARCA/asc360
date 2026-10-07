"""
Motored: `/api/motored/reporte-asesor`, the daily asesor report message
in Configuración (odd/motored-reporte-diario-asesor, T3b). ADMIN only.

- `GET /estado`: the switch and hours, the last data date sent with its
  counts (enviados, fallidos, bloqueados), how many asesores would get the
  message now, the names of those skipped, and `asesores`: one row per
  asesor with sales, with its `estado` code, last send and `puede_enviar`
  (T3d). Never a token, URL or full cédula (last 4 digits only).
- `POST /reenviar` `{fecha_datos?}`: "Reenviar reportes a todos los
  asesores". Default date: the latest data date. It messages every
  eligible asesor again, bypassing the once-per-date rule, in a background
  task, and answers 202 with how many will be sent. It works with the
  daily switch off; it refuses (409) without `LORE_BOT_TOKEN` or
  `MOTORED_PUBLIC_URL`, or while another resend runs.
- `POST /enviar/{usuario_id}` `{fecha_datos?}`: "Enviar ahora" of one
  asesor (T3d). Synchronous; it bypasses the once-per-date rule and works
  with the daily switch off. 409 without the settings, 404 for an unknown
  usuario, 422 naming what is missing when the asesor is not ready, 502
  when Telegram fails; a 403 from Telegram answers `estado: bloqueado`.
"""
import asyncio
import uuid
from datetime import date, timedelta
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.deps import (
    MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles,
)
from app.motored.services import reporte_asesor_envio as envio
from app.motored.services.reloj import hoy_bogota
from app.motored.services.trabajos import supervisor_reporte_asesor as sup

router = APIRouter(
    prefix="/reporte-asesor",
    tags=["motored-reporte-asesor"],
    dependencies=[Depends(require_motored_ready)],
)

_require_admin = require_roles("ADMIN")

MSG_EN_CURSO = (
    "Ya hay un reenvío de reportes en curso. Espere a que termine.")
MSG_SIN_VENTAS = "No hay ventas aplicadas: no hay informe para enviar."
MSG_FECHA = "La fecha de los datos debe ser anterior a hoy."
MSG_NO_EXISTE = "El asesor no existe."
MSG_NO_LISTO = "No se puede enviar el informe: "
MSG_FALLO = (
    "Telegram no aceptó el mensaje. Intente de nuevo en unos minutos.")
FALTANTES = {
    envio.CEDULA_PENDIENTE:
        "su cédula no está aprobada. Apruébela en Gestión de usuarios.",
    envio.USUARIO_INACTIVO:
        "su usuario está inactivo o su registro no está aprobado.",
    envio.SIN_TELEGRAM: "no tiene Telegram vinculado.",
    envio.SIN_ENLACE:
        "no tiene enlace del informe. Genérelo en Gestión de usuarios.",
    envio.SIN_PRESUPUESTO:
        "no tiene presupuesto para ese mes. Cárguelo en Presupuestos.",
    envio.BLOQUEADO:
        "bloqueó a Lore en Telegram; debe desbloquearlo para recibirlo.",
    envio.SIN_CEDULA: "no tiene cédula registrada.",
    envio.SIN_VENTAS: "no tiene ventas a esa fecha.",
}


class ReenvioIn(BaseModel):
    fecha_datos: Optional[date] = None


@router.get("/estado")
async def estado(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> Dict[str, Any]:
    resumen = await envio.estado_envio(db, hoy_bogota())
    return {**resumen, "falta_configuracion": sup.falta_configuracion()}


def _conflicto(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT,
                         detail=detalle)


async def _fecha(db, pedida: Optional[date]) -> date:
    hoy = hoy_bogota()
    if pedida is not None:
        if pedida > hoy - timedelta(days=1):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=MSG_FECHA)
        return pedida
    fecha = await envio.ultima_fecha_datos(db, hoy)
    if fecha is None:
        raise _conflicto(MSG_SIN_VENTAS)
    return fecha


@router.post("/reenviar", status_code=status.HTTP_202_ACCEPTED)
async def reenviar(
    tareas: BackgroundTasks,
    cuerpo: Optional[ReenvioIn] = None,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> Dict[str, Any]:
    falta = sup.falta_configuracion()
    if falta is not None:
        raise _conflicto(falta)
    fecha = await _fecha(db, cuerpo.fecha_datos if cuerpo else None)
    if not sup.reservar_reenvio():
        raise _conflicto(MSG_EN_CURSO)
    try:
        destinos = await envio.preparar_destinos(db, fecha)
    except BaseException:
        sup.liberar_reenvio()
        raise
    if not destinos:
        sup.liberar_reenvio()
    else:
        tareas.add_task(sup.reenviar_en_segundo_plano, destinos, fecha,
                        uuid.UUID(str(user.user_id)))
    return {"fecha_datos": fecha.isoformat(), "a_enviar": len(destinos)}


async def enviar_por_lore(chat_id: int, texto: str) -> envio.Respuesta:
    return await envio.enviar_telegram(
        settings.LORE_BOT_TOKEN, chat_id, texto)


def _resultado(resultado: envio.EnvioUno) -> str:
    if resultado.estado == envio.FALLIDO:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=MSG_FALLO)
    if resultado.estado == envio.BLOQUEADO:
        return (f"{resultado.nombre} bloqueó a Lore en Telegram: el "
                "informe no le llegó.")
    return f"Informe enviado a {resultado.nombre} por Lore."


@router.post("/enviar/{usuario_id}")
async def enviar_uno(
    usuario_id: uuid.UUID,
    cuerpo: Optional[ReenvioIn] = None,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> Dict[str, Any]:
    falta = sup.falta_configuracion()
    if falta is not None:
        raise _conflicto(falta)
    fecha = await _fecha(db, cuerpo.fecha_datos if cuerpo else None)
    try:
        resultado = await envio.enviar_a_uno(
            db, usuario_id, fecha, enviar_por_lore, asyncio.sleep,
            uuid.UUID(str(user.user_id)))
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=MSG_NO_EXISTE) from None
    except envio.NoListo as error:
        falta = FALTANTES.get(error.estado, error.estado)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=MSG_NO_LISTO + falta) from None
    return {"estado": resultado.estado, "fecha_datos": fecha.isoformat(),
            "detalle": _resultado(resultado)}
