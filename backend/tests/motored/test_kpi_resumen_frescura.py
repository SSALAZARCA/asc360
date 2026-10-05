"""R7b: what the KPI tabs and `/kpis/estado` say about the freshness of their data (unit)."""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.services import kpi_resumen as k
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_kpis as kpis
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

ACTUALIZADO = datetime.datetime(2026, 10, 4, 15, 30, tzinfo=datetime.timezone.utc)
RECONSTRUIDO = datetime.datetime(2026, 10, 4, 2, 0, tzinfo=datetime.timezone.utc)


def _estado(**cambios):
    base = dict(sucio=False, reconstruyendo=False, actualizado_en=ACTUALIZADO,
                ultima_reconstruccion_total=RECONSTRUIDO, version=1)
    return k.Estado(**{**base, **cambios})


@pytest.fixture
def con_estado(monkeypatch):
    def preparar(estado, lectura_activada=True):
        async def leer(db):
            return estado

        monkeypatch.setattr(k, "estado", leer)
        monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", lectura_activada)

    return preparar


async def test_the_tabs_report_the_summary_timestamp_when_the_summary_answers(con_estado):
    con_estado(_estado())

    assert await lectura.frescura(None) == {
        "usando_resumen": True, "datos_actualizados_en": ACTUALIZADO.isoformat()}


async def test_a_summary_without_partial_updates_reports_its_last_full_rebuild(con_estado):
    con_estado(_estado(actualizado_en=None))

    assert (await lectura.frescura(None))["datos_actualizados_en"] == RECONSTRUIDO.isoformat()


@pytest.mark.parametrize("estado,activada", [
    (_estado(), False), (None, True), (_estado(sucio=True), True),
    (_estado(ultima_reconstruccion_total=None, sucio=True), True),
], ids=["switch-off", "no-row", "dirty", "never-built"])
async def test_the_tabs_report_live_data_when_the_summary_does_not_answer(con_estado, estado, activada):
    con_estado(estado, activada)

    assert await lectura.frescura(None) == {"usando_resumen": False, "datos_actualizados_en": None}


async def test_the_estado_endpoint_payload_has_every_field(con_estado):
    con_estado(_estado(reconstruyendo=True))

    assert await kpis.calcular_estado(None) == {
        "actualizado_en": ACTUALIZADO.isoformat(), "sucio": False, "reconstruyendo": True,
        "ultima_reconstruccion_total": RECONSTRUIDO.isoformat(), "usando_resumen": True}


async def test_a_never_built_summary_counts_as_dirty_in_the_estado_payload(con_estado):
    con_estado(None)

    assert await kpis.calcular_estado(None) == {
        "actualizado_en": None, "sucio": True, "reconstruyendo": False,
        "ultima_reconstruccion_total": None, "usando_resumen": False}


# --- HTTP: roles ------------------------------------------------------------------------------

BASE = "/api/motored/tablero-asesores/kpis"


@pytest.fixture
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "kpis-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "kpis-test-asc360-secret")
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_LOOP_ENABLED", False)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def servicios(monkeypatch):
    registro = []

    async def solicitar(db):
        registro.append("solicitar")

    async def estado(db):
        registro.append("estado")
        return {"sucio": True}

    monkeypatch.setattr(k, "solicitar_recalculo", solicitar)
    monkeypatch.setattr(kpis, "calcular_estado", estado)
    return registro


def _como(rol):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))


def _llamar(metodo, ruta):
    with TestClient(app) as client:
        return client.request(metodo, f"{BASE}/{ruta}")


def test_an_admin_can_request_a_recalculation_and_gets_the_estado(_motored_ready, servicios):
    _como("ADMIN")

    respuesta = _llamar("POST", "recalcular")

    assert respuesta.status_code == 200 and respuesta.json() == {"sucio": True}
    assert servicios == ["solicitar", "estado"]


@pytest.mark.parametrize("rol", ["COMPRAS", "GERENCIA", "CONSULTA", "SUCURSAL", "SERVICIO_CLIENTE"])
def test_only_the_admin_can_request_a_recalculation(_motored_ready, servicios, rol):
    _como(rol)

    assert _llamar("POST", "recalcular").status_code == 403
    assert servicios == []


def test_a_recalculation_that_cannot_get_the_lock_is_a_409_with_the_reason(_motored_ready, monkeypatch):
    async def ocupado(db):
        raise k.ResumenOcupadoError("Los resúmenes de KPI se están reconstruyendo.")

    monkeypatch.setattr(k, "solicitar_recalculo", ocupado)
    _como("ADMIN")

    respuesta = _llamar("POST", "recalcular")

    assert respuesta.status_code == 409 and "reconstruyendo" in respuesta.json()["detail"]


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS", "GERENCIA"])
def test_the_estado_is_readable_by_admin_compras_and_gerencia(_motored_ready, servicios, rol):
    _como(rol)

    respuesta = _llamar("GET", "estado")

    assert respuesta.status_code == 200 and respuesta.json() == {"sucio": True}


@pytest.mark.parametrize("rol", ["CONSULTA", "SUCURSAL", "SERVICIO_CLIENTE"])
def test_the_estado_is_forbidden_to_other_roles(_motored_ready, servicios, rol):
    _como(rol)

    assert _llamar("GET", "estado").status_code == 403
    assert servicios == []
