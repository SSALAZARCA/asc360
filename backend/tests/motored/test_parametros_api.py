"""
Motored Pedidos F3 "Motor", S4b (sdd/motored-pedidos-motor, ADR-7): la
lista blanca de claves en `POST /api/motored/parametros`.

Sólo las ESCRITURAS nuevas se validan. La lectura de una clave ya guardada,
conocida o no, no pasa por el registro.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import parametros as parametros_api
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.sucursal import Sucursal
from app.motored.services.auth import MotoredUser
from app.motored.services.parametros_claves import REGISTRO
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

URL = "/api/motored/parametros"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "param-test-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "param-test-asc360-secret")
    # La regla "no escribir en un mes pasado" depende del reloj: se fija.
    monkeypatch.setattr(
        parametros_api, "hoy_bogota", lambda: datetime.date(2026, 10, 15))
    yield
    app.dependency_overrides.clear()


def _cliente(execute_queue=None, get_queue=None):
    override_motored_user(
        MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    db = FakeAsyncSession(
        execute_queue=execute_queue or [[]] * 4, get_queue=get_queue)
    override_motored_db(db)
    return TestClient(app), db


def _cuerpo(clave, valor, **extra):
    return {"clave": clave, "valor": valor,
            "vigente_desde": "2026-10-01", **extra}


def test_a_registered_key_with_a_valid_value_is_created():
    client, db = _cliente()

    respuesta = client.post(URL, json=_cuerpo("dias_entre_pedidos", 15))

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["clave"] == "dias_entre_pedidos"
    assert db.added[0].valor == 15 and db.committed is True


def test_an_unknown_key_is_a_coded_422_and_writes_nothing():
    client, db = _cliente()

    respuesta = client.post(URL, json=_cuerpo("clave_que_no_existe", 1))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-001"
    assert "clave_que_no_existe" in respuesta.json()["detail"]["message"]
    assert db.added == [] and db.committed is False


def test_an_invalid_value_is_a_coded_422():
    client, db = _cliente()

    respuesta = client.post(URL, json=_cuerpo("dias_entre_pedidos", 0))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == []


def test_sucursal_scope_on_a_global_only_key_is_e_param_003():
    client, db = _cliente()

    respuesta = client.post(
        URL, json=_cuerpo(
            "consolidar_sustituidas", True, sucursal_id=str(uuid.uuid4())),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-003"
    assert db.added == []


def test_a_sucursal_scoped_row_is_stored_with_its_sucursal():
    sucursal = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE")
    client, db = _cliente(get_queue=[sucursal])

    respuesta = client.post(
        URL, json=_cuerpo(
            "dias_entre_pedidos", 7, sucursal_id=str(sucursal.id)),
    )

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["sucursal_id"] == str(sucursal.id)
    assert db.added[0].sucursal_id == sucursal.id


def test_a_sucursal_that_does_not_exist_is_a_coded_422():
    client, db = _cliente(get_queue=[None])

    respuesta = client.post(
        URL, json=_cuerpo(
            "dias_entre_pedidos", 7, sucursal_id=str(uuid.uuid4())),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == []


@pytest.mark.parametrize("clave", [
    "tipos_inventario_incluidos", "crear_referencias_desconocidas",
    "estados_backorder_vigentes", "dias_ventana_ingresos",
    "tolerancia_ingreso_pct",
])
def test_every_f2_ingest_key_can_still_be_written(clave):
    client, _db = _cliente()

    respuesta = client.post(URL, json=_cuerpo(clave, REGISTRO[clave].default))

    assert respuesta.status_code == 201, respuesta.text


def test_reading_a_stored_key_the_registry_does_not_know_still_works():
    fila = ParametroMetodologia(
        id=uuid.uuid4(), clave="clave_historica_rara", valor="x",
        vigente_desde=datetime.date(2026, 1, 1),
    )
    # El primer resultado vacío es la sonda de disponibilidad de Motored.
    client, _db = _cliente(execute_queue=[[], [fila]])

    respuesta = client.get(f"{URL}/clave_historica_rara/vigente")

    assert respuesta.status_code == 200
    assert respuesta.json()["valor"] == "x"
    assert respuesta.json()["sucursal_id"] is None


# --- F4 (B5a): el tope de presupuesto por `POST /parametros` ---------------


MODO = "modo_tope_presupuesto"
TOPE = "presupuesto_maximo_pedido"


def test_admin_can_switch_the_budget_mode_on_with_the_generic_endpoint():
    client, db = _cliente()

    respuesta = client.post(URL, json=_cuerpo(MODO, True))

    assert respuesta.status_code == 201, respuesta.text
    assert db.added[0].clave == MODO and db.added[0].valor is True
    assert db.added[0].sucursal_id is None and db.committed is True


@pytest.mark.parametrize("valor", ["true", 1, None, "si"])
def test_a_non_boolean_budget_switch_is_e_param_002(valor):
    client, db = _cliente()

    respuesta = client.post(URL, json=_cuerpo(MODO, valor))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == []


def test_the_budget_switch_with_a_sucursal_is_e_param_003():
    client, db = _cliente()

    respuesta = client.post(
        URL, json=_cuerpo(MODO, True, sucursal_id=str(uuid.uuid4())))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-003"
    assert db.added == []


def test_a_global_cap_is_a_coded_e_param_004_and_writes_nothing():
    client, db = _cliente()

    respuesta = client.post(URL, json=_cuerpo(TOPE, "80000000"))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-004"
    assert TOPE in respuesta.json()["detail"]["message"]
    assert db.added == [] and db.committed is False


def test_a_cap_with_a_sucursal_is_stored_for_that_sucursal():
    sucursal = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE")
    client, db = _cliente(get_queue=[sucursal])

    respuesta = client.post(
        URL, json=_cuerpo(TOPE, "80000000", sucursal_id=str(sucursal.id)))

    assert respuesta.status_code == 201, respuesta.text
    assert db.added[0].sucursal_id == sucursal.id
    assert db.added[0].valor == "80000000"


def test_a_null_cap_with_a_sucursal_is_a_valid_removal():
    sucursal = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE")
    client, db = _cliente(get_queue=[sucursal])

    respuesta = client.post(
        URL, json=_cuerpo(TOPE, None, sucursal_id=str(sucursal.id)))

    assert respuesta.status_code == 201, respuesta.text
    assert db.added[0].valor is None


@pytest.mark.parametrize("valor", [0, -5, "abc"])
def test_an_invalid_cap_value_is_e_param_002(valor):
    client, db = _cliente()

    respuesta = client.post(
        URL, json=_cuerpo(TOPE, valor, sucursal_id=str(uuid.uuid4())))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == []


@pytest.mark.parametrize("rol", ["COMPRAS", "CONSULTA", "SUCURSAL"])
def test_only_admin_writes_the_budget_keys_with_the_generic_endpoint(rol):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    db = FakeAsyncSession(execute_queue=[[]] * 4)
    override_motored_db(db)

    respuesta = TestClient(app).post(URL, json=_cuerpo(MODO, True))

    assert respuesta.status_code == 403
    assert db.added == [] and db.committed is False


# --- WU4 conteos: reconteo amount < critical amount -------------------------

RECONTEO = "conteo_umbral_reconteo_pesos"
CRITICO = "conteo_umbral_critico_pesos"


def _vigentes(monkeypatch, valores):
    llamadas = []

    async def falso(_db, fecha, respaldos):
        llamadas.append((fecha, dict(respaldos)))
        return {c: valores.get(c, d) for c, d in respaldos.items()}

    monkeypatch.setattr(parametros_api, "leer_valores", falso)
    return llamadas


def test_a_reconteo_amount_not_below_critical_is_a_spanish_422(monkeypatch):
    llamadas = _vigentes(monkeypatch, {CRITICO: 500000})
    client, db = _cliente()

    respuesta = client.post(URL, json=_cuerpo(RECONTEO, 500000))

    assert respuesta.status_code == 422
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "E-PARAM-002"
    assert "debe ser menor que el monto de diferencia" in detalle["message"]
    assert llamadas == [(datetime.date(2026, 10, 1), {CRITICO: 500000})]
    assert db.added == [] and db.committed is False


def test_a_critical_amount_not_above_reconteo_is_a_422(monkeypatch):
    _vigentes(monkeypatch, {RECONTEO: 300000})
    client, db = _cliente()

    respuesta = client.post(URL, json=_cuerpo(CRITICO, 200000))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == []


def test_a_reconteo_amount_below_critical_is_created(monkeypatch):
    _vigentes(monkeypatch, {CRITICO: 500000})
    client, db = _cliente()

    respuesta = client.post(URL, json=_cuerpo(RECONTEO, 150000))

    assert respuesta.status_code == 201, respuesta.text
    assert db.added[0].valor == 150000 and db.committed is True


def test_keys_without_a_relation_do_not_read_other_values(monkeypatch):
    llamadas = _vigentes(monkeypatch, {})
    client, _db = _cliente()

    respuesta = client.post(
        URL, json=_cuerpo("conteo_inventario_vigencia_horas", 12))

    assert respuesta.status_code == 201, respuesta.text
    assert llamadas == []
