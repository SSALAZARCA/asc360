"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B3b, ADR-1, ADR-11,
spec CI-25..CI-36c, decisiones F4-11, F4-13 y F4-15): marcar como enviado el
pedido de cada tienda, el bloqueo de envío duplicado y la corrección del
número de orden.

Con una sesión de juguete que graba el SQL se prueba lo que no depende del
motor de Postgres: la tabla de transiciones con sus códigos (042, 040, 041,
065, 049, 047, 048, 050, 056, 067), el ORDEN de los chequeos, el orden de los
bloqueos (corrida SHARE -> tiendas UPDATE por `sucursal_id`), lo que se
escribe (la fila `corrida_envio` y el evento) y que un rechazo no escribe
nada. Las mismas reglas contra Postgres real, incluida la UNIQUE y las
carreras, corren en `pg_real/test_envio_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import CompileError, IntegrityError

from app.motored.models.corrida_envio import CorridaEnvio
from app.motored.services.corridas import codigos, envio
from tests.motored.conftest import SesionConCommits
from tests.motored.fixtures import corridas_api as fx

USUARIO = uuid.UUID(int=900)
CORRIDA = fx.CORRIDA_ID
PROVEEDOR = fx.PROVEEDOR_ID
SUC_A, SUC_B = fx.SUC_A, fx.SUC_B
CORTE = fx.CORTE
HOY = datetime.date(2026, 9, 30)
ENVIO = datetime.date(2026, 9, 22)
UQ = "uq_corrida_envio_corte_sucursal"
DUPLICADA = IntegrityError(
    "INSERT", {}, Exception(f'duplicate key violates unique "{UQ}"'))


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    monkeypatch.setattr(envio, "hoy_bogota", lambda: HOY)


class _Sesion(SesionConCommits):
    """Savepoints contados y, si `falla`, un `flush` que la lanza en cuanto
    hay una fila `corrida_envio` por escribir (la UNIQUE de Postgres)."""

    def __init__(self, *args, falla=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.falla = falla

    async def flush(self):
        if self.falla is not None and self.added:
            raise self.falla


def _sql(sentencia) -> str:
    """SQL con literales; los JSONB no tienen renderizador literal, así que
    esas sentencias (los eventos) se muestran con sus marcadores."""
    try:
        return str(sentencia.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True}))
    except CompileError:
        return str(sentencia.compile(dialect=postgresql.dialect()))


def _params(sentencia) -> list:
    return list(sentencia.compile(dialect=postgresql.dialect())
                .params.values())


def _corrida(**campos):
    base = dict(
        id=CORRIDA, codigo="PED-2026-S39-001", estado="BORRADOR",
        es_escenario=False, invalidada=False, proveedor_id=PROVEEDOR,
        fecha_corte=CORTE)
    return SimpleNamespace(**{**base, **campos})


def _tienda(sucursal_id=SUC_A, estado_pedido="CERRADO", estado="OK"):
    return SimpleNamespace(
        corrida_id=CORRIDA, sucursal_id=sucursal_id, estado=estado,
        estado_pedido=estado_pedido)


def _fila(sucursal_id=SUC_A, nombre="UNO", **campos):
    return (_tienda(sucursal_id, **campos), nombre)


def _sesion(*, corrida=None, filas=None, extra=(), **kwargs):
    """Cola en el orden en que se consulta: la corrida, las tiendas y lo que
    siga (`extra`: duplicados, sumas, el INSERT de eventos...). Un paso que
    rechaza corta la cola: el resto no se consulta."""
    cola = [[corrida] if corrida is not None else []]
    if filas is not None:
        cola.append(list(filas))
    cola.extend(list(e) for e in extra)
    return _Sesion(execute_queue=cola, **kwargs)


def _feliz(*, filas=None, sumas=None, dups=()):
    """Cola de un envío válido: duplicados, sumas y el INSERT de eventos."""
    filas = filas if filas is not None else [_fila()]
    sumas = sumas if sumas is not None else [
        (f[0].sucursal_id, Decimal("10")) for f in filas]
    return _sesion(
        corrida=_corrida(), filas=filas, extra=[list(dups), sumas, []])


def _sql_inicio(sentencia) -> str:
    return str(sentencia.compile(dialect=postgresql.dialect()))[:25]


def _con_carrera(rival, falla):
    """Un envío válido cuyo INSERT choca con la UNIQUE (`falla`); `rival` es
    lo que devuelve la nueva lectura del duplicado."""
    return _sesion(
        corrida=_corrida(), filas=[_fila()],
        extra=[[], [(SUC_A, Decimal("10"))], rival], falla=falla)


def _sin_escrituras(db) -> bool:
    return not db.added and not any(
        _sql(s).startswith(("INSERT", "UPDATE"))
        for s in db.executed_statements)


async def _error(coro):
    with pytest.raises(BaseException) as error:
        await coro
    return error.value


def _pedido(sucursal_id=SUC_A, numero="12345", fecha=ENVIO):
    return envio.PedidoEnviar(sucursal_id, numero, fecha)


async def _enviar(db, **campos):
    p = _pedido(**campos)
    return await envio.enviar_tienda(
        db, CORRIDA, p.sucursal_id, p.numero, p.fecha_envio, USUARIO)


async def _lote(db, *pedidos):
    return await envio.enviar_lote(db, CORRIDA, list(pedidos), USUARIO)


# --- Enviar: el camino feliz y el orden de los bloqueos ---------------------


async def test_the_locks_follow_corrida_share_then_tiendas_update_ci_25():
    db = _feliz()

    await _enviar(db)

    sqls = [_sql(s) for s in db.executed_statements]
    assert "FROM corrida " in sqls[0] and sqls[0].endswith("FOR SHARE")
    assert "FROM corrida_sucursal" in sqls[1]
    assert "ORDER BY corrida_sucursal.sucursal_id" in sqls[1]
    assert sqls[1].endswith("FOR UPDATE OF corrida_sucursal")
    assert "FROM corrida_envio" in sqls[2]
    assert "FROM corrida_linea" in sqls[3]
    assert sqls[4].startswith("INSERT INTO pedido_evento")


async def test_sending_one_tienda_marks_it_enviado_and_writes_the_envio():
    fila = _fila()
    db = _feliz(filas=[fila])

    resultado = await _enviar(db, numero="  12345  ")

    assert fila[0].estado_pedido == "ENVIADO"
    (fila_envio,) = db.added_of_type(CorridaEnvio)
    assert fila_envio.corrida_id == CORRIDA
    assert fila_envio.sucursal_id == SUC_A
    assert fila_envio.proveedor_id == PROVEEDOR
    assert fila_envio.fecha_corte == CORTE
    assert fila_envio.numero_pedido_proveedor == "12345"
    assert fila_envio.fecha_envio == ENVIO
    assert fila_envio.enviada_por == USUARIO
    assert fila_envio.enviada_en is not None
    assert resultado.envios == [fila_envio]
    assert resultado.corrida.codigo == "PED-2026-S39-001"


async def test_the_envio_row_is_written_inside_a_savepoint():
    db = _feliz()

    await _enviar(db)

    assert db.savepoints == 1


async def test_the_enviado_event_records_who_the_number_and_the_date():
    db = _feliz()

    await _enviar(db, numero="777")

    valores = _params(db.executed_statements[4])
    assert "ENVIADO" in valores and USUARIO in valores
    assert SUC_A in valores and CORRIDA in valores
    assert {"numero": "777", "fecha_envio": "2026-09-22"} in valores


async def test_a_batch_stores_each_number_and_locks_in_sucursal_order_ci_26():
    a, b = _fila(SUC_A, "UNO"), _fila(SUC_B, "DOS")
    db = _feliz(filas=[a, b])

    resultado = await _lote(
        db, _pedido(SUC_B, "B-22"), _pedido(SUC_A, "A-11"))

    numeros = {
        e.sucursal_id: e.numero_pedido_proveedor for e in resultado.envios}
    assert numeros == {SUC_A: "A-11", SUC_B: "B-22"}
    assert a[0].estado_pedido == b[0].estado_pedido == "ENVIADO"
    assert db.savepoints == 2
    assert len(db.executed_statements) == 5
    valores = _params(db.executed_statements[4])
    assert {"numero": "A-11", "fecha_envio": "2026-09-22"} in valores
    assert {"numero": "B-22", "fecha_envio": "2026-09-22"} in valores


async def test_a_legacy_cerrada_corrida_is_operable_for_sending():
    db = _sesion(
        corrida=_corrida(estado="CERRADA"), filas=[_fila()],
        extra=[[], [(SUC_A, Decimal("5"))], []])

    resultado = await _enviar(db)

    assert resultado.envios[0].numero_pedido_proveedor == "12345"


# --- Enviar: fecha y número válidos -----------------------------------------


@pytest.mark.parametrize("fecha", [
    ENVIO, "2026-09-22", CORTE, "2026-09-21", HOY, "2026-09-30"])
async def test_a_send_date_between_the_corte_and_today_is_accepted(fecha):
    db = _feliz()

    resultado = await _enviar(db, fecha=fecha)

    esperada = (
        fecha if isinstance(fecha, datetime.date)
        else datetime.date.fromisoformat(fecha))
    assert resultado.envios[0].fecha_envio == esperada


@pytest.mark.parametrize("numero", ["", "   ", None, 5, "x" * 51])
async def test_a_blank_missing_or_oversized_number_is_048_ci_27(numero):
    fila = _fila()
    db = _sesion(corrida=_corrida(), filas=[fila])

    error = await _error(_enviar(db, numero=numero))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_INVALIDO
    assert fila[0].estado_pedido == "CERRADO" and _sin_escrituras(db)


@pytest.mark.parametrize("fecha", [
    None, "ayer", 20260922, datetime.datetime(2026, 9, 22, 10),
    HOY + datetime.timedelta(days=1), CORTE - datetime.timedelta(days=1),
    "2026-10-01", "2026-09-20"])
async def test_an_invalid_future_or_early_send_date_is_048_ci_27(fecha):
    fila = _fila()
    db = _sesion(corrida=_corrida(), filas=[fila])

    error = await _error(_enviar(db, fecha=fecha))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_INVALIDO
    assert fila[0].estado_pedido == "CERRADO" and _sin_escrituras(db)


async def test_a_number_of_exactly_50_characters_is_accepted():
    db = _feliz()

    resultado = await _enviar(db, numero="x" * 50)

    assert len(resultado.envios[0].numero_pedido_proveedor) == 50


async def test_a_batch_names_the_tienda_with_the_invalid_payload():
    db = _sesion(
        corrida=_corrida(), filas=[_fila(SUC_A, "UNO"), _fila(SUC_B, "DOS")])

    error = await _error(_lote(db, _pedido(SUC_A), _pedido(SUC_B, "")))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_INVALIDO
    assert "DOS" in error.mensaje and "UNO" not in error.mensaje
    assert _sin_escrituras(db)


async def test_the_same_tienda_twice_in_a_batch_is_048_before_any_query():
    db = _sesion()

    error = await _error(_lote(db, _pedido(SUC_A), _pedido(SUC_A, "9")))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_INVALIDO
    assert db.executed_statements == []


# --- Enviar: rechazos y su orden --------------------------------------------


async def test_an_unknown_corrida_is_a_404_after_one_query():
    db = _sesion()

    error = await _error(_enviar(db))

    assert isinstance(error, LookupError)
    assert len(db.executed_statements) == 1 and _sin_escrituras(db)


async def test_an_unknown_tienda_is_a_404():
    db = _sesion(corrida=_corrida(), filas=[])

    error = await _error(_enviar(db))

    assert isinstance(error, LookupError) and _sin_escrituras(db)


async def test_a_scenario_is_042_with_the_action_before_any_state_rule_ci_31():
    db = _sesion(
        corrida=_corrida(es_escenario=True, estado="PENDIENTE"),
        filas=[_fila(estado_pedido=None)])

    error = await _error(_enviar(db))

    assert error.codigo == codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA
    assert "enviar" in error.mensaje and _sin_escrituras(db)


@pytest.mark.parametrize("estado", [
    "PENDIENTE", "CALCULANDO", "FALLIDA", "ANULADA"])
async def test_a_corrida_not_calculated_is_040(estado):
    db = _sesion(corrida=_corrida(estado=estado), filas=[_fila()])

    error = await _error(_enviar(db))

    assert error.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE
    assert _sin_escrituras(db)


async def test_an_invalidated_corrida_cannot_send_041():
    db = _sesion(corrida=_corrida(invalidada=True), filas=[_fila()])

    error = await _error(_enviar(db))

    assert error.codigo == codigos.E_CORRIDA_INVALIDADA


async def test_a_tienda_without_pedido_is_065_ci_30():
    db = _sesion(corrida=_corrida(), filas=[_fila(estado_pedido=None)])

    error = await _error(_enviar(db))

    assert error.codigo == codigos.E_CORRIDA_SIN_PEDIDO
    assert "UNO" in error.mensaje and _sin_escrituras(db)


async def test_a_borrador_pedido_is_047_ci_29():
    fila = _fila(estado_pedido="BORRADOR")
    db = _sesion(corrida=_corrida(), filas=[fila])

    error = await _error(_enviar(db))

    assert error.codigo == codigos.E_CORRIDA_ENVIAR_NO_CERRADO
    assert "UNO" in error.mensaje and "BORRADOR" in error.mensaje
    assert fila[0].estado_pedido == "BORRADOR" and _sin_escrituras(db)


async def test_an_already_sent_pedido_is_049_and_names_its_number_ci_28():
    fila = _fila(estado_pedido="ENVIADO")
    db = _sesion(corrida=_corrida(), filas=[fila], extra=[["11111"]])

    error = await _error(_enviar(db, numero="22222"))

    assert error.codigo == codigos.E_CORRIDA_ENVIAR_YA_ENVIADO
    assert "11111" in error.mensaje and "UNO" in error.mensaje
    assert fila[0].estado_pedido == "ENVIADO" and _sin_escrituras(db)
    assert "FROM corrida_envio" in _sql(db.executed_statements[2])


async def test_the_state_is_checked_before_the_payload():
    db = _sesion(
        corrida=_corrida(), filas=[_fila(estado_pedido="BORRADOR")])

    error = await _error(_enviar(db, numero=""))

    assert error.codigo == codigos.E_CORRIDA_ENVIAR_NO_CERRADO


async def test_a_batch_is_all_or_nothing_and_names_the_offender_ci_32():
    cerrada = _fila(SUC_A, "UNO")
    abierta = _fila(SUC_B, "DOS", estado_pedido="BORRADOR")
    db = _sesion(corrida=_corrida(), filas=[cerrada, abierta])

    error = await _error(_lote(db, _pedido(SUC_A), _pedido(SUC_B, "2")))

    assert error.codigo == codigos.E_CORRIDA_ENVIAR_NO_CERRADO
    assert "DOS" in error.mensaje
    assert cerrada[0].estado_pedido == "CERRADO" and _sin_escrituras(db)


async def test_065_is_named_before_047_in_a_batch():
    sin_pedido = _fila(SUC_B, "DOS", estado_pedido=None)
    abierta = _fila(SUC_A, "UNO", estado_pedido="BORRADOR")
    db = _sesion(corrida=_corrida(), filas=[abierta, sin_pedido])

    error = await _error(_lote(db, _pedido(SUC_A), _pedido(SUC_B, "2")))

    assert error.codigo == codigos.E_CORRIDA_SIN_PEDIDO
    assert "DOS" in error.mensaje


# --- Enviar: F4-13, duplicado entre corridas --------------------------------


async def test_a_tienda_already_sent_for_the_same_corte_is_050_ci_34():
    fila = _fila(nombre="Manizales")
    db = _feliz(filas=[fila], dups=[(SUC_A, "PED-2026-S39-000", "12345")])

    error = await _error(_enviar(db, numero="999"))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_DUPLICADO
    assert error.mensaje == (
        "Manizales ya tiene un pedido enviado para esta semana (corrida "
        "PED-2026-S39-000, orden 12345).")
    assert error.detalle == {
        "sucursal_id": str(SUC_A), "tienda": "Manizales",
        "corrida": "PED-2026-S39-000", "numero_pedido_proveedor": "12345"}
    assert fila[0].estado_pedido == "CERRADO" and _sin_escrituras(db)


async def test_the_duplicate_lookup_filters_by_proveedor_corte_and_tienda():
    db = _feliz()

    await _enviar(db)

    consulta = _sql(db.executed_statements[2])
    assert f"corrida_envio.proveedor_id = '{PROVEEDOR}'" in consulta
    assert f"corrida_envio.fecha_corte = '{CORTE}'" in consulta
    assert f"corrida_envio.sucursal_id IN ('{SUC_A}')" in consulta
    assert f"corrida_envio.corrida_id != '{CORRIDA}'" in consulta


async def test_another_tienda_sent_in_the_other_corrida_does_not_block_ci_36():
    a, b = _fila(SUC_A, "UNO"), _fila(SUC_B, "DOS")
    db = _feliz(filas=[a, b], dups=[])

    resultado = await _lote(db, _pedido(SUC_A), _pedido(SUC_B, "2"))

    assert len(resultado.envios) == 2


async def test_a_batch_names_the_duplicated_tienda_and_changes_nothing():
    a, b = _fila(SUC_A, "UNO"), _fila(SUC_B, "DOS")
    db = _feliz(filas=[a, b], dups=[(SUC_B, "PED-2026-S39-000", "55")])

    error = await _error(_lote(db, _pedido(SUC_A), _pedido(SUC_B, "2")))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_DUPLICADO
    assert "DOS" in error.mensaje
    assert a[0].estado_pedido == b[0].estado_pedido == "CERRADO"
    assert _sin_escrituras(db)


async def test_a_concurrent_unique_violation_is_mapped_to_050_ci_36c():
    """Otra corrida ganó la carrera entre la consulta y el INSERT: la UNIQUE
    salta dentro del savepoint, se vuelve a leer y responde 050."""
    db = _con_carrera([(SUC_A, "PED-2026-S39-000", "12345")], DUPLICADA)

    error = await _error(_enviar(db))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_DUPLICADO
    assert "PED-2026-S39-000" in error.mensaje


async def test_a_unique_violation_that_is_not_ours_is_not_swallowed():
    otra = IntegrityError("INSERT", {}, Exception("violates foreign key"))
    db = _con_carrera([], otra)

    error = await _error(_enviar(db))

    assert error is otra


async def test_a_unique_violation_with_no_rival_found_is_not_swallowed():
    db = _con_carrera([], DUPLICADA)

    error = await _error(_enviar(db))

    assert error is DUPLICADA


# --- Enviar: nada que pedir (A1) ---------------------------------------------


@pytest.mark.parametrize("sumas", [[], [(SUC_A, Decimal("0"))]])
async def test_a_pedido_with_nothing_to_order_cannot_be_sent_056(sumas):
    fila = _fila(nombre="Manizales")
    db = _feliz(filas=[fila], sumas=sumas)

    error = await _error(_enviar(db))

    assert error.codigo == codigos.E_CORRIDA_NADA_QUE_ENVIAR
    assert "Manizales" in error.mensaje
    assert fila[0].estado_pedido == "CERRADO" and _sin_escrituras(db)


async def test_the_sum_counts_only_the_included_lines_of_the_tiendas():
    db = _feliz()

    await _enviar(db)

    consulta = _sql(db.executed_statements[3])
    assert "sum(corrida_linea.pedido_final)" in consulta
    assert "corrida_linea.motivo_exclusion IS NULL" in consulta
    assert f"corrida_linea.sucursal_id IN ('{SUC_A}')" in consulta
    assert "GROUP BY corrida_linea.sucursal_id" in consulta


async def test_one_tienda_with_nothing_blocks_the_whole_batch_names_it():
    a, b = _fila(SUC_A, "UNO"), _fila(SUC_B, "DOS")
    db = _feliz(filas=[a, b], sumas=[(SUC_A, Decimal("4"))])

    error = await _error(_lote(db, _pedido(SUC_A), _pedido(SUC_B, "2")))

    assert error.codigo == codigos.E_CORRIDA_NADA_QUE_ENVIAR
    assert "DOS" in error.mensaje and _sin_escrituras(db)


# --- Corregir el número (F4-15) ----------------------------------------------


def _sesion_corregir(*, corrida=None, tienda=None, actual="12345"):
    """Cola de `corregir_numero`: corrida, tienda y la fila `corrida_envio`
    (bloqueada `FOR UPDATE`); si cambia, el INSERT del evento."""
    envio_orm = None
    if actual is not None:
        envio_orm = SimpleNamespace(
            corrida_id=CORRIDA, sucursal_id=SUC_A,
            numero_pedido_proveedor=actual, fecha_envio=ENVIO)
    cola = [[corrida] if corrida is not None else []]
    if tienda is not None:
        cola.append([tienda])
    if envio_orm is not None:
        cola.append([envio_orm])
    cola.append([])
    return _Sesion(execute_queue=cola), envio_orm


async def _corregir(db, numero="99999"):
    return await envio.corregir_numero(
        db, CORRIDA, SUC_A, numero, USUARIO)


async def test_correcting_the_number_updates_it_and_audits_before_after():
    tienda = _tienda(estado_pedido="ENVIADO")
    db, fila_envio = _sesion_corregir(corrida=_corrida(), tienda=tienda)

    resultado = await _corregir(db, "  99999 ")

    assert fila_envio.numero_pedido_proveedor == "99999"
    assert resultado.envio is fila_envio and resultado.cambio is True
    assert tienda.estado_pedido == "ENVIADO"
    assert fila_envio.fecha_envio == ENVIO
    evento = db.executed_statements[3]
    assert _sql_inicio(evento) == "INSERT INTO pedido_evento"
    valores = _params(evento)
    assert "ENVIO_CORREGIDO" in valores and USUARIO in valores
    assert {"antes": "12345", "despues": "99999"} in valores


async def test_the_correction_locks_corrida_share_tienda_and_envio_update():
    db, _ = _sesion_corregir(
        corrida=_corrida(), tienda=_tienda(estado_pedido="ENVIADO"))

    await _corregir(db)

    sqls = [_sql(s) for s in db.executed_statements]
    assert "FROM corrida " in sqls[0] and sqls[0].endswith("FOR SHARE")
    assert "FROM corrida_sucursal" in sqls[1]
    assert sqls[1].endswith("FOR UPDATE")
    assert "FROM corrida_envio" in sqls[2] and sqls[2].endswith("FOR UPDATE")


@pytest.mark.parametrize("numero", ["12345", "  12345  "])
async def test_the_same_number_is_a_no_op_with_no_event(numero):
    db, fila_envio = _sesion_corregir(
        corrida=_corrida(), tienda=_tienda(estado_pedido="ENVIADO"))

    resultado = await _corregir(db, numero)

    assert resultado.cambio is False and resultado.envio is fila_envio
    assert len(db.executed_statements) == 3
    assert fila_envio.numero_pedido_proveedor == "12345"


@pytest.mark.parametrize("estado", ["CERRADO", "BORRADOR"])
async def test_correcting_a_pedido_that_is_not_enviado_is_067(estado):
    tienda = _tienda(estado_pedido=estado)
    db, _ = _sesion_corregir(
        corrida=_corrida(), tienda=tienda, actual=None)

    error = await _error(_corregir(db))

    assert error.codigo == codigos.E_CORRIDA_CORREGIR_NO_ENVIADO
    assert estado in error.mensaje and _sin_escrituras(db)


async def test_correcting_a_tienda_without_pedido_is_065():
    db, _ = _sesion_corregir(
        corrida=_corrida(), tienda=_tienda(estado_pedido=None), actual=None)

    error = await _error(_corregir(db))

    assert error.codigo == codigos.E_CORRIDA_SIN_PEDIDO


@pytest.mark.parametrize("numero", ["", "   ", None, 7, "x" * 51])
async def test_a_blank_or_oversized_corrected_number_is_048(numero):
    db, fila_envio = _sesion_corregir(
        corrida=_corrida(), tienda=_tienda(estado_pedido="ENVIADO"))

    error = await _error(_corregir(db, numero))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_INVALIDO
    assert fila_envio.numero_pedido_proveedor == "12345"
    assert len(db.executed_statements) == 2


async def test_the_state_is_checked_before_the_corrected_number():
    db, _ = _sesion_corregir(
        corrida=_corrida(), tienda=_tienda(estado_pedido="CERRADO"),
        actual=None)

    error = await _error(_corregir(db, ""))

    assert error.codigo == codigos.E_CORRIDA_CORREGIR_NO_ENVIADO


async def test_correcting_in_a_scenario_is_042_with_the_action():
    db, _ = _sesion_corregir(
        corrida=_corrida(es_escenario=True),
        tienda=_tienda(estado_pedido=None), actual=None)

    error = await _error(_corregir(db))

    assert error.codigo == codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA
    assert "corregir el envío" in error.mensaje


async def test_correcting_an_unknown_corrida_or_tienda_is_a_404():
    sin_corrida, _ = _sesion_corregir(actual=None)
    sin_tienda, _ = _sesion_corregir(corrida=_corrida(), actual=None)

    assert isinstance(await _error(_corregir(sin_corrida)), LookupError)
    assert isinstance(await _error(_corregir(sin_tienda)), LookupError)


async def test_an_invalidated_corrida_still_allows_the_correction():
    db, fila_envio = _sesion_corregir(
        corrida=_corrida(invalidada=True),
        tienda=_tienda(estado_pedido="ENVIADO"))

    resultado = await _corregir(db)

    assert resultado.cambio is True
    assert fila_envio.numero_pedido_proveedor == "99999"


async def test_an_enviado_tienda_with_no_envio_row_is_an_internal_error():
    db, _ = _sesion_corregir(
        corrida=_corrida(), tienda=_tienda(estado_pedido="ENVIADO"),
        actual=None)

    error = await _error(_corregir(db))

    assert isinstance(error, RuntimeError)
