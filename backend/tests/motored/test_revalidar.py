"""
"Volver a validar" (R2, odd/tasks/motored-cargas-revalidar.md): the same
carga is processed again from its stored file, with the current catalog,
mappings and the rows the user chose to ignore.

No live database (`FakeAsyncSession`); the real wipe and state transition
on Postgres live in `pg_real/test_revalidar_carga_pg.py`.
"""
import io
import uuid
from datetime import date, datetime
from decimal import Decimal

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Delete

from app.config import settings
from app.main import app
from app.motored.api import cargas as cargas_api
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.auth import MotoredUser
from app.motored.services.ingesta import facturas as facturas_mod
from app.motored.services.ingesta import orquestador
from app.motored.services.ingesta import revalidar as revalidar_mod
from app.motored.services.trabajos.runner import JobRunner
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

CARGAS_URL = "/api/motored/cargas"
PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
CONOCIDA_ID = uuid.uuid4()


class _RunnerQueAnota(JobRunner):
    def __init__(self):
        self.encoladas = []

    async def enqueue(self, carga_id, tipo) -> None:
        self.encoladas.append((carga_id, tipo))


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "revalidar-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "revalidar-asc360-secret")
    anotador = _RunnerQueAnota()
    app.dependency_overrides[cargas_api.get_job_runner] = lambda: anotador
    yield anotador
    app.dependency_overrides.clear()


def _carga(estado="VALIDADO", origen="EXCEL", log=None, **extra):
    base = dict(
        id=uuid.uuid4(), tipo="FACTURAS_PEDIDOS", origen=origen,
        nombre_archivo="f.xlsx", hash_sha256="a" * 64,
        ruta_objeto="FACTURAS_PEDIDOS/x.xlsx", bytes=10, estado=estado,
        filas_leidas=30, filas_validas=25, filas_rechazadas=5,
        periodo_desde=None, periodo_hasta=None, lotes_staged=2,
        ultimo_lote_aplicado=0, latido_en=datetime.utcnow(), log=log,
        subido_por=uuid.uuid4(), aplicado_en=None,
        created_at=datetime.utcnow())
    base.update(extra)
    return CargaArchivo(**base)


def _cliente(role, queue):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    sesion = FakeAsyncSession(execute_queue=queue)
    override_motored_db(sesion)
    return TestClient(app), sesion


@pytest.mark.parametrize(
    "estado", ["APLICADO", "ANULADO", "PROCESANDO", "PENDIENTE", "APLICANDO"])
def test_revalidar_se_rechaza_fuera_de_validado_o_con_errores(
        runner, estado):
    carga = _carga(estado=estado)
    cliente, sesion = _cliente("ADMIN", [[], [carga]])

    respuesta = cliente.post(f"{CARGAS_URL}/{carga.id}/revalidar")

    assert respuesta.status_code == 409
    assert "volver a validar" in respuesta.json()["detail"]
    assert carga.estado == estado
    assert runner.encoladas == []
    assert not sesion.committed


def test_revalidar_una_carga_del_bot_es_409(runner):
    carga = _carga(origen="BOT", tipo="DEMANDA_PERDIDA")
    cliente, _ = _cliente("COMPRAS", [[], [carga]])

    respuesta = cliente.post(f"{CARGAS_URL}/{carga.id}/revalidar")

    assert respuesta.status_code == 409
    assert runner.encoladas == []


@pytest.mark.parametrize("role", ["SUCURSAL", "CONSULTA"])
def test_revalidar_es_solo_para_admin_y_compras(runner, role):
    carga = _carga()
    cliente, _ = _cliente(role, [[], [carga]])

    respuesta = cliente.post(f"{CARGAS_URL}/{carga.id}/revalidar")

    assert respuesta.status_code == 403


def _tablas_borradas(sesion):
    return [s.table.name for s in sesion.executed_statements
            if isinstance(s, Delete)]


@pytest.mark.parametrize("estado", ["VALIDADO", "CON_ERRORES"])
def test_revalidar_borra_staging_y_errores_reinicia_y_encola(runner, estado):
    log = {
        "reemplaza_mes_completo": True,
        "asignaciones_linea": [{"codigo": "X"}],
        "ignorados": [{"codigo_error": "E", "valor": "v"}],
        "filas_con_error": 5, "filas_sin_linea": 3,
        "periodo_veredicto": "ACEPTADO", "error_interno": "boom",
        "columnas_faltantes": ["Parte"],
    }
    carga = _carga(estado=estado, log=log)
    cliente, sesion = _cliente("COMPRAS", [[], [carga], [], []])

    respuesta = cliente.post(f"{CARGAS_URL}/{carga.id}/revalidar")

    assert respuesta.status_code == 202, respuesta.text
    assert sorted(_tablas_borradas(sesion)) == [
        "carga_error", "carga_fila_staging"]
    assert carga.estado == "PENDIENTE"
    assert (carga.filas_leidas, carga.filas_validas,
            carga.filas_rechazadas, carga.lotes_staged) == (0, 0, 0, 0)
    assert carga.latido_en is None
    assert set(carga.log) == {
        "reemplaza_mes_completo", "asignaciones_linea", "ignorados",
        "revalidaciones"}
    assert len(carga.log["revalidaciones"]) == 1
    assert (carga.nombre_archivo, carga.hash_sha256) == ("f.xlsx", "a" * 64)
    assert sesion.committed
    assert runner.encoladas == [(carga.id, "FACTURAS_PEDIDOS")]


def test_un_doble_clic_solo_revalida_una_vez(runner):
    carga = _carga()
    cliente, _ = _cliente("ADMIN", [[], [carga], [], [], [], [carga]])

    primera = cliente.post(f"{CARGAS_URL}/{carga.id}/revalidar")
    segunda = cliente.post(f"{CARGAS_URL}/{carga.id}/revalidar")

    assert primera.status_code == 202
    assert segunda.status_code == 409
    assert runner.encoladas == [(carga.id, "FACTURAS_PEDIDOS")]


def test_aplicar_se_rechaza_mientras_la_revalidacion_espera(runner):
    carga = _carga(estado="PENDIENTE")
    cliente, _ = _cliente("ADMIN", [[], [carga]])

    respuesta = cliente.post(f"{CARGAS_URL}/{carga.id}/aplicar")

    assert respuesta.status_code == 409


# --- end to end over the real dry-run (FACTURAS_PEDIDOS) -------------------


def _xlsx(filas):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(list(facturas_mod.COLUMNAS_ESPERADAS))
    for fila in filas:
        hoja.append(list(fila))
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _fila(parte, factura):
    return ("1801", "MR BUCARAMANGA", None, factura, date(2026, 7, 15),
            parte, 2, Decimal("1000"))


ARCHIVO = _xlsx(
    [_fila("BTX4L", f"RH{100 + i}") for i in range(3)]
    + [_fila("CONOCIDA", "RH200")])


def _cola_dry_run(referencias):
    return [
        [(SUCURSAL_ID, "MR BUCARAMANGA", "1801")],
        [], [],
        list(referencias),
        [PROVEEDOR_ID],
    ]


CONOCIDA = ("CONOCIDA", PROVEEDOR_ID, CONOCIDA_ID)


async def _procesar(monkeypatch, carga, referencias):
    monkeypatch.setattr(
        orquestador.storage, "descargar_archivo", lambda ruta: ARCHIVO)
    sesion = FakeAsyncSession(execute_queue=_cola_dry_run(referencias))
    await orquestador._dry_run(sesion, carga)
    return sesion


async def test_tras_crear_la_referencia_revalidar_deja_las_filas_validas(
        monkeypatch):
    carga = _carga(estado="PROCESANDO", log=None)
    primera = await _procesar(monkeypatch, carga, [CONOCIDA])
    errores = primera.added_of_type(CargaError)
    assert [e.valor for e in errores] == ["BTX4L"] * 3
    assert carga.log["filas_con_error"] == 3

    preparacion = FakeAsyncSession(execute_queue=[[], []])
    await revalidar_mod.preparar_revalidacion(
        preparacion, carga, uuid.uuid4())
    assert carga.estado == "PENDIENTE"
    creada = ("BTX4L", PROVEEDOR_ID, uuid.uuid4())
    segunda = await _procesar(monkeypatch, carga, [CONOCIDA, creada])

    assert segunda.added_of_type(CargaError) == []
    staged = segunda.added_of_type(CargaFilaStaging)
    assert len(staged) == 4
    assert {f.referencia_id for f in staged} == {CONOCIDA_ID, creada[2]}
    assert carga.estado == "VALIDADO"
    assert carga.filas_validas == 4
    assert carga.log["filas_con_error"] == 0


async def test_las_filas_ignoradas_siguen_ignoradas_al_revalidar(monkeypatch):
    carga = _carga(estado="VALIDADO", log={"ignorados": [
        {"codigo_error": "REFERENCIA_NO_ENCONTRADA", "valor": "BTX4L"}]})
    await revalidar_mod.preparar_revalidacion(
        FakeAsyncSession(execute_queue=[[], []]), carga, uuid.uuid4())

    sesion = await _procesar(monkeypatch, carga, [CONOCIDA])

    assert sesion.added_of_type(CargaError) == []
    staged = sesion.added_of_type(CargaFilaStaging)
    assert [f.referencia_id for f in staged] == [CONOCIDA_ID]
    assert carga.log["filas_ignoradas"] == 3
    assert carga.filas_leidas == 4
    assert carga.estado == "VALIDADO"
    assert carga.log["ignorados"] == [
        {"codigo_error": "REFERENCIA_NO_ENCONTRADA", "valor": "BTX4L"}]
