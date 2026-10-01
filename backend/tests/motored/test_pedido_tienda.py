"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B3a, ADR-1, spec
CI-01..CI-24, DM-01): el ciclo de vida del pedido por tienda (cerrar,
cerrar varias y reabrir) y el resumen de estados.

Con una sesión de juguete que graba el SQL literal se prueba lo que no depende
del motor de Postgres: la tabla de transiciones con sus códigos, el ORDEN de
los chequeos (404, 042, 040, 041, 065, 064), el orden de los bloqueos (cargas
SHARE -> corrida SHARE -> tiendas UPDATE por `sucursal_id`), los eventos que
se escriben y que un rechazo no escribe nada. Las mismas reglas contra
Postgres real corren en `pg_real/test_pedido_tienda_pg.py` y
`pg_real/test_pedido_concurrencia_pg.py`.
"""
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.services.corridas import codigos, pedido_tienda
from tests.motored.conftest import FakeAsyncSession
from tests.motored.fixtures import corridas_api as fx

USUARIO = uuid.UUID(int=900)
CORRIDA = fx.CORRIDA_ID
SUC_A, SUC_B = fx.SUC_A, fx.SUC_B
SUC_C = uuid.UUID(int=603)


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def _corrida(**campos):
    base = dict(
        id=CORRIDA, codigo="PED-2026-S39-001", estado="BORRADOR",
        es_escenario=False, invalidada=False)
    return SimpleNamespace(**{**base, **campos})


def _tienda(sucursal_id=SUC_A, estado_pedido="BORRADOR", estado="OK"):
    return SimpleNamespace(
        corrida_id=CORRIDA, sucursal_id=sucursal_id, estado=estado,
        estado_pedido=estado_pedido)


def _fila(sucursal_id=SUC_A, nombre="UNO", **campos):
    return (_tienda(sucursal_id, **campos), nombre)


def _sesion(*, cargas=(), corrida=None, tiendas=None, escribe=True):
    """Cola en el orden en que `cerrar_todas` consulta: las cargas, la
    corrida, las tiendas y, si escribe, la respuesta del INSERT de eventos.
    Un paso que falla corta la cola: el resto no se consulta."""
    cola = [
        [(uuid.UUID(int=i + 700), "ANULADO" if anulada else "APLICADO")
         for i, anulada in enumerate(cargas)],
        [corrida] if corrida is not None else [],
    ]
    if tiendas is not None:
        cola.append(list(tiendas))
    if escribe:
        cola.append([])
    return FakeAsyncSession(execute_queue=cola)


def _sin_escrituras(db) -> bool:
    return not any(
        _sql(s).startswith(("INSERT", "UPDATE"))
        for s in db.executed_statements)


async def _error(coro):
    with pytest.raises(BaseException) as error:
        await coro
    return error.value


async def _cerrar(db, ids=None):
    return await pedido_tienda.cerrar_todas(db, CORRIDA, USUARIO, ids)


# --- Cerrar: el camino feliz y el orden de los bloqueos ---------------------


async def test_the_locks_follow_cargas_corrida_share_tiendas_update():
    db = _sesion(corrida=_corrida(), tiendas=[_fila(SUC_A), _fila(SUC_B)])

    await _cerrar(db)

    sqls = [_sql(s) for s in db.executed_statements]
    assert "FROM carga_archivo" in sqls[0] and sqls[0].endswith(
        "FOR SHARE OF carga_archivo")
    assert "FROM corrida " in sqls[1] and sqls[1].endswith("FOR SHARE")
    assert "FROM corrida_sucursal" in sqls[2]
    assert "ORDER BY corrida_sucursal.sucursal_id" in sqls[2]
    assert sqls[2].endswith("FOR UPDATE OF corrida_sucursal")
    assert sqls[3].startswith("INSERT INTO pedido_evento")


async def test_closing_all_closes_only_the_borrador_tiendas_ci_05():
    cerrada = _fila(SUC_B, "DOS", estado_pedido="CERRADO")
    enviada = _fila(SUC_C, "TRES", estado_pedido="ENVIADO")
    abierta = _fila(SUC_A, "UNO")
    db = _sesion(corrida=_corrida(), tiendas=[abierta, cerrada, enviada])

    resultado = await _cerrar(db)

    assert resultado.cerradas == [SUC_A]
    assert resultado.ya_cerradas == 2
    assert abierta[0].estado_pedido == "CERRADO"
    assert cerrada[0].estado_pedido == "CERRADO"
    assert enviada[0].estado_pedido == "ENVIADO"
    assert resultado.corrida.codigo == "PED-2026-S39-001"


async def test_every_closed_tienda_gets_a_cerrado_event_with_who_and_when():
    db = _sesion(
        corrida=_corrida(), tiendas=[_fila(SUC_A), _fila(SUC_B, "DOS")])

    await _cerrar(db)

    sql = _sql(db.executed_statements[3])
    assert sql.count("'CERRADO'") == 2
    assert sql.count(f"'{USUARIO}'") == 2
    assert f"'{SUC_A}'" in sql and f"'{SUC_B}'" in sql
    assert f"'{CORRIDA}'" in sql


async def test_the_absent_list_loads_only_the_ok_tiendas():
    db = _sesion(corrida=_corrida(), tiendas=[_fila(SUC_A)])

    await _cerrar(db)

    consulta = _sql(db.executed_statements[2])
    assert "corrida_sucursal.estado = 'OK'" in consulta
    assert "sucursal_id IN" not in consulta


async def test_a_named_list_loads_exactly_those_tiendas_ci_06():
    a, b = _fila(SUC_A), _fila(SUC_B, "DOS")
    db = _sesion(corrida=_corrida(), tiendas=[a, b])

    resultado = await _cerrar(db, [SUC_B, SUC_A])

    consulta = _sql(db.executed_statements[2])
    assert f"'{SUC_A}'" in consulta and f"'{SUC_B}'" in consulta
    assert sorted(resultado.cerradas) == [SUC_A, SUC_B]
    assert a[0].estado_pedido == b[0].estado_pedido == "CERRADO"


async def test_a_failed_tienda_elsewhere_never_blocks_the_close_no_043():
    db = _sesion(corrida=_corrida(), tiendas=[_fila(SUC_A)])

    resultado = await pedido_tienda.cerrar_tienda(
        db, CORRIDA, SUC_A, USUARIO)

    assert resultado.estado_pedido == "CERRADO"
    assert codigos.E_CORRIDA_SUCURSAL_FALLIDA not in " ".join(
        _sql(s) for s in db.executed_statements)


async def test_a_legacy_cerrada_corrida_is_operable():
    db = _sesion(
        corrida=_corrida(estado="CERRADA"), tiendas=[_fila(SUC_A)])

    resultado = await _cerrar(db, [SUC_A])

    assert resultado.cerradas == [SUC_A]


# --- Cerrar: rechazos y su orden --------------------------------------------


async def test_an_unknown_corrida_is_a_404_after_two_queries():
    db = _sesion()

    error = await _error(_cerrar(db))

    assert isinstance(error, LookupError)
    assert len(db.executed_statements) == 2 and _sin_escrituras(db)


async def test_an_unknown_named_tienda_is_a_404():
    db = _sesion(corrida=_corrida(), tiendas=[_fila(SUC_A)])

    error = await _error(_cerrar(db, [SUC_A, SUC_B]))

    assert isinstance(error, LookupError)
    assert _sin_escrituras(db)


async def test_a_scenario_is_042_with_the_action_and_before_any_state_rule():
    db = _sesion(
        corrida=_corrida(es_escenario=True, estado="PENDIENTE"),
        tiendas=[_fila(SUC_A, estado_pedido=None)])

    error = await _error(_cerrar(db, [SUC_A]))

    assert error.codigo == codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA
    assert "cerrar" in error.mensaje and _sin_escrituras(db)


@pytest.mark.parametrize("estado", [
    "PENDIENTE", "CALCULANDO", "FALLIDA", "ANULADA"])
async def test_a_corrida_that_is_not_calculated_is_040(estado):
    db = _sesion(
        corrida=_corrida(estado=estado), tiendas=[_fila(SUC_A)])

    error = await _error(_cerrar(db, [SUC_A]))

    assert error.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE
    assert estado in error.mensaje and _sin_escrituras(db)


async def test_an_invalidated_corrida_is_041():
    db = _sesion(
        corrida=_corrida(invalidada=True), tiendas=[_fila(SUC_A)])

    error = await _error(_cerrar(db, [SUC_A]))

    assert error.codigo == codigos.E_CORRIDA_INVALIDADA
    assert _sin_escrituras(db)


async def test_a_linked_carga_that_was_annulled_is_041():
    db = _sesion(
        cargas=(False, True), corrida=_corrida(), tiendas=[_fila(SUC_A)])

    error = await _error(_cerrar(db, [SUC_A]))

    assert error.codigo == codigos.E_CORRIDA_INVALIDADA
    assert _sin_escrituras(db)


async def test_a_tienda_without_pedido_is_065_naming_it():
    db = _sesion(
        corrida=_corrida(),
        tiendas=[_fila(SUC_A, "UNO", estado_pedido=None, estado="FALLIDA")])

    error = await _error(_cerrar(db, [SUC_A]))

    assert error.codigo == codigos.E_CORRIDA_SIN_PEDIDO
    assert "UNO" in error.mensaje and _sin_escrituras(db)


@pytest.mark.parametrize("estado", ["CERRADO", "ENVIADO"])
async def test_a_tienda_that_is_not_borrador_is_064_ci_07(estado):
    db = _sesion(
        corrida=_corrida(),
        tiendas=[_fila(SUC_A, "UNO"),
                 _fila(SUC_B, "DOS", estado_pedido=estado)])

    error = await _error(_cerrar(db, [SUC_A, SUC_B]))

    assert error.codigo == codigos.E_CORRIDA_CERRAR_NO_BORRADOR
    assert "DOS" in error.mensaje and estado in error.mensaje
    assert error.detalle["sucursal_id"] == str(SUC_B)
    assert _sin_escrituras(db)


async def test_a_batch_with_nobody_in_borrador_is_064():
    db = _sesion(
        corrida=_corrida(),
        tiendas=[_fila(SUC_A, estado_pedido="CERRADO"),
                 _fila(SUC_B, estado_pedido="ENVIADO")])

    error = await _error(_cerrar(db))

    assert error.codigo == codigos.E_CORRIDA_CERRAR_NO_BORRADOR
    assert "ninguna" in error.mensaje.lower() and _sin_escrituras(db)


async def test_the_check_order_is_042_040_041_065_064():
    por_orden = [
        (_corrida(es_escenario=True, estado="ANULADA", invalidada=True),
         codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA),
        (_corrida(estado="ANULADA", invalidada=True),
         codigos.E_CORRIDA_ESTADO_NO_ADMITE),
        (_corrida(invalidada=True), codigos.E_CORRIDA_INVALIDADA),
    ]
    for corrida, esperado in por_orden:
        db = _sesion(
            corrida=corrida, tiendas=[_fila(SUC_A, estado_pedido=None)])
        assert (await _error(_cerrar(db, [SUC_A]))).codigo == esperado
    sin_pedido = _sesion(
        corrida=_corrida(), tiendas=[_fila(SUC_A, estado_pedido=None)])
    assert (await _error(_cerrar(sin_pedido, [SUC_A]))).codigo == (
        codigos.E_CORRIDA_SIN_PEDIDO)


async def test_a_single_close_returns_the_tienda_and_writes_one_event():
    db = _sesion(corrida=_corrida(), tiendas=[_fila(SUC_A)])

    tienda = await pedido_tienda.cerrar_tienda(db, CORRIDA, SUC_A, USUARIO)

    assert (tienda.sucursal_id, tienda.estado_pedido) == (SUC_A, "CERRADO")
    assert _sql(db.executed_statements[3]).count("'CERRADO'") == 1


# --- Reabrir ----------------------------------------------------------------


def _sesion_reabrir(*, corrida=None, tienda=None, numero=None):
    """corrida SHARE, tienda UPDATE, (número de la orden si está ENVIADO),
    INSERT del evento."""
    cola = [[corrida] if corrida is not None else []]
    if corrida is not None:
        cola.append([tienda] if tienda is not None else [])
    if tienda is not None:
        if tienda.estado_pedido == "ENVIADO":
            cola.append([numero])
        cola.append([])
    return FakeAsyncSession(execute_queue=cola)


async def _reabrir(db, motivo="Corrección de cantidades"):
    return await pedido_tienda.reabrir_tienda(
        db, CORRIDA, SUC_A, USUARIO, motivo)


async def test_reopening_takes_corrida_share_then_the_tienda_for_update():
    db = _sesion_reabrir(
        corrida=_corrida(), tienda=_tienda(estado_pedido="CERRADO"))

    await _reabrir(db)

    sqls = [_sql(s) for s in db.executed_statements]
    assert "FROM corrida " in sqls[0] and sqls[0].endswith("FOR SHARE")
    assert "FROM corrida_sucursal" in sqls[1]
    assert sqls[1].endswith("FOR UPDATE")
    assert sqls[2].startswith("INSERT INTO pedido_evento")


async def test_a_closed_pedido_goes_back_to_borrador_with_a_motivo_ci_15():
    tienda = _tienda(estado_pedido="CERRADO")
    db = _sesion_reabrir(corrida=_corrida(), tienda=tienda)

    resultado = await _reabrir(db, "  Corrección de cantidades  ")

    assert resultado.estado_pedido == "BORRADOR" == tienda.estado_pedido
    sql = _sql(db.executed_statements[2])
    assert "'REABIERTO'" in sql and "'Corrección de cantidades'" in sql
    assert f"'{USUARIO}'" in sql and f"'{SUC_A}'" in sql


async def test_an_invalidated_corrida_can_still_be_reopened():
    db = _sesion_reabrir(
        corrida=_corrida(invalidada=True),
        tienda=_tienda(estado_pedido="CERRADO"))

    resultado = await _reabrir(db)

    assert resultado.estado_pedido == "BORRADOR"


async def test_reopening_in_a_legacy_cerrada_corrida_works():
    db = _sesion_reabrir(
        corrida=_corrida(estado="CERRADA"),
        tienda=_tienda(estado_pedido="CERRADO"))

    assert (await _reabrir(db)).estado_pedido == "BORRADOR"


async def test_a_sent_pedido_cannot_be_reopened_and_names_the_order_ci_18():
    tienda = _tienda(estado_pedido="ENVIADO")
    db = _sesion_reabrir(
        corrida=_corrida(), tienda=tienda, numero="12345")

    error = await _error(_reabrir(db))

    assert error.codigo == codigos.E_CORRIDA_REABRIR_ENVIADO
    assert "12345" in error.mensaje
    assert tienda.estado_pedido == "ENVIADO"
    assert _sin_escrituras(db)


async def test_a_borrador_pedido_is_044():
    db = _sesion_reabrir(corrida=_corrida(), tienda=_tienda())

    error = await _error(_reabrir(db))

    assert error.codigo == codigos.E_CORRIDA_REABRIR_BORRADOR
    assert _sin_escrituras(db)


async def test_a_tienda_without_pedido_is_065_on_reopen():
    db = _sesion_reabrir(
        corrida=_corrida(), tienda=_tienda(estado_pedido=None))

    error = await _error(_reabrir(db))

    assert error.codigo == codigos.E_CORRIDA_SIN_PEDIDO


async def test_reopening_a_scenario_is_042_with_the_action_ci_20():
    db = _sesion_reabrir(
        corrida=_corrida(es_escenario=True),
        tienda=_tienda(estado_pedido=None))

    error = await _error(_reabrir(db))

    assert error.codigo == codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA
    assert "reabrir" in error.mensaje


@pytest.mark.parametrize("estado", ["PENDIENTE", "FALLIDA", "ANULADA"])
async def test_reopening_in_a_corrida_not_calculated_is_040(estado):
    db = _sesion_reabrir(
        corrida=_corrida(estado=estado),
        tienda=_tienda(estado_pedido="CERRADO"))

    error = await _error(_reabrir(db))

    assert error.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE


@pytest.mark.parametrize("motivo", [None, "", "   ", 5, "x" * 501])
async def test_a_missing_blank_or_oversized_motivo_is_046_ci_17(motivo):
    tienda = _tienda(estado_pedido="CERRADO")
    db = _sesion_reabrir(corrida=_corrida(), tienda=tienda)

    error = await _error(_reabrir(db, motivo))

    assert error.codigo == codigos.E_CORRIDA_REABRIR_MOTIVO
    assert tienda.estado_pedido == "CERRADO" and _sin_escrituras(db)


async def test_the_state_is_checked_before_the_motivo():
    db = _sesion_reabrir(corrida=_corrida(), tienda=_tienda())

    error = await _error(_reabrir(db, ""))

    assert error.codigo == codigos.E_CORRIDA_REABRIR_BORRADOR


async def test_a_motivo_of_exactly_500_characters_is_accepted():
    db = _sesion_reabrir(
        corrida=_corrida(), tienda=_tienda(estado_pedido="CERRADO"))

    assert (await _reabrir(db, "x" * 500)).estado_pedido == "BORRADOR"


async def test_reopening_an_unknown_tienda_is_a_404():
    db = _sesion_reabrir(corrida=_corrida())

    assert isinstance(await _error(_reabrir(db)), LookupError)


# --- Resumen de pedidos -----------------------------------------------------


async def test_the_summary_counts_ok_tiendas_by_pedido_state():
    otra = uuid.UUID(int=501)
    db = FakeAsyncSession(execute_queue=[[
        (CORRIDA, "BORRADOR", 34), (CORRIDA, "CERRADO", 10),
        (CORRIDA, "ENVIADO", 3), (otra, None, 2)]])

    resumen = await pedido_tienda.resumen_pedidos(db, [CORRIDA, otra])

    assert resumen[CORRIDA] == {
        "total": 47, "borrador": 34, "cerrados": 10, "enviados": 3}
    assert resumen[otra] == {
        "total": 2, "borrador": 0, "cerrados": 0, "enviados": 0}
    consulta = _sql(db.executed_statements[0])
    assert "corrida_sucursal.estado = 'OK'" in consulta
    assert "GROUP BY corrida_sucursal.corrida_id" in consulta


async def test_a_corrida_with_no_tiendas_is_not_in_the_summary():
    db = FakeAsyncSession(execute_queue=[[]])

    assert await pedido_tienda.resumen_pedidos(db, [CORRIDA]) == {}


async def test_the_summary_asks_nothing_for_an_empty_page():
    db = FakeAsyncSession(execute_queue=[])

    assert await pedido_tienda.resumen_pedidos(db, []) == {}
    assert db.executed_statements == []


async def test_a_scoped_summary_counts_only_the_visible_tiendas():
    db = FakeAsyncSession(execute_queue=[[(CORRIDA, "BORRADOR", 1)]])

    await pedido_tienda.resumen_pedidos(
        db, [CORRIDA], alcance=frozenset({SUC_A}))

    assert f"corrida_sucursal.sucursal_id IN ('{SUC_A}')" in _sql(
        db.executed_statements[0])
