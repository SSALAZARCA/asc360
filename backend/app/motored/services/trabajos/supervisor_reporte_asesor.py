"""
Motored: asyncio loop of the daily asesor report message
(odd/motored-reporte-diario-asesor, T3b), plus the ADMIN resend runner.

Same pattern as `supervisor_avisos.py`: LAZY start from
`deps.require_motored_ready` (`ensure_started()`, O(1) after the first
call), stop by cancelling the task, and a failing tick is logged without
killing the loop. It sleeps BEFORE the first tick, so the request that
started it never waits for a send.

A tick is cheap: without `LORE_BOT_TOKEN` or `MOTORED_PUBLIC_URL` it does
not touch the DB; otherwise it reads the Configuración once and stops when
the switch is off or it is before the minimum hour. Only then it takes the
advisory lock `LOCK_ENVIO` (in its own session, never committed, so the
per-send commits of the work session do not release it): two workers never
send at the same time, and the ledger's partial unique index backs that up.

The resend ("Reenviar a todos", ADMIN) runs even with the switch off:
`reservar_reenvio` refuses a second one in this process, `LOCK_REENVIO`
skips one already running in another worker, and it waits (up to
`ESPERA_CANDADO_SEGUNDOS`) for a daily run in progress to finish.

Switch (`app/config.py`): `MOTORED_ENABLED=false` turns all Motored off.
"""
import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Callable, Dict, List, Optional, Set

from app.config import settings
from app.motored.database import motored_session_maker
from app.motored.services import reporte_asesor_envio as envio
from app.motored.services.reloj import BOGOTA_OFFSET

logger = logging.getLogger("motored.trabajos.supervisor_reporte_asesor")

TICK_SEGUNDOS = 300
ESPERA_CANDADO_SEGUNDOS = 900

MSG_SIN_TOKEN = (
    "Falta configurar LORE_BOT_TOKEN: no se pueden enviar los informes "
    "por Lore.")
MSG_SIN_URL = (
    "Falta configurar MOTORED_PUBLIC_URL: no se puede armar el enlace del "
    "informe.")

_task: Optional[asyncio.Task] = None
_memoria_config: dict = {}
# Per data date, the usuarios known to have no sales (see `envio_diario`).
_sin_reporte: Dict[date, Set[uuid.UUID]] = {}
_reenvio_en_curso = False


def ensure_started() -> None:
    """Lazy, idempotent start. Never raises: it runs on EVERY Motored
    request."""
    global _task
    if not settings.MOTORED_ENABLED:
        return
    if _task is not None and not _task.done():
        return
    try:
        _task = asyncio.get_running_loop().create_task(
            _run_forever(), name="motored-reporte-asesor")
    except Exception:  # noqa: BLE001 -- never towards the request
        logger.exception("no se pudo arrancar el loop del reporte asesor")


def falta_configuracion() -> Optional[str]:
    """The message for the first missing setting, or None."""
    if not (settings.LORE_BOT_TOKEN or "").strip():
        return MSG_SIN_TOKEN
    if not (settings.MOTORED_PUBLIC_URL or "").strip():
        return MSG_SIN_URL
    return None


def _enviar_por_defecto() -> envio.Enviar:
    token = settings.LORE_BOT_TOKEN

    async def enviar(chat_id: int, texto: str) -> envio.Respuesta:
        return await envio.enviar_telegram(token, chat_id, texto)

    return enviar


def _olvidar_fechas_viejas(hoy: date) -> None:
    for fecha in [f for f in _sin_reporte if f < hoy.replace(day=1)]:
        del _sin_reporte[fecha]


async def run_tick(*, session_factory=None,
                   ahora: Optional[datetime] = None, enviar=None,
                   dormir: Callable = asyncio.sleep
                   ) -> Optional[envio.Conteo]:
    """One tick. Returns the counts of a send, or None when nothing ran."""
    if falta_configuracion() is not None:
        return None
    fabrica = session_factory or motored_session_maker()
    ahora = ahora or datetime.now(timezone.utc)
    async with fabrica() as db:
        config = await envio.leer_config(db, ahora, _memoria_config)
    local = ahora.astimezone(BOGOTA_OFFSET)
    if not config.activo or local.time() < config.hora_minima:
        return None
    _olvidar_fechas_viejas(local.date())
    async with fabrica() as cerrojo:
        if not await envio.tomar_candado(cerrojo, envio.LOCK_ENVIO):
            return None
        async with fabrica() as db:
            return await envio.envio_diario(
                db, ahora, config, enviar or _enviar_por_defecto(), dormir,
                _sin_reporte)


# --- ADMIN resend ----------------------------------------------------------

def reservar_reenvio() -> bool:
    """True for the one resend allowed at a time in this process."""
    global _reenvio_en_curso
    if _reenvio_en_curso:
        return False
    _reenvio_en_curso = True
    return True


def liberar_reenvio() -> None:
    global _reenvio_en_curso
    _reenvio_en_curso = False


async def ejecutar_reenvio(destinos: List[envio.Destino], fecha: date,
                           solicitado_por: uuid.UUID, *,
                           session_factory=None, enviar=None,
                           dormir: Callable = asyncio.sleep
                           ) -> Optional[envio.Conteo]:
    """Sends `destinos` now, bypassing the once-per-date rule; every
    ledger row is `reenvio` with `solicitado_por`. None when another
    worker is already resending or a daily run never let go."""
    fabrica = session_factory or motored_session_maker()
    async with fabrica() as cerrojo:
        if not await envio.tomar_candado(cerrojo, envio.LOCK_REENVIO):
            logger.warning("reporte asesor: otro reenvío ya está en curso")
            return None
        if not await envio.esperar_candado(
                cerrojo, envio.LOCK_ENVIO, ESPERA_CANDADO_SEGUNDOS):
            logger.warning("reporte asesor: el envío diario no terminó")
            return None
        async with fabrica() as db:
            return await envio.enviar_lote(
                db, destinos, fecha, enviar or _enviar_por_defecto(),
                dormir, reenvio=True, solicitado_por=solicitado_por)


async def reenviar_en_segundo_plano(destinos: List[envio.Destino],
                                    fecha: date,
                                    solicitado_por: uuid.UUID) -> None:
    """The background task of `POST /reporte-asesor/reenviar`: never
    raises and always releases the in-process guard."""
    try:
        await ejecutar_reenvio(destinos, fecha, solicitado_por)
    except Exception:  # noqa: BLE001 -- a background task has no caller
        logger.exception("reporte asesor: el reenvío falló")
    finally:
        liberar_reenvio()


# --- Loop ------------------------------------------------------------------

async def _run_forever(dormir: Callable = asyncio.sleep) -> None:
    """One tick every `TICK_SEGUNDOS`, until cancelled."""
    while True:
        await dormir(TICK_SEGUNDOS)
        try:
            await run_tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- a broken tick does not fall
            logger.exception("motored reporte asesor: tick falló")


async def detener() -> None:
    """Cancels the task and clears the state (clean stop and tests)."""
    global _task
    tarea, _task = _task, None
    _memoria_config.clear()
    _sin_reporte.clear()
    liberar_reenvio()
    if tarea is not None and not tarea.done():
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass
