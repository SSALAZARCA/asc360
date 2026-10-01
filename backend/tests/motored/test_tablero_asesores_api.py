"""
Tablero de asesores (feature motored-tablero-asesores, T4): capa HTTP.

La consulta SQL se prueba en `pg_real/test_tablero_asesores_pg.py`; aqui se
sustituye por un doble para comprobar permisos (ADMIN|COMPRAS), validacion del
rango y el paso de parametros.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.services import tablero_asesores_consultas as consultas
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

URL = "/api/motored/tablero-asesores"


@pytest.fixture
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "tablero-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "tablero-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def llamadas(monkeypatch):
    registro = []

    async def falso(db, desde, hasta, modo_hmcl):
        registro.append((desde, hasta, modo_hmcl))
        # El rango se valida de verdad, como en la consulta real.
        from app.motored.services.tablero_asesores import validar_rango
        validar_rango(desde, hasta)
        return {"filas": [], "venta_sin_linea": 0.0}

    monkeypatch.setattr(consultas, "calcular_tablero", falso)
    return registro


def _como(rol):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))


@pytest.mark.parametrize("rol", ["CONSULTA", "SUCURSAL", "SERVICIO_CLIENTE"])
def test_otros_roles_no_entran(_motored_ready, llamadas, rol):
    _como(rol)

    with TestClient(app) as client:
        r = client.get(URL, params={"desde": "2026-01", "hasta": "2026-06"})

    assert r.status_code == 403
    assert llamadas == []


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS"])
def test_admin_y_compras_entran_y_los_parametros_llegan(_motored_ready, llamadas, rol):
    _como(rol)

    with TestClient(app) as client:
        r = client.get(URL, params={"desde": "2026-01", "hasta": "2026-06", "hmcl": "solo"})

    assert r.status_code == 200 and r.json()["filas"] == []
    assert llamadas == [("2026-01", "2026-06", "solo")]


def test_hmcl_por_defecto_es_incluir(_motored_ready, llamadas):
    _como("ADMIN")

    with TestClient(app) as client:
        client.get(URL, params={"desde": "2026-01", "hasta": "2026-02"})

    assert llamadas == [("2026-01", "2026-02", "incluir")]


@pytest.mark.parametrize("params", [
    {"desde": "2026-06", "hasta": "2026-01"},   # invertido
    {"desde": "2025-01", "hasta": "2026-01"},   # 13 meses
    {"desde": "2026-13", "hasta": "2026-13"},   # mes inexistente
    {"desde": "enero", "hasta": "2026-01"},     # formato
    {"desde": "2026-01"},                       # falta hasta
    {"desde": "2026-01", "hasta": "2026-02", "hmcl": "todos"},
])
def test_parametros_invalidos_son_422(_motored_ready, llamadas, params):
    _como("ADMIN")

    with TestClient(app) as client:
        r = client.get(URL, params=params)

    assert r.status_code == 422


def test_el_rango_invertido_explica_el_motivo_en_espanol(_motored_ready, llamadas):
    _como("ADMIN")

    with TestClient(app) as client:
        r = client.get(URL, params={"desde": "2026-06", "hasta": "2026-01"})

    assert "posterior" in r.json()["detail"]


def test_exactamente_12_meses_es_valido(_motored_ready, llamadas):
    _como("COMPRAS")

    with TestClient(app) as client:
        r = client.get(URL, params={"desde": "2025-10", "hasta": "2026-09"})

    assert r.status_code == 200


def test_el_tablero_tiene_su_propia_ruta_y_no_cuelga_de_corridas():
    rutas = [p for p in app.openapi()["paths"] if "tablero-asesores" in p]
    assert rutas == [URL]
