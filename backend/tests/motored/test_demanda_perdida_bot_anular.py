"""
Phase 3 "Backend bugfixes" (sdd/motored-ventas-perdidas-bot, tasks 3.7/3.8;
design D4) — unit coverage for `services/demanda_perdida_bot.py::
anular_registro_bot`, the web-ADMIN-only (`validar_ventana=False`) reversal
path that `api/cargas.py::anular_carga` delegates to for a BOT-origin row.

Phase 6 (tasks 6.12/6.13) extends this coverage below (see the "Phase 6"
section) for `validar_ventana=True` -- the bot's own `/anular` endpoint,
with its propio-actor/mismo-día 409 rules. The `validar_ventana=False`
tests above are UNCHANGED (design/task 6.13 explicitly requires not
regressing them while extending this function).

Phase 6 fix-up (review finding #1, BLOCKER): `_revertir_linea` no longer
does a `SELECT` + Python subtraction + ORM mutate/delete against
`demanda_perdida` (an unlocked read-modify-write race with `PATCH .../
lineas/{id}`'s atomic `_ejecutar_delta_negativo`) -- it now delegates to
that SAME atomic `UPDATE ... SET col = col - :monto` / conditional `DELETE`
primitive. Because there is no more ORM-tracked `DemandaPerdida` row for
these tests to mutate directly, every test that exercises a REAL reversal
outcome (partial/full/orphan) now drives `AdditiveDemandaPerdidaFakeSession`
(`tests/motored/conftest.py`) instead of asserting against a hand-built
`DemandaPerdida` object -- same behavior proven (partial reversal stays
positive, full reversal deletes, orphan case logs a warning), different
(now real, not hollow) mechanism.

Same `FakeAsyncSession` convention as the rest of `tests/motored/`.
"""
import logging
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.services.auth import MotoredUser
from app.motored.services.demanda_perdida_bot import (
    CargaNoPerteneceAlActorError,
    CargaYaAnuladaError,
    FueraDeVentanaError,
    anular_registro_bot,
)
from app.motored.services.reloj import hoy_bogota
from tests.motored.conftest import AdditiveDemandaPerdidaFakeSession, FakeAsyncSession

SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID_1 = uuid.uuid4()
REFERENCIA_ID_2 = uuid.uuid4()


def _carga_bot(**overrides) -> CargaArchivo:
    base = dict(
        id=uuid.uuid4(), tipo="DEMANDA_PERDIDA", origen="BOT", estado="APLICADO",
        nombre_archivo=None, hash_sha256=None, ruta_objeto=None, bytes=None,
        filas_leidas=0, filas_validas=0, filas_rechazadas=0,
        lotes_staged=0, ultimo_lote_aplicado=0, log=None,
        subido_por=uuid.uuid4(),
    )
    base.update(overrides)
    return CargaArchivo(**base)


def _linea(
    carga_id, referencia_id, cantidad, estado="ACTIVA", usuario_id=None, fecha=None
) -> DemandaPerdidaBotLinea:
    return DemandaPerdidaBotLinea(
        id=uuid.uuid4(), carga_id=carga_id, usuario_id=usuario_id or uuid.uuid4(),
        fecha=fecha or date(2026, 9, 24), sucursal_id=SUCURSAL_ID, referencia_id=referencia_id,
        cantidad=Decimal(cantidad), estado=estado,
    )


def _clave(linea: DemandaPerdidaBotLinea) -> tuple:
    return (linea.fecha, linea.sucursal_id, linea.referencia_id, "BOT")


class _BotActor:
    """Minimal stand-in for `deps_bot.BotActor` -- only `usuario_id` is
    read by `_actor_identificador`/`_validar_ventana_propia`."""

    def __init__(self, usuario_id: str):
        self.usuario_id = usuario_id


# ---------------------------------------------------------------------------
# Phase 6 (tasks 6.12/6.13) — `validar_ventana=True`: the bot's own
# `/anular` endpoint. Actor-owns-it + today-only pre-checks, run BEFORE the
# SAME atomic claim/reversal shared with `validar_ventana=False` above.
# ---------------------------------------------------------------------------


async def test_validar_ventana_true_success_reuses_shared_claim_and_reversal():
    actor_id = str(uuid.uuid4())
    carga = _carga_bot(subido_por=uuid.UUID(actor_id))
    linea = _linea(carga.id, REFERENCIA_ID_1, cantidad=4, fecha=hoy_bogota())
    actor = _BotActor(actor_id)

    db = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[
            [hoy_bogota()],  # _validar_ventana_propia: fecha de la primer linea del ledger
            [carga.id],  # claim atómico -- UPDATE ... RETURNING id
            [linea],  # select de líneas ACTIVA
        ],
        filas_iniciales={_clave(linea): Decimal(10)},
    )

    await anular_registro_bot(db, carga, actor, validar_ventana=True)

    assert linea.estado == "ANULADA"
    assert carga.estado == "ANULADO"
    assert db.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id
    ) == Decimal(6)
    assert carga.log["anulado_por"] == actor_id


async def test_validar_ventana_true_other_actor_gets_carga_no_pertenece_al_actor():
    carga = _carga_bot(subido_por=uuid.uuid4())
    actor = _BotActor(str(uuid.uuid4()))
    db = FakeAsyncSession(execute_queue=[])

    with pytest.raises(CargaNoPerteneceAlActorError):
        await anular_registro_bot(db, carga, actor, validar_ventana=True)

    # Ownership fails before any query is issued -- no leak of existence
    # via timing/behavior beyond the immediate exception.
    assert db.executed_statements == []


async def test_validar_ventana_true_excel_origin_gets_carga_no_pertenece_al_actor():
    """A BOT actor can never own an EXCEL-origin carga_archivo row (only
    ADMIN/COMPRAS can create those) -- but defense-in-depth still rejects an
    arbitrary carga_id that happens to have a matching `subido_por` UUID by
    pure coincidence, rather than trusting `subido_por` alone."""
    actor_id = str(uuid.uuid4())
    carga = _carga_bot(origen="EXCEL", subido_por=uuid.UUID(actor_id))
    actor = _BotActor(actor_id)
    db = FakeAsyncSession(execute_queue=[])

    with pytest.raises(CargaNoPerteneceAlActorError):
        await anular_registro_bot(db, carga, actor, validar_ventana=True)


async def test_validar_ventana_true_stale_date_gets_fuera_de_ventana():
    actor_id = str(uuid.uuid4())
    carga = _carga_bot(subido_por=uuid.UUID(actor_id))
    fecha_ayer = date(2020, 1, 1)
    linea = _linea(carga.id, REFERENCIA_ID_1, cantidad=4, fecha=fecha_ayer)
    actor = _BotActor(actor_id)
    db = FakeAsyncSession(execute_queue=[[fecha_ayer]])

    with pytest.raises(FueraDeVentanaError):
        await anular_registro_bot(db, carga, actor, validar_ventana=True)

    # The date check fails BEFORE the atomic claim -- carga.estado is
    # untouched, no reversal was attempted.
    assert carga.estado == "APLICADO"
    assert len(db.executed_statements) == 1


async def test_validar_ventana_true_no_ledger_line_gets_fuera_de_ventana():
    """Defensive: a carga_id with no ledger line at all (should be
    unreachable in practice -- every registration writes at least one line)
    must not crash; it fails closed as FUERA_DE_VENTANA rather than
    proceeding with an unknown date."""
    actor_id = str(uuid.uuid4())
    carga = _carga_bot(subido_por=uuid.UUID(actor_id))
    actor = _BotActor(actor_id)
    db = FakeAsyncSession(execute_queue=[[]])

    with pytest.raises(FueraDeVentanaError):
        await anular_registro_bot(db, carga, actor, validar_ventana=True)


async def test_validar_ventana_true_already_anulada_gets_carga_ya_anulada():
    """The already-ANULADO race is still the SAME shared atomic claim as
    `validar_ventana=False` -- ownership/date pass, but the claim itself
    finds 0 rows affected."""
    actor_id = str(uuid.uuid4())
    carga = _carga_bot(subido_por=uuid.UUID(actor_id), estado="ANULADO")
    linea = _linea(carga.id, REFERENCIA_ID_1, cantidad=4, fecha=hoy_bogota())
    actor = _BotActor(actor_id)
    db = FakeAsyncSession(
        execute_queue=[
            [hoy_bogota()],  # _validar_ventana_propia passes
            [],  # claim atómico -- 0 filas, ya está ANULADO
        ]
    )

    with pytest.raises(CargaYaAnuladaError):
        await anular_registro_bot(db, carga, actor, validar_ventana=True)


async def test_reverses_partial_line_and_deletes_fully_reversed_line_marks_anulado():
    """Two ACTIVA lines: one partial reversal (demanda stays positive,
    updated in place) and one full reversal (demanda hits <= 0, deleted).
    Both lines end ANULADA; the header ends ANULADO with a log."""
    carga = _carga_bot()
    linea_parcial = _linea(carga.id, REFERENCIA_ID_1, cantidad=3)
    linea_total = _linea(carga.id, REFERENCIA_ID_2, cantidad=5)
    actor = MotoredUser(user_id="actor-1", role="ADMIN")

    db = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[
            [carga.id],  # UPDATE ... WHERE estado != 'ANULADO' RETURNING id -- claim succeeds
            [linea_parcial, linea_total],  # select ACTIVA lines for this carga
        ],
        filas_iniciales={
            _clave(linea_parcial): Decimal(10),  # 10 - 3 = 7, stays
            _clave(linea_total): Decimal(5),  # 5 - 5 = 0, deleted
        },
    )

    await anular_registro_bot(db, carga, actor, validar_ventana=False)

    assert db.cantidad_actual(
        fecha=linea_parcial.fecha, sucursal_id=linea_parcial.sucursal_id,
        referencia_id=linea_parcial.referencia_id,
    ) == Decimal(7)
    assert db.cantidad_actual(
        fecha=linea_total.fecha, sucursal_id=linea_total.sucursal_id,
        referencia_id=linea_total.referencia_id,
    ) is None
    assert linea_parcial.estado == "ANULADA"
    assert linea_total.estado == "ANULADA"
    assert carga.estado == "ANULADO"
    assert carga.log["anulado_por"] == "actor-1"
    assert "anulado_en" in carga.log


async def test_no_active_lines_still_marks_header_anulado():
    carga = _carga_bot()
    actor = MotoredUser(user_id="actor-2", role="ADMIN")
    db = FakeAsyncSession(execute_queue=[[carga.id], []])

    await anular_registro_bot(db, carga, actor, validar_ventana=False)

    assert carga.estado == "ANULADO"
    assert carga.log["anulado_por"] == "actor-2"


async def test_missing_demanda_row_still_marks_line_anulada_without_crashing():
    """Defensive: if the `demanda_perdida` row was already removed by some
    other path, the reversal must not crash -- the line still gets marked
    ANULADA and the header still gets ANULADO. `filas_iniciales` is left
    empty on purpose: the atomic `UPDATE` for this line's key matches 0
    rows, exactly like a real Postgres `UPDATE` against a missing row."""
    carga = _carga_bot()
    linea = _linea(carga.id, REFERENCIA_ID_1, cantidad=2)
    actor = MotoredUser(user_id="actor-3", role="ADMIN")
    db = AdditiveDemandaPerdidaFakeSession(execute_queue=[[carga.id], [linea]])

    await anular_registro_bot(db, carga, actor, validar_ventana=False)

    assert linea.estado == "ANULADA"
    assert carga.estado == "ANULADO"


async def test_missing_demanda_row_logs_inconsistent_state_error(caplog):
    """Review finding #5 (post-Phase-3): a ledger line `ACTIVA` with no
    matching `demanda_perdida` counterpart is a data-integrity failure (the
    ledger says a reversal happened, but nothing was actually reversed) --
    it must be logged loudly, not silently masked. Post-Phase-6-fix-up
    (finding #1): "no matching row" is now detected via the atomic
    `UPDATE`'s rowcount (0 rows affected), never a prior `SELECT`."""
    carga = _carga_bot()
    linea = _linea(carga.id, REFERENCIA_ID_1, cantidad=2)
    actor = MotoredUser(user_id="actor-4", role="ADMIN")
    db = AdditiveDemandaPerdidaFakeSession(execute_queue=[[carga.id], [linea]])

    with caplog.at_level(logging.ERROR, logger="motored.demanda_perdida_bot"):
        await anular_registro_bot(db, carga, actor, validar_ventana=False)

    assert any(
        record.levelno == logging.ERROR and str(linea.id) in record.getMessage()
        for record in caplog.records
    )


async def test_concurrent_anular_second_call_gets_carga_ya_anulada_and_does_not_double_reverse():
    """Review finding #2 (post-Phase-3): closes the unlocked read-modify-
    write race. Two concurrent web-ADMIN `POST .../anular` calls (double
    click, client retry) against the SAME BOT `carga_id` could both read
    `carga.estado == 'APLICADO'` and both read the same ACTIVA ledger lines
    before either commits, double-reversing the same `demanda_perdida.
    cantidad_solicitada`.

    Simulated here (no real concurrency needed) by driving
    `anular_registro_bot` twice sequentially against two SEPARATE
    `FakeAsyncSession`s, each representing one transaction's own view of
    the row: the second transaction's atomic conditional `UPDATE ... WHERE
    estado != 'ANULADO'` finds 0 rows affected (the first transaction
    already won the claim), so it must raise `CargaYaAnuladaError` and
    reverse NOTHING -- `demanda_perdida.cantidad_solicitada` must be
    reversed exactly once, not twice."""
    carga = _carga_bot()
    linea = _linea(carga.id, REFERENCIA_ID_1, cantidad=4)
    actor = MotoredUser(user_id="actor-1", role="ADMIN")

    # First transaction: wins the atomic claim, reverses the line partially
    # (10 - 4 = 6, stays positive -- an atomic UPDATE, no delete call).
    db1 = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[
            [carga.id],  # UPDATE ... RETURNING id -- claim succeeds
            [linea],  # select ACTIVA lines
        ],
        filas_iniciales={_clave(linea): Decimal(10)},
    )
    await anular_registro_bot(db1, carga, actor, validar_ventana=False)

    assert linea.estado == "ANULADA"
    assert carga.estado == "ANULADO"
    assert db1.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id
    ) == Decimal(6)

    # Second transaction: read the SAME carga before the first one
    # committed -- its own claim finds 0 rows affected (already ANULADO).
    db2 = FakeAsyncSession(execute_queue=[[]])  # UPDATE ... RETURNING id -- 0 rows

    with pytest.raises(CargaYaAnuladaError):
        await anular_registro_bot(db2, carga, actor, validar_ventana=False)

    # No second execute() call was ever issued -- the ledger SELECT was
    # never reached, proving the race is closed BEFORE any reversal logic
    # runs.
    assert len(db2.executed_statements) == 1
    # The reversal happened exactly once (in the first call, on db1) --
    # not twice: db2 never touched demanda_perdida at all.
    assert db1.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id
    ) == Decimal(6)
