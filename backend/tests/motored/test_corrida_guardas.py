"""
Motored Pedidos F3 "Motor", S6a (sdd/motored-pedidos-motor, ADR-11) y Fase 4
B3b (sdd/motored-pedidos-ui, ADR-5, spec DM-09..DM-12, CI-37..CI-40): gancho
de la guarda de anulación de cargas y regla de anulación de la corrida.

`aplicar_guard_anulacion(db, carga)` es lo que F2 llama al anular una carga
EXCEL: bloquea la fila de la carga, rechaza si algún pedido de tienda
CERRADO o ENVIADO de las corridas que la usaron (o una corrida que F3 dejó
CERRADA) depende de ella (E-CARGA-050, nombrando tienda y corrida) e
invalida las corridas vivas que la usaron. Sin corridas, no hace nada
(regresión de F2). `exigir_sin_pedidos_cerrados` es la regla de anular una
corrida (E-CORRIDA-051).
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


async def test_a_legacy_cerrada_corrida_blocks_the_annulment_and_names_it():
    """Una corrida que F3 dejó CERRADA sigue bloqueando aunque no tenga
    ninguna tienda cerrada (no hay tienda que nombrar)."""
    db = FakeAsyncSession(execute_queue=[
        [CARGA.id], [("PED-2026-S39-002", None, None)]])

    with pytest.raises(gu.ErrorCorrida) as error:
        await gu.aplicar_guard_anulacion(db, CARGA)

    assert error.value.codigo == codigos.E_CARGA_ANULACION_BLOQUEADA
    assert "PED-2026-S39-002" in error.value.mensaje
    assert error.value.detalle == {
        "corrida": "PED-2026-S39-002", "tienda": None,
        "estado_pedido": None}


@pytest.mark.parametrize("estado,palabra", [
    ("CERRADO", "cerrado"), ("ENVIADO", "enviado")])
async def test_a_closed_or_sent_tienda_blocks_and_names_tienda_and_corrida(
        estado, palabra):
    db = FakeAsyncSession(execute_queue=[
        [CARGA.id], [("PED-2026-S39-002", "Manizales", estado)]])

    with pytest.raises(gu.ErrorCorrida) as error:
        await gu.aplicar_guard_anulacion(db, CARGA)

    assert error.value.codigo == codigos.E_CARGA_ANULACION_BLOQUEADA
    assert error.value.mensaje == (
        f"La carga la usa el pedido {palabra} de Manizales (corrida "
        "PED-2026-S39-002) y no se puede anular.")
    assert error.value.detalle == {
        "corrida": "PED-2026-S39-002", "tienda": "Manizales",
        "estado_pedido": estado}


async def test_a_blocked_annulment_invalidates_nothing():
    db = FakeAsyncSession(execute_queue=[
        [CARGA.id], [("PED-2026-S39-002", "Manizales", "CERRADO")]])

    with pytest.raises(gu.ErrorCorrida):
        await gu.aplicar_guard_anulacion(db, CARGA)

    assert len(db.executed_statements) == 2


async def test_the_blocker_lookup_joins_the_corrida_to_its_cargas():
    db = FakeAsyncSession(execute_queue=[[CARGA.id], [], []])

    await gu.aplicar_guard_anulacion(db, CARGA)

    busqueda = db.executed_statements[1].compile(
        dialect=postgresql.dialect())
    assert "corrida_carga" in str(busqueda)
    assert "CERRADA" in busqueda.params.values()


async def test_the_blocker_lookup_reads_closed_and_sent_tiendas_dm_09_dm_10():
    db = FakeAsyncSession(execute_queue=[[CARGA.id], [], []])

    await gu.aplicar_guard_anulacion(db, CARGA)

    texto = _sql(db.executed_statements[1])
    assert "corrida_sucursal" in texto
    assert "estado_pedido IN" in texto
    parametros = db.executed_statements[1].compile(
        dialect=postgresql.dialect()).params.values()
    assert ["CERRADO", "ENVIADO"] in parametros
    assert "ORDER BY corrida.codigo, sucursal.nombre" in texto
    assert "LIMIT" in texto


async def test_a_carga_with_no_closed_tienda_is_still_invalidating_dm_11():
    """Todas las tiendas en BORRADOR (por ejemplo tras reabrir la última
    cerrada): la guarda no bloquea y la corrida queda invalidada."""
    db = FakeAsyncSession(execute_queue=[
        [CARGA.id], [], ["PED-2026-S39-001"]])

    invalidadas = await gu.aplicar_guard_anulacion(db, CARGA)

    assert invalidadas == ["PED-2026-S39-001"]


# --- Anular la corrida: E-CORRIDA-051 ----------------------------------------


async def test_a_corrida_with_closed_or_sent_tiendas_cannot_be_annulled():
    db = FakeAsyncSession(execute_queue=[
        [("Manizales", "CERRADO"), ("Pereira", "ENVIADO")]])

    with pytest.raises(gu.ErrorCorrida) as error:
        await gu.exigir_sin_pedidos_cerrados(db, uuid.UUID(int=5))

    assert error.value.codigo == codigos.E_CORRIDA_ANULAR_CON_PEDIDOS
    assert "Manizales (CERRADO)" in error.value.mensaje
    assert "Pereira (ENVIADO)" in error.value.mensaje
    assert error.value.detalle == {"tiendas": [
        {"tienda": "Manizales", "estado_pedido": "CERRADO"},
        {"tienda": "Pereira", "estado_pedido": "ENVIADO"}]}


async def test_the_annulment_rule_reads_only_closed_and_sent_tiendas():
    db = FakeAsyncSession(execute_queue=[[]])

    await gu.exigir_sin_pedidos_cerrados(db, uuid.UUID(int=5))

    consulta = db.executed_statements[0].compile(
        dialect=postgresql.dialect())
    assert "corrida_sucursal" in str(consulta)
    assert ["CERRADO", "ENVIADO"] in consulta.params.values()
    assert "ORDER BY sucursal.nombre" in str(consulta)


async def test_a_long_list_of_tiendas_is_abbreviated_in_the_message():
    filas = [(f"Tienda {n:02d}", "CERRADO") for n in range(12)]
    db = FakeAsyncSession(execute_queue=[filas])

    with pytest.raises(gu.ErrorCorrida) as error:
        await gu.exigir_sin_pedidos_cerrados(db, uuid.UUID(int=5))

    assert "Tienda 00 (CERRADO)" in error.value.mensaje
    assert "Tienda 11" not in error.value.mensaje
    assert "y 7 más" in error.value.mensaje
    assert len(error.value.detalle["tiendas"]) == 12


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
