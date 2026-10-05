"""R7 advisories: a busy KPI rebuild is a clean 409 (never a 500) and the per-transaction dirty cache is savepoint-safe."""
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.services import kpi_resumen as k
from app.motored.services import tablero_kpis as kpis
from app.motored.services.auth import MotoredUser
from app.motored.services.ingesta import orquestador
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

MENSAJE = "Los indicadores se están recalculando; intente de nuevo en unos minutos."


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "ocupado-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "ocupado-test-asc360-secret")
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_LOOP_ENABLED", False)
    yield
    app.dependency_overrides.clear()


def _como(rol, cola=None):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    override_motored_db(FakeAsyncSession(execute_queue=cola if cola is not None else [[]]))


def _carga(**cambios):
    base = dict(
        id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", nombre_archivo="a.xlsx", hash_sha256="a" * 64,
        ruta_objeto="VENTAS/2026/09/x.xlsx", bytes=100, estado="VALIDADO", filas_leidas=0, filas_validas=0,
        filas_rechazadas=0, periodo_desde=None, periodo_hasta=None, lotes_staged=0, ultimo_lote_aplicado=0,
        latido_en=None, log=None, subido_por=uuid.uuid4(), aplicado_en=None, created_at=datetime.utcnow())
    base.update(cambios)
    return CargaArchivo(**base)


def _ocupado():
    async def lanzar(*args, **kwargs):
        raise k.ResumenOcupadoError("detalle interno del candado")

    return lanzar


def test_a_busy_rebuild_during_a_kpi_read_is_a_409_with_the_friendly_message(monkeypatch):
    monkeypatch.setattr(kpis, "calcular_opciones", _ocupado())
    _como("ADMIN")

    with TestClient(app) as client:
        respuesta = client.get("/api/motored/tablero-asesores/kpis/opciones")

    assert respuesta.status_code == 409 and respuesta.json()["detail"] == MENSAJE


def test_a_busy_rebuild_during_a_carga_apply_is_a_409_not_a_500(monkeypatch):
    monkeypatch.setattr(orquestador, "ejecutar_aplicar", _ocupado())
    carga = _carga()
    _como("ADMIN", [[], [carga]])

    with TestClient(app, raise_server_exceptions=False) as client:
        respuesta = client.post(f"/api/motored/cargas/{carga.id}/aplicar")

    assert respuesta.status_code == 409 and respuesta.json()["detail"] == MENSAJE


async def test_the_apply_rolls_back_and_surfaces_the_busy_error_when_the_summary_is_locked(monkeypatch):
    async def ocupado(db, *args, **kwargs):
        raise k.ResumenOcupadoError("candado")

    monkeypatch.setattr(orquestador.inventario_mod, "aplicar_detalle", ocupado)
    carga = _carga(tipo="INVENTARIO", periodo_desde=datetime(2026, 9, 15).date())
    sesion = FakeAsyncSession(execute_queue=[[], [], []])

    with pytest.raises(k.ResumenOcupadoError):
        await orquestador.ejecutar_aplicar(sesion, carga)

    assert sesion.rolled_back is True and carga.estado == "VALIDADO"


# --- the per-transaction dirty cache vs savepoints ---------------------------------------------


class _Transaccion:
    pass


class _SyncSesion:
    def __init__(self):
        self.externa = _Transaccion()
        self.anidada = None

    def get_transaction(self):
        return self.externa

    def get_nested_transaction(self):
        return self.anidada


class _SesionConSavepoint:
    def __init__(self):
        self.info = {}
        self.sync_session = _SyncSesion()
        self.marcas = 0


@pytest.fixture
def sesion_espiada(monkeypatch):
    sesion = _SesionConSavepoint()

    async def bloquear(db):
        return None

    async def leer(db):
        return k.Estado(False, False, None, datetime(2026, 10, 1), 1)

    async def sucio(db):
        db.marcas += 1

    monkeypatch.setattr(k, "_bloquear", bloquear)
    monkeypatch.setattr(k, "estado", leer)
    monkeypatch.setattr(k, "marcar_sucio", sucio)
    return sesion


async def test_a_mark_made_inside_a_rolled_back_savepoint_does_not_hide_the_next_mark(sesion_espiada):
    sesion = sesion_espiada
    sesion.sync_session.anidada = _Transaccion()  # SAVEPOINT opened
    await k.marcar_sucio_si_construido(sesion)
    sesion.sync_session.anidada = None  # ... and rolled back

    await k.marcar_sucio_si_construido(sesion)

    assert sesion.marcas == 2


async def test_repeated_marks_in_the_same_transaction_still_write_once(sesion_espiada):
    for _ in range(3):
        await k.marcar_sucio_si_construido(sesion_espiada)

    assert sesion_espiada.marcas == 1
