"""
Motored aviso de antiguedad: `GET /api/motored/avisos-antiguedad`, lo que
alimenta el banner. Solo ADMIN y COMPRAS; devuelve los datos que vencen hoy
o manana (hora de Bogota).
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.services import avisos_antiguedad as av
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

RUTA = "/api/motored/avisos-antiguedad"
HOY = date(2026, 10, 2)


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "avisos-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "avisos-asc360")
    monkeypatch.setattr(settings, "MOTORED_AVISOS_ANTIGUEDAD_ENABLED", False)
    monkeypatch.setattr("app.motored.api.avisos_antiguedad.hoy_bogota",
                        lambda: HOY)
    yield
    app.dependency_overrides.clear()


def _como(rol):
    override_motored_user(MotoredUser(
        user_id=str(uuid.UUID(int=900)), role=rol, sucursal_ids=[]))
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 4))
    return TestClient(app)


def _venc(tipo, nombre, vence):
    return av.Vencimiento(
        tipo=tipo, nombre=nombre, fecha_carga=vence - timedelta(days=7),
        fecha_vencimiento=vence, limite_dias=7)


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS"])
def test_devuelve_lo_que_vence_hoy_o_manana(monkeypatch, rol):
    async def leer(db, hoy):
        return [
            _venc("inventario", "inventario", date(2026, 10, 3)),
            _venc("backorder", "backorder", date(2026, 10, 2)),
            _venc("facturas", "facturas de pedidos", date(2026, 10, 9)),
        ]

    monkeypatch.setattr(av, "leer_vencimientos", leer)

    respuesta = _como(rol).get(RUTA)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"avisos": [
        {"dataset": "backorder", "nombre": "backorder", "vence": "hoy",
         "fecha_carga": "2026-09-25", "fecha_vencimiento": "2026-10-02"},
        {"dataset": "inventario", "nombre": "inventario",
         "vence": "manana", "fecha_carga": "2026-09-26",
         "fecha_vencimiento": "2026-10-03"},
    ]}


@pytest.mark.parametrize(
    "rol", ["SUCURSAL", "CONSULTA", "SERVICIO_CLIENTE", "ASESOR_MOSTRADOR"])
def test_los_demas_roles_reciben_403(rol):
    assert _como(rol).get(RUTA).status_code == 403
