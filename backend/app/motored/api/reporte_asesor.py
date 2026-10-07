"""
Motored: `/api/motored/reporte-asesor`, the daily asesor report message
in Configuración (odd/motored-reporte-diario-asesor, T3b). ADMIN only.

- `GET /estado`: the switch and hours, the last data date sent with its
  counts (enviados, fallidos, bloqueados), how many asesores would get the
  message now, and the names of those skipped (no link, no approved cédula,
  no Telegram, blocked the bot). Never a token, URL or cédula.
- `POST /reenviar` `{fecha_datos?}`: "Reenviar reportes a todos los
  asesores". Default date: the latest data date. It messages every
  eligible asesor again, bypassing the once-per-date rule, in a background
  task, and answers 202 with how many will be sent. It works with the
  daily switch off; it refuses (409) without `LORE_BOT_TOKEN` or
  `MOTORED_PUBLIC_URL`, or while another resend runs.
"""
import uuid
from datetime import date, timedelta
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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
