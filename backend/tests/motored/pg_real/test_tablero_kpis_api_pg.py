"""
KPI's (B6) end to end against a real Postgres (opt-in): each endpoint through
the real app, router and queries, over the world of `test_tablero_kpis_b5_pg`
(sales in 2097-01..06, inventory cut-off 2099-12-29).
"""
import httpx
import pytest

from app.config import settings
from app.main import app
from app.motored.deps import get_current_motored_user, get_motored_db
from app.motored.services.auth import MotoredUser
from tests.motored.pg_real.test_tablero_asesores_pg import URL, pytestmark, sesion  # noqa: F401
from tests.motored.pg_real.test_tablero_kpis_b5_pg import _mundo

BASE = "/api/motored/tablero-asesores/kpis"
MESES = ",".join(f"2097-0{m}" for m in range(1, 7))


@pytest.fixture
async def http(sesion, monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "kpis-api-pg")

    async def db():
        yield sesion

    async def usuario():
        return MotoredUser(user_id="00000000-0000-0000-0000-000000000001", role="GERENCIA")

    app.dependency_overrides[get_motored_db] = db
    app.dependency_overrides[get_current_motored_user] = usuario
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://motored") as cliente:
        yield cliente
    app.dependency_overrides.clear()


async def test_ventas_endpoint_returns_json_numbers_for_the_network(http, sesion):
    w = await _mundo(sesion)

    r = await http.get(f"{BASE}/ventas", params={"meses": MESES})

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["total"]["venta"]["total"] == 3400.0 and cuerpo["meses"][0] == "2097-01"
    assert cuerpo["tecnired"]["clientes"] == 7 and cuerpo["tecnired"]["top5"][0]["razon_social"] == "Taller T1"
    assert isinstance(cuerpo["tecnired"]["venta"], float)
    assert {f["sucursal_id"] for f in cuerpo["tiendas"]} == {str(w.s[0].id), str(w.s[1].id)}


async def test_tiendas_endpoint_filters_by_store_and_returns_inventory_days(http, sesion):
    w = await _mundo(sesion)

    r = await http.get(f"{BASE}/tiendas", params={"meses": MESES, "sucursales": str(w.s[0].id)})

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert [f["sucursal_id"] for f in cuerpo["tiendas"]] == [str(w.s[0].id)]
    assert cuerpo["tiendas"][0]["dias_inventario"]["valor_inventario"] == 2500.0
    assert cuerpo["inventario"]["fecha_corte"] == "2099-12-29" and cuerpo["sucursales"] == [str(w.s[0].id)]


async def test_asesores_endpoint_returns_the_board_with_compliance(http, sesion):
    await _mundo(sesion)

    r = await http.get(f"{BASE}/asesores", params={"meses": "2097-01,2097-03", "hmcl": "excluir"})

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["hmcl"] == "excluir" and cuerpo["meses"] == ["2097-01", "2097-03"]
    assert set(cuerpo["cumplimiento"]) == {"asesores", "conteos", "advertencias"} and "filas" in cuerpo


async def test_options_endpoint_lists_months_stores_and_the_last_month(http, sesion):
    w = await _mundo(sesion)

    r = await http.get(f"{BASE}/opciones")

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["ultimo_mes"] == "2097-07" == cuerpo["meses_disponibles"][-1]
    assert {"2097-01", "2097-06"} <= set(cuerpo["meses_disponibles"])
    assert {"id": str(w.s[2].id), "nombre": w.s[2].nombre} in cuerpo["tiendas"]


async def test_a_bad_months_list_is_a_spanish_422(http, sesion):
    r = await http.get(f"{BASE}/ventas", params={"meses": "2097-13"})

    assert r.status_code == 422 and "inválido" in r.json()["detail"]
