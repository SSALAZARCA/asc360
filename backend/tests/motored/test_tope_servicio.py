"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B5b, ADR-6, decisiones
F4-7 y F4-12, spec TP-08..TP-14b y TP-24..TP-33): ver y aplicar el recorte
al tope de presupuesto de UNA tienda (`services/corridas/tope.py`).

Con la sesión de juguete (`FakeAsyncSession`, que graba el SQL y la lista de
parámetros de un executemany) se prueba lo que no depende de Postgres: el
ORDEN de los chequeos (404, 042/040/041, 065, 061, 058, 059, 060), el orden
de los bloqueos (corrida SHARE -> tienda UPDATE -> líneas UPDATE por id), lo
que se escribe (cada línea recortada y su fila de historial con el tope) y
que un rechazo no escribe nada. La lectura (`previsualizar`) no toma ningún
bloqueo ni escribe. Las mismas reglas contra Postgres real, y la
concurrencia, corren en `pg_real/test_tope_pg.py` y
`pg_real/test_pedido_concurrencia_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros, parametros_topes
from app.motored.services.corridas import codigos, recorte, tope
from tests.motored.conftest import FakeAsyncSession
from tests.motored.fixtures import corridas_api as fx

CORRIDA = fx.CORRIDA_ID
SUC, OTRA = fx.SUC_A, fx.SUC_B
USUARIO = uuid.UUID(int=900)
HOY = datetime.date(2026, 10, 1)
PARAM_ID = uuid.UUID(int=77)
D = Decimal


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def _corrida(**campos):
    base = dict(
        id=CORRIDA, codigo="PED-2026-S39-001", estado="BORRADOR",
        es_escenario=False, invalidada=False)
    return SimpleNamespace(**{**base, **campos})


def _tienda(estado_pedido="BORRADOR", sucursal_id=SUC):
    return SimpleNamespace(
        corrida_id=CORRIDA, sucursal_id=sucursal_id, estado="OK",
        estado_pedido=estado_pedido)


def _param(clave, valor, sucursal_id=None, fila_id=None):
    return ParametroMetodologia(
        id=fila_id or uuid.uuid4(), clave=clave, valor=valor,
        vigente_desde=datetime.date(2026, 9, 28), sucursal_id=sucursal_id)


MODO_ON = _param("modo_tope_presupuesto", True)
MODO_OFF = _param("modo_tope_presupuesto", False)


def _tope(valor="9000", sucursal_id=SUC):
    return _param(
        "presupuesto_maximo_pedido", valor, sucursal_id, fila_id=PARAM_ID)


def _fila(linea_id, codigo, clase, pedido, *, empaque=10, precio="100.00",
          y="0.00", n="10.000000", nombre="PARTE"):
    """Una línea de la tienda como la devuelve la consulta del recorte."""
    return SimpleNamespace(
        id=linea_id, codigo_referencia=codigo, nombre_parte=nombre,
        clase_abc=clase, pedido_final=D(pedido), unidad_empaque=empaque,
        precio=None if precio is None else D(precio),
        inventario_final=None if y is None else D(y),
        demanda_ponderada=None if n is None else D(n))


# Valor total 11.000 con precio 100. Con tope 9.000 el exceso es 2.000: se
# corta la C-1 (50 -> 30), la que conserva más cobertura, y no se toca A ni B.
LINEAS = [
    _fila(1, "C-1", "C", "50.00"),
    _fila(2, "C-2", "C", "30.00"),
    _fila(3, "B-1", "B", "20.00"),
    _fila(4, "A-1", "A", "10.00"),
]
TOTALES = [(D("1010"), D("90000"), D("1100"), D("110000"))]


def _cola_lectura(*, corrida=None, tienda=None, params=(MODO_ON, _tope()),
                  lineas=LINEAS):
    return [
        [corrida or _corrida()], [tienda or _tienda()], list(params),
        list(lineas)]


def _sesion_aplicar(**campos):
    """La cola en el orden en que `aplicar` consulta: corrida, tienda,
    parámetros, líneas, el UPDATE, el INSERT y los totales."""
    return FakeAsyncSession(
        execute_queue=_cola_lectura(**campos) + [[], [], TOTALES])


def _sesion_ver(**campos):
    return FakeAsyncSession(execute_queue=_cola_lectura(**campos))


async def _error(coro):
    with pytest.raises(BaseException) as error:
        await coro
    return error.value


async def _ver(db=None, **campos):
    db = db or _sesion_ver(**campos)
    return await tope.previsualizar(db, CORRIDA, SUC, hoy=HOY)


async def _aplicar(db, token, usuario=USUARIO):
    return await tope.aplicar(db, CORRIDA, SUC, token, usuario, hoy=HOY)


async def _token_vigente(**campos):
    return (await _ver(**campos))["token"]


def _sin_escrituras(db) -> bool:
    return not any(
        _sql(s).startswith(("INSERT", "UPDATE"))
        for s in db.executed_statements)


# --- El token: puro ---------------------------------------------------------


def _recorte(linea_id=1, actual=50, propuesto=30):
    return recorte.Recorte(
        linea_id, f"C-{linea_id}", "C", Fraction(actual),
        Fraction(propuesto), Fraction(actual - propuesto) * 100)


def test_the_token_is_a_sha256_hex_and_stable_for_equal_cuts():
    cortes = (_recorte(1), _recorte(2, 30, 20))

    uno = tope.token_de(SUC, Fraction(9000), cortes)
    otro = tope.token_de(SUC, Fraction(9000), tuple(reversed(cortes)))

    assert uno == otro
    assert len(uno) == 64 and set(uno) <= set("0123456789abcdef")


@pytest.mark.parametrize("sucursal,limite,cortes", [
    (OTRA, 9000, (_recorte(1),)),
    (SUC, 9001, (_recorte(1),)),
    (SUC, 9000, (_recorte(1, 50, 20),)),
    (SUC, 9000, (_recorte(1, 60, 30),)),
    (SUC, 9000, (_recorte(2),)),
    (SUC, 9000, (_recorte(1), _recorte(2, 30, 20))),
    (SUC, 9000, ()),
])
def test_any_ingredient_of_the_proposal_changes_the_token(
        sucursal, limite, cortes):
    base = tope.token_de(SUC, Fraction(9000), (_recorte(1),))

    assert tope.token_de(sucursal, Fraction(limite), cortes) != base


# --- Las líneas de la consulta -> LineaRecortable: puro ---------------------


def test_the_lines_carry_y_from_inventario_final_and_n_from_the_demand():
    fila = _fila(1, "C-1", "C", "50.00", y="12.50", n="7.250000")

    [linea] = tope.lineas_recortables([fila])

    assert linea == recorte.LineaRecortable(
        linea_id=1, codigo="C-1", clase_abc="C", pedido=Fraction(50),
        unidad_empaque=10, precio=Fraction(100), y=Fraction(25, 2),
        n=Fraction(29, 4))


def test_missing_demand_price_or_stock_do_not_break_the_conversion():
    fila = _fila(2, "C-2", "C", "5.00", precio=None, y=None, n=None)

    [linea] = tope.lineas_recortables([fila])

    assert linea.precio is None and linea.n is None
    assert linea.y == Fraction(0)


# --- previsualizar ----------------------------------------------------------


async def test_the_preview_proposes_the_cut_with_its_numbers_tp_09():
    propuesta = await _ver()

    assert propuesta["activo"] is True
    assert propuesta["motivo_inactivo"] is None
    assert propuesta["modo_activo"] is True
    assert propuesta["tope"] == D("9000")
    assert propuesta["valor_actual"] == D("11000.00")
    assert propuesta["exceso"] == D("2000.00")
    assert propuesta["valor_final"] == D("9000.00")
    assert propuesta["exceso_residual"] == D("0.00")
    assert propuesta["lineas_sin_precio"] == 0
    assert propuesta["recortes"] == [{
        "linea_id": 1, "codigo": "C-1", "nombre": "PARTE",
        "clase_abc": "C", "unidad_empaque": 10,
        "pedido_actual": D("50.00"), "pedido_propuesto": D("30.00"),
        "empaques_recortados": D("2"), "valor_recortado": D("2000.00")}]
    assert propuesta["advertencias"] == []


async def test_under_the_cap_the_proposal_is_empty_but_active_tp_08():
    propuesta = await _ver(params=(MODO_ON, _tope("20000")))

    assert propuesta["activo"] is True
    assert propuesta["exceso"] == D("0.00")
    assert propuesta["recortes"] == []
    assert propuesta["valor_final"] == propuesta["valor_actual"]


async def test_the_token_of_a_proposal_changes_when_a_line_changes():
    base = await _token_vigente()
    editadas = [_fila(1, "C-1", "C", "40.00"), *LINEAS[1:]]

    otro = await _token_vigente(lineas=editadas)

    assert otro != base


async def test_the_same_inputs_give_the_same_token_tp_23():
    assert await _token_vigente() == await _token_vigente()


async def test_the_preview_takes_no_lock_and_writes_nothing_tp_13():
    db = _sesion_ver()

    await _ver(db)

    sqls = [_sql(s) for s in db.executed_statements]
    assert len(sqls) == 4
    assert not any("FOR UPDATE" in s or "FOR SHARE" in s for s in sqls)
    assert _sin_escrituras(db)
    assert db.executed_params == [None] * 4


async def test_lines_without_a_price_are_counted_and_warned_tp_12():
    sin_precio = [
        _fila(5, "S-1", "C", "10.00", precio=None),
        _fila(6, "S-2", "B", "4.00", precio="0.00")]

    propuesta = await _ver(lineas=[*LINEAS, *sin_precio])

    assert propuesta["lineas_sin_precio"] == 2
    [aviso] = propuesta["advertencias"]
    assert aviso["codigo"] == codigos.A_CORRIDA_TOPE_SIN_PRECIO
    assert "2" in aviso["mensaje"]


async def test_a_cut_of_a_line_off_its_pack_warns_a_120():
    fuera = [_fila(7, "C-7", "C", "25.00", empaque=12, n="1.000000"),
             _fila(8, "A-8", "A", "100.00")]

    propuesta = await _ver(
        lineas=fuera, params=(MODO_ON, _tope("12450")))

    [recorte_] = propuesta["recortes"]
    assert recorte_["pedido_actual"] == D("25.00")
    assert recorte_["pedido_propuesto"] == D("24.00")
    assert [a["codigo"] for a in propuesta["advertencias"]] == [
        codigos.A_CORRIDA_FUERA_DE_EMPAQUE]


async def test_a_cut_on_a_pack_multiple_has_no_pack_warning():
    propuesta = await _ver()

    assert [a["codigo"] for a in propuesta["advertencias"]] == []


@pytest.mark.parametrize("cola,motivo,modo", [
    (dict(corrida=_corrida(es_escenario=True)), "ESCENARIO", None),
    (dict(corrida=_corrida(estado="PENDIENTE")),
     "CORRIDA_NO_CALCULADA", None),
    (dict(corrida=_corrida(invalidada=True)), "CORRIDA_INVALIDADA", None),
    (dict(tienda=_tienda(None)), "SIN_PEDIDO", None),
    (dict(tienda=_tienda("CERRADO")), "NO_BORRADOR", None),
    (dict(tienda=_tienda("ENVIADO")), "NO_BORRADOR", None),
    (dict(params=(MODO_OFF, _tope())), "MODO_OFF", False),
    (dict(params=()), "MODO_OFF", False),
    (dict(params=(MODO_ON,)), "SIN_TOPE", True),
])
async def test_an_inactive_preview_says_why_and_proposes_nothing(
        cola, motivo, modo):
    propuesta = await _ver(**cola)

    assert propuesta["activo"] is False
    assert propuesta["motivo_inactivo"] == motivo
    assert propuesta["modo_activo"] is modo
    assert propuesta["recortes"] == []
    assert propuesta["token"] is None
    assert propuesta["tope"] is None and propuesta["exceso"] is None


async def test_an_inactive_preview_stops_before_reading_the_lines():
    db = _sesion_ver(tienda=_tienda("CERRADO"))
    db._execute_queue = db._execute_queue[:2]

    propuesta = await _ver(db)

    assert propuesta["activo"] is False
    assert len(db.executed_statements) == 2


@pytest.mark.parametrize("cola", [
    [[]],
    [[_corrida()], []],
])
async def test_a_missing_corrida_or_tienda_is_a_lookup_error(cola):
    db = FakeAsyncSession(execute_queue=cola)

    error = await _error(tope.previsualizar(db, CORRIDA, SUC, hoy=HOY))

    assert isinstance(error, LookupError)


async def test_a_global_cap_row_is_not_the_cap_of_the_tienda():
    propuesta = await _ver(params=(MODO_ON, _tope("9000", None)))

    assert propuesta["motivo_inactivo"] == "SIN_TOPE"


# --- aplicar ----------------------------------------------------------------


async def test_the_locks_follow_corrida_share_tienda_update_lines_by_id():
    db = _sesion_aplicar()

    await _aplicar(db, await _token_vigente())

    sqls = [_sql(s) for s in db.executed_statements]
    assert "FROM corrida " in sqls[0] and sqls[0].endswith("FOR SHARE")
    assert "FROM corrida_sucursal" in sqls[1]
    assert sqls[1].endswith("FOR UPDATE")
    assert "FROM parametro_metodologia" in sqls[2]
    assert "FROM corrida_linea" in sqls[3]
    assert "ORDER BY corrida_linea.id" in sqls[3]
    assert sqls[3].endswith("FOR UPDATE")
    assert sqls[4].startswith("UPDATE corrida_linea")
    assert sqls[5].startswith("INSERT INTO corrida_linea_historial")


async def test_the_lines_query_takes_only_the_included_lines_of_the_tienda():
    db = _sesion_aplicar()

    await _aplicar(db, await _token_vigente())

    consulta = _sql(db.executed_statements[3])
    assert f"corrida_linea.corrida_id = '{CORRIDA}'" in consulta
    assert f"corrida_linea.sucursal_id = '{SUC}'" in consulta
    assert "corrida_linea.motivo_exclusion IS NULL" in consulta


async def test_apply_cuts_the_lines_and_returns_the_new_numbers_tp_24():
    db = _sesion_aplicar()

    resultado = await _aplicar(db, await _token_vigente())

    assert resultado["lineas_recortadas"] == 1
    assert resultado["valor_liberado"] == D("2000.00")
    assert resultado["valor_final"] == D("9000.00")
    assert resultado["exceso_residual"] == D("0.00")
    assert resultado["tope"] == D("9000")
    assert resultado["totales_tienda"] == {
        "unidades_a_pedir": D("1010"), "valor_a_pedir": D("90000"),
        "unidades_sugerido": D("1100"), "valor_sugerido": D("110000")}


async def test_each_cut_line_is_updated_with_its_new_quantity_and_value():
    db = _sesion_aplicar()

    await _aplicar(db, await _token_vigente())

    actualizacion = _sql(db.executed_statements[4])
    assert "pedido_final" in actualizacion and "valor_pedido" in actualizacion
    assert "WHERE corrida_linea.id" in actualizacion
    assert db.executed_params[4] == [{
        "b_id": 1, "b_final": D("30.00"), "b_valor": D("3000.00")}]


async def test_the_history_rows_carry_the_cap_the_token_and_the_user_tp_24():
    db = _sesion_aplicar()
    token = await _token_vigente()

    await _aplicar(db, token)

    assert db.executed_params[5] == [{
        "corrida_id": CORRIDA, "linea_id": 1, "sucursal_id": SUC,
        "campo": "pedido_final", "valor_anterior": D("50.00"),
        "valor_nuevo": D("30.00"), "motivo": "RECORTE_PRESUPUESTO",
        "detalle": {"tope": "9000", "parametro_id": str(PARAM_ID),
                    "token": token},
        "usuario_id": USUARIO}]


async def test_a_class_a_and_b_line_is_never_written_when_c_is_enough():
    db = _sesion_aplicar()

    await _aplicar(db, await _token_vigente())

    escritas = [p["b_id"] for p in db.executed_params[4]]
    assert escritas == [1]


async def test_several_cut_lines_become_several_update_and_history_rows():
    lineas = [_fila(1, "C-1", "C", "50.00"), _fila(2, "C-2", "C", "50.00")]
    cola = dict(lineas=lineas, params=(MODO_ON, _tope("7000")))
    db = _sesion_aplicar(**cola)

    resultado = await _aplicar(db, await _token_vigente(**cola))

    assert resultado["lineas_recortadas"] == 2
    assert [p["b_id"] for p in db.executed_params[4]] == [1, 2]
    assert [p["linea_id"] for p in db.executed_params[5]] == [1, 2]


@pytest.mark.parametrize("token", [None, "", "otro", 12345])
async def test_a_missing_or_wrong_token_is_060_and_writes_nothing(token):
    db = _sesion_aplicar()
    db._execute_queue = db._execute_queue[:4]

    error = await _error(_aplicar(db, token))

    assert error.codigo == codigos.E_CORRIDA_PROPUESTA_DESACTUALIZADA
    assert _sin_escrituras(db)


async def test_a_proposal_changed_after_the_preview_is_060_with_the_new_one():
    viejo = await _token_vigente()
    editadas = [_fila(1, "C-1", "C", "40.00"), *LINEAS[1:]]
    db = FakeAsyncSession(execute_queue=_cola_lectura(lineas=editadas))

    error = await _error(_aplicar(db, viejo))

    assert error.codigo == "E-CORRIDA-060"
    assert _sin_escrituras(db)
    fresca = error.detalle["propuesta"]
    assert fresca["token"] != viejo
    assert fresca["recortes"][0]["linea_id"] == 1
    assert fresca["recortes"][0]["pedido_actual"] == "40.00"


async def test_an_empty_proposal_is_060_even_with_its_own_token_tp_31():
    cola = dict(params=(MODO_ON, _tope("20000")))
    token = await _token_vigente(**cola)
    db = FakeAsyncSession(execute_queue=_cola_lectura(**cola))

    error = await _error(_aplicar(db, token))

    assert error.codigo == "E-CORRIDA-060"
    assert _sin_escrituras(db)


async def test_applying_twice_with_the_same_token_fails_the_second_tp_31():
    token = await _token_vigente()
    despues = [_fila(1, "C-1", "C", "30.00"), *LINEAS[1:]]
    db = FakeAsyncSession(execute_queue=_cola_lectura(lineas=despues))

    error = await _error(_aplicar(db, token))

    assert error.codigo == "E-CORRIDA-060"


async def test_the_mode_off_is_058_before_the_lines_are_read_tp_26():
    db = _sesion_aplicar(params=(MODO_OFF, _tope()))
    db._execute_queue = db._execute_queue[:3]

    error = await _error(_aplicar(db, "x"))

    assert error.codigo == codigos.E_CORRIDA_RECORTE_MODO_OFF
    assert len(db.executed_statements) == 3
    assert _sin_escrituras(db)


@pytest.mark.parametrize(
    "params", [(MODO_ON,), (MODO_ON, _tope("9000", None))])
async def test_a_tienda_without_its_own_cap_is_059_tp_26(params):
    db = _sesion_aplicar(params=params)
    db._execute_queue = db._execute_queue[:3]

    error = await _error(_aplicar(db, "x"))

    assert error.codigo == codigos.E_CORRIDA_RECORTE_SIN_TOPE


@pytest.mark.parametrize("estado", ["CERRADO", "ENVIADO"])
async def test_a_closed_or_sent_pedido_is_061_before_the_params_tp_27(estado):
    db = FakeAsyncSession(execute_queue=_cola_lectura(
        tienda=_tienda(estado))[:2])

    error = await _error(_aplicar(db, "x"))

    assert error.codigo == codigos.E_CORRIDA_RECORTE_NO_BORRADOR
    assert estado in error.mensaje
    assert len(db.executed_statements) == 2


async def test_a_tienda_without_pedido_is_065_before_the_state():
    db = FakeAsyncSession(execute_queue=_cola_lectura(
        tienda=_tienda(None))[:2])

    error = await _error(_aplicar(db, "x"))

    assert error.codigo == codigos.E_CORRIDA_SIN_PEDIDO


@pytest.mark.parametrize("corrida,codigo", [
    (_corrida(es_escenario=True), "E-CORRIDA-042"),
    (_corrida(estado="CALCULANDO"), "E-CORRIDA-040"),
    (_corrida(estado="ANULADA"), "E-CORRIDA-040"),
    (_corrida(invalidada=True), "E-CORRIDA-041"),
])
async def test_the_corrida_rules_come_before_the_pedido_state(
        corrida, codigo):
    cola = _cola_lectura(corrida=corrida, tienda=_tienda(None))[:2]
    db = FakeAsyncSession(execute_queue=cola)

    error = await _error(_aplicar(db, "x"))

    assert error.codigo == codigo
    assert len(db.executed_statements) == 2


async def test_a_scenario_says_what_it_cannot_do_042():
    cola = _cola_lectura(corrida=_corrida(es_escenario=True))[:2]

    error = await _error(_aplicar(FakeAsyncSession(execute_queue=cola), "x"))

    assert "recortar" in error.mensaje


@pytest.mark.parametrize("cola", [[[]], [[_corrida()], []]])
async def test_apply_on_a_missing_corrida_or_tienda_is_a_lookup_error(cola):
    error = await _error(_aplicar(FakeAsyncSession(execute_queue=cola), "x"))

    assert isinstance(error, LookupError)


# --- El tope vigente de una tienda ------------------------------------------


def _vigentes(*filas):
    return parametros.VigentesMotor.desde_filas(filas, HOY)


@pytest.mark.parametrize("filas,esperado", [
    ([_tope("80000000.50")], (D("80000000.50"), PARAM_ID)),
    ([_tope(None)], (None, None)),
    ([_tope("abc")], (None, None)),
    ([_tope("-5")], (None, None)),
    ([_tope("9000", None)], (None, None)),
    ([_tope("9000", OTRA)], (None, None)),
    ([], (None, None)),
])
def test_the_cap_of_a_tienda_is_its_own_valid_row_or_nothing(filas, esperado):
    assert parametros_topes.tope_de(_vigentes(*filas), SUC) == esperado


# --- El resumen por corrida -------------------------------------------------


def _fila_resumen(sucursal_id, nombre, estado, valor, sin_precio=0):
    return (sucursal_id, nombre, estado, D(valor), sin_precio)


async def test_the_summary_lists_each_tienda_with_cap_value_and_excess():
    filas = [
        _fila_resumen(SUC, "Cali", "BORRADOR", "11000.00", 2),
        _fila_resumen(OTRA, "Pereira", "CERRADO", "500.00")]
    db = FakeAsyncSession(execute_queue=[
        [_corrida()], [MODO_ON, _tope("9000")], filas])

    resumen = await tope.resumen_topes(db, CORRIDA, hoy=HOY)

    assert resumen["activo"] is True
    assert resumen["corrida_id"] == CORRIDA
    assert resumen["tiendas"] == [
        {"sucursal_id": SUC, "nombre": "Cali", "estado_pedido": "BORRADOR",
         "tope": D("9000"), "valor_a_pedir": D("11000.00"),
         "exceso": D("2000.00"), "lineas_sin_precio": 2},
        {"sucursal_id": OTRA, "nombre": "Pereira",
         "estado_pedido": "CERRADO", "tope": None,
         "valor_a_pedir": D("500.00"), "exceso": None,
         "lineas_sin_precio": 0}]


async def test_a_tienda_under_its_cap_has_zero_excess():
    db = FakeAsyncSession(execute_queue=[
        [_corrida()], [MODO_ON, _tope("9000")],
        [_fila_resumen(SUC, "Cali", "BORRADOR", "100.00")]])

    resumen = await tope.resumen_topes(db, CORRIDA, hoy=HOY)

    assert resumen["tiendas"][0]["exceso"] == D("0.00")


async def test_the_summary_is_inactive_with_the_mode_off_tp_10():
    db = FakeAsyncSession(execute_queue=[[_corrida()], [MODO_OFF, _tope()]])

    resumen = await tope.resumen_topes(db, CORRIDA, hoy=HOY)

    assert resumen == {
        "activo": False, "corrida_id": CORRIDA, "tiendas": []}
    assert len(db.executed_statements) == 2


async def test_the_summary_of_a_scenario_is_inactive_without_querying_more():
    db = FakeAsyncSession(execute_queue=[[_corrida(es_escenario=True)]])

    resumen = await tope.resumen_topes(db, CORRIDA, hoy=HOY)

    assert resumen["activo"] is False and resumen["tiendas"] == []
    assert len(db.executed_statements) == 1


async def test_the_summary_of_a_missing_corrida_is_a_lookup_error():
    error = await _error(tope.resumen_topes(
        FakeAsyncSession(execute_queue=[[]]), CORRIDA, hoy=HOY))

    assert isinstance(error, LookupError)


async def test_the_summary_reads_only_ok_tiendas_that_have_a_pedido():
    db = FakeAsyncSession(execute_queue=[
        [_corrida()], [MODO_ON], []])

    await tope.resumen_topes(db, CORRIDA, hoy=HOY)

    consulta = _sql(db.executed_statements[2])
    assert "corrida_sucursal.estado = 'OK'" in consulta
    assert "corrida_sucursal.estado_pedido IS NOT NULL" in consulta
    assert "corrida_linea.motivo_exclusion IS NULL" in consulta
    assert "corrida_linea.pedido_final > 0" in consulta


# --- El tope congelado al cerrar --------------------------------------------


async def test_the_cap_in_force_is_frozen_for_each_closed_tienda():
    db = FakeAsyncSession(execute_queue=[
        [MODO_ON, _tope("9000"), _param(
            "presupuesto_maximo_pedido", "5000", OTRA)]])

    congelados = await tope.topes_congelados(db, [SUC, OTRA], hoy=HOY)

    assert congelados[SUC] == {"tope": "9000", "parametro_id": str(PARAM_ID)}
    assert congelados[OTRA]["tope"] == "5000"


async def test_a_tienda_without_cap_is_not_in_the_frozen_map():
    db = FakeAsyncSession(execute_queue=[[MODO_ON, _tope("9000")]])

    congelados = await tope.topes_congelados(db, [SUC, OTRA], hoy=HOY)

    assert list(congelados) == [SUC]


async def test_nothing_is_frozen_when_the_mode_is_off():
    db = FakeAsyncSession(execute_queue=[[MODO_OFF, _tope("9000")]])

    assert await tope.topes_congelados(db, [SUC], hoy=HOY) == {}


# --- Los códigos ------------------------------------------------------------


@pytest.mark.parametrize("codigo,texto", [
    (codigos.E_CORRIDA_RECORTE_MODO_OFF, "apagado"),
    (codigos.E_CORRIDA_RECORTE_SIN_TOPE, "tope"),
    (codigos.E_CORRIDA_PROPUESTA_DESACTUALIZADA, "cambió"),
    (codigos.E_CORRIDA_RECORTE_NO_BORRADOR, "BORRADOR"),
])
def test_the_recorte_codes_have_their_number_and_a_spanish_message(
        codigo, texto):
    mensaje = codigos.mensaje(codigo, estado="CERRADO")

    assert texto in mensaje


def test_the_recorte_codes_keep_the_numbers_of_the_catalog():
    assert (
        codigos.E_CORRIDA_RECORTE_MODO_OFF,
        codigos.E_CORRIDA_RECORTE_SIN_TOPE,
        codigos.E_CORRIDA_PROPUESTA_DESACTUALIZADA,
        codigos.E_CORRIDA_RECORTE_NO_BORRADOR,
        codigos.A_CORRIDA_FUERA_DE_EMPAQUE,
        codigos.A_CORRIDA_TOPE_SIN_PRECIO,
    ) == ("E-CORRIDA-058", "E-CORRIDA-059", "E-CORRIDA-060",
          "E-CORRIDA-061", "A-CORRIDA-120", "A-CORRIDA-121")
