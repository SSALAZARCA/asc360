"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, ADR-3, spec
ED-01..ED-09b, ED-16..ED-19): el servicio de edición y los bloqueos.

Con una sesión de juguete que graba el SQL literal se prueba lo que no depende
del motor de Postgres: el ORDEN de los chequeos (404, 042, estado de la
corrida, 065, 052, 053, 054, 066), el orden de los bloqueos (corrida SHARE ->
tienda SHARE -> línea UPDATE) y que un rechazo no escribe nada. Las mismas
reglas contra Postgres real corren en `pg_real/test_pedido_edicion_pg.py`.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.services.corridas import bloqueos, codigos, edicion
from app.motored.services.corridas.codigos import ErrorCorrida
from tests.motored.conftest import FakeAsyncSession
from tests.motored.fixtures import corridas_api as fx

D = Decimal
USUARIO = uuid.UUID(int=900)
CORRIDA = fx.CORRIDA_ID


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def _corrida(**campos):
    base = dict(
        id=CORRIDA, estado="BORRADOR", es_escenario=False, invalidada=False)
    return SimpleNamespace(**{**base, **campos})


def _tienda(estado_pedido="BORRADOR"):
    return SimpleNamespace(
        corrida_id=CORRIDA, sucursal_id=fx.SUC_A,
        estado_pedido=estado_pedido)


def _linea(**campos):
    return fx.linea(**{
        "id": 7, "pedido_sugerido": D("50.00"), "pedido_final": D("50.00"),
        "valor_pedido": D("23037.50"), "precio": D("460.75"),
        "unidad_empaque": 12, **campos})


FILA_TOTALES = (D("1010.00"), D("6000000.00"), D("1000.00"), D("5000000.00"))


def _sesion(*, corrida=None, linea=None, tienda=None, bloqueada=None,
            edicion_fila=None, escribe=True):
    """Cola en el orden en que `editar_linea` consulta; cada paso que
    falla corta la cola (el resto no se consulta). `escribe` agrega la
    respuesta del INSERT del historial (un no-op no lo emite)."""
    cola = [
        [corrida] if corrida is not None else [],
        [linea] if linea is not None else [],
        [tienda] if tienda is not None else [],
        [bloqueada if bloqueada is not None else linea],
    ]
    if escribe:
        cola.append([])
    cola += [[edicion_fila] if edicion_fila else [], [FILA_TOTALES]]
    return FakeAsyncSession(execute_queue=cola)


async def _editar(db, cantidad=60, esperado=None):
    return await edicion.editar_linea(
        db, CORRIDA, 7, cantidad, esperado, USUARIO)


def _feliz(**campos):
    linea = _linea()
    base = dict(corrida=_corrida(), linea=linea, tienda=_tienda())
    return _sesion(**{**base, **campos})


# --- El camino feliz y el orden de los bloqueos -----------------------------


async def test_the_locks_follow_corrida_share_tienda_share_line_update():
    db = _feliz()

    await _editar(db)

    sqls = [_sql(s) for s in db.executed_statements]
    assert "FROM corrida " in sqls[0] and sqls[0].endswith("FOR SHARE")
    assert "FROM corrida_linea" in sqls[1] and "FOR " not in sqls[1]
    assert "FROM corrida_sucursal" in sqls[2]
    assert sqls[2].endswith("FOR SHARE")
    assert "FROM corrida_linea" in sqls[3] and sqls[3].endswith("FOR UPDATE")
    assert sqls[4].startswith("INSERT INTO corrida_linea_historial")


async def test_the_edit_stores_the_value_and_recomputes_it_like_the_engine():
    db = _feliz()

    resultado = await _editar(db, 60)

    linea = resultado.linea
    assert linea.pedido_final == D("60.00")
    assert linea.valor_pedido == D("27645.00")
    assert linea.pedido_sugerido == D("50.00")
    assert resultado.totales_tienda == {
        "unidades_a_pedir": D("1010.00"), "valor_a_pedir": D("6000000.00"),
        "unidades_sugerido": D("1000.00"),
        "valor_sugerido": D("5000000.00")}


async def test_the_history_row_carries_before_after_user_and_manual_motive():
    db = _feliz()

    await _editar(db, 60)

    sql = _sql(db.executed_statements[4])
    assert "50.00" in sql and "60.00" in sql
    assert f"'{USUARIO}'" in sql and "'MANUAL'" in sql
    assert "'pedido_final'" in sql
    assert f"'{CORRIDA}'" in sql and f"'{fx.SUC_A}'" in sql


async def test_a_line_without_price_gets_value_zero_but_keeps_the_quantity():
    linea = _linea(precio=None, valor_pedido=D("0.00"))
    db = _sesion(corrida=_corrida(), linea=linea, tienda=_tienda())

    resultado = await _editar(db, 10)

    assert resultado.linea.pedido_final == D("10.00")
    assert str(resultado.linea.valor_pedido) == "0.00"


async def test_zero_is_a_valid_edit_ed_04():
    db = _feliz()

    resultado = await _editar(db, 0)

    assert resultado.linea.pedido_final == D("0.00")
    assert str(resultado.linea.valor_pedido) == "0.00"


async def test_the_same_value_is_a_no_op_with_no_history_row_ed_03():
    db = _sesion(
        corrida=_corrida(), linea=_linea(), tienda=_tienda(), escribe=False)

    resultado = await _editar(db, 50)

    sqls = [_sql(s) for s in db.executed_statements]
    assert not any(s.startswith("INSERT") for s in sqls)
    assert resultado.linea.pedido_final == D("50.00")


async def test_a_matching_esperado_is_accepted():
    db = _feliz()

    resultado = await _editar(db, 60, esperado=D("50"))

    assert resultado.linea.pedido_final == D("60.00")


async def test_the_last_edit_is_read_back_for_the_response():
    fila = (7, "Maria", fx.CREADA, "MANUAL")
    db = _feliz(edicion_fila=fila)

    resultado = await _editar(db, 60)

    assert resultado.ultima_edicion.usuario == "Maria"
    assert resultado.ultima_edicion.motivo == "MANUAL"


# --- Orden de los chequeos --------------------------------------------------


async def _error(db, cantidad=60, esperado=None):
    with pytest.raises(BaseException) as error:
        await _editar(db, cantidad, esperado)
    return error.value


def _sin_escrituras(db):
    escrituras = ("INSERT", "UPDATE")
    return not any(
        _sql(s).startswith(escrituras) for s in db.executed_statements)


async def test_an_unknown_corrida_is_a_404_after_one_query():
    db = _sesion()

    error = await _error(db)

    assert isinstance(error, LookupError)
    assert str(error) == "Corrida no encontrada."
    assert len(db.executed_statements) == 1


async def test_a_line_of_another_corrida_is_a_404_before_any_rule_ed_09():
    db = _sesion(corrida=_corrida(es_escenario=True))

    error = await _error(db)

    assert isinstance(error, LookupError)
    assert str(error) == "Línea no encontrada."
    assert len(db.executed_statements) == 2


async def test_a_scenario_is_042_and_asks_nothing_else_ed_07():
    db = _sesion(corrida=_corrida(es_escenario=True), linea=_linea())

    error = await _error(db, cantidad="abc")

    assert error.codigo == codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA
    assert "editar" in error.mensaje
    assert len(db.executed_statements) == 2 and _sin_escrituras(db)


@pytest.mark.parametrize("estado", [
    "PENDIENTE", "CALCULANDO", "FALLIDA", "ANULADA"])
async def test_a_corrida_that_is_not_calculated_is_040(estado):
    db = _sesion(corrida=_corrida(estado=estado), linea=_linea())

    error = await _error(db)

    assert error.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE
    assert estado in error.mensaje
    assert len(db.executed_statements) == 2


async def test_a_legacy_cerrada_corrida_is_still_operable():
    db = _feliz(corrida=_corrida(estado="CERRADA"))

    resultado = await _editar(db, 60)

    assert resultado.linea.pedido_final == D("60.00")


async def test_an_invalidated_corrida_is_041():
    db = _sesion(corrida=_corrida(invalidada=True), linea=_linea())

    error = await _error(db)

    assert error.codigo == codigos.E_CORRIDA_INVALIDADA


async def test_a_tienda_without_pedido_is_065():
    db = _feliz(tienda=_tienda(None))

    error = await _error(db)

    assert error.codigo == codigos.E_CORRIDA_SIN_PEDIDO
    assert len(db.executed_statements) == 3 and _sin_escrituras(db)


@pytest.mark.parametrize("estado", ["CERRADO", "ENVIADO"])
async def test_a_closed_or_sent_tienda_is_052_before_the_payload_ed_06(
        estado):
    db = _feliz(tienda=_tienda(estado))

    error = await _error(db, cantidad="abc")

    assert error.codigo == codigos.E_CORRIDA_PEDIDO_NO_BORRADOR
    assert estado in error.mensaje
    assert len(db.executed_statements) == 3 and _sin_escrituras(db)


@pytest.mark.parametrize("bruto", [-1, 2.5, "abc", None, 10_000_000])
async def test_an_invalid_quantity_is_053_and_locks_no_line_ed_05(bruto):
    db = _feliz()

    error = await _error(db, cantidad=bruto)

    assert error.codigo == codigos.E_CORRIDA_CANTIDAD_INVALIDA
    assert len(db.executed_statements) == 3 and _sin_escrituras(db)


async def test_an_excluded_line_is_054_ed_08():
    excluida = _linea(motivo_exclusion="SUSTITUIDA", pedido_final=None)
    db = _sesion(
        corrida=_corrida(), linea=excluida, tienda=_tienda(),
        bloqueada=excluida)

    error = await _error(db)

    assert error.codigo == codigos.E_CORRIDA_LINEA_EXCLUIDA
    assert "SUSTITUIDA" in error.mensaje and _sin_escrituras(db)


async def test_a_stale_esperado_is_066_and_names_the_current_value():
    db = _feliz()

    error = await _error(db, 60, esperado=D("45.00"))

    assert error.codigo == codigos.E_CORRIDA_EDICION_DESACTUALIZADA
    assert "50" in error.mensaje and _sin_escrituras(db)


async def test_esperado_is_compared_against_the_locked_line_not_the_first():
    """Dos ediciones concurrentes: la segunda lee 50, espera el bloqueo y
    recibe la fila ya cambiada a 55 por la primera."""
    cambiada = _linea(pedido_final=D("55.00"))
    db = _sesion(
        corrida=_corrida(), linea=_linea(), tienda=_tienda(),
        bloqueada=cambiada)

    error = await _error(db, 60, esperado=D("50.00"))

    assert error.codigo == codigos.E_CORRIDA_EDICION_DESACTUALIZADA


async def test_the_history_before_value_is_the_one_read_under_the_lock():
    cambiada = _linea(pedido_final=D("55.00"))
    db = _sesion(
        corrida=_corrida(), linea=_linea(), tienda=_tienda(),
        bloqueada=cambiada)

    await _editar(db, 60)

    sql = _sql(db.executed_statements[4])
    assert "55.00" in sql and "60.00" in sql


# --- bloqueos ---------------------------------------------------------------


async def test_a_shared_corrida_lock_is_for_share_and_exclusive_for_update():
    compartido = FakeAsyncSession(execute_queue=[[_corrida()]])
    exclusivo = FakeAsyncSession(execute_queue=[[_corrida()]])

    await bloqueos.bloquear_corrida(compartido, CORRIDA, exclusivo=False)
    await bloqueos.bloquear_corrida(exclusivo, CORRIDA, exclusivo=True)

    assert _sql(compartido.executed_statements[0]).endswith("FOR SHARE")
    assert _sql(exclusivo.executed_statements[0]).endswith("FOR UPDATE")


async def test_a_missing_corrida_lock_is_a_lookup_error():
    db = FakeAsyncSession(execute_queue=[[]])

    with pytest.raises(LookupError):
        await bloqueos.bloquear_corrida(db, CORRIDA, exclusivo=False)


async def test_the_tienda_lock_targets_the_corrida_sucursal_row():
    db = FakeAsyncSession(execute_queue=[[_tienda()]])

    await bloqueos.bloquear_tienda(
        db, CORRIDA, fx.SUC_A, exclusivo=True)

    sql = _sql(db.executed_statements[0])
    assert "FROM corrida_sucursal" in sql
    assert f"corrida_sucursal.corrida_id = '{CORRIDA}'" in sql
    assert f"corrida_sucursal.sucursal_id = '{fx.SUC_A}'" in sql
    assert sql.endswith("FOR UPDATE")


async def test_a_missing_tienda_row_is_a_lookup_error():
    db = FakeAsyncSession(execute_queue=[[]])

    with pytest.raises(LookupError):
        await bloqueos.bloquear_tienda(
            db, CORRIDA, fx.SUC_A, exclusivo=False)


# --- exigir_operable --------------------------------------------------------


def test_the_scenario_rule_wins_over_the_state_and_invalidation():
    corrida = _corrida(es_escenario=True, estado="ANULADA", invalidada=True)

    with pytest.raises(ErrorCorrida) as error:
        bloqueos.exigir_operable(corrida, "exportar")

    assert error.value.codigo == codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA
    assert "exportar" in error.value.mensaje


def test_the_state_rule_wins_over_invalidation():
    corrida = _corrida(estado="FALLIDA", invalidada=True)

    with pytest.raises(ErrorCorrida) as error:
        bloqueos.exigir_operable(corrida, "editar")

    assert error.value.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE


def test_a_calculated_real_valid_corrida_is_operable():
    assert bloqueos.exigir_operable(_corrida(), "editar") is None
