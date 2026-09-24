"""
Phase 3 "Backend bugfixes" (sdd/motored-ventas-perdidas-bot, tasks 3.7/3.8;
design D4) — unit coverage for `services/demanda_perdida_bot.py::
anular_registro_bot`, the web-ADMIN-only (`validar_ventana=False`) reversal
path that `api/cargas.py::anular_carga` delegates to for a BOT-origin row.

`validar_ventana=True` (the bot's own `/anular` endpoint, with its
propio-actor/mismo-día 409 rules) is explicitly OUT of scope here -- it is
Phase 6's job (tasks 6.12/6.13); this module raises `NotImplementedError`
for that branch on purpose (see the module's own docstring).

Same `FakeAsyncSession` convention as the rest of `tests/motored/`.
"""
import logging
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.services.auth import MotoredUser
from app.motored.services.demanda_perdida_bot import CargaYaAnuladaError, anular_registro_bot
from tests.motored.conftest import FakeAsyncSession

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


def _linea(carga_id, referencia_id, cantidad, estado="ACTIVA", usuario_id=None) -> DemandaPerdidaBotLinea:
    return DemandaPerdidaBotLinea(
        id=uuid.uuid4(), carga_id=carga_id, usuario_id=usuario_id or uuid.uuid4(),
        fecha=date(2026, 9, 24), sucursal_id=SUCURSAL_ID, referencia_id=referencia_id,
        cantidad=Decimal(cantidad), estado=estado,
    )


def _demanda(referencia_id, cantidad) -> DemandaPerdida:
    return DemandaPerdida(
        id=uuid.uuid4(), fecha=date(2026, 9, 24), sucursal_id=SUCURSAL_ID,
        referencia_id=referencia_id, cantidad_solicitada=Decimal(cantidad),
        origen="BOT", carga_id=uuid.uuid4(),
    )


async def test_validar_ventana_true_is_not_implemented_yet():
    """Explicitly Phase 6's job (tasks 6.12/6.13) -- Fase 3 only implements
    the web-ADMIN path."""
    carga = _carga_bot()
    actor = MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN")
    db = FakeAsyncSession(execute_queue=[])

    with pytest.raises(NotImplementedError):
        await anular_registro_bot(db, carga, actor, validar_ventana=True)


async def test_reverses_partial_line_and_deletes_fully_reversed_line_marks_anulado():
    """Two ACTIVA lines: one partial reversal (demanda stays positive,
    updated in place) and one full reversal (demanda hits <= 0, deleted).
    Both lines end ANULADA; the header ends ANULADO with a log."""
    carga = _carga_bot()
    linea_parcial = _linea(carga.id, REFERENCIA_ID_1, cantidad=3)
    linea_total = _linea(carga.id, REFERENCIA_ID_2, cantidad=5)
    demanda_parcial = _demanda(REFERENCIA_ID_1, cantidad=10)  # 10 - 3 = 7, stays
    demanda_total = _demanda(REFERENCIA_ID_2, cantidad=5)  # 5 - 5 = 0, deleted
    actor = MotoredUser(user_id="actor-1", role="ADMIN")

    db = FakeAsyncSession(
        execute_queue=[
            [carga.id],  # UPDATE ... WHERE estado != 'ANULADO' RETURNING id -- claim succeeds
            [linea_parcial, linea_total],  # select ACTIVA lines for this carga
            [demanda_parcial],  # select demanda_perdida for linea_parcial's key
            [demanda_total],  # select demanda_perdida for linea_total's key
            [],  # delete(DemandaPerdida) for the fully-reversed row
        ]
    )

    await anular_registro_bot(db, carga, actor, validar_ventana=False)

    assert demanda_parcial.cantidad_solicitada == Decimal(7)
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
    ANULADA and the header still gets ANULADO."""
    carga = _carga_bot()
    linea = _linea(carga.id, REFERENCIA_ID_1, cantidad=2)
    actor = MotoredUser(user_id="actor-3", role="ADMIN")
    db = FakeAsyncSession(execute_queue=[[carga.id], [linea], []])

    await anular_registro_bot(db, carga, actor, validar_ventana=False)

    assert linea.estado == "ANULADA"
    assert carga.estado == "ANULADO"


async def test_missing_demanda_row_logs_inconsistent_state_error(caplog):
    """Review finding #5 (post-Phase-3): a ledger line `ACTIVA` with no
    matching `demanda_perdida` counterpart is a data-integrity failure (the
    ledger says a reversal happened, but nothing was actually reversed) --
    it must be logged loudly, not silently masked by the bare `if demanda
    is not None` branch."""
    carga = _carga_bot()
    linea = _linea(carga.id, REFERENCIA_ID_1, cantidad=2)
    actor = MotoredUser(user_id="actor-4", role="ADMIN")
    db = FakeAsyncSession(execute_queue=[[carga.id], [linea], []])

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
    demanda = _demanda(REFERENCIA_ID_1, cantidad=10)
    actor = MotoredUser(user_id="actor-1", role="ADMIN")

    # First transaction: wins the atomic claim, reverses the line partially
    # (10 - 4 = 6, stays positive -- updated in place, no delete call).
    db1 = FakeAsyncSession(
        execute_queue=[
            [carga.id],  # UPDATE ... RETURNING id -- claim succeeds
            [linea],  # select ACTIVA lines
            [demanda],  # select demanda_perdida for this line's key
        ]
    )
    await anular_registro_bot(db1, carga, actor, validar_ventana=False)

    assert linea.estado == "ANULADA"
    assert carga.estado == "ANULADO"
    assert demanda.cantidad_solicitada == Decimal(6)

    # Second transaction: read the SAME carga before the first one
    # committed -- its own claim finds 0 rows affected (already ANULADO).
    db2 = FakeAsyncSession(execute_queue=[[]])  # UPDATE ... RETURNING id -- 0 rows

    with pytest.raises(CargaYaAnuladaError):
        await anular_registro_bot(db2, carga, actor, validar_ventana=False)

    # No second execute() call was ever issued -- the ledger SELECT was
    # never reached, proving the race is closed BEFORE any reversal logic
    # runs.
    assert len(db2.executed_statements) == 1
    # The reversal happened exactly once (in the first call) -- not twice.
    assert demanda.cantidad_solicitada == Decimal(6)
