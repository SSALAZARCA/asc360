"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6b, ADR-5): el loop
asyncio PROPIO de las corridas.

Es un segundo loop, separado del supervisor de cargas de la Fase 2
(`supervisor.py`, que queda intacto): el `run_tick` de F2 espera inline al
handler de la carga, así que una corrida dentro de él y las cargas se
frenarían entre sí. Acá cada loop tiene su claim, su barrido y su tick.

Arranque y cierre, igual que F2: `main.py` no tiene `lifespan`; el loop
arranca de forma PEREZOSA desde `deps.require_motored_ready` (una línea al
lado de la de F2) con `ensure_started()`, un chequeo O(1) después de la
primera llamada. Se detiene con la cancelación del task (`SIGTERM` en cada
deploy): la corrida en vuelo se devuelve a PENDIENTE sin gastar un intento y
el tick siguiente de la nueva instancia la retoma.

Interruptores (`app/config.py`):
- `MOTORED_ENABLED=false` apaga todo Motored, este loop incluido.
- `MOTORED_CORRIDAS_LOOP_ENABLED=false` apaga SÓLO este loop (por defecto
  encendido); el de cargas no se toca. Se cambia con la variable de entorno
  y un redeploy.

Seguridad de un loop que vive dentro de la app en producción:
- un tick que falla se registra y el loop sigue; nada de lo que pase acá
  llega a un request ni al supervisor de cargas;
- si la tabla `corrida` no existe todavía (el código llegó antes que la
  migración) el loop avisa UNA vez por arranque y queda en espera larga, sin
  ruido ni caída, y retoma solo cuando aparece;
- varias réplicas del backend son seguras: el claim y el barrido usan
  `SKIP LOCKED` (ver `services/corridas/ejecucion.py`).
"""
import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional
from uuid import UUID

from sqlalchemy.exc import DBAPIError

from app.config import settings
from app.motored.database import motored_session_maker
from app.motored.services.corridas import ejecucion, retencion_corridas
from app.motored.services.trabajos.supervisor import POOL_INGESTA

logger = logging.getLogger("motored.trabajos.supervisor_corridas")

# Espera del loop mientras la tabla `corrida` no existe.
ESPERA_SIN_TABLA_SEGUNDOS = 60

# Task del loop; `None` hasta el primer `ensure_started()` exitoso.
_task: Optional[asyncio.Task] = None

# Ya se avisó (una vez por arranque) que falta la tabla `corrida`.
_aviso_tabla_ausente = False


def _crear_tarea() -> asyncio.Task:
    return asyncio.get_running_loop().create_task(
        _run_forever(), name="motored-corridas-supervisor")


def ensure_started() -> None:
    """Arranque perezoso e idempotente. Nunca lanza: corre en la ruta de
    CADA request de Motored y un fallo acá no puede tumbarlos."""
    global _task
    if not settings.MOTORED_ENABLED:
        return
    if not settings.MOTORED_CORRIDAS_LOOP_ENABLED:
        return
    if _task is not None and not _task.done():
        return
    try:
        _task = _crear_tarea()
    except Exception:  # noqa: BLE001 -- nunca hacia el request
        logger.exception("no se pudo arrancar el loop de corridas")


def es_tabla_ausente(error: BaseException) -> bool:
    """`True` si el error es "la tabla de corridas no existe" (migración de
    F3 sin aplicar todavía): un error de SQL cuyo mensaje dice que la
    relación `corrida*` no existe."""
    if not isinstance(error, DBAPIError):
        return False
    texto = str(error.orig if error.orig is not None else error).lower()
    return "corrida" in texto and (
        "does not exist" in texto or "no such table" in texto)


def _registrar_tabla_ausente() -> None:
    global _aviso_tabla_ausente
    if _aviso_tabla_ausente:
        return
    _aviso_tabla_ausente = True
    logger.warning(
        "la tabla `corrida` no existe todavía: el loop de corridas espera "
        "a que se aplique la migración de la Fase 3 (avisa una sola vez)")


def _registrar_tabla_disponible() -> None:
    global _aviso_tabla_ausente
    if _aviso_tabla_ausente:
        _aviso_tabla_ausente = False
        logger.info("la tabla `corrida` ya está disponible: loop reanudado")


async def _run_forever(dormir: Callable = asyncio.sleep) -> None:
    """Cuerpo del loop: un tick cada `MOTORED_CORRIDA_POLL_SEGUNDOS`, para
    siempre hasta ser cancelado. Un tick que falla NUNCA mata el loop."""
    while True:
        espera = settings.MOTORED_CORRIDA_POLL_SEGUNDOS
        try:
            await run_tick()
            _registrar_tabla_disponible()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 -- un tick roto no cae
            if es_tabla_ausente(error):
                _registrar_tabla_ausente()
                espera = ESPERA_SIN_TABLA_SEGUNDOS
            else:
                logger.exception("motored corridas: tick falló")
        await dormir(espera)


async def run_tick(
    *, session_factory=None,
    reloj: Optional[Callable[[], datetime]] = None,
    dormir: Callable = asyncio.sleep,
    ejecutor=POOL_INGESTA,
) -> Optional[UUID]:
    """Un tick: barrido de estancadas, claim de UNA corrida PENDIENTE y, si
    el claim no encontró nada, el due-check de retención. La corrida
    reclamada corre DESPUÉS de cerrar la sesión del claim y en su propia
    sesión. Público para disparar un tick determinístico en los tests."""
    fabrica = session_factory or motored_session_maker()
    reloj = reloj or ejecucion.ahora_utc
    ahora = reloj()
    async with fabrica() as db:
        await ejecucion.barrer_estancadas(
            db, ahora,
            timeout_min=settings.MOTORED_CORRIDA_TIMEOUT_MIN,
            max_intentos=settings.MOTORED_CORRIDA_MAX_INTENTOS)
        corrida_id = await ejecucion.reclamar_siguiente(db, ahora)
        if corrida_id is None:
            await retencion_corridas.ejecutar_si_corresponde(db, ahora)
    if corrida_id is None:
        return None
    await ejecucion.ejecutar_corrida(
        corrida_id, session_factory=fabrica, ejecutor=ejecutor,
        dormir=dormir, reloj=reloj)
    return corrida_id


async def detener() -> None:
    """Cancela el task del loop y limpia el estado del módulo (cierre
    limpio; también lo usan los tests para no dejar un loop de fondo)."""
    global _task, _aviso_tabla_ausente
    tarea, _task = _task, None
    _aviso_tabla_ausente = False
    if tarea is not None and not tarea.done():
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass
