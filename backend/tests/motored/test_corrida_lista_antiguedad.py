"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, corrección V1 del
verify W2, spec UX-06): la lista de corridas avisa cuando los datos de
entrada de una corrida son viejos.

El aviso sale del bloque `antiguedad` que la corrida ya congeló (el mismo
que muestra el detalle), sin recalcular nada y SIN consulta extra: la
columna viaja en el SELECT de la página. Cuatro capas: la proyección pura
(`peor_antiguedad`), el renglón de la lista, el SQL y el contrato HTTP.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.main import app
from app.motored.schemas.corrida import CorridaItem
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import consultas as cq
from app.motored.services.corridas import proyecciones as pr
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)
from tests.motored.fixtures import corridas_api as fx
from tests.motored.test_corrida_consultas import _fila_lista

BASE = "/api/motored/corridas"
USUARIO = str(uuid.UUID(int=900))


def _dato(dias, limite):
    return {
        "carga_id": str(uuid.UUID(int=1)), "fecha_usada": "2026-09-19",
        "antiguedad_dias": dias, "limite_dias": limite,
        "fuente_limite": "DEFAULT"}


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


# --- La proyección pura -----------------------------------------------------


def test_the_worst_dataset_is_the_one_closest_to_its_limit():
    bloque = {
        "inventario": _dato(2, 7), "backorder": _dato(6, 7),
        "facturas": _dato(1, 7), "ingresos": _dato(5, 30)}

    peor = pr.peor_antiguedad(bloque)

    assert peor == {
        "dataset": "backorder", "antiguedad_dias": 6, "limite_dias": 7,
        "supera_limite": False}


def test_a_dataset_over_its_limit_is_flagged():
    bloque = {"inventario": _dato(2, 7), "facturas": _dato(9, 7)}

    peor = pr.peor_antiguedad(bloque)

    assert peor["dataset"] == "facturas"
    assert (peor["antiguedad_dias"], peor["limite_dias"]) == (9, 7)
    assert peor["supera_limite"] is True


def test_the_margin_beats_the_raw_age_across_different_limits():
    bloque = {"inventario": _dato(20, 90), "backorder": _dato(5, 7)}

    assert pr.peor_antiguedad(bloque)["dataset"] == "backorder"


def test_a_tie_keeps_the_first_dataset_of_the_block():
    bloque = {"inventario": _dato(3, 7), "backorder": _dato(3, 7)}

    assert pr.peor_antiguedad(bloque)["dataset"] == "inventario"


def test_entries_without_age_or_limit_are_ignored():
    bloque = {
        "inventario": {"antiguedad_dias": None, "limite_dias": 7},
        "backorder": {"antiguedad_dias": 4, "limite_dias": None},
        "facturas": _dato(1, 7)}

    assert pr.peor_antiguedad(bloque)["dataset"] == "facturas"


@pytest.mark.parametrize("bloque", [None, {}, {"inventario": {}}])
def test_no_usable_evidence_yields_no_warning_data(bloque):
    assert pr.peor_antiguedad(bloque) is None


# --- El renglón de la lista --------------------------------------------------


def test_the_list_item_carries_the_worst_age_of_its_row():
    fila = _fila_lista(antiguedad_datos={"facturas": _dato(9, 7)})

    item = pr.item_de_fila(fila)

    assert item["antiguedad_peor"]["dataset"] == "facturas"
    assert item["antiguedad_peor"]["supera_limite"] is True


def test_a_row_without_frozen_evidence_has_no_age_data():
    assert pr.item_de_fila(_fila_lista())["antiguedad_peor"] is None
    sin = _fila_lista(antiguedad_datos=None)
    assert pr.item_de_fila(sin)["antiguedad_peor"] is None


def test_the_schema_accepts_and_defaults_the_new_field():
    base = fx.item_lista()

    assert CorridaItem(**base).antiguedad_peor is None
    con = CorridaItem(**base, antiguedad_peor={
        "dataset": "facturas", "antiguedad_dias": 9, "limite_dias": 7,
        "supera_limite": True})
    assert con.antiguedad_peor.dataset == "facturas"


# --- El SQL: sin consulta extra ---------------------------------------------


async def _listar(db):
    return await cq.listar(
        db, alcance=None, proveedor_id=None, estado=None, desde=None,
        hasta=None, escenario=None, limite=50, offset=0)


async def test_the_page_select_extracts_only_the_antiguedad_block():
    db = FakeAsyncSession(execute_queue=[[1], [_fila_lista()], []])

    await _listar(db)

    pagina = _sql(db.executed_statements[1])
    assert "corrida.seleccion_datos['antiguedad']" in pagina
    assert "corrida.seleccion_datos," not in pagina
    assert "corrida.seleccion_datos AS" not in pagina


async def test_the_list_still_costs_three_queries_whatever_the_page_size():
    filas = [_fila_lista(id=uuid.UUID(int=n)) for n in range(1, 6)]
    db = FakeAsyncSession(execute_queue=[[5], filas, []])

    items, _ = await _listar(db)

    assert len(items) == 5
    assert len(db.executed_statements) == 3


async def test_the_list_returns_the_age_data_per_row():
    viejas = _fila_lista(
        id=uuid.UUID(int=1), antiguedad_datos={"facturas": _dato(9, 7)})
    frescas = _fila_lista(
        id=uuid.UUID(int=2), antiguedad_datos={"facturas": _dato(1, 7)})
    db = FakeAsyncSession(execute_queue=[[2], [viejas, frescas], []])

    items, _ = await _listar(db)

    assert [i["antiguedad_peor"]["supera_limite"] for i in items] == [
        True, False]


# --- El contrato HTTP --------------------------------------------------------


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "lista-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "lista-asc360")
    yield
    app.dependency_overrides.clear()


def test_the_http_list_exposes_the_age_warning_fields(monkeypatch):
    doble = fx.instalar(monkeypatch)
    doble.lista = ([fx.item_lista(antiguedad_peor={
        "dataset": "facturas", "antiguedad_dias": 9, "limite_dias": 7,
        "supera_limite": True}), fx.item_lista(
        id=uuid.UUID(int=502), codigo="PED-2026-S39-002")], 2)
    override_motored_user(MotoredUser(user_id=USUARIO, role="COMPRAS"))
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 8))

    items = TestClient(app).get(BASE).json()["items"]

    assert items[0]["antiguedad_peor"] == {
        "dataset": "facturas", "antiguedad_dias": 9, "limite_dias": 7,
        "supera_limite": True}
    assert items[1]["antiguedad_peor"] is None
