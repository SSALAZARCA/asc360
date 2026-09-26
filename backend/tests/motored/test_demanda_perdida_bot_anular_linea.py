"""Phase 3 (sdd/motored-ventas-perdidas-panel, tasks 3.1/3.2; design D4) —
unit coverage for `services/demanda_perdida_bot.py::anular_linea_bot`, the
LINE-level anular used by the future ADMIN panel (Phase 4/5, not built yet).

Unlike `anular_registro_bot` (which claims the whole `carga_archivo` header
and cancels every ACTIVA line under it), this function claims exactly ONE
`demanda_perdida_bot_linea` row -- the panel lets an ADMIN anular a single
line without touching its siblings or the parent header's `estado`.

Claim mechanism (design D4, mirrors `_reclamar_anulacion`'s own convention
for "claim exactly one row, race-safe"): a single atomic
`UPDATE ... WHERE id=:id AND estado='ACTIVA' ... RETURNING id`. The row lock
implicit in that atomic conditional UPDATE is what makes two concurrent
calls against the SAME line serialize -- the loser's claim matches 0 rows
and raises `LineaYaAnuladaError` before touching anything else. This is the
SAME idiom `_reclamar_anulacion` uses for the header claim, just scoped to
one line's `id`+`estado` instead of the header's `estado`.

`anular_linea_bot` never re-implements the reversal math: it calls the
EXISTING `_revertir_linea(db, linea, carga_id)` (used by `anular_registro_
bot` since the Phase 6 fix-up) and returns exactly what that function
returns -- `True` if a matching `demanda_perdida` aggregate row existed and
was reversed, `False` if it was already missing (an inconsistent-but-
logged state, still marked ANULADA). Per design D4, this bool is what the
future panel endpoint will surface to the client as `agregado_consistente`.

No `validar_ventana`/ownership parameter exists on purpose (proposal
decision #4): an ADMIN can anular ANY line regardless of date or original
advisor -- the caller (Phase 5's endpoint, not built yet) enforces
ADMIN-only access at the API layer, matching how `aplicar_delta_demanda_
perdida` is already actor-agnostic.

Same `FakeAsyncSession`/`AdditiveDemandaPerdidaFakeSession` convention as
`test_demanda_perdida_bot_anular.py`.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.services.auth import MotoredUser
from app.motored.services.demanda_perdida_bot import (
    LineaYaAnuladaError,
    anular_linea_bot,
)
from tests.motored.conftest import AdditiveDemandaPerdidaFakeSession, FakeAsyncSession

CARGA_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()


def _linea(cantidad, estado="ACTIVA") -> DemandaPerdidaBotLinea:
    return DemandaPerdidaBotLinea(
        id=uuid.uuid4(), carga_id=CARGA_ID, usuario_id=uuid.uuid4(),
        fecha=date(2026, 9, 24), sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        cantidad=Decimal(cantidad), estado=estado,
    )


def _clave(linea: DemandaPerdidaBotLinea) -> tuple:
    return (linea.fecha, linea.sucursal_id, linea.referencia_id, "BOT")


def _admin() -> MotoredUser:
    return MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN")


async def test_successful_anulacion_reverses_aggregate_and_stamps_audit_columns():
    linea = _linea(cantidad=4)
    actor = _admin()
    db = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[[linea.id]],  # claim atomico -- UPDATE ... RETURNING id
        filas_iniciales={_clave(linea): Decimal(10)},
    )

    resultado = await anular_linea_bot(db, linea, actor)

    assert resultado is True
    assert linea.estado == "ANULADA"
    assert linea.anulado_por == uuid.UUID(actor.user_id)
    assert linea.anulado_en is not None
    assert linea.anulado_en.tzinfo is not None
    assert db.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id,
    ) == Decimal(6)


async def test_already_anulada_line_raises_error_and_performs_no_reversal():
    linea = _linea(cantidad=4, estado="ANULADA")
    actor = _admin()
    db = FakeAsyncSession(execute_queue=[[]])  # claim atomico -- 0 filas, ya anulada

    with pytest.raises(LineaYaAnuladaError):
        await anular_linea_bot(db, linea, actor)

    # The lost claim happens BEFORE any reversal is attempted -- exactly
    # one execute() call, nothing touched `demanda_perdida`.
    assert len(db.executed_statements) == 1
    assert linea.estado == "ANULADA"
    assert linea.anulado_por is None
    assert linea.anulado_en is None


async def test_claim_is_atomic_conditional_update_matching_module_convention():
    """Mirrors `_reclamar_anulacion`'s own claim idiom: a single
    `UPDATE ... WHERE id=:id AND estado='ACTIVA' ... RETURNING id`, never a
    `SELECT ... FOR UPDATE` followed by a separate write -- proven via
    compiled-SQL introspection, the same style already used in this module
    for `test_lineas_activas_select_locks_rows_with_for_update`."""
    linea = _linea(cantidad=4)
    actor = _admin()
    db = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[[linea.id]],
        filas_iniciales={_clave(linea): Decimal(10)},
    )

    await anular_linea_bot(db, linea, actor)

    claim_stmt = db.executed_statements[0]
    compiled = str(claim_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "demanda_perdida_bot_linea" in compiled
    assert "ACTIVA" in compiled
    assert "ANULADA" in compiled
    assert "RETURNING" in compiled.upper()
    assert linea.id.hex in compiled.replace("-", "")


async def test_concurrent_second_call_loses_claim_and_does_not_double_reverse():
    """Race-safety proof (mirrors `test_demanda_perdida_bot_anular.py::
    test_concurrent_anular_second_call_gets_carga_ya_anulada_and_does_not_
    double_reverse`'s pattern at the header level): two concurrent panel
    ADMINs anulando la MISMA línea. The first transaction wins the claim
    and reverses; the second transaction's own claim re-evaluates
    `WHERE estado='ACTIVA'` against the now-committed row and matches 0
    rows, raising `LineaYaAnuladaError` before touching `demanda_perdida`
    a second time."""
    linea = _linea(cantidad=4)
    actor = _admin()

    db1 = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[[linea.id]],
        filas_iniciales={_clave(linea): Decimal(10)},
    )
    resultado1 = await anular_linea_bot(db1, linea, actor)

    assert resultado1 is True
    assert linea.estado == "ANULADA"
    assert db1.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id,
    ) == Decimal(6)

    db2 = FakeAsyncSession(execute_queue=[[]])  # UPDATE ... RETURNING id -- 0 filas
    with pytest.raises(LineaYaAnuladaError):
        await anular_linea_bot(db2, linea, actor)

    assert len(db2.executed_statements) == 1
    assert db1.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id,
    ) == Decimal(6)


async def test_returns_false_when_matching_aggregate_row_is_missing():
    """Adapted from `test_missing_demanda_row_still_marks_line_anulada_
    without_crashing`: `filas_iniciales` is left empty on purpose -- the
    atomic `UPDATE` inside `_ejecutar_delta_negativo` matches 0 rows for
    this line's key, exactly like a real Postgres `UPDATE` against a
    missing row. `anular_linea_bot` surfaces that as `False` (per design
    D4, the future panel endpoint's `agregado_consistente`), while still
    marking the line ANULADA and stamping the audit columns."""
    linea = _linea(cantidad=2)
    actor = _admin()
    db = AdditiveDemandaPerdidaFakeSession(execute_queue=[[linea.id]])

    resultado = await anular_linea_bot(db, linea, actor)

    assert resultado is False
    assert linea.estado == "ANULADA"
    assert linea.anulado_por == uuid.UUID(actor.user_id)
    assert linea.anulado_en is not None
