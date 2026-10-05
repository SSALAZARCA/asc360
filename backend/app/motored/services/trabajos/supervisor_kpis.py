"""
Motored: loop asyncio que reconstruye las tablas resumen de los KPI's.

Mismo patron que `supervisor_avisos.py`: arranque PEREZOSO desde
`deps.require_motored_ready` (`ensure_started()`, O(1) despues de la primera
llamada), cierre por cancelacion del task y un tick que falla se registra sin
matar el loop (y se reintenta tras una espera, no cada tick).

Cada tick lee la fila de estado (`kpi_resumen_estado`) y decide con `decidir`:
- `primera`: la fila no existe o nunca termino una reconstruccion completa Y ya hay
  lineas de ventas o de inventario que resumir (con la base vacia espera). Asi
  produccion hace su primer llenado despues del deploy, sin paso manual.
- `sucia`: algo que no tiene refresco incremental cambio (linea de una referencia,
  lista Tecnired, `hmcl_nits`/`lineas_comerciales`, inventario) o el ADMIN pidio
  "Recalcular" (ver `services/kpi_resumen.marcar_sucio`).
- `nocturna`: la ultima reconstruccion completa tiene mas de `HORAS_NOCTURNA`
  horas y la hora de Bogota esta en la ventana 01:00-05:00. Es la red de
  seguridad contra cualquier deriva; 20 h (no 24) para que el cambio de hora del
  dia en que corrio una reconstruccion por "sucia" no la salte una noche entera.

Una reconstruccion completa tiene tres pasos, cada uno en su propia transaccion:
1. `reconstruyendo=true`, confirmado ANTES de empezar (la pantalla lo muestra);
2. la reconstruccion (`kpi_resumen.reconstruir_todo`), que toma el candado
   consultivo y lo suelta al confirmar;
3. `reconstruyendo=false`, SIEMPRE (tambien si la reconstruccion fallo).

Candado: mientras dura la reconstruccion, una carga de ventas (o un cambio de
Configuracion) que llegue espera el candado hasta
`MOTORED_KPI_RESUMEN_LOCK_TIMEOUT_SEGUNDOS` (60 s) y despues falla con
`ResumenOcupadoError` ("intente de nuevo en unos minutos"), en vez de colgarse.
La reconstruccion es por conjuntos (INSERT ... SELECT; un par de decenas de
segundos con ~1M de lineas) y tiene su propio tope,
`MOTORED_KPI_RESUMEN_REBUILD_TIMEOUT_SEGUNDOS` (30 min), que la corta y suelta
el candado si algo la cuelga.

Interruptores (`app/config.py`): `MOTORED_ENABLED=false` apaga todo Motored;
`MOTORED_KPI_RESUMEN_LOOP_ENABLED=false` apaga solo este loop (nadie
reconstruye las tablas). Es independiente de `MOTORED_KPI_RESUMEN_ENABLED`, que
solo decide si las pantallas LEEN de las tablas.

Una sola replica es lo esperado. Con varias, cada una reconstruiria (el candado
las serializa; la segunda repite el trabajo sin dañar nada).
"""
import asyncio
import datetime
import logging
from datetime import datetime as DateTime
from datetime import timezone
from typing import Callable, Optional

from sqlalchemy import func, select

from app.config import settings
from app.motored.database import motored_session_maker
from app.motored.services import kpi_resumen
from app.motored.services.reloj import BOGOTA_OFFSET

logger = logging.getLogger("motored.trabajos.supervisor_kpis")

MOTIVO_PRIMERA = "primera"
MOTIVO_SUCIA = "sucia"
MOTIVO_NOCTURNA = "nocturna"

HORAS_NOCTURNA = 20
VENTANA_NOCTURNA = (datetime.time(1, 0), datetime.time(5, 0))  # hora de Bogota, [inicio, fin)
ESPERA_TRAS_FALLO_SEGUNDOS = 600
# Extra wait, on top of the rebuild timeout, before a `reconstruyendo` flag counts as stale.
MARGEN_RECONSTRUCCION_SEGUNDOS = 300

_task: Optional[asyncio.Task] = None
# Hasta cuando no se reintenta tras un fallo (reloj monotonico del loop, en UTC).
_no_reintentar_antes: Optional[DateTime] = None
# Since when this process has seen `reconstruyendo=true` without a rebuild of its own running
# (None while the flag is false). The state row has no "since" column, so the loop times it.
_reconstruyendo_desde: Optional[DateTime] = None


def ensure_started() -> None:
    """Arranque perezoso e idempotente. Nunca lanza: corre en la ruta de
    CADA request de Motored."""
    global _task
    if not settings.MOTORED_ENABLED:
        return
    if not settings.MOTORED_KPI_RESUMEN_LOOP_ENABLED:
        return
    if _task is not None and not _task.done():
        return
    try:
        _task = asyncio.get_running_loop().create_task(_run_forever(), name="motored-kpi-resumen")
    except Exception:  # noqa: BLE001 -- nunca hacia el request
        logger.exception("no se pudo arrancar el loop de resumenes de KPI")


def en_ventana_nocturna(ahora: DateTime) -> bool:
    hora = ahora.astimezone(BOGOTA_OFFSET).time()
    inicio, fin = VENTANA_NOCTURNA
    return inicio <= hora < fin


def decidir(estado: Optional[kpi_resumen.Estado], ahora: DateTime) -> Optional[str]:
    """Motivo de la reconstruccion que toca ahora, o None. Pura: `ahora` es UTC con zona."""
    if estado is None or estado.ultima_reconstruccion_total is None:
        return MOTIVO_PRIMERA
    if estado.sucio:
        return MOTIVO_SUCIA
    ultima = estado.ultima_reconstruccion_total
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    vencida = ahora - ultima >= datetime.timedelta(hours=HORAS_NOCTURNA)
    if vencida and en_ventana_nocturna(ahora):
        return MOTIVO_NOCTURNA
    return None


async def _poner_reconstruyendo(fabrica, valor: bool) -> None:
    async with fabrica() as db:
        await kpi_resumen.marcar_reconstruyendo(db, valor)
        await db.commit()


async def reconstruir(fabrica) -> None:
    """Una reconstruccion completa con su bandera `reconstruyendo` (ver el docstring del modulo)."""
    await _poner_reconstruyendo(fabrica, True)
    try:
        async with fabrica() as db:
            tope = max(int(settings.MOTORED_KPI_RESUMEN_REBUILD_TIMEOUT_SEGUNDOS), 1)
            await db.execute(select(func.set_config("statement_timeout", f"{tope}s", True)))
            await kpi_resumen.reconstruir_todo(db)
            await db.commit()
    finally:
        try:
            await _poner_reconstruyendo(fabrica, False)
        except Exception:  # noqa: BLE001 -- no tapar el error de la reconstruccion
            logger.exception("no se pudo limpiar la bandera reconstruyendo")


async def _vigilar_bandera(fabrica, estado: Optional[kpi_resumen.Estado], ahora: DateTime) -> None:
    """Resets a `reconstruyendo` flag a dead process left behind. Ticks never overlap a rebuild
    of this process, so a flag seen at tick time belongs to another replica or to a crash; once
    it has been seen for longer than the rebuild timeout (+ margin), no live rebuild can own it
    (the statement timeout would have cut it) and the UI must stop saying "recalculando"."""
    global _reconstruyendo_desde
    if estado is None or not estado.reconstruyendo:
        _reconstruyendo_desde = None
        return
    if _reconstruyendo_desde is None:
        _reconstruyendo_desde = ahora
        return
    tope = max(int(settings.MOTORED_KPI_RESUMEN_REBUILD_TIMEOUT_SEGUNDOS), 1) + MARGEN_RECONSTRUCCION_SEGUNDOS
    if ahora - _reconstruyendo_desde > datetime.timedelta(seconds=tope):
        logger.warning("resumenes de KPI: bandera reconstruyendo vencida, se limpia")
        await _poner_reconstruyendo(fabrica, False)
        _reconstruyendo_desde = None


async def run_tick(*, session_factory=None, ahora: Optional[DateTime] = None) -> Optional[str]:
    """Un tick. Devuelve el motivo de la reconstruccion que hizo, o None si no tocaba (o si
    todavia esta en espera tras un fallo). Un fallo de la reconstruccion se propaga."""
    global _no_reintentar_antes
    fabrica = session_factory or motored_session_maker()
    ahora = ahora or DateTime.now(timezone.utc)
    if _no_reintentar_antes is not None and ahora < _no_reintentar_antes:
        return None
    async with fabrica() as db:
        estado = await kpi_resumen.estado(db)
    await _vigilar_bandera(fabrica, estado, ahora)
    motivo = decidir(estado, ahora)
    if motivo is None:
        return None
    if motivo == MOTIVO_PRIMERA:
        async with fabrica() as db:
            if not await kpi_resumen.hay_datos(db):
                return None  # nothing to summarize yet: the first build waits for the first lines
    logger.info("resumenes de KPI: reconstruccion completa (%s)", motivo)
    try:
        await reconstruir(fabrica)
    except Exception:
        _no_reintentar_antes = ahora + datetime.timedelta(seconds=ESPERA_TRAS_FALLO_SEGUNDOS)
        raise
    _no_reintentar_antes = None
    return motivo


async def _run_forever(dormir: Callable = asyncio.sleep) -> None:
    """Un tick cada `MOTORED_KPI_RESUMEN_POLL_SEGUNDOS`, hasta ser cancelado. Duerme ANTES
    del primer tick: el request que arranco el loop no compite con una reconstruccion y el
    primer llenado de produccion llega un intervalo (60 s) despues del deploy."""
    while True:
        await dormir(settings.MOTORED_KPI_RESUMEN_POLL_SEGUNDOS)
        try:
            await run_tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- un tick roto no cae
            logger.exception("motored resumenes de KPI: tick fallo")


async def detener() -> None:
    """Cancela el task y limpia el estado (cierre limpio y tests)."""
    global _task, _no_reintentar_antes, _reconstruyendo_desde
    tarea, _task = _task, None
    _no_reintentar_antes = None
    _reconstruyendo_desde = None
    if tarea is not None and not tarea.done():
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass
