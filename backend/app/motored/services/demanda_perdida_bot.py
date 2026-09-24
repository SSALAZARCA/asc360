"""
Motored Pedidos — bot "Lore" write path (sdd/motored-ventas-perdidas-bot,
design D3/D4).

**Scope note**: this module is created NOW, in Phase 3 ("Backend
bugfixes"), to satisfy task 3.7/3.8's PATCH/anular BOT guards -- the web
ADMIN `POST /cargas/{id}/anular` endpoint must delegate to
`anular_registro_bot(db, carga, actor, validar_ventana=False)` for a
BOT-origin row (design D4). Phase 6 ("Demanda perdida — bot write path")
owns the REST of this module: `construir_upsert_aditivo` (D3's additive
upsert), the negative-delta update/delete helper used by the bot's own
`PATCH .../lineas/{id}` and `POST .../{carga_id}/anular` endpoints (with
`validar_ventana=True`, enforcing the actor-owns-it + today-only 409
rules), and the full atomic-under-concurrency SQL shape D3 describes
(`UPDATE ... WHERE key AND origen='BOT'` then `DELETE ... WHERE cantidad
<= 0`, never a plain ORM read-mutate-write) for the general case.

The `validar_ventana=False` branch below (the ONLY branch Phase 3 needs,
since it is exactly the web ADMIN correction path) uses a simpler
ORM-level read-then-mutate-then-commit shape -- consistent with how the
rest of `api/cargas.py` already mutates `CargaArchivo` rows (e.g.
`anular_carga`'s EXCEL path), not the raw compiled-SQL shape D3 prescribes
for the bot's own concurrent-write endpoints. This is safe here because,
until Phase 5/6 ship, no code path can create a SECOND concurrent writer
against the same `demanda_perdida` row -- but Phase 6 should revisit
whether to reuse the same atomic UPDATE-based helper for both call sites
once it exists, rather than keeping two different reversal strategies.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids import cycles
    from app.motored.services.auth import MotoredUser

logger = logging.getLogger("motored.demanda_perdida_bot")


class CargaYaAnuladaError(Exception):
    """La carga ya estaba `ANULADO` en el momento del claim atómico (ver
    docstring de `anular_registro_bot`, sección "Claim atómico"). Mismo
    criterio que `orquestador.EstadoInvalidoParaAplicarError`: una excepción
    de dominio propia del servicio, traducida a `HTTPException(409)` en la
    capa de API (`api/cargas.py::anular_carga`), nunca levantada acá
    directamente -- este módulo no depende de FastAPI."""


async def anular_registro_bot(
    db: AsyncSession,
    carga: "CargaArchivo",
    actor: "MotoredUser",
    validar_ventana: bool = False,
) -> None:
    """Anula una registración BOT (design D4): revierte, por cada línea
    `ACTIVA` del ledger, la cantidad CURRENTE que esa línea aportó a
    `demanda_perdida` (nunca la cantidad original si hubo una edición
    previa), marca la línea `ANULADA`, y deja el header en
    `estado='ANULADO'` con `log.anulado_por`/`log.anulado_en`.

    `validar_ventana=True` (el propio endpoint del bot, Fase 6) exige
    además que `actor` sea el dueño de la registración y que sea del día
    de hoy (Bogotá) -- Fase 3 no implementa esa rama; se usa
    exclusivamente desde el web ADMIN (`validar_ventana=False`), que no
    tiene esas restricciones.

    **Claim atómico (post-Phase-3 review, finding #2)**: dos llamadas
    concurrentes contra el MISMO `carga_id` (doble-click, retry del
    cliente) podían leer ambas `carga.estado != "ANULADO"` -- el guard de
    `api/cargas.py::anular_carga` es un SELECT + chequeo en Python, NO
    atómico -- y ambas revertir el mismo ledger antes de que cualquiera
    hiciera commit, duplicando la reversa de `demanda_perdida.
    cantidad_solicitada`. Se cierra ACÁ, no en el endpoint, porque este es
    el único punto común a toda llamada concurrente contra la misma fila:
    un `UPDATE ... WHERE id=:id AND estado != 'ANULADO' ... RETURNING id`
    (mismo patrón que `services/trabajos/supervisor.py::_claim_by_id` usa
    para el claim de jobs -- ver ese docstring) afecta como máximo una fila
    entre todos los llamadores concurrentes; el que pierde ve 0 filas
    afectadas y levanta `CargaYaAnuladaError` ANTES de tocar ninguna línea
    del ledger."""
    if validar_ventana:
        raise NotImplementedError(
            "anular_registro_bot(validar_ventana=True) es responsabilidad de "
            "Fase 6 (sdd/motored-ventas-perdidas-bot, tasks 6.12/6.13) -- "
            "Fase 3 solo implementa el camino web ADMIN (validar_ventana=False)."
        )

    await _reclamar_anulacion(db, carga)

    lineas_result = await db.execute(
        select(DemandaPerdidaBotLinea).where(
            DemandaPerdidaBotLinea.carga_id == carga.id,
            DemandaPerdidaBotLinea.estado == "ACTIVA",
        )
    )
    for linea in lineas_result.scalars().all():
        await _revertir_linea(db, linea, carga.id)

    carga.log = {
        **(carga.log or {}),
        "anulado_por": actor.user_id,
        "anulado_en": datetime.utcnow().isoformat(),
    }


async def _reclamar_anulacion(db: AsyncSession, carga: "CargaArchivo") -> None:
    """Claim atómico: ver la sección homónima en el docstring de
    `anular_registro_bot`. Deja `carga.estado` sincronizado en memoria tras
    ganar el claim; levanta `CargaYaAnuladaError` si lo perdió."""
    claim = await db.execute(
        update(CargaArchivo)
        .where(CargaArchivo.id == carga.id, CargaArchivo.estado != "ANULADO")
        .values(estado="ANULADO")
        .returning(CargaArchivo.id)
    )
    if claim.scalars().first() is None:
        raise CargaYaAnuladaError(f"La carga {carga.id} ya está anulada.")
    carga.estado = "ANULADO"


async def _revertir_linea(
    db: AsyncSession, linea: DemandaPerdidaBotLinea, carga_id
) -> None:
    """Revierte, contra `demanda_perdida`, la cantidad CURRENTE que `linea`
    aportó (nunca la cantidad original si hubo una edición previa), y marca
    la línea `ANULADA`. Finding #5 (post-Phase-3 review): si no hay fila
    `demanda_perdida` correspondiente, es un estado inconsistente -- se
    loguea RUIDOSAMENTE en vez de continuar en silencio, pero no aborta el
    resto de la anulación por una sola línea huérfana."""
    demanda_result = await db.execute(
        select(DemandaPerdida).where(
            DemandaPerdida.fecha == linea.fecha,
            DemandaPerdida.sucursal_id == linea.sucursal_id,
            DemandaPerdida.referencia_id == linea.referencia_id,
            DemandaPerdida.origen == "BOT",
        )
    )
    demanda = demanda_result.scalars().first()
    if demanda is not None:
        nueva_cantidad = demanda.cantidad_solicitada - linea.cantidad
        if nueva_cantidad <= 0:
            await db.execute(delete(DemandaPerdida).where(DemandaPerdida.id == demanda.id))
        else:
            demanda.cantidad_solicitada = nueva_cantidad
    else:
        logger.error(
            "anular_registro_bot: demanda_perdida faltante para linea "
            "bot %s (carga=%s, fecha=%s, sucursal=%s, referencia=%s) -- "
            "estado inconsistente, se marca ANULADA de todos modos",
            linea.id, carga_id, linea.fecha, linea.sucursal_id, linea.referencia_id,
        )
    linea.estado = "ANULADA"
