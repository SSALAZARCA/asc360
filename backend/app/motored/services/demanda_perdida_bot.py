"""
Motored Pedidos — bot "Lore" write path (sdd/motored-ventas-perdidas-bot,
design D3/D4).

**Scope note**: this module was created in Phase 3 ("Backend bugfixes") to
satisfy task 3.7/3.8's PATCH/anular BOT guards -- the web ADMIN
`POST /cargas/{id}/anular` endpoint delegates to `anular_registro_bot(db,
carga, actor, validar_ventana=False)` for a BOT-origin row (design D4).
Phase 6 ("Demanda perdida — bot write path") adds the REST of this module:
`construir_upsert_aditivo` (D3's additive upsert), `aplicar_delta_
demanda_perdida` (the dispatcher used by the bot's own register/edit
endpoints), and the `validar_ventana=True` branch of `anular_registro_bot`
(the bot's own `POST .../{carga_id}/anular` endpoint, enforcing the
actor-owns-it + today-only 409 rules Phase 3 explicitly deferred).

**Interpretation flagged (load-bearing, not guessed silently)**: design D4
literally describes the bot's own "today" checks (`GET .../hoy`, this
anular branch, `PATCH .../lineas/{id}`) as comparing against
`carga_archivo.periodo_desde`. That column is NEVER populated for a
BOT-origin `carga_archivo` row -- `api/cargas.py::listar_cargas`'s own
Phase-3 docstring states this as a PERMANENT invariant ("un header BOT
NUNCA declara período... un registro puntual del asesor no es un archivo
con período"), not a temporary gap. Setting `periodo_desde`/`periodo_hasta`
here to make the design's literal SQL work would silently regress that
already-shipped invariant. Instead, this module (and `api/bot_demanda_
perdida.py`'s `/demanda-perdida/hoy` and `/demanda-perdida/{carga_id}/
anular` endpoints -- split out of `api/bot.py` in the Phase 6 fix-up)
use `demanda_perdida_bot_linea.fecha` as the "today" source of truth --
the ledger is already documented (Phase 1 model docstring) as the
authoritative record of a registration's contribution, and every line
written by ONE registration event shares the same `fecha` (computed once,
via `hoy_bogota()`, when the registration is created -- see
`api/bot_demanda_perdida.py::registrar_demanda_perdida`).

Phase 6 fix-up (post-Phase-6 4-lens review, finding #1, BLOCKER): the
`validar_ventana=False` branch's per-line reversal (`_revertir_linea`)
originally used a simpler ORM-level read-then-mutate-then-commit shape
(`SELECT` -> Python subtraction -> ORM assignment/DELETE) -- consistent
with how the rest of `api/cargas.py` mutates `CargaArchivo` rows, but
UNSAFE here: this function is shared by BOTH the web-ADMIN anular path
(low concurrency) and the bot's own self-anular endpoint (genuinely
concurrent -- different advisors/edits can race on the SAME `(fecha,
sucursal_id, referencia_id, origen='BOT')` key). A `PATCH .../lineas/{id}`
edit (which correctly used the atomic `_ejecutar_delta_negativo` for a
negative delta) and a concurrent `_revertir_linea` reversal could both read
the same pre-commit value, and the reversal's Python-computed subtraction
would silently overwrite the edit's already-committed decrement -- a lost
update with no error, no log. `_revertir_linea` now delegates to
`_ejecutar_delta_negativo` (the SAME atomic `UPDATE col = col - :monto` /
conditional `DELETE` primitive `PATCH .../lineas/{id}` already used for a
negative delta) instead of duplicating the SELECT-then-mutate shape --
never a second reversal mechanism. The "log loudly if no matching
`demanda_perdida` row" behavior (finding #5, Phase 3 review) is preserved
by checking the atomic `UPDATE`'s rowcount (0 rows affected = no matching
row) instead of a prior `SELECT`.

Phase 6 reuses `_revertir_linea` for `validar_ventana=True` too (task
6.13): the only NEW behavior for that branch is the actor-owns-it +
today-only pre-check (`_validar_ventana_propia`), run BEFORE the shared
atomic claim.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.services.reloj import hoy_bogota

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids import cycles
    from app.motored.services.auth import MotoredUser
    from app.motored.deps_bot import BotActor

logger = logging.getLogger("motored.demanda_perdida_bot")

_CLAVE_DEMANDA_PERDIDA = ("fecha", "sucursal_id", "referencia_id", "origen")


class CargaYaAnuladaError(Exception):
    """La carga ya estaba `ANULADO` en el momento del claim atómico (ver
    docstring de `anular_registro_bot`, sección "Claim atómico"). Mismo
    criterio que `orquestador.EstadoInvalidoParaAplicarError`: una excepción
    de dominio propia del servicio, traducida a `HTTPException(409)` en la
    capa de API (`api/cargas.py::anular_carga`), nunca levantada acá
    directamente -- este módulo no depende de FastAPI."""


class CargaNoPerteneceAlActorError(Exception):
    """`validar_ventana=True`: la carga no existe, no es `origen='BOT'`, o
    `subido_por` no coincide con el actor que pide anularla -- SIEMPRE se
    traduce a 404 (nunca 403), para no revelar la existencia de la
    registración de otro asesor. Excepción de dominio propia, nunca
    levantada directamente contra el cliente."""


class FueraDeVentanaError(Exception):
    """`validar_ventana=True`: la fecha de la registración (tomada del
    ledger `demanda_perdida_bot_linea`, ver docstring del módulo) no es la
    de hoy (Bogotá) -- se traduce a 409 `{"code": "FUERA_DE_VENTANA"}`."""


async def anular_registro_bot(
    db: AsyncSession,
    carga: "CargaArchivo",
    actor: "MotoredUser | BotActor",
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
        await _validar_ventana_propia(db, carga, actor)

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
        "anulado_por": _actor_identificador(actor),
        "anulado_en": datetime.utcnow().isoformat(),
    }


def _actor_identificador(actor: "MotoredUser | BotActor") -> str:
    """`MotoredUser` (web JWT, `validar_ventana=False`) expone `.user_id`;
    `BotActor` (bot Lore, `validar_ventana=True`, Fase 6) expone
    `.usuario_id` -- unifica el accesor para que este módulo sirva a ambos
    callers sin depender del tipo concreto (evita un import real de
    `deps_bot.py` acá, que a su vez importa `deps.py`; `TYPE_CHECKING` alcanza
    porque solo se usa como anotación)."""
    valor = getattr(actor, "usuario_id", None)
    return valor if valor is not None else actor.user_id


async def _validar_ventana_propia(
    db: AsyncSession, carga: "CargaArchivo", actor: "MotoredUser | BotActor"
) -> None:
    """`validar_ventana=True` (Fase 6, tasks 6.12/6.13) -- exige, ANTES del
    claim atómico compartido: (1) que la carga sea `origen='BOT'` y que
    `subido_por` coincida con el actor que pide anularla (si no,
    `CargaNoPerteneceAlActorError` -> 404, nunca 403 -- ver docstring de la
    excepción); (2) que la fecha de la registración sea la de hoy (Bogotá).

    La fecha se toma del ledger (`demanda_perdida_bot_linea.fecha`), NUNCA
    de `carga_archivo.periodo_desde` -- ver el docstring del módulo,
    sección "Interpretation flagged": esa columna nunca se puebla para una
    fila BOT, por diseño ya shippeado (Fase 3, `api/cargas.py::
    listar_cargas`). Cualquier línea del ledger sirve -- todas las líneas
    de UNA registración comparten la misma `fecha` (se computa una sola vez
    en `api/bot_demanda_perdida.py::registrar_demanda_perdida`)."""
    actor_id = _actor_identificador(actor)
    if (
        carga.origen != "BOT"
        or carga.subido_por is None
        or str(carga.subido_por) != str(actor_id)
    ):
        raise CargaNoPerteneceAlActorError(
            f"La carga {carga.id} no existe o no pertenece al actor {actor_id}."
        )

    fecha_result = await db.execute(
        select(DemandaPerdidaBotLinea.fecha)
        .where(DemandaPerdidaBotLinea.carga_id == carga.id)
        .limit(1)
    )
    fecha_registro = fecha_result.scalars().first()
    if fecha_registro is None or fecha_registro != hoy_bogota():
        raise FueraDeVentanaError(
            f"La carga {carga.id} no es de hoy (Bogotá) -- fuera de ventana de autocorrección."
        )


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
    la línea `ANULADA`.

    Post-Phase-6-review fix (finding #1, BLOCKER): delega en
    `_ejecutar_delta_negativo` -- el MISMO `UPDATE ... SET cantidad_
    solicitada = cantidad_solicitada - :monto` / `DELETE` condicional
    atómico que `PATCH .../lineas/{id}` ya usa para un delta negativo --
    en vez de un `SELECT` + resta en Python + mutación ORM/DELETE (ver el
    docstring del módulo, sección "Phase 6 fix-up"). Nunca una segunda
    implementación de la reversa.

    Finding #5 (post-Phase-3 review): si no hay fila `demanda_perdida`
    correspondiente, es un estado inconsistente -- se loguea RUIDOSAMENTE en
    vez de continuar en silencio, pero no aborta el resto de la anulación
    por una sola línea huérfana. Detectado ahora vía el `rowcount` del
    `UPDATE` atómico (0 filas afectadas = no había fila para esa clave),
    nunca vía un `SELECT` previo."""
    rowcount = await _ejecutar_delta_negativo(
        db,
        fecha=linea.fecha,
        sucursal_id=linea.sucursal_id,
        referencia_id=linea.referencia_id,
        delta=-linea.cantidad,
    )
    if rowcount == 0:
        logger.error(
            "anular_registro_bot: demanda_perdida faltante para linea "
            "bot %s (carga=%s, fecha=%s, sucursal=%s, referencia=%s) -- "
            "estado inconsistente, se marca ANULADA de todos modos",
            linea.id, carga_id, linea.fecha, linea.sucursal_id, linea.referencia_id,
        )
    linea.estado = "ANULADA"


def construir_upsert_aditivo(
    *,
    fecha,
    sucursal_id: uuid.UUID,
    referencia_id: uuid.UUID,
    delta: Decimal,
    carga_id: uuid.UUID,
):
    """Design D3, tasks 6.1/6.2 -- el upsert ADITIVO de una fila BOT de
    `demanda_perdida`: `INSERT ... ON CONFLICT (fecha, sucursal_id,
    referencia_id, origen) DO UPDATE SET cantidad_solicitada =
    demanda_perdida.cantidad_solicitada + excluded.cantidad_solicitada`.

    Mismo primitivo Postgres (`pg_insert().on_conflict_do_update`) que
    `services/ingesta/demanda_perdida.py::construir_statement_upsert` ya
    usa para el camino EXCEL -- la ÚNICA diferencia real es el SET
    expression: EXCEL reemplaza (`= excluded.cantidad_solicitada`), esto
    SUMA (`= cantidad_solicitada + excluded.cantidad_solicitada`). Es
    atómico bajo concurrencia porque Postgres resuelve el conflicto y
    aplica el SET dentro de UN solo statement -- dos registraciones BOT
    concurrentes para la MISMA clave nunca pueden perder la escritura de la
    otra (a diferencia de un SELECT + `python: cantidad += delta` +
    `UPDATE`, que sí podría).

    `delta` DEBE ser positivo -- un delta negativo (una edición hacia abajo
    o una anulación) NUNCA debe pasar por acá: insertaría una fila BOT
    inicial con `cantidad_solicitada` negativa si todavía no existe,
    violando `ck_demanda_perdida_bot_linea_cantidad_positiva`'s análoga
    (implícita) para `demanda_perdida` -- para eso existe
    `_ejecutar_delta_negativo` (tasks 6.3/6.4), nunca este upsert. Usar
    `aplicar_delta_demanda_perdida` como despachador único en vez de llamar
    a esta función directamente desde un caller que no controle el signo."""
    if delta <= 0:
        raise ValueError(
            "construir_upsert_aditivo solo acepta delta > 0 -- usar "
            "aplicar_delta_demanda_perdida (o _ejecutar_delta_negativo) para un delta <= 0."
        )
    stmt = pg_insert(DemandaPerdida).values(
        id=uuid.uuid4(),
        fecha=fecha,
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
        cantidad_solicitada=delta,
        carga_id=carga_id,
        origen="BOT",
    )
    return stmt.on_conflict_do_update(
        index_elements=list(_CLAVE_DEMANDA_PERDIDA),
        set_={
            "cantidad_solicitada": DemandaPerdida.cantidad_solicitada
            + stmt.excluded.cantidad_solicitada,
            "carga_id": stmt.excluded.carga_id,
        },
    )


async def _ejecutar_delta_negativo(
    db: AsyncSession,
    *,
    fecha,
    sucursal_id: uuid.UUID,
    referencia_id: uuid.UUID,
    delta: Decimal,
) -> int:
    """Design D3, tasks 6.3/6.4 -- NUNCA pasa por el upsert (que podría
    insertar una fila BOT nueva con cantidad negativa si todavía no existe
    ninguna para esta clave, p.ej. dos anulaciones/ediciones concurrentes
    fuera de orden). En su lugar: `UPDATE demanda_perdida SET
    cantidad_solicitada = cantidad_solicitada + :delta WHERE key AND
    origen='BOT'`, después `DELETE ... WHERE key AND origen='BOT' AND
    cantidad_solicitada <= 0`. `col = col + x` es atómico bajo los locks de
    fila de Postgres -- nunca un SELECT + mutación en Python + UPDATE.

    Devuelve el `rowcount` del `UPDATE` (post-Phase-6-review fix, finding
    #1): 0 filas afectadas significa que no existía ninguna fila
    `demanda_perdida` para esa clave -- el caller (`_revertir_linea`) usa
    esto para loguear el mismo caso "estado inconsistente" que antes
    detectaba con un `SELECT` previo, sin volver a introducir uno."""
    if delta >= 0:
        raise ValueError(
            "_ejecutar_delta_negativo solo acepta delta < 0 -- usar "
            "construir_upsert_aditivo (vía aplicar_delta_demanda_perdida) para un delta > 0."
        )
    filtro = (
        DemandaPerdida.fecha == fecha,
        DemandaPerdida.sucursal_id == sucursal_id,
        DemandaPerdida.referencia_id == referencia_id,
        DemandaPerdida.origen == "BOT",
    )
    resultado = await db.execute(
        update(DemandaPerdida).where(*filtro).values(
            cantidad_solicitada=DemandaPerdida.cantidad_solicitada + delta
        )
    )
    await db.execute(
        delete(DemandaPerdida).where(*filtro, DemandaPerdida.cantidad_solicitada <= 0)
    )
    return resultado.rowcount


async def aplicar_delta_demanda_perdida(
    db: AsyncSession,
    *,
    fecha,
    sucursal_id: uuid.UUID,
    referencia_id: uuid.UUID,
    delta: Decimal,
    carga_id: Optional[uuid.UUID] = None,
) -> None:
    """Despachador único (Fase 6) para toda escritura ADITIVA de una fila
    BOT de `demanda_perdida`, usado tanto por el registro inicial (Fase 6,
    `POST /bot/demanda-perdida`, siempre `delta > 0`) como por la edición de
    cantidad (`PATCH /bot/demanda-perdida/lineas/{id}`, `delta` puede ser
    positivo, negativo o cero): `delta > 0` -> `construir_upsert_aditivo`
    (requiere `carga_id`); `delta < 0` -> `_ejecutar_delta_negativo`;
    `delta == 0` -> no-op (una edición que deja la cantidad igual no debe
    tocar `demanda_perdida` en absoluto)."""
    if delta == 0:
        return
    if delta > 0:
        if carga_id is None:
            raise ValueError("aplicar_delta_demanda_perdida requiere carga_id cuando delta > 0.")
        stmt = construir_upsert_aditivo(
            fecha=fecha,
            sucursal_id=sucursal_id,
            referencia_id=referencia_id,
            delta=delta,
            carga_id=carga_id,
        )
        await db.execute(stmt)
    else:
        await _ejecutar_delta_negativo(
            db, fecha=fecha, sucursal_id=sucursal_id, referencia_id=referencia_id, delta=delta
        )
