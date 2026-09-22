"""
Motored Pedidos — Fase 2 "Ingesta", supervisor asyncio en proceso
(sdd/motored-pedidos-ingesta, ADR-1/ADR-1b).

`main.py` NO tiene un hook `lifespan` y esta fase lo deja así (ADR-1): el
supervisor se auto-arranca de forma PEREZOSA desde
`deps.require_motored_ready` (ya es una dependencia de cada endpoint de
Motored) vía `ensure_started()`, un chequeo O(1) después de la primera
llamada. Con `MOTORED_ENABLED=false` nunca existe task, thread ni poll --
`ensure_started()` es un no-op puro.

Alcance de esta fase: SOLO el motor de ejecución. Ningún tipo de trabajo
real (VENTAS, INVENTARIO, etc.) tiene todavía un handler registrado en
`jobs.JOB_HANDLERS` -- el claim/dispatch/sweep de acá son genéricos y no
cambian cuando la Fase 3+ registre transforms reales.

Estado (ADR-1b): `PENDIENTE -> PROCESANDO -> VALIDADO | CON_ERRORES`;
`VALIDADO ->(usuario) APLICANDO -> APLICADO`; cualquiera `-> ANULADO`.
`latido_en` se escribe en la MISMA transacción que cualquier commit de
lote (eso lo hace el handler real de cada job, Fase 3+; acá solo se
consume). El timeout se mide contra el heartbeat, NUNCA contra el
`created_at` -- un job legítimamente lento nunca es reclamado como muerto
por error, y la regla es independiente del tamaño del archivo por
construcción.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.database import motored_session_maker
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.services.trabajos import jobs

logger = logging.getLogger("motored.trabajos.supervisor")

# Executor dedicado de UN solo thread (ADR-1) -- NUNCA el executor default
# ni el pool de anyio -- para que a lo sumo exista un thread de ingesta en
# todo el proceso. El parseo real (openpyxl) que corre acá es Fase 3+; la
# plumbing del executor pertenece a esta fase.
POOL_INGESTA = ThreadPoolExecutor(max_workers=1, thread_name_prefix="motored-ingesta")

# Task del poll loop; `None` hasta el primer `ensure_started()` exitoso.
_task: Optional[asyncio.Task] = None

# `carga_id` que el dispatch actual tiene en vuelo, si alguno -- lo que el
# flush de SIGTERM necesita para saber qué marcar como interrumpido.
_current_carga_id: Optional[uuid.UUID] = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ensure_started() -> None:
    """Arranque perezoso e idempotente (ADR-1). Un chequeo O(1) (`_task`
    ya vivo) en cada llamada después de la primera. No hace nada si el
    módulo está apagado -- ni task, ni thread, ni poll llegan a existir."""
    global _task
    if not settings.MOTORED_ENABLED:
        return
    if _task is not None and not _task.done():
        return
    loop = asyncio.get_event_loop()
    _task = loop.create_task(_run_forever(), name="motored-ingesta-supervisor")


async def _run_forever() -> None:
    """Cuerpo del poll loop: sweep + claim/dispatch en cada tick, cada
    `MOTORED_INGESTA_POLL_SEGUNDOS`, para siempre hasta ser cancelado
    (`SIGTERM` en cada deploy de Coolify). Un tick que falla NUNCA debe
    matar el loop para los ticks siguientes."""
    try:
        while True:
            try:
                await run_tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 -- un tick roto no debe tirar el loop
                logger.exception("motored.trabajos.supervisor: tick falló")
            await asyncio.sleep(settings.MOTORED_INGESTA_POLL_SEGUNDOS)
    except asyncio.CancelledError:
        # Flush de mejor esfuerzo ante SIGTERM (ADR-1b): si había un
        # carga_id en vuelo, se marca antes de que el proceso termine. El
        # sweep del próximo boot es el backstop si esto no llega a correr.
        if _current_carga_id is not None:
            await _mark_interrupted(_current_carga_id)
        raise


async def run_tick() -> None:
    """Un tick del supervisor: sweep de heartbeat, después claim+dispatch
    de UNA fila `PENDIENTE` si existe. Público (no `_run_tick`) para que
    los tests puedan disparar un tick determinístico sin el loop de
    sleep."""
    session_maker = motored_session_maker()
    async with session_maker() as session:
        await sweep_heartbeats(session)
        claimed = await claim_next_pendiente(session)

    if claimed is None:
        return

    carga_id, tipo = claimed
    await _dispatch(carga_id, tipo)


async def _dispatch(carga_id: uuid.UUID, tipo: str) -> None:
    """Despacha `carga_id` al handler registrado para `tipo`. Ningún
    handler real existe todavía (Fase 3+) -- sin uno registrado, esto es
    un no-op documentado y la fila queda `PROCESANDO` hasta que el sweep
    de heartbeat la recupere por timeout, exactamente igual que un job real
    que nunca manda su primer heartbeat.

    Deliberadamente NO usa `finally` para limpiar `_current_carga_id`: un
    `finally` corre ANTES de que un `CancelledError` (SIGTERM) siga
    propagándose hacia `_run_forever`, así que `_current_carga_id` ya
    aparecía en `None` justo cuando el flush de SIGTERM necesitaba verlo
    seteado -- el flush nunca se disparaba para el caso que existe para
    cubrir. Limpiar solo en el camino feliz (después del `await`, nunca
    alcanzado si `handler` lanza o es cancelado) deja `_current_carga_id`
    intacto para que `_run_forever` lo vea. Un handler que falla con una
    excepción normal (no cancelación) deja el valor colgado hasta el
    próximo dispatch exitoso -- inocuo: la recuperación real de esa fila la
    hace el sweep de heartbeat en la base de datos, no esta variable, que
    es solo diagnóstico para el log de SIGTERM."""
    global _current_carga_id
    handler = jobs.JOB_HANDLERS.get(tipo)
    if handler is None:
        return
    _current_carga_id = carga_id
    await handler(carga_id)
    _current_carga_id = None


async def _claim_by_id(
    session: AsyncSession, carga_id: uuid.UUID, now: datetime
) -> Optional[uuid.UUID]:
    """El claim atómico (ADR-1): `UPDATE ... WHERE id=:id AND
    estado='PENDIENTE' ... RETURNING id`. Incluso si dos supervisores (un
    futuro `--workers N`) reclaman el mismo candidato, solo el UPDATE cuyo
    WHERE todavía matchea `estado='PENDIENTE'` en el momento del commit
    afecta una fila -- el otro ve 0 filas afectadas y `RETURNING` vacío."""
    result = await session.execute(
        update(CargaArchivo)
        .where(CargaArchivo.id == carga_id, CargaArchivo.estado == "PENDIENTE")
        .values(estado="PROCESANDO", latido_en=now)
        .returning(CargaArchivo.id)
    )
    claimed_id = result.scalars().first()
    await session.commit()
    return claimed_id


async def claim_next_pendiente(
    session: AsyncSession, now: Optional[datetime] = None
) -> Optional[Tuple[uuid.UUID, str]]:
    """Busca la fila `PENDIENTE` más antigua y la reclama atómicamente.
    Devuelve `(carga_id, tipo)` si se reclamó algo, o `None` si no había
    nada `PENDIENTE` o el candidato fue reclamado por otro proceso primero
    entre el SELECT y el UPDATE."""
    now = now or _now_utc()
    candidate = await session.execute(
        select(CargaArchivo.id, CargaArchivo.tipo)
        .where(CargaArchivo.estado == "PENDIENTE")
        .order_by(CargaArchivo.created_at)
        .limit(1)
    )
    row = candidate.first()
    if row is None:
        return None

    candidate_id, tipo = row
    claimed_id = await _claim_by_id(session, candidate_id, now)
    if claimed_id is None:
        return None
    return claimed_id, tipo


async def sweep_heartbeats(session: AsyncSession, now: Optional[datetime] = None) -> None:
    """Sweep de recuperación de caídas (ADR-1b). Corre en el primer tick
    después de un boot y en cada tick siguiente. Una fila cuyo `latido_en`
    esté más viejo que `MOTORED_INGESTA_TIMEOUT_MIN` se considera muerta:

    - `PROCESANDO` -> `CON_ERRORES` (un dry-run parcial no es confiable).
    - `APLICANDO` -> `VALIDADO` (el usuario reintenta; el apply real, Fase
      3+, resume desde `ultimo_lote_aplicado + 1`).

    Un heartbeat fresco queda intacto. `PENDIENTE` nunca tiene `latido_en`
    (se setea recién al reclamar), así que el filtro `latido_en IS NOT
    NULL` ya la excluye por construcción."""
    now = now or _now_utc()
    stale_before = now - timedelta(minutes=settings.MOTORED_INGESTA_TIMEOUT_MIN)

    await session.execute(
        update(CargaArchivo)
        .where(
            CargaArchivo.estado == "PROCESANDO",
            CargaArchivo.latido_en.isnot(None),
            CargaArchivo.latido_en < stale_before,
        )
        .values(estado="CON_ERRORES")
    )
    await session.execute(
        update(CargaArchivo)
        .where(
            CargaArchivo.estado == "APLICANDO",
            CargaArchivo.latido_en.isnot(None),
            CargaArchivo.latido_en < stale_before,
        )
        .values(estado="VALIDADO")
    )
    await session.commit()


async def _mark_interrupted(carga_id: uuid.UUID) -> None:
    """Flush de mejor esfuerzo ante SIGTERM (ADR-1b): nunca debe lanzar --
    que falle durante el shutdown no puede bloquear la salida del proceso.
    El sweep del próximo boot es el backstop si esto ni siquiera llega a
    correr."""
    try:
        session_maker = motored_session_maker()
        async with session_maker() as session:
            await session.execute(
                update(CargaArchivo)
                .where(CargaArchivo.id == carga_id)
                .values(log={"interrumpido_por": "SIGTERM"})
            )
            await session.commit()
    except Exception:  # noqa: BLE001 -- mejor esfuerzo, nunca debe propagar
        logger.exception(
            "motored.trabajos.supervisor: flush de SIGTERM falló para %s", carga_id
        )


async def reset_for_tests() -> None:
    """SOLO PARA TESTS: cancela el task del supervisor si existe y limpia
    el estado del módulo, para que un test no deje un poll loop corriendo
    de fondo hacia el siguiente. Ningún código de producción llama a
    esto."""
    global _task, _current_carga_id
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    _current_carga_id = None
