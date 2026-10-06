"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B4, alcance agregado
por B3b; spec DM, "Corrida detail and list expose each tienda's ... envío
data (order number, date, who)"): el bloque `envio` de las lecturas.

La tabla de tiendas (F2a) y la pantalla de la tienda (F3) necesitan el número
de orden, la fecha de envío y quién y cuándo lo marcó, y hasta B3b sólo salían
por `GET .../eventos`. Tres capas, como `test_pedido_lecturas.py`: la
proyección pura, las consultas con una sesión de juguete y el SQL literal, y
el contrato HTTP de la cabecera de la tienda y del detalle de la corrida.

El bloque es `null` mientras la tienda no está ENVIADO (`ENVIADO <=> existe la
fila de `corrida_envio``, invariante de B3b): por eso la consulta extra sólo
se hace cuando alguna tienda visible está ENVIADO, y la lista de corridas,
que no trae filas por tienda, no lo necesita.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.main import app
from app.motored.api import corridas as api
from app.motored.schemas.corrida import EnvioInfo
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import consultas as cq
from app.motored.services.corridas import lecturas_pedido as lp
from app.motored.services.corridas import proyecciones as pr
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)
from tests.motored.fixtures import corridas_api as fx
from tests.motored.test_corrida_consultas import SUC_C, _corrida, _suc

SUC_A, SUC_B = fx.SUC_A, fx.SUC_B
FECHA = datetime.date(2026, 9, 22)
ENVIADO_EN = datetime.datetime(2026, 9, 22, 14, 5)
BLOQUE = {
    "numero_orden": "12345", "fecha_envio": FECHA, "enviado_por": "Maria",
    "enviado_en": ENVIADO_EN}
BASE = "/api/motored/corridas"
USUARIO = str(uuid.UUID(int=900))
JSON_BLOQUE = {
    "numero_orden": "12345", "fecha_envio": "2026-09-22",
    "enviado_por": "Maria", "enviado_en": "2026-09-22T14:05:00+00:00"}


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def _envio(usuario="Maria"):
    return pr.EnvioTienda("12345", FECHA, usuario, ENVIADO_EN)


def _fila_envio(sucursal_id=SUC_A, numero="12345", usuario="Maria"):
    return (sucursal_id, numero, FECHA, usuario, ENVIADO_EN)


# --- Proyección --------------------------------------------------------------


def _detalle(envios=None):
    sucursales = [
        _suc(SUC_A, "UNO", 1, estado_pedido="ENVIADO"),
        _suc(SUC_B, "DOS", 2, estado_pedido="BORRADOR"),
        _suc(SUC_C, "TRES", 3, "FALLIDA", estado_pedido=None)]
    return pr.armar_detalle(
        _corrida(), sucursales, [], [], None, (), None, envios)


def test_a_sent_tienda_carries_its_envio_block_in_the_detail():
    uno, dos, tres = _detalle({SUC_A: _envio()})["sucursales"]

    assert uno["envio"] == BLOQUE
    assert dos["envio"] is None and tres["envio"] is None


def test_the_detail_without_envios_still_builds_with_null_blocks():
    assert [s["envio"] for s in _detalle()["sucursales"]] == [
        None, None, None]


def test_the_block_survives_an_unknown_user():
    uno = _detalle({SUC_A: _envio(usuario=None)})["sucursales"][0]

    assert uno["envio"]["enviado_por"] is None
    assert uno["envio"]["numero_orden"] == "12345"


def test_the_header_projection_adds_the_envio_block():
    tienda = _suc(SUC_A, "UNO", 1, estado_pedido="ENVIADO")

    con = pr.cabecera_tienda(
        _corrida(), tienda, "UNO", "SIC-1", {}, None, _envio())
    sin = pr.cabecera_tienda(_corrida(), tienda, "UNO", "SIC-1", {}, None)

    assert con["envio"] == BLOQUE
    assert sin["envio"] is None


# --- Acción exportar ---------------------------------------------------------


@pytest.mark.parametrize("estado_pedido,esperada", [
    ("BORRADOR", False), ("CERRADO", True), ("ENVIADO", True),
    (None, False)])
def test_exporting_is_offered_for_closed_or_sent_pedidos_only(
        estado_pedido, esperada):
    acciones = pr.acciones_de(_corrida(), estado_pedido)

    assert acciones["exportar"] is esperada


def test_exporting_is_never_offered_for_a_scenario_or_uncalculated_corrida():
    for estado_pedido in ("CERRADO", "ENVIADO"):
        assert pr.acciones_de(
            _corrida(es_escenario=True), estado_pedido)["exportar"] is False
        for estado in ("PENDIENTE", "CALCULANDO", "FALLIDA", "ANULADA"):
            assert pr.acciones_de(
                _corrida(estado=estado), estado_pedido)["exportar"] is False


def test_exporting_is_blocked_by_an_invalidated_corrida_like_the_service():
    assert pr.acciones_de(
        _corrida(invalidada=True), "CERRADO")["exportar"] is False


def test_a_legacy_cerrada_corrida_still_offers_exporting():
    assert pr.acciones_de(
        _corrida(estado="CERRADA"), "CERRADO")["exportar"] is True


# --- Consulta de los envíos --------------------------------------------------


async def test_the_envios_come_keyed_by_tienda_in_one_query():
    db = FakeAsyncSession(execute_queue=[[
        _fila_envio(SUC_A, "12345"), _fila_envio(SUC_B, "12346", None)]])

    envios = await lp.envios_de(db, fx.CORRIDA_ID, None)

    assert envios == {
        SUC_A: pr.EnvioTienda("12345", FECHA, "Maria", ENVIADO_EN),
        SUC_B: pr.EnvioTienda("12346", FECHA, None, ENVIADO_EN)}
    assert len(db.executed_statements) == 1
    sql = _sql(db.executed_statements[0])
    assert "FROM corrida_envio LEFT OUTER JOIN usuario" in sql
    assert f"corrida_envio.corrida_id = '{fx.CORRIDA_ID}'" in sql
    assert "IN (" not in sql


async def test_the_envios_can_be_narrowed_to_one_tienda_and_to_the_scope():
    db = FakeAsyncSession(execute_queue=[[]])

    assert await lp.envios_de(
        db, fx.CORRIDA_ID, frozenset({SUC_A}), SUC_A) == {}

    sql = _sql(db.executed_statements[0])
    assert f"corrida_envio.sucursal_id IN ('{SUC_A}')" in sql
    assert f"corrida_envio.sucursal_id = '{SUC_A}'" in sql


# --- Detalle y cabecera: cuándo se consulta ----------------------------------


def _cola_detalle(sucursales, envios=None):
    """Corrida, sucursales, resumen, cargas, a pedir, eventos, the
    envios (only with a sent tienda) and the corrida totals (last)."""
    cola = [[_corrida()], sucursales, [], [], [], []]
    return cola + ([envios] if envios is not None else []) + [[]]


async def test_a_detail_with_a_sent_tienda_asks_one_extra_query_for_envios():
    db = FakeAsyncSession(execute_queue=_cola_detalle(
        [_suc(SUC_A, "UNO", 1, estado_pedido="ENVIADO"),
         _suc(SUC_B, "DOS", 2, estado_pedido="CERRADO")],
        [_fila_envio()]))

    detalle = await cq.detalle(db, fx.CORRIDA_ID, None)

    assert len(db.executed_statements) == 8
    assert "FROM corrida_envio" in _sql(db.executed_statements[6])
    uno, dos = detalle["sucursales"]
    assert uno["envio"] == BLOQUE and dos["envio"] is None


async def test_a_detail_with_no_sent_tienda_pays_for_no_extra_query():
    db = FakeAsyncSession(execute_queue=_cola_detalle(
        [_suc(SUC_A, "UNO", 1, estado_pedido="CERRADO"),
         _suc(SUC_B, "DOS", 2, estado_pedido="BORRADOR")]))

    detalle = await cq.detalle(db, fx.CORRIDA_ID, None)

    assert len(db.executed_statements) == 7
    assert [s["envio"] for s in detalle["sucursales"]] == [None, None]


async def test_a_scoped_detail_scopes_the_envios_too():
    db = FakeAsyncSession(execute_queue=_cola_detalle(
        [_suc(SUC_A, "UNO", 1, estado_pedido="ENVIADO")], [_fila_envio()]))

    await cq.detalle(db, fx.CORRIDA_ID, frozenset({SUC_A}))

    assert f"corrida_envio.sucursal_id IN ('{SUC_A}')" in _sql(
        db.executed_statements[6])


def _fila_cabecera(estado_pedido):
    tienda = _suc(SUC_A, "UNO", 1, estado_pedido=estado_pedido)
    return (_corrida(), tienda, "UNO", "SIC-1")


TOTALES = (1, 2, 3, 4)


async def test_the_header_of_a_sent_tienda_adds_its_envio_with_one_query():
    db = FakeAsyncSession(execute_queue=[
        [_fila_cabecera("ENVIADO")], [TOTALES], [], [_fila_envio()]])

    cuerpo = await lp.cabecera_tienda(db, fx.CORRIDA_ID, SUC_A, None)

    assert cuerpo["envio"] == BLOQUE
    assert len(db.executed_statements) == 4
    assert f"corrida_envio.sucursal_id = '{SUC_A}'" in _sql(
        db.executed_statements[3])


async def test_the_header_of_a_tienda_not_sent_has_no_envio_nor_extra_query():
    db = FakeAsyncSession(execute_queue=[
        [_fila_cabecera("CERRADO")], [TOTALES], []])

    cuerpo = await lp.cabecera_tienda(db, fx.CORRIDA_ID, SUC_A, None)

    assert cuerpo["envio"] is None
    assert len(db.executed_statements) == 3


# --- HTTP --------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "envio-lectura")
    monkeypatch.setattr(settings, "SECRET_KEY", "envio-lectura-asc360")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def espia(monkeypatch):
    doble = fx.instalar(monkeypatch)
    app.dependency_overrides[api.get_corrida_runner] = (
        lambda: fx.RunnerDoble(doble))
    return doble


def _cliente():
    override_motored_user(MotoredUser(user_id=USUARIO, role="COMPRAS"))
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 8))
    return TestClient(app)


def test_the_header_serves_the_envio_block_of_a_sent_tienda(espia):
    espia.cabecera = fx.cabecera_tienda(
        estado_pedido="ENVIADO", envio=BLOQUE,
        acciones={"corregir_envio": True, "exportar": True})

    cuerpo = _cliente().get(
        f"{BASE}/{fx.CORRIDA_ID}/sucursales/{fx.SUC_A}").json()

    assert cuerpo["envio"] == JSON_BLOQUE
    assert cuerpo["acciones"]["exportar"] is True


def test_the_header_of_a_tienda_not_sent_serves_a_null_envio(espia):
    cuerpo = _cliente().get(
        f"{BASE}/{fx.CORRIDA_ID}/sucursales/{fx.SUC_A}").json()

    assert "envio" in cuerpo and cuerpo["envio"] is None
    assert cuerpo["acciones"]["exportar"] is False


def test_the_detail_serves_the_envio_block_in_each_tienda_row(espia):
    espia.detalle = fx.detalle(sucursales=[
        fx.sucursal_estado(SUC_A, "UNO", estado_pedido="ENVIADO",
                           envio=BLOQUE),
        fx.sucursal_estado(SUC_B, "DOS", estado_pedido="CERRADO")])

    filas = _cliente().get(f"{BASE}/{fx.CORRIDA_ID}").json()["sucursales"]

    assert filas[0]["envio"] == JSON_BLOQUE
    assert "envio" in filas[1] and filas[1]["envio"] is None


def test_the_envio_schema_has_exactly_the_four_documented_fields():
    assert set(EnvioInfo.model_fields) == {
        "numero_orden", "fecha_envio", "enviado_por", "enviado_en"}
