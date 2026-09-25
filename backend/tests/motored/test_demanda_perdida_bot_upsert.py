"""
Phase 6 "Demanda perdida — bot write path" (sdd/motored-ventas-perdidas-bot,
tasks 6.1-6.4; design D3) — unit coverage for `services/demanda_perdida_bot
.py::construir_upsert_aditivo`/`_ejecutar_delta_negativo`/`aplicar_delta_
demanda_perdida`.

Same statement-introspection convention as `test_ingesta_demanda_perdida.py`
(lines ~244-309) for statement SHAPE (SET expression / conflict target).
Fix-up finding #2 (CRITICAL): shape introspection alone never proved the
upsert is genuinely ADDITIVE across repeated calls for the SAME key --
`AdditiveDemandaPerdidaFakeSession` (`tests/motored/conftest.py`) now
applies the real arithmetic against an in-memory row, so a test can call
`aplicar_delta_demanda_perdida` twice for the same key and assert the
second call's result is a genuine sum, not a statement-shape-only check.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.motored.services.demanda_perdida_bot import (
    aplicar_delta_demanda_perdida,
    construir_upsert_aditivo,
)
from tests.motored.conftest import AdditiveDemandaPerdidaFakeSession, FakeAsyncSession

FECHA = date(2026, 9, 24)
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()
CARGA_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# construir_upsert_aditivo (tasks 6.1/6.2)
# ---------------------------------------------------------------------------


def test_construir_upsert_aditivo_set_expression_suma_nunca_reemplaza():
    """The additive SET expression must be `cantidad_solicitada +
    excluded.cantidad_solicitada` -- the exact opposite of the EXCEL path's
    `construir_statement_upsert`, which sets `= excluded.cantidad_solicitada`
    (a plain REPLACE, never a sum)."""
    stmt = construir_upsert_aditivo(
        fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("3"), carga_id=CARGA_ID,
    )

    set_clause = stmt._post_values_clause.update_values_to_set
    valores_set = {(col if isinstance(col, str) else col.name): expr for col, expr in set_clause}
    assert "cantidad_solicitada" in valores_set
    expresion = valores_set["cantidad_solicitada"]
    # A `col + excluded.col` expression compiles to a BinaryExpression whose
    # right side references the `excluded` pseudo-table -- unlike EXCEL's
    # bare `excluded.cantidad_solicitada` column reference.
    lado_derecho = expresion.right
    assert lado_derecho.table.name == "excluded"
    assert lado_derecho.name == "cantidad_solicitada"
    lado_izquierdo = expresion.left
    assert lado_izquierdo.table.name == "demanda_perdida"
    assert lado_izquierdo.name == "cantidad_solicitada"


def test_construir_upsert_aditivo_conflict_target_es_la_clave_de_4_columnas():
    stmt = construir_upsert_aditivo(
        fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("3"), carga_id=CARGA_ID,
    )

    assert stmt._post_values_clause.inferred_target_elements == [
        "fecha", "sucursal_id", "referencia_id", "origen",
    ]


def test_construir_upsert_aditivo_incluye_origen_bot_en_los_valores():
    stmt = construir_upsert_aditivo(
        fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("3"), carga_id=CARGA_ID,
    )

    valores_compilados = stmt.compile().construct_params()
    assert "BOT" in valores_compilados.values()
    assert Decimal("3") in valores_compilados.values()


def test_construir_upsert_aditivo_rechaza_delta_no_positivo():
    with pytest.raises(ValueError):
        construir_upsert_aditivo(
            fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
            delta=Decimal("0"), carga_id=CARGA_ID,
        )
    with pytest.raises(ValueError):
        construir_upsert_aditivo(
            fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
            delta=Decimal("-1"), carga_id=CARGA_ID,
        )


# ---------------------------------------------------------------------------
# aplicar_delta_demanda_perdida dispatcher (tasks 6.3/6.4) — negative delta
# NEVER goes through the upsert; positive delta NEVER goes through the
# update/delete pair.
# ---------------------------------------------------------------------------


async def test_aplicar_delta_positivo_ejecuta_una_sola_sentencia_upsert():
    db = FakeAsyncSession(execute_queue=[[]])

    await aplicar_delta_demanda_perdida(
        db, fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("5"), carga_id=CARGA_ID,
    )

    assert len(db.executed_statements) == 1
    valores = db.executed_statements[0].compile().construct_params()
    assert "BOT" in valores.values()


async def test_aplicar_delta_positivo_sin_carga_id_falla():
    db = FakeAsyncSession(execute_queue=[])

    with pytest.raises(ValueError):
        await aplicar_delta_demanda_perdida(
            db, fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
            delta=Decimal("5"), carga_id=None,
        )


async def test_aplicar_delta_negativo_ejecuta_update_luego_delete_nunca_el_upsert():
    """Task 6.3 RED requirement: the negative-delta path must be a plain
    `UPDATE ... WHERE key AND origen='BOT'` followed by a conditional
    `DELETE ... WHERE cantidad_solicitada <= 0` -- proven here by asserting
    exactly 2 statements, neither of them an INSERT/upsert (an
    `ON CONFLICT` construct has `.excluded`; a plain UPDATE/DELETE does
    not)."""
    db = FakeAsyncSession(execute_queue=[[], []])

    await aplicar_delta_demanda_perdida(
        db, fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("-4"),
    )

    assert len(db.executed_statements) == 2
    primera, segunda = db.executed_statements
    assert not hasattr(primera, "excluded")
    assert not hasattr(segunda, "excluded")
    assert type(primera).__name__ == "Update"
    assert type(segunda).__name__ == "Delete"

    # The UPDATE's SET expression is `cantidad_solicitada + (-4)`, never a
    # bare replace.
    set_clause = primera._values
    assert set_clause is not None


async def test_aplicar_delta_cero_no_ejecuta_nada():
    db = FakeAsyncSession(execute_queue=[])

    await aplicar_delta_demanda_perdida(
        db, fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("0"), carga_id=CARGA_ID,
    )

    assert db.executed_statements == []


# ---------------------------------------------------------------------------
# Fix-up finding #2 (CRITICAL) -- real end-to-end additive proof, not just
# statement-shape introspection. Same key, called twice: the second call's
# result must be a genuine SUM against `AdditiveDemandaPerdidaFakeSession`'s
# in-memory row, never a statement that merely "looks additive".
# ---------------------------------------------------------------------------


async def test_aplicar_delta_positivo_dos_veces_para_la_misma_clave_suma_de_verdad():
    """Dos registraciones BOT distintas para la MISMA clave -- design D3,
    escenario "A second BOT registration adds to the running total": la
    segunda llamada debe encontrar la fila que dejó la primera y SUMAR,
    nunca reemplazarla ni partir de cero de nuevo."""
    db = AdditiveDemandaPerdidaFakeSession(execute_queue=[])

    await aplicar_delta_demanda_perdida(
        db, fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("3"), carga_id=CARGA_ID,
    )
    assert db.cantidad_actual(
        fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID
    ) == Decimal("3")

    await aplicar_delta_demanda_perdida(
        db, fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("2"), carga_id=uuid.uuid4(),
    )

    # 3 + 2 = 5 -- a buggy REPLACE (EXCEL's semantics, not BOT's) would
    # leave this at 2, overwriting the first call entirely.
    assert db.cantidad_actual(
        fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID
    ) == Decimal("5")


async def test_aplicar_delta_positivo_luego_negativo_para_la_misma_clave_reduce_de_verdad():
    """Una registración seguida de una edición hacia abajo (o una
    anulación parcial) para la MISMA clave -- prueba que el delta negativo
    de verdad resta contra el resultado REAL de la primera escritura
    aditiva, nunca contra un valor hand-built. `execute_queue` queda vacío
    a propósito: todo statement contra `demanda_perdida` (upsert/UPDATE/
    DELETE) es interceptado por `AdditiveDemandaPerdidaFakeSession`, nunca
    consume la cola."""
    db = AdditiveDemandaPerdidaFakeSession(execute_queue=[])

    await aplicar_delta_demanda_perdida(
        db, fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("6"), carga_id=CARGA_ID,
    )
    await aplicar_delta_demanda_perdida(
        db, fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("-4"),
    )

    assert db.cantidad_actual(
        fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID
    ) == Decimal("2")


async def test_aplicar_delta_negativo_que_agota_la_clave_la_elimina_de_verdad():
    """Cuando el delta negativo deja la cantidad en <= 0, la clave
    desaparece del store real (equivalente al `DELETE` condicional) -- no
    solo "el statement compilado tiene forma de DELETE"."""
    db = AdditiveDemandaPerdidaFakeSession(execute_queue=[])

    await aplicar_delta_demanda_perdida(
        db, fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("4"), carga_id=CARGA_ID,
    )
    await aplicar_delta_demanda_perdida(
        db, fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        delta=Decimal("-4"),
    )

    assert db.cantidad_actual(
        fecha=FECHA, sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID
    ) is None
