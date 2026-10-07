"""
`reemplaza_mes_completo` on `POST /cargas` (VENTAS only, kept in the carga
`log`) and the `GET /cargas/{id}/vaciado-previsto` guards. The purge itself
and the live preview run against Postgres in
`pg_real/test_ingesta_ventas_lineas_pg.py`.
"""
import io
import uuid
from datetime import datetime

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import cargas as cargas_api
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.services.auth import MotoredUser
from app.motored.services.ingesta import ventas
from app.motored.services.storage import ResultadoSubida
from app.motored.services.trabajos.runner import JobRunner
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

URL = "/api/motored/cargas"


class _SinJob(JobRunner):
    async def enqueue(self, carga_id, tipo) -> None:
        return None


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "reemplazo-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "reemplazo-asc360-secret")
    monkeypatch.setattr(
        cargas_api.storage, "subir_archivo",
        lambda *a, **k: ResultadoSubida(
            ruta_objeto="VENTAS/x.xlsx", hash_sha256="ab" * 32))
    app.dependency_overrides[cargas_api.get_job_runner] = lambda: _SinJob()
    yield
    app.dependency_overrides.clear()


def _xlsx(encabezado):
    libro = openpyxl.Workbook()
    libro.active.append(list(encabezado))
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


ARCHIVO = {
    "VENTAS": _xlsx(ventas.COLUMNAS_ESPERADAS),
    "INVENTARIO": _xlsx(
        ["Referencia", "Bodega", "Desc.bodega", "Existencia", "Costo prom. uni."]),
}


def _cliente(rol, cola):
    sesion = FakeAsyncSession(execute_queue=cola)
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    override_motored_db(sesion)
    return TestClient(app), sesion


def _subir(tipo, datos):
    cliente, sesion = _cliente("COMPRAS", [[], []])
    respuesta = cliente.post(
        URL, files={"file": ("a.xlsx", ARCHIVO[tipo], "application/octet-stream")},
        data={"tipo": tipo, "periodo_desde": "2026-09-01",
              "periodo_hasta": "2026-09-30", **datos})
    assert respuesta.status_code == 202, respuesta.text
    return sesion.added_of_type(CargaArchivo)[0]


def test_a_ventas_upload_with_the_flag_keeps_it_in_the_carga_log():
    carga = _subir("VENTAS", {"reemplaza_mes_completo": "true"})

    assert carga.log == {"reemplaza_mes_completo": True}


@pytest.mark.parametrize("datos", [{}, {"reemplaza_mes_completo": "false"}])
def test_without_the_flag_the_carga_log_stays_empty(datos):
    assert _subir("VENTAS", datos).log is None


def test_the_flag_is_ignored_for_other_types():
    assert _subir("INVENTARIO", {"reemplaza_mes_completo": "true"}).log is None


def _carga(log=None, estado="VALIDADO"):
    return CargaArchivo(
        id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", nombre_archivo="a.xlsx",
        hash_sha256="a" * 64, ruta_objeto="x", bytes=1, estado=estado,
        filas_leidas=0, filas_validas=0, filas_rechazadas=0, lotes_staged=0,
        ultimo_lote_aplicado=0, subido_por=uuid.uuid4(), log=log,
        created_at=datetime(2026, 9, 21, 10))


def test_the_carga_read_exposes_the_flag():
    carga = _carga({"reemplaza_mes_completo": True})
    cliente, _ = _cliente("CONSULTA", [[], [carga]])

    assert cliente.get(f"{URL}/{carga.id}").json()["reemplaza_mes_completo"] is True


def test_the_carga_read_defaults_the_flag_to_false():
    carga = _carga()
    cliente, _ = _cliente("CONSULTA", [[], [carga]])

    assert cliente.get(f"{URL}/{carga.id}").json()["reemplaza_mes_completo"] is False


@pytest.mark.parametrize("rol", ["SUCURSAL", "CONSULTA"])
def test_only_admin_and_compras_read_the_planned_purge(rol):
    carga = _carga({"reemplaza_mes_completo": True})
    cliente, _ = _cliente(rol, [[], [carga]])

    assert cliente.get(f"{URL}/{carga.id}/vaciado-previsto").status_code == 403


def test_the_planned_purge_is_empty_without_the_flag():
    carga = _carga()
    cliente, _ = _cliente("COMPRAS", [[], [carga], []])

    respuesta = cliente.get(f"{URL}/{carga.id}/vaciado-previsto")

    assert respuesta.status_code == 200
    assert respuesta.json() == []
