"""
Configuración tab "Ingresos de facturas" (odd/motored-ingresos-responsable-
plantilla, T1): the advisor threshold and the fixed values of the ERP
"Entradas x Compra" template.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import parametros as parametros_api
from app.motored.services import parametros_claves as pc
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import codigos
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

DEFAULTS = {
    "ingreso_umbral_referencias_asesor": 10,
    "ingreso_plantilla_tipo_documento": 16,
    "ingreso_plantilla_descuento_global": 5,
    "ingreso_plantilla_proveedor_nit": 900723988,
    "ingreso_plantilla_sucursal_proveedor": "001",
    "ingreso_plantilla_comprador": 1151943311,
    "ingreso_plantilla_descuento_item": 0,
    "ingreso_plantilla_unidad_negocio": "003",
    "ingreso_tipos_pedido_excluidos": ["GARANTIA25"],
}
URL = "/api/motored/parametros"


def test_the_constants_map_to_the_registry_with_the_owner_defaults():
    assert pc.CLAVES_INGRESOS == tuple(DEFAULTS)
    for clave, default in DEFAULTS.items():
        assert pc.REGISTRO[clave].default == default
    assert pc.RESPALDOS_INGRESOS == DEFAULTS


@pytest.mark.parametrize("clave", list(DEFAULTS))
def test_the_keys_live_in_the_ingresos_tab_and_are_not_snapshotted(clave):
    ficha = pc.ficha(pc.REGISTRO[clave])
    assert ficha["seccion"] == "ingresos"
    assert ficha["grupo"] == pc.GRUPO_OPERACION
    assert ficha["snapshotted"] is False


def test_ingresos_is_a_known_tab():
    assert "ingresos" in pc.SECCIONES


@pytest.mark.parametrize("clave", list(DEFAULTS))
def test_the_defaults_are_valid(clave):
    pc.validar_escritura(clave, DEFAULTS[clave])


@pytest.mark.parametrize("valor", [0, -1, "10", 1.5, None, True, 1001])
def test_the_threshold_must_be_an_integer_from_1_to_1000(valor):
    with pytest.raises(pc.ErrorParametro) as error:
        pc.validar_escritura("ingreso_umbral_referencias_asesor", valor)
    assert error.value.codigo == codigos.E_PARAM_VALOR_INVALIDO


@pytest.mark.parametrize("clave", [
    "ingreso_plantilla_sucursal_proveedor", "ingreso_plantilla_unidad_negocio"])
@pytest.mark.parametrize("valor", [1, "", "  ", "12a", "1234567", None, "0 1"])
def test_the_text_keys_refuse_non_digit_text(clave, valor):
    with pytest.raises(pc.ErrorParametro):
        pc.validar_escritura(clave, valor)


def test_the_text_keys_keep_leading_zeros():
    pc.validar_escritura("ingreso_plantilla_unidad_negocio", "007")
    assert pc.parsear("ingreso_plantilla_unidad_negocio", "007") == "007"


@pytest.mark.parametrize("clave", [
    "ingreso_plantilla_tipo_documento", "ingreso_plantilla_proveedor_nit",
    "ingreso_plantilla_comprador"])
@pytest.mark.parametrize("valor", [0, -5, "16", 1.5, None, True])
def test_the_numeric_identifiers_refuse_non_positive_or_non_integers(
        clave, valor):
    with pytest.raises(pc.ErrorParametro):
        pc.validar_escritura(clave, valor)


@pytest.mark.parametrize("clave", [
    "ingreso_plantilla_descuento_global", "ingreso_plantilla_descuento_item"])
def test_the_discounts_accept_0_to_100_with_decimals(clave):
    pc.validar_escritura(clave, 0)
    pc.validar_escritura(clave, 12.5)
    for malo in (-1, 100.01, "abc", None, True):
        with pytest.raises(pc.ErrorParametro):
            pc.validar_escritura(clave, malo)


@pytest.fixture
def _api(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "ing-test-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "ing-test-asc360-secret")
    monkeypatch.setattr(
        parametros_api, "hoy_bogota", lambda: datetime.date(2026, 10, 15))
    override_motored_user(
        MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    db = FakeAsyncSession(execute_queue=[[]] * 4)
    override_motored_db(db)
    yield TestClient(app), db
    app.dependency_overrides.clear()


@pytest.mark.parametrize("clave,valor", [
    ("ingreso_umbral_referencias_asesor", 15),
    ("ingreso_plantilla_sucursal_proveedor", "002"),
    ("ingreso_plantilla_descuento_global", 7.5),
])
def test_the_api_stores_a_valid_value(_api, clave, valor):
    client, db = _api

    respuesta = client.post(URL, json={
        "clave": clave, "valor": valor, "vigente_desde": "2026-10-01"})

    assert respuesta.status_code == 201, respuesta.text
    assert db.added[0].valor == valor


def test_the_api_refuses_an_invalid_threshold(_api):
    client, db = _api

    respuesta = client.post(URL, json={
        "clave": "ingreso_umbral_referencias_asesor", "valor": 0,
        "vigente_desde": "2026-10-01"})

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == []


@pytest.mark.parametrize("valor", [[], [""], ["  "], "GARANTIA25", None, [1]])
def test_the_excluded_types_list_cannot_be_saved_empty_or_malformed(valor):
    with pytest.raises(pc.ErrorParametro) as error:
        pc.validar_escritura("ingreso_tipos_pedido_excluidos", valor)
    assert error.value.codigo == codigos.E_PARAM_VALOR_INVALIDO
