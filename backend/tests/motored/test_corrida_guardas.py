"""
Motored Pedidos F3 "Motor", S6a (sdd/motored-pedidos-motor, ADR-11): gancho
de la guarda de anulación de cargas.

`aplicar_guard_anulacion(db, carga)` es lo que F2 llamará al anular una carga
EXCEL (el cableado en `api/cargas.py` es de S7): bloquea la fila de la carga,
rechaza si una corrida CERRADA la usó (E-CARGA-050, con el código de la
corrida) e invalida las corridas vivas que la usaron. Sin corridas, no hace
nada (regresión de F2).
"""
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.services.corridas import codigos
from app.motored.services.corridas import guardas as gu
from tests.motored.conftest import FakeAsyncSession

CARGA = SimpleNamespace(id=uuid.UUID(int=77))


def _sql(sentencia) -> str:
    return str(sentencia.compile(dialect=postgresql.dialect()))


async def test_an_unused_carga_is_left_alone():
    db = FakeAsyncSession(execute_queue=[[CARGA.id], [], []])

    invalidadas = await gu.aplicar_guard_anulacion(db, CARGA)

    assert invalidadas == []
    assert len(db.executed_statements) == 3


async def test_the_carga_row_is_locked_first_to_wait_for_a_closing_corrida():
    db = FakeAsyncSession(execute_queue=[[CARGA.id], [], []])

    await gu.aplicar_guard_anulacion(db, CARGA)

    bloqueo = _sql(db.executed_statements[0])
    assert "FROM carga_archivo" in bloqueo and "FOR UPDATE" in bloqueo


async def test_a_closed_corrida_blocks_the_annulment_and_names_itself():
    db = FakeAsyncSession(execute_queue=[[CARGA.id], ["PED-2026-S39-002"]])

    with pytest.raises(gu.ErrorCorrida) as error:
        await gu.aplicar_guard_anulacion(db, CARGA)

    assert error.value.codigo == codigos.E_CARGA_ANULACION_BLOQUEADA
    assert "PED-2026-S39-002" in error.value.mensaje


async def test_a_blocked_annulment_invalidates_nothing():
    db = FakeAsyncSession(execute_queue=[[CARGA.id], ["PED-2026-S39-002"]])

    with pytest.raises(gu.ErrorCorrida):
        await gu.aplicar_guard_anulacion(db, CARGA)

    assert len(db.executed_statements) == 2


async def test_the_closed_lookup_joins_the_corrida_to_its_cargas():
    db = FakeAsyncSession(execute_queue=[[CARGA.id], [], []])

    await gu.aplicar_guard_anulacion(db, CARGA)

    busqueda = db.executed_statements[1].compile(
        dialect=postgresql.dialect())
    assert "corrida_carga" in str(busqueda)
    assert "CERRADA" in busqueda.params.values()


async def test_live_corridas_are_invalidated_and_their_codes_returned():
    db = FakeAsyncSession(execute_queue=[
        [CARGA.id], [], ["PED-2026-S39-001", "ESC-2026-S39-001"]])

    invalidadas = await gu.aplicar_guard_anulacion(db, CARGA)

    assert invalidadas == ["PED-2026-S39-001", "ESC-2026-S39-001"]


async def test_the_invalidation_records_the_carga_and_the_reason():
    db = FakeAsyncSession(
        execute_queue=[[CARGA.id], [], ["PED-2026-S39-001"]])

    await gu.aplicar_guard_anulacion(db, CARGA)

    actualizacion = db.executed_statements[2].compile(
        dialect=postgresql.dialect())
    assert actualizacion.params["invalidada"] is True
    assert actualizacion.params["motivo_invalidacion"] == {
        "tipo": "CARGA_ANULADA", "carga_id": str(CARGA.id)}


async def test_only_the_live_states_are_invalidated():
    db = FakeAsyncSession(execute_queue=[[CARGA.id], [], []])

    await gu.aplicar_guard_anulacion(db, CARGA)

    actualizacion = db.executed_statements[2].compile(
        dialect=postgresql.dialect())
    estados = [
        valor for clave, valor in actualizacion.params.items()
        if isinstance(valor, list)]
    assert "corrida_carga" in str(actualizacion)
    assert sorted(estados[0]) == [
        "BORRADOR", "CALCULANDO", "FALLIDA", "PENDIENTE"]
