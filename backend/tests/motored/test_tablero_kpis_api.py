"""
KPI's (B6), HTTP layer: per-tab endpoints under `/tablero-asesores/kpis`.

The services are replaced by doubles to check roles, parameter parsing, the
Spanish 422s and the response passthrough; the real queries run end to end in
`pg_real/test_tablero_kpis_api_pg.py`.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as consultas
from app.motored.services import tablero_kpis as kpis
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

BASE = "/api/motored/tablero-asesores/kpis"
PESTANAS = ["ventas", "tiendas", "asesores", "comisiones"]
UUID_A, UUID_B = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "kpis-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "kpis-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def llamadas(monkeypatch):
    registro = []

    async def falso_filtro(db, meses, modo_hmcl, sucursal_ids=None):
        registro.append(("filtro", meses, modo_hmcl, sucursal_ids))
        meses = t.validar_meses(meses)  # validated for real, like the query does
        return t.filtro_de_meses(meses, modo_hmcl, sucursal_ids)

    def falso_calculo(pestana):
        async def calculo(db, filtro):
            registro.append((pestana, filtro.meses, filtro.modo_hmcl, filtro.sucursal_ids))
            return {"pestana": pestana, "monto": 12.5}
        return calculo

    async def falsas_opciones(db):
        registro.append(("opciones",))
        return {"meses_disponibles": ["2026-01"], "ultimo_mes": "2026-01", "tiendas": []}

    monkeypatch.setattr(consultas, "cargar_filtro", falso_filtro)
    for pestana in PESTANAS:
        monkeypatch.setattr(kpis, f"calcular_kpis_{pestana}", falso_calculo(pestana))
    monkeypatch.setattr(kpis, "calcular_opciones", falsas_opciones)

    async def falso_detalle(db, filtro, cedula):
        registro.append(("detalle", filtro.meses, filtro.modo_hmcl, filtro.sucursal_ids, cedula))
        return None if cedula == "999" else {"asesor": {"cedula": cedula}}

    async def falsas_opciones_asesores(db, filtro):
        registro.append(("opciones_asesores", filtro.meses, filtro.modo_hmcl, filtro.sucursal_ids))
        return {"asesores": [{"cedula": "100", "nombre": "Ana", "tienda": "Norte", "sucursal_id": UUID_A, "venta": 5.0}]}

    monkeypatch.setattr(kpis, "calcular_kpis_asesor_detalle", falso_detalle)
    monkeypatch.setattr(kpis, "calcular_opciones_asesores", falsas_opciones_asesores)
    return registro


def _como(rol):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))


def _get(ruta, **params):
    with TestClient(app) as client:
        return client.get(f"{BASE}/{ruta}", params=params)


@pytest.mark.parametrize("ruta", PESTANAS + ["opciones"])
@pytest.mark.parametrize("rol", ["CONSULTA", "SUCURSAL", "SERVICIO_CLIENTE"])
def test_other_roles_are_forbidden(_motored_ready, llamadas, ruta, rol):
    _como(rol)

    assert _get(ruta, meses="2026-01").status_code == 403
    assert llamadas == []


@pytest.mark.parametrize("ruta", PESTANAS + ["opciones"])
def test_unauthenticated_is_401(_motored_ready, llamadas, ruta):
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))

    assert _get(ruta, meses="2026-01").status_code == 401


@pytest.mark.parametrize("pestana", PESTANAS)
@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS", "GERENCIA"])
def test_allowed_roles_get_the_service_payload(_motored_ready, llamadas, pestana, rol):
    _como(rol)

    r = _get(pestana, meses="2026-03,2026-01")

    assert r.status_code == 200 and r.json() == {"pestana": pestana, "monto": 12.5}
    assert llamadas[-1] == (pestana, ("2026-01", "2026-03"), "incluir", None)


def test_the_filter_params_reach_the_services(_motored_ready, llamadas):
    _como("ADMIN")

    r = _get("tiendas", meses="2026-01", sucursales=f"{UUID_A},{UUID_B},{UUID_A}", hmcl="solo")

    assert r.status_code == 200
    assert llamadas[0][2] == "solo" and [str(i) for i in llamadas[0][3]] == [UUID_A, UUID_B]
    assert llamadas[1][2:] == ("solo", frozenset(llamadas[0][3]))


@pytest.mark.parametrize("params, motivo", [
    ({}, "meses"),
    ({"meses": ""}, "mes"),
    ({"meses": "2026-13"}, "inválido"),
    ({"meses": "enero"}, "inválido"),
    ({"meses": ",".join(f"2025-{m:02d}" for m in range(1, 13)) + ",2026-01"}, "12"),
    ({"meses": "2026-01", "hmcl": "todos"}, "hmcl"),
    ({"meses": "2026-01", "sucursales": "no-es-uuid"}, "Sucursal"),
])
@pytest.mark.parametrize("pestana", PESTANAS)
def test_invalid_params_are_422_in_spanish(_motored_ready, llamadas, pestana, params, motivo):
    _como("COMPRAS")

    r = _get(pestana, **params)

    assert r.status_code == 422 and motivo in r.json()["detail"]
    assert not [x for x in llamadas if x[0] == pestana]


def test_the_options_endpoint_returns_the_filter_data(_motored_ready, llamadas):
    _como("GERENCIA")

    r = _get("opciones")

    assert r.status_code == 200
    assert set(r.json()) == {"meses_disponibles", "ultimo_mes", "tiendas"}


def test_kpis_routes_are_the_documented_paths():
    rutas = sorted(p for p in app.openapi()["paths"] if p.startswith(BASE))
    assert rutas == sorted(f"{BASE}/{n}" for n in PESTANAS + [
        "opciones", "estado", "recalcular", "comisiones/excel", "asesores/detalle", "asesores/opciones",
        "inventario", "inventario/excel"])


# --- Single-asesor detail and the asesor options ---------------------------------------------------


@pytest.mark.parametrize("ruta, params", [
    ("asesores/detalle", {"meses": "2026-01", "cedula": "100"}), ("asesores/opciones", {"meses": "2026-01"}),
])
@pytest.mark.parametrize("rol", ["CONSULTA", "SUCURSAL", "SERVICIO_CLIENTE"])
def test_asesor_routes_forbid_the_other_roles(_motored_ready, llamadas, ruta, params, rol):
    _como(rol)

    assert _get(ruta, **params).status_code == 403
    assert llamadas == []


@pytest.mark.parametrize("ruta, params", [
    ("asesores/detalle", {"meses": "2026-01", "cedula": "100"}), ("asesores/opciones", {"meses": "2026-01"}),
])
def test_asesor_routes_need_authentication(_motored_ready, llamadas, ruta, params):
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))

    assert _get(ruta, **params).status_code == 401


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS", "GERENCIA"])
def test_the_detail_is_returned_with_the_filter_and_the_clean_cedula(_motored_ready, llamadas, rol):
    _como(rol)

    r = _get("asesores/detalle", meses="2026-03,2026-01", hmcl="excluir", sucursales=UUID_A, cedula=" 1.130.123 ")

    assert r.status_code == 200 and r.json() == {"asesor": {"cedula": "1130123"}}
    assert llamadas[-1][0] == "detalle" and llamadas[-1][1:3] == (("2026-01", "2026-03"), "excluir")
    assert llamadas[-1][4] == "1130123"


def test_an_asesor_without_data_is_a_404_in_spanish(_motored_ready, llamadas):
    _como("ADMIN")

    r = _get("asesores/detalle", meses="2026-01", cedula="999")

    assert r.status_code == 404 and r.json()["detail"] == "Asesor no encontrado"


@pytest.mark.parametrize("params, motivo", [
    ({"meses": "2026-01"}, "cédula"),
    ({"meses": "2026-01", "cedula": ""}, "cédula"),
    ({"meses": "2026-01", "cedula": "12ab"}, "números"),
    ({"meses": "2026-01", "cedula": "12-34"}, "números"),
    ({"cedula": "100"}, "meses"),
])
def test_the_detail_rejects_a_bad_cedula_or_filter_with_a_422(_motored_ready, llamadas, params, motivo):
    _como("COMPRAS")

    r = _get("asesores/detalle", **params)

    assert r.status_code == 422 and motivo in r.json()["detail"]
    assert not [x for x in llamadas if x[0] == "detalle"]


def test_the_asesor_options_follow_the_same_filter_as_the_tab(_motored_ready, llamadas):
    _como("GERENCIA")

    r = _get("asesores/opciones", meses="2026-01,2026-02", hmcl="excluir", sucursales=f"{UUID_A},{UUID_B}")

    assert r.status_code == 200 and r.json()["asesores"][0]["cedula"] == "100"
    registro = llamadas[-1]
    assert registro[:3] == ("opciones_asesores", ("2026-01", "2026-02"), "excluir")
    assert {str(i) for i in registro[3]} == {UUID_A, UUID_B}


def test_the_asesor_options_without_a_store_filter_cover_the_whole_network(_motored_ready, llamadas):
    _como("ADMIN")

    assert _get("asesores/opciones", meses="2026-01").status_code == 200
    assert llamadas[-1] == ("opciones_asesores", ("2026-01",), "incluir", None)


def test_the_asesor_options_need_the_period(_motored_ready, llamadas):
    _como("ADMIN")

    r = _get("asesores/opciones")

    assert r.status_code == 422 and "meses" in r.json()["detail"]
    assert not [x for x in llamadas if x[0] == "opciones_asesores"]


def test_the_asesor_options_reject_a_bad_store_id(_motored_ready, llamadas):
    _como("ADMIN")

    r = _get("asesores/opciones", meses="2026-01", sucursales="no-es-uuid")

    assert r.status_code == 422 and "Sucursal" in r.json()["detail"]
