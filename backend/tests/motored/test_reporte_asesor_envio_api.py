"""
`/api/motored/reporte-asesor` (odd/motored-reporte-diario-asesor, T3b):
`GET /estado` and `POST /reenviar` are ADMIN only. The resend refuses (409)
without `LORE_BOT_TOKEN` or `MOTORED_PUBLIC_URL`, or while another resend
runs; otherwise it answers 202 with how many asesores it will message and
sends in the background, even with the daily switch off.

The router is mounted on a local app with the same `/api/motored` prefix,
so these tests do not depend on where it is registered.
"""
import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.motored.api import reporte_asesor
from app.motored.database import get_motored_db
from app.motored.deps import get_current_motored_user
from app.motored.services import reporte_asesor_envio as envio
from app.motored.services.auth import MotoredUser
from app.motored.services.trabajos import supervisor_reporte_asesor as sup
from tests.motored.conftest import FakeAsyncSession

URL = "/api/motored/reporte-asesor"
NO_ADMIN = ["COMPRAS", "SUCURSAL", "CONSULTA", "GERENCIA",
            "ASESOR_MOSTRADOR"]
AYER = date(2026, 10, 6)


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "envio-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "envio-asc360")
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "envio-sonia")
    monkeypatch.setattr(settings, "LORE_BOT_TOKEN", "1:tok")
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", "https://m.co")
    yield
    sup.liberar_reenvio()


def _cliente(role, user_id=None):
    app = FastAPI()
    app.include_router(reporte_asesor.router, prefix="/api/motored")
    sesion = FakeAsyncSession(execute_queue=[[]])
    usuario = MotoredUser(user_id=str(user_id or uuid.uuid4()), role=role)

    async def _usuario():
        return usuario

    app.dependency_overrides[get_motored_db] = lambda: sesion
    app.dependency_overrides[get_current_motored_user] = _usuario
    return TestClient(app)


def _destinos(n):
    return [envio.Destino(
        envio.Asesor(uuid.uuid4(), f"A{i}", str(i), True, i, "t" * 40),
        "hola") for i in range(n)]


@pytest.fixture
def preparar(monkeypatch):
    mock = AsyncMock(return_value=_destinos(3))
    monkeypatch.setattr(envio, "preparar_destinos", mock)
    monkeypatch.setattr(
        envio, "ultima_fecha_datos", AsyncMock(return_value=AYER))
    return mock


@pytest.fixture
def ejecutar(monkeypatch):
    mock = AsyncMock(return_value=envio.Conteo(enviados=3))
    monkeypatch.setattr(sup, "ejecutar_reenvio", mock)
    return mock


@pytest.mark.parametrize("role", NO_ADMIN)
def test_estado_is_admin_only(role, monkeypatch):
    estado = AsyncMock()
    monkeypatch.setattr(envio, "estado_envio", estado)

    respuesta = _cliente(role).get(f"{URL}/estado")

    assert respuesta.status_code == 403
    estado.assert_not_awaited()


@pytest.mark.parametrize("role", NO_ADMIN)
def test_reenviar_is_admin_only(role, preparar, ejecutar):
    respuesta = _cliente(role).post(f"{URL}/reenviar", json={})

    assert respuesta.status_code == 403
    preparar.assert_not_awaited()
    ejecutar.assert_not_awaited()


def test_estado_returns_the_service_summary(monkeypatch):
    resumen = {"envio_activo": False, "elegibles": 4}
    monkeypatch.setattr(
        envio, "estado_envio", AsyncMock(return_value=resumen))

    respuesta = _cliente("ADMIN").get(f"{URL}/estado")

    assert respuesta.status_code == 200
    assert respuesta.json()["elegibles"] == 4
    assert "falta_configuracion" in respuesta.json()


@pytest.mark.parametrize("variable", ["LORE_BOT_TOKEN", "MOTORED_PUBLIC_URL"])
def test_reenviar_refuses_without_settings(
        variable, monkeypatch, preparar, ejecutar):
    monkeypatch.setattr(settings, variable, "")

    respuesta = _cliente("ADMIN").post(f"{URL}/reenviar", json={})

    assert respuesta.status_code == 409
    assert variable in respuesta.json()["detail"]
    preparar.assert_not_awaited()


def test_reenviar_sends_in_the_background_and_returns_202(
        preparar, ejecutar):
    admin = uuid.uuid4()

    respuesta = _cliente("ADMIN", admin).post(f"{URL}/reenviar", json={})

    assert respuesta.status_code == 202
    assert respuesta.json() == {
        "fecha_datos": AYER.isoformat(), "a_enviar": 3}
    assert preparar.await_args.args[1] == AYER
    args = ejecutar.await_args.args
    assert len(args[0]) == 3 and args[1] == AYER and args[2] == admin
    assert sup.reservar_reenvio() is True


def test_reenviar_accepts_a_date(preparar, ejecutar):
    respuesta = _cliente("ADMIN").post(
        f"{URL}/reenviar", json={"fecha_datos": "2026-10-02"})

    assert respuesta.status_code == 202
    assert preparar.await_args.args[1] == date(2026, 10, 2)


def test_reenviar_refuses_today_or_a_future_date(preparar, ejecutar):
    respuesta = _cliente("ADMIN").post(
        f"{URL}/reenviar", json={"fecha_datos": "2099-01-01"})

    assert respuesta.status_code == 422
    preparar.assert_not_awaited()


def test_reenviar_without_sales_loaded_is_a_conflict(
        monkeypatch, preparar, ejecutar):
    monkeypatch.setattr(
        envio, "ultima_fecha_datos", AsyncMock(return_value=None))

    respuesta = _cliente("ADMIN").post(f"{URL}/reenviar", json={})

    assert respuesta.status_code == 409
    ejecutar.assert_not_awaited()


def test_a_second_concurrent_resend_is_refused(preparar, ejecutar):
    assert sup.reservar_reenvio()

    respuesta = _cliente("ADMIN").post(f"{URL}/reenviar", json={})

    assert respuesta.status_code == 409
    assert "en curso" in respuesta.json()["detail"]
    ejecutar.assert_not_awaited()


def test_nobody_to_message_answers_zero_and_releases_the_guard(
        preparar, ejecutar):
    preparar.return_value = []

    respuesta = _cliente("ADMIN").post(f"{URL}/reenviar", json={})

    assert respuesta.status_code == 202
    assert respuesta.json()["a_enviar"] == 0
    ejecutar.assert_not_awaited()
    assert sup.reservar_reenvio() is True


def test_reenviar_works_with_the_daily_switch_off(
        monkeypatch, preparar, ejecutar):
    leer = AsyncMock(side_effect=AssertionError("must not read the switch"))
    monkeypatch.setattr(envio, "leer_config", leer)

    respuesta = _cliente("ADMIN").post(f"{URL}/reenviar", json={})

    assert respuesta.status_code == 202
    ejecutar.assert_awaited_once()
