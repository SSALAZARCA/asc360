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

    async def falso(db, desde, hasta, modo_hmcl, **extra):
        registro.append((desde, hasta, modo_hmcl) + ((extra,) if extra else ()))
        # El rango se valida de verdad, como en la consulta real.
        from app.motored.services.tablero_asesores import validar_rango
        validar_rango(desde, hasta)
        return {"filas": [], "venta_sin_linea": 0.0}

    async def falso_por_meses(db, meses, modo_hmcl, sucursal_ids=None):
        registro.append(("meses", meses, modo_hmcl, sucursal_ids))
        # La lista se valida de verdad, como en la consulta real.
        from app.motored.services.tablero_asesores import validar_meses
        validar_meses(meses)
        return {"filas": [], "venta_sin_linea": 0.0}

    monkeypatch.setattr(consultas, "calcular_tablero", falso)
    monkeypatch.setattr(consultas, "calcular_tablero_por_meses", falso_por_meses)
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


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS", "GERENCIA"])
def test_admin_compras_y_gerencia_entran_y_los_parametros_llegan(_motored_ready, llamadas, rol):
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


def test_meses_en_csv_llegan_como_lista_y_hmcl_por_defecto_es_incluir(_motored_ready, llamadas):
    _como("ADMIN")

    with TestClient(app) as client:
        r = client.get(URL, params={"meses": "2026-01,2026-03"})

    assert r.status_code == 200
    assert llamadas == [("meses", ["2026-01", "2026-03"], "incluir", None)]


def test_las_sucursales_llegan_como_uuid_sin_repetidos(_motored_ready, llamadas):
    _como("COMPRAS")
    a, b = uuid.uuid4(), uuid.uuid4()

    with TestClient(app) as client:
        r = client.get(URL, params={"meses": "2026-02", "sucursales": f"{a},{b}, {a}", "hmcl": "solo"})

    assert r.status_code == 200
    assert llamadas == [("meses", ["2026-02"], "solo", [a, b])]


def test_desde_y_hasta_aceptan_sucursales(_motored_ready, llamadas):
    _como("ADMIN")
    a = uuid.uuid4()

    with TestClient(app) as client:
        r = client.get(URL, params={"desde": "2026-01", "hasta": "2026-02", "sucursales": str(a)})

    assert r.status_code == 200
    assert llamadas == [("2026-01", "2026-02", "incluir", {"sucursal_ids": [a]})]


@pytest.mark.parametrize("params", [
    {"meses": "2026-01", "desde": "2026-01", "hasta": "2026-02"},   # meses y rango juntos
    {"meses": "2026-01", "desde": "2026-01"},
    {},                                                              # nada
    {"meses": "2026-13"},                                            # mes inexistente
    {"meses": "enero"},
    {"meses": "2026-1"},                                             # sin cero
    {"meses": ""},
    {"meses": "2026-01,,2026-02"},
    {"meses": ",".join(f"2025-{m:02d}" for m in range(1, 13)) + ",2026-01"},  # 13 meses
    {"meses": "2026-01", "sucursales": "no-es-uuid"},
    {"meses": "2026-01", "sucursales": ""},
    {"meses": "2026-01", "hmcl": "todos"},
])
def test_parametros_invalidos_de_meses_y_sucursales_son_422(_motored_ready, llamadas, params):
    _como("ADMIN")

    with TestClient(app) as client:
        r = client.get(URL, params=params)

    assert r.status_code == 422


def test_meses_y_rango_juntos_explican_el_motivo(_motored_ready, llamadas):
    _como("ADMIN")

    with TestClient(app) as client:
        r = client.get(URL, params={"meses": "2026-01", "desde": "2026-01", "hasta": "2026-01"})

    assert "no ambos" in r.json()["detail"] and llamadas == []


def test_doce_meses_salteados_son_validos_y_repetidos_no_cuentan(_motored_ready, llamadas):
    _como("ADMIN")
    doce = ",".join(f"2025-{m:02d}" for m in range(1, 13))

    with TestClient(app) as client:
        r = client.get(URL, params={"meses": doce + ",2025-01"})

    assert r.status_code == 200
    from app.motored.services.tablero_asesores import validar_meses
    assert llamadas == [("meses", doce.split(",") + ["2025-01"], "incluir", None)]
    assert validar_meses(llamadas[0][1]) == doce.split(",")  # the repeated month collapses to 12
