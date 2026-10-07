"""
Lore self-registration with a cédula (odd/motored-reporte-diario-asesor,
T1): `POST /bot/registro` stores the cédula clean and PENDING
(`cedula_aprobada=false`) until an ADMIN approves it. A cédula that no
active vendedor holds is still stored (the admin sees it flagged in
Gestión de usuarios); the response never says whether it was found.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.usuario import Usuario
from tests.motored.conftest import FakeAsyncSession, override_motored_db

URL = "/api/motored/bot/registro"
SECRET = "registro-cedula-lore-secret"


@pytest.fixture(autouse=True)
def _lore_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "reg-ced-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "reg-ced-asc360")
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "reg-ced-sonia")
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", SECRET)
    yield
    app.dependency_overrides.clear()


def _headers():
    return {"X-Lore-Secret": SECRET, "X-Lore-Telegram-Id": "4242"}


def _payload(**extra):
    base = {
        "nombre": "Ana Pérez", "phone": "3001234567",
        "sucursal_id": str(uuid.uuid4()),
    }
    base.update(extra)
    return base


def _registrar(cola, payload):
    # probe, existing-telegram pre-check, then `cola`
    sesion = FakeAsyncSession(execute_queue=[[], []] + list(cola))
    override_motored_db(sesion)
    response = TestClient(app).post(URL, json=payload, headers=_headers())
    return response, sesion


@pytest.mark.parametrize("en_maestro", [[uuid.uuid4()], []])
def test_registro_stores_the_cedula_clean_and_pending(en_maestro):
    response, sesion = _registrar(
        [en_maestro, []], _payload(cedula="1.130.123.456"))

    assert response.status_code == 201, response.text
    creado = sesion.added_of_type(Usuario)[0]
    assert creado.cedula == "1130123456"
    assert creado.cedula_aprobada is False


def test_registro_response_never_reveals_the_master_check():
    con, _ = _registrar([[uuid.uuid4()], []], _payload(cedula="123456"))
    sin, _ = _registrar([[], []], _payload(cedula="123456"))

    assert con.json()["usuario"].keys() == sin.json()["usuario"].keys()
    assert "cedula" not in str(con.json())


def test_registro_logs_a_cedula_outside_the_master_without_the_value(
    caplog,
):
    caplog.set_level("INFO", logger="app.motored.api.bot")

    response, _ = _registrar([[], []], _payload(cedula="98765432"))

    assert response.status_code == 201
    assert "maestro" in caplog.text
    assert "98765432" not in caplog.text


@pytest.mark.parametrize("cedula", ["12AB", "", "1" * 21])
def test_registro_with_a_malformed_cedula_returns_422(cedula):
    sesion = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(sesion)

    response = TestClient(app).post(
        URL, json=_payload(cedula=cedula), headers=_headers())

    assert response.status_code == 422


def test_registro_without_cedula_still_works_for_an_older_bot():
    response, sesion = _registrar([[]], _payload())

    assert response.status_code == 201, response.text
    creado = sesion.added_of_type(Usuario)[0]
    assert creado.cedula is None
    assert creado.cedula_aprobada is False
