"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B6, ADR-9, decisión
F4-8, spec SC-01/SC-04): el catálogo de claves que el lanzador de escenarios
del ADMIN usa para armar sus campos, `GET /api/motored/parametros/claves`.

- `parametros_claves.catalogo`: puro. Cada clave del grupo con su tipo, su
  dominio, su valor por defecto y, si es de opciones, la lista de opciones.
  Las claves de tope de presupuesto (grupo PEDIDO) y las de la ingesta no
  entran: no son del motor, así que no se pueden usar de override
  (E-CORRIDA-010).
- El endpoint: ADMIN y COMPRAS (el resto, 403; sin sesión, 401). Sólo el
  grupo MOTOR. No hace consultas: lee el registro en memoria.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.services import parametros_claves as pc
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

URL = "/api/motored/parametros/claves"
TOPES = ["modo_tope_presupuesto", "presupuesto_maximo_pedido"]
DENEGADOS = ["CONSULTA", "SUCURSAL", "SERVICIO_CLIENTE", "ASESOR_MOSTRADOR"]


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "claves-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "claves-asc360")
    yield
    app.dependency_overrides.clear()


def _como(rol):
    override_motored_user(
        MotoredUser(user_id=str(uuid.UUID(int=900)), role=rol))
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))
    return TestClient(app)


def _por_clave(entradas):
    return {e["clave"]: e for e in entradas}


# --- El catálogo ------------------------------------------------------------


def test_the_catalog_lists_every_motor_key_in_registry_order_sc_01():
    claves = [e["clave"] for e in pc.catalogo(pc.GRUPO_MOTOR)]

    assert claves == pc.claves_motor()


def test_the_budget_keys_are_not_in_the_motor_catalog_sc_04():
    claves = [e["clave"] for e in pc.catalogo(pc.GRUPO_MOTOR)]

    for clave in TOPES:
        assert clave not in claves


def test_the_ingestion_keys_are_not_in_the_motor_catalog():
    ingesta = {c for c, e in pc.REGISTRO.items()
               if e.grupo == pc.GRUPO_INGESTA}
    claves = {e["clave"] for e in pc.catalogo(pc.GRUPO_MOTOR)}

    assert ingesta and not ingesta & claves


def test_each_entry_has_its_type_domain_and_default():
    entradas = _por_clave(pc.catalogo(pc.GRUPO_MOTOR))

    consolidar = entradas["consolidar_sustituidas"]
    assert consolidar["tipo"] == "bool"
    assert consolidar["default"] is False
    assert consolidar["dominio"] == "verdadero o falso"
    dias = entradas["dias_entre_pedidos"]
    assert dias["tipo"] == "entero" and dias["default"] == 30
    assert dias["dominio"] == "un entero entre 1 y 60"
    assert entradas["factor_demanda_perdida"]["tipo"] == "decimal"


def test_an_options_key_lists_its_options():
    entrada = _por_clave(pc.catalogo(pc.GRUPO_MOTOR))["modo_mes_en_curso"]

    assert entrada["tipo"] == "opcion"
    assert entrada["opciones"] == ["EXCLUIDO", "PONDERADO"]
    assert entrada["default"] == "EXCLUIDO"


def test_a_key_without_options_has_no_options_entry():
    entradas = pc.catalogo(pc.GRUPO_MOTOR)

    for entrada in entradas:
        assert ("opciones" in entrada) == (entrada["tipo"] == "opcion")


def test_k_fms_is_a_typed_object_with_its_three_values():
    entrada = _por_clave(pc.catalogo(pc.GRUPO_MOTOR))["k_fms"]

    assert entrada["tipo"] == "k_fms"
    assert entrada["default"] == {"F": "3", "M": "1.5", "S": "1"}


def test_the_catalog_hands_out_copies_of_the_defaults():
    entrada = _por_clave(pc.catalogo(pc.GRUPO_MOTOR))["k_fms"]
    entrada["default"]["F"] = "999"

    assert pc.REGISTRO["k_fms"].default["F"] == "3"


def test_every_default_in_the_catalog_passes_its_own_validation():
    for entrada in pc.catalogo(pc.GRUPO_MOTOR):
        pc.validar_escritura(entrada["clave"], entrada["default"])


# --- El endpoint ------------------------------------------------------------


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS"])
def test_admin_and_compras_read_the_catalog_sc_01(rol):
    respuesta = _como(rol).get(URL, params={"grupo": "MOTOR"})

    assert respuesta.status_code == 200, respuesta.text
    entradas = respuesta.json()
    assert [e["clave"] for e in entradas] == pc.claves_motor()
    for clave in TOPES:
        assert clave not in {e["clave"] for e in entradas}


def test_the_group_defaults_to_motor():
    respuesta = _como("ADMIN").get(URL)

    assert [e["clave"] for e in respuesta.json()] == pc.claves_motor()


def test_the_json_carries_options_only_for_options_keys():
    entradas = _por_clave(_como("ADMIN").get(URL).json())

    assert entradas["modo_redondeo_empaque"]["opciones"] == [
        "CERCANO", "ARRIBA"]
    assert "opciones" not in entradas["consolidar_sustituidas"]
    assert entradas["dias_entre_pedidos"]["default"] == 30


@pytest.mark.parametrize("grupo", ["PEDIDO", "INGESTA", "otro"])
def test_only_the_motor_group_is_served(grupo):
    respuesta = _como("ADMIN").get(URL, params={"grupo": grupo})

    assert respuesta.status_code == 422


@pytest.mark.parametrize("rol", DENEGADOS)
def test_the_other_roles_get_403(rol):
    assert _como(rol).get(URL).status_code == 403


def test_without_a_session_the_catalog_is_401():
    app.dependency_overrides.clear()
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))

    assert TestClient(app).get(URL).status_code == 401
