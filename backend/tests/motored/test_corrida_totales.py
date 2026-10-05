"""
Motored Pedidos: the totals of a whole corrida (value, distinct
referencias and units to order), shown above the tabs of the detail and on
each row of the corridas list.

The rule lives in `services/corridas/totales_corrida.py`: the same
aggregate the Tiendas tab adds per store (`pedido_final` and
`valor_pedido` of the non-excluded lines), plus the DISTINCT referencia
codes with a quantity above zero. The list reads it inside its page query
(a LATERAL aggregate), so the list still costs three queries; the detail
adds one read. Postgres runs the same SQL in
`pg_real/test_corrida_totales_pg.py`.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.main import app
from app.motored.schemas.corrida import CorridaItem, TotalesCorrida
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import consultas as cq
from app.motored.services.corridas import totales_corrida as tc
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)
from tests.motored.fixtures import corridas_api as fx
from tests.motored.test_corrida_consultas import _corrida, _fila_lista

D = Decimal
BASE = "/api/motored/corridas"


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


async def _listar(db):
    return await cq.listar(
        db, alcance=None, proveedor_id=None, estado=None, desde=None,
        hasta=None, escenario=None, limite=50, offset=0)


# --- The pure projection ----------------------------------------------------


def test_a_calculated_corrida_projects_its_three_totals():
    totales = tc.proyectar("BORRADOR", D("2100.00"), 3, D("24.00"))

    assert totales == {
        "valor_total": D("2100.00"), "referencias": 3,
        "unidades": D("24.00")}


def test_a_calculated_corrida_without_lines_has_zero_totals():
    totales = tc.proyectar("CERRADA", None, None, None)

    assert totales == {
        "valor_total": D("0"), "referencias": 0, "unidades": D("0")}


@pytest.mark.parametrize(
    "estado", ["PENDIENTE", "CALCULANDO", "FALLIDA", "ANULADA"])
def test_a_corrida_not_calculated_has_no_totals(estado):
    assert tc.proyectar(estado, D("10.00"), 1, D("1.00")) is None


# --- The SQL rule -----------------------------------------------------------


def test_the_aggregate_is_the_tiendas_rule_plus_distinct_referencias():
    sql = _sql(tc.consulta_de_corrida(uuid.UUID(int=1), None))

    assert "sum(corrida_linea.valor_pedido)" in sql
    assert "sum(corrida_linea.pedido_final)" in sql
    assert ("count(DISTINCT corrida_linea.codigo_referencia) FILTER "
            "(WHERE corrida_linea.pedido_final > 0)") in sql
    assert "corrida_linea.motivo_exclusion IS NULL" in sql


def test_a_scoped_aggregate_only_reads_the_visible_sucursales():
    visible = uuid.UUID(int=601)

    sql = _sql(tc.consulta_de_corrida(uuid.UUID(int=1), frozenset({visible})))

    assert f"corrida_linea.sucursal_id IN ('{visible}'" in sql


# --- The list: inside the page query ---------------------------------------


async def test_the_list_reads_the_totals_inside_its_page_query():
    db = FakeAsyncSession(execute_queue=[[1], [_fila_lista()], []])

    await _listar(db)

    pagina = _sql(db.executed_statements[1])
    assert "LATERAL" in pagina
    assert "count(DISTINCT corrida_linea.codigo_referencia)" in pagina
    assert len(db.executed_statements) == 3


async def test_each_list_item_carries_its_totals():
    fila = _fila_lista(
        estado="BORRADOR", valor_total=D("2100.00"),
        referencias_total=3, unidades_total=D("24.00"))
    db = FakeAsyncSession(execute_queue=[[1], [fila], []])

    items, _ = await _listar(db)

    assert items[0]["totales_corrida"] == {
        "valor_total": D("2100.00"), "referencias": 3,
        "unidades": D("24.00")}


async def test_a_list_item_still_calculating_has_null_totals():
    fila = _fila_lista(
        estado="CALCULANDO", valor_total=None, referencias_total=0,
        unidades_total=None)
    db = FakeAsyncSession(execute_queue=[[1], [fila], []])

    items, _ = await _listar(db)

    assert items[0]["totales_corrida"] is None


# --- The detail: one more read ---------------------------------------------


async def test_the_detail_adds_one_read_for_its_totals():
    totales = SimpleNamespace(
        valor_total=D("2100.00"), referencias_total=3,
        unidades_total=D("24.00"))
    # corrida, sucursales, resumen, cargas, a pedir, eventos, totales.
    db = FakeAsyncSession(
        execute_queue=[[_corrida()], [], [], [], [], [], [totales]])

    cuerpo = await cq.detalle(db, fx.CORRIDA_ID, None)

    assert len(db.executed_statements) == 7
    assert cuerpo["totales_corrida"] == {
        "valor_total": D("2100.00"), "referencias": 3,
        "unidades": D("24.00")}


async def test_a_detail_still_calculating_skips_the_read():
    db = FakeAsyncSession(
        execute_queue=[[_corrida(estado="CALCULANDO")], [], [], [], [], []])

    cuerpo = await cq.detalle(db, fx.CORRIDA_ID, None)

    assert len(db.executed_statements) == 6
    assert cuerpo["totales_corrida"] is None


# --- The schema and the HTTP contract --------------------------------------


def test_the_schema_serializes_money_and_units_as_exact_text():
    item = CorridaItem(**fx.item_lista(totales_corrida=TotalesCorrida(
        valor_total=D("2100.00"), referencias=3, unidades=D("24.00"))))

    assert item.model_dump(mode="json")["totales_corrida"] == {
        "valor_total": "2100.00", "referencias": 3, "unidades": "24.00"}


def test_the_schema_defaults_the_totals_to_null():
    assert CorridaItem(**fx.item_lista()).totales_corrida is None


@pytest.fixture
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "totales-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "totales-asc360")
    yield
    app.dependency_overrides.clear()


def test_the_http_list_exposes_the_totals(monkeypatch, _listo):
    doble = fx.instalar(monkeypatch)
    doble.lista = ([fx.item_lista(totales_corrida={
        "valor_total": D("2100.00"), "referencias": 3,
        "unidades": D("24.00")}), fx.item_lista(
        id=uuid.UUID(int=502), codigo="PED-2026-S39-002")], 2)
    override_motored_user(MotoredUser(user_id=str(uuid.UUID(int=900)),
                                      role="COMPRAS"))
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 8))

    items = TestClient(app).get(BASE).json()["items"]

    assert items[0]["totales_corrida"] == {
        "valor_total": "2100.00", "referencias": 3, "unidades": "24.00"}
    assert items[1]["totales_corrida"] is None
