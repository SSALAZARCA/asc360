"""
Motored: loop asyncio del aviso anticipado de antiguedad de datos.

Mismo patron que `supervisor_corridas.py`: arranque PEREZOSO desde
`deps.require_motored_ready` (`ensure_started()`, O(1) despues de la primera
llamada), cierre por cancelacion del task y un tick que falla se registra
sin matar el loop. Cada tick es barato: antes de las 08:30 de Bogota no toca
la base, y sin `LORE_BOT_TOKEN` tampoco (se avisa UNA vez por arranque).

Interruptores (`app/config.py`): `MOTORED_ENABLED=false` apaga todo Motored;
`MOTORED_AVISOS_ANTIGUEDAD_ENABLED=false` apaga solo este loop.

Varias replicas son seguras: cada envio se reserva con un INSERT unico en
`aviso_antiguedad_enviado` (ver `services/avisos_antiguedad.py`).
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from app.config import settings
from app.motored.database import motored_session_maker
from app.motored.services import avisos_antiguedad, avisos_telegram

logger = logging.getLogger("motored.trabajos.supervisor_avisos")

_task: Optional[asyncio.Task] = None
_aviso_sin_token = False


def ensure_started() -> None:
    """Arranque perezoso e idempotente. Nunca lanza: corre en la ruta de
    CADA request de Motored."""
    global _task
    if not settings.MOTORED_ENABLED:
        return
    if not settings.MOTORED_AVISOS_ANTIGUEDAD_ENABLED:
        return
    if _task is not None and not _task.done():
        return
    try:
        _task = asyncio.get_running_loop().create_task(
            _run_forever(), name="motored-avisos-antiguedad")
    except Exception:  # noqa: BLE001 -- nunca hacia el request
        logger.exception("no se pudo arrancar el loop de avisos")


def _hay_token() -> bool:
    global _aviso_sin_token
    if settings.LORE_BOT_TOKEN:
        return True
    if not _aviso_sin_token:
        _aviso_sin_token = True
        logger.warning(
            "LORE_BOT_TOKEN vacío: no se envían avisos de antigüedad por "
            "Telegram (el banner en la app sigue activo; avisa una vez)")
    return False


async def run_tick(
    *, session_factory=None, ahora: Optional[datetime] = None,
    enviar=None,
) -> int:
    """Un tick. Devuelve cuántos mensajes se entregaron."""
    if not _hay_token():
        return 0
    fabrica = session_factory or motored_session_maker()
    ahora = ahora or datetime.now(timezone.utc)
    token = settings.LORE_BOT_TOKEN

    async def por_defecto(chat_id: int, texto: str) -> bool:
        return await avisos_telegram.enviar_mensaje(token, chat_id, texto)

    async with fabrica() as db:
        return await avisos_antiguedad.procesar_avisos(
            db, ahora, enviar or por_defecto)


async def _run_forever(dormir: Callable = asyncio.sleep) -> None:
    """Un tick cada `MOTORED_AVISOS_POLL_SEGUNDOS`, hasta ser cancelado."""
    while True:
        try:
            await run_tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- un tick roto no cae
            logger.exception("motored avisos de antigüedad: tick falló")
        await dormir(settings.MOTORED_AVISOS_POLL_SEGUNDOS)


async def detener() -> None:
    """Cancela el task y limpia el estado (cierre limpio y tests)."""
    global _task, _aviso_sin_token
    tarea, _task = _task, None
    _aviso_sin_token = False
    if tarea is not None and not tarea.done():
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass
