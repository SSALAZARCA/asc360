"""
Motored Pedidos — Fase 2 "Ingesta", Phase 12 "Retention Purge" (sdd/motored-
pedidos-ingesta, design ADR-3).

Runs off the supervisor's own tick (`services/trabajos/supervisor.py`) --
no new mechanism, no Redis lock, no self-rescheduling job. State lives
entirely in Postgres:

- `retencion_ejecucion` (built in Phase 1) is BOTH the ledger (rows removed,
  limit date, duration) AND the scheduler's anchor -- `esta_vencida()`
  reconstructs "is it due?" purely from `max(ejecutado_en)` in that table,
  so a process restart can never double-run nor skip a day, with zero
  in-process state.
- The "no active job" gate (`hay_job_activo()`) reads `carga_archivo`
  directly for any `PROCESANDO`/`APLICANDO` row -- also DB-anchored, not an
  in-process registry -- which is what ELIMINATES the purge-vs-apply hazard
  rather than merely testing for it: even a freshly-restarted process (empty
  in-memory state) sees a live job and skips.
- The window is anchored to `max(fecha_corte)` already IN `inventario_
  snapshot`, never to `now()` -- a pause in loading can never purge
  everything.

Gated by `MOTORED_RETENCION_ENABLED` (default `False`, see `app/config.py`).

Deliberate deviation from the design's literal wording: ADR-3 says
"20 000-row `ctid`-bounded chunks". `ctid` is a Postgres physical row
identifier -- this module instead bounds each batch by selecting up to
`chunk_size` PRIMARY KEY ids and deleting exactly that batch. Functionally
equivalent to the design's intent (one `DELETE` never touches more than
`chunk_size` rows, no full-table scan, no long lock) while staying pure
async SQLAlchemy Core, portable to the SQLite the rest of this suite tests
transactional DB contracts against (see `tests/motored/test_supervisor.py`),
and testable with the suite's `FakeAsyncSession` convention with no live
Postgres anywhere (see `tests/motored/test_retencion.py`).
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.retencion_ejecucion import RetencionEjecucion

TABLA_INVENTARIO_SNAPSHOT = "inventario_snapshot"

# ADR-3's due-check interval: "if older than 24 h".
INTERVALO_DEBIDO = timedelta(hours=24)

# ADR-3's default chunk size. An explicit parameter on `ejecutar_purga_
# inventario` so tests can force 2+ chunks without a tens-of-thousands-row
# fixture -- production always uses this default.
TAMANO_CHUNK = 20000

# A live job in either of these states is what the purge must never race
# with (ADR-3's "no ingest job active" gate).
ESTADOS_JOB_ACTIVO = ("PROCESANDO", "APLICANDO")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _como_aware(valor: datetime) -> datetime:
    """`retencion_ejecucion.ejecutado_en` is a naive `DateTime` column (see
    the model), but every caller in this module works in UTC-aware time --
    this normalizes a value read back from the table before comparing it to
    an aware `now`."""
    return valor if valor.tzinfo is not None else valor.replace(tzinfo=timezone.utc)


def _como_naive_utc(valor: datetime) -> datetime:
    """The inverse of `_como_aware`, for the write path. `ejecutado_en` is
    a NAIVE `DateTime` column (unlike `carga_archivo.latido_en`, which is
    `DateTime(timezone=True)`) -- writing an aware value there is correct
    in memory but raises against a real asyncpg connection (a
    `DataError`, aware/naive column-type mismatch). Every other naive
    `DateTime` column in this model file is written the same way, via
    `default=datetime.utcnow` (also naive)."""
    return valor.replace(tzinfo=None) if valor.tzinfo is not None else valor


async def hay_job_activo(session: AsyncSession) -> bool:
    """ADR-3's "no active job" gate. Reads `carga_archivo` directly -- not
    an in-process registry -- so the decision is correct even immediately
    after a restart, when no in-memory state exists yet."""
    resultado = await session.execute(
        select(CargaArchivo.id).where(CargaArchivo.estado.in_(ESTADOS_JOB_ACTIVO)).limit(1)
    )
    return resultado.first() is not None


async def esta_vencida(
    session: AsyncSession,
    tabla: str = TABLA_INVENTARIO_SNAPSHOT,
    now: Optional[datetime] = None,
) -> bool:
    """Due-check anchored purely in `retencion_ejecucion` (ADR-3): "if older
    than 24 h". Never having run at all counts as due. Takes only `session`
    and `now` -- no module-level state -- so calling this from scratch after
    a restart reproduces the exact same decision the process would have
    made right before it died."""
    now = now or _now_utc()
    resultado = await session.execute(
        select(func.max(RetencionEjecucion.ejecutado_en)).where(RetencionEjecucion.tabla == tabla)
    )
    ultima_ejecucion = resultado.scalars().first()
    if ultima_ejecucion is None:
        return True
    return (now - _como_aware(ultima_ejecucion)) > INTERVALO_DEBIDO


def calcular_fecha_limite(fecha_corte_maxima: date, dias: int) -> date:
    """The window is anchored to the newest `fecha_corte` already in the
    table, NEVER to `now()` (ADR-3) -- a pause in loading cannot purge
    everything."""
    return fecha_corte_maxima - timedelta(days=dias)


async def ejecutar_purga_inventario(
    session: AsyncSession,
    now: Optional[datetime] = None,
    chunk_size: int = TAMANO_CHUNK,
) -> Optional[RetencionEjecucion]:
    """The chunked delete itself (ADR-3). Bounded to `fecha_corte <
    max(fecha_corte) - MOTORED_RETENCION_DIAS`; runs in `chunk_size`-bounded
    batches, one commit per batch. Writes exactly one `retencion_ejecucion`
    row per run (rows removed, limit date, duration) -- ledger AND scheduler
    anchor for the next `esta_vencida()` call. Returns `None` (writes
    nothing) if `inventario_snapshot` is empty -- there is no `fecha_corte`
    to anchor a window to."""
    now = now or _now_utc()

    resultado_max = await session.execute(select(func.max(InventarioSnapshot.fecha_corte)))
    fecha_corte_maxima = resultado_max.scalars().first()
    if fecha_corte_maxima is None:
        return None

    fecha_limite = calcular_fecha_limite(fecha_corte_maxima, settings.MOTORED_RETENCION_DIAS)

    inicio = time.monotonic()
    total_eliminadas = 0
    while True:
        resultado_ids = await session.execute(
            select(InventarioSnapshot.id)
            .where(InventarioSnapshot.fecha_corte < fecha_limite)
            .limit(chunk_size)
        )
        ids_del_chunk = resultado_ids.scalars().all()
        if not ids_del_chunk:
            break

        await session.execute(delete(InventarioSnapshot).where(InventarioSnapshot.id.in_(ids_del_chunk)))
        await session.commit()
        total_eliminadas += len(ids_del_chunk)

        if len(ids_del_chunk) < chunk_size:
            break

    duracion_ms = int((time.monotonic() - inicio) * 1000)

    ejecucion = RetencionEjecucion(
        tabla=TABLA_INVENTARIO_SNAPSHOT,
        ejecutado_en=_como_naive_utc(now),
        fecha_limite=fecha_limite,
        filas_eliminadas=total_eliminadas,
        duracion_ms=duracion_ms,
    )
    session.add(ejecucion)
    await session.commit()
    return ejecucion


async def ejecutar_si_corresponde(
    session: AsyncSession, now: Optional[datetime] = None
) -> Optional[RetencionEjecucion]:
    """Entry point called from the supervisor's own tick (ADR-3). No-op
    unless `MOTORED_RETENCION_ENABLED` -- checked FIRST, before any query,
    so a disabled purge never touches the database regardless of how
    overdue it is. Then the "no active job" gate, THEN the due-check, in
    that order, so a live job short-circuits with a single query and never
    even asks whether the purge is due."""
    if not settings.MOTORED_RETENCION_ENABLED:
        return None

    now = now or _now_utc()

    if await hay_job_activo(session):
        return None

    if not await esta_vencida(session, now=now):
        return None

    return await ejecutar_purga_inventario(session, now=now)
