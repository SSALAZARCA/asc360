"""
Motored "Configuración", Indicadores: the three keys of the KPI's Inventario tab
(target days, color cuts and the idle threshold), their defaults and validation.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.services import parametros_claves as pc
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import codigos
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

CLAVES = ("kpi_inventario_dias_meta", "kpi_inventario_dias_cortes",
          "kpi_inventario_sin_movimiento_dias")


def _acepta(clave, valor):
    pc.validar_escritura(clave, valor)


def _rechaza(clave, valor):
    with pytest.raises(pc.ErrorParametro) as error:
        pc.validar_escritura(clave, valor)
    assert error.value.codigo == codigos.E_PARAM_VALOR_INVALIDO


def test_the_keys_are_registered_in_the_indicadores_section_with_their_defaults():
    for clave in CLAVES:
        espec = pc.REGISTRO[clave]
        assert espec.seccion == "indicadores"
        assert espec.grupo == pc.GRUPO_OPERACION
    assert pc.REGISTRO["kpi_inventario_dias_meta"].default == 60
    assert pc.REGISTRO["kpi_inventario_dias_cortes"].default == {
        "verde_hasta": 60, "ambar_hasta": 90}
    assert pc.REGISTRO["kpi_inventario_sin_movimiento_dias"].default == 180


@pytest.mark.parametrize("clave", ["kpi_inventario_dias_meta",
                                   "kpi_inventario_sin_movimiento_dias"])
@pytest.mark.parametrize("valor", [1, 60, 365])
def test_the_day_counts_accept_whole_numbers_in_range(clave, valor):
    _acepta(clave, valor)


@pytest.mark.parametrize("clave", ["kpi_inventario_dias_meta",
                                   "kpi_inventario_sin_movimiento_dias"])
@pytest.mark.parametrize("valor", [0, -1, 3651, 1.5, "60", True, None])
def test_the_day_counts_reject_zero_negative_text_and_decimals(clave, valor):
    _rechaza(clave, valor)


@pytest.mark.parametrize("valor", [
    {"verde_hasta": 60, "ambar_hasta": 90},
    {"verde_hasta": 0, "ambar_hasta": 1},
    {"verde_hasta": "45.5", "ambar_hasta": "90"},
])
def test_the_cuts_accept_an_increasing_pair(valor):
    _acepta("kpi_inventario_dias_cortes", valor)


@pytest.mark.parametrize("valor", [
    {"verde_hasta": 90, "ambar_hasta": 90},
    {"verde_hasta": 100, "ambar_hasta": 90},
    {"verde_hasta": 60},
    {"verde_hasta": 60, "ambar_hasta": 90, "otro": 1},
    {"verde_hasta": -1, "ambar_hasta": 90},
    {"verde_hasta": "x", "ambar_hasta": 90},
    {"verde_hasta": 60, "ambar_hasta": 3651},
])
def test_the_cuts_reject_a_wrong_order_or_shape(valor):
    _rechaza("kpi_inventario_dias_cortes", valor)


def test_the_cuts_ficha_tells_the_page_its_fields():
    ficha = pc.ficha(pc.REGISTRO["kpi_inventario_dias_cortes"])
    assert ficha["campos"] == ["verde_hasta", "ambar_hasta"]


# --- through the API -----------------------------------------------------------

URL = "/api/motored/parametros"


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "cfg-test-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "cfg-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    db = FakeAsyncSession(execute_queue=[[]] * 4)
    override_motored_db(db)
    yield TestClient(app), db
    app.dependency_overrides.clear()


def test_the_configuration_page_lists_the_three_keys_in_indicadores(cliente):
    client, _ = cliente
    db = FakeAsyncSession(execute_queue=[[], [], []])
    override_motored_db(db)

    secciones = client.get(f"{URL}/configuracion").json()["secciones"]

    indicadores = next(s for s in secciones if s["seccion"] == "indicadores")
    claves = {c["clave"]: c for g in indicadores["grupos"] for c in g["claves"]}
    assert set(CLAVES) <= set(claves)
    assert claves["kpi_inventario_dias_meta"]["default"] == 60
    assert claves["kpi_inventario_dias_cortes"]["campos"] == ["verde_hasta", "ambar_hasta"]


def test_posting_a_valid_cut_pair_is_created(cliente):
    client, db = cliente

    respuesta = client.post(URL, json={
        "clave": "kpi_inventario_dias_cortes",
        "valor": {"verde_hasta": 45, "ambar_hasta": 75}, "vigente_desde": "2026-10-01"})

    assert respuesta.status_code == 201, respuesta.text
    assert db.added[0].valor == {"verde_hasta": 45, "ambar_hasta": 75}


def test_posting_an_inverted_cut_pair_is_a_422_and_stores_nothing(cliente):
    client, db = cliente

    respuesta = client.post(URL, json={
        "clave": "kpi_inventario_dias_cortes",
        "valor": {"verde_hasta": 90, "ambar_hasta": 60}, "vigente_desde": "2026-10-01"})

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == []


def test_posting_a_zero_target_is_a_422(cliente):
    client, db = cliente

    respuesta = client.post(URL, json={
        "clave": "kpi_inventario_dias_meta", "valor": 0, "vigente_desde": "2026-10-01"})

    assert respuesta.status_code == 422
    assert db.added == []
