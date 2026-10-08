"""
Cargas > Errores: "Crear referencia" takes a línea comercial and a
proveedor (R1, odd/tasks/motored-cargas-revalidar.md), and "Ignorar" is
remembered on the carga so a revalidation keeps the row out.

No live database: `FakeAsyncSession` queues, and the configured lines are
stubbed (`_lineas_permitidas`); the real Configuración read is covered by
`pg_real/test_revalidar_carga_pg.py`.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import cargas as cargas_api
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

CARGAS_URL = "/api/motored/cargas"
PERMITIDAS = {
    "REPUESTOS": "Repuestos",
    "ACCESORIOS": "Accesorios",
    "NO COMERCIAL": "NO COMERCIAL",
}


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "resolver-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "resolver-asc360-secret")

    async def lineas(db, carga):
        return dict(PERMITIDAS)

    monkeypatch.setattr(cargas_api, "_lineas_permitidas", lineas)
    yield
    app.dependency_overrides.clear()


def _proveedor(codigo="HMCL", activa=True, principal=True):
    return Proveedor(
        id=uuid.uuid4(), codigo=codigo, nombre=codigo,
        es_principal=principal, activa=activa)


def _carga(estado="VALIDADO", log=None):
    return CargaArchivo(
        id=uuid.uuid4(), tipo="FACTURAS_PEDIDOS", origen="EXCEL",
        nombre_archivo="f.xlsx", hash_sha256="a" * 64,
        ruta_objeto="FACTURAS_PEDIDOS/x.xlsx", bytes=10, estado=estado,
        filas_leidas=0, filas_validas=0, filas_rechazadas=0,
        periodo_desde=None, periodo_hasta=None, lotes_staged=0,
        ultimo_lote_aplicado=0, latido_en=None, log=log,
        subido_por=uuid.uuid4(), aplicado_en=None,
        created_at=datetime.utcnow())


def _accion(**campos):
    base = dict(codigo_error="REFERENCIA_NO_ENCONTRADA", valor="BTX4L",
                accion="crear_referencia", linea_comercial=None,
                proveedor_id=None)
    base.update(campos)
    return SimpleNamespace(**base)


async def test_crea_la_referencia_con_la_linea_y_el_proveedor_elegidos():
    otros = _proveedor("OTROS", principal=False)
    db = FakeAsyncSession(execute_queue=[[otros], []])

    aplicada = await cargas_api._aplicar_creacion_referencia(
        db, _accion(linea_comercial=" repuestos ", proveedor_id=otros.id),
        _carga())

    assert aplicada is True
    [creada] = db.added_of_type(Referencia)
    assert creada.codigo == "BTX4L"
    assert creada.proveedor_id == otros.id
    assert creada.linea_comercial == "Repuestos"
    assert creada.unidad_empaque == 1


async def test_sin_proveedor_usa_el_proveedor_principal():
    hmcl = _proveedor("HMCL")
    db = FakeAsyncSession(execute_queue=[[hmcl], []])

    assert await cargas_api._aplicar_creacion_referencia(
        db, _accion(linea_comercial="Accesorios"), _carga()) is True

    [creada] = db.added_of_type(Referencia)
    assert creada.proveedor_id == hmcl.id
    assert creada.linea_comercial == "Accesorios"
    sql = str(db.executed_statements[0].compile(
        compile_kwargs={"literal_binds": True}))
    assert "es_principal" in sql


async def test_un_cliente_viejo_sin_linea_crea_la_referencia_sin_linea():
    hmcl = _proveedor("HMCL")
    db = FakeAsyncSession(execute_queue=[[hmcl], []])

    assert await cargas_api._aplicar_creacion_referencia(
        db, SimpleNamespace(valor="OLD-1")) is True

    [creada] = db.added_of_type(Referencia)
    assert creada.linea_comercial is None
    assert creada.proveedor_id == hmcl.id


@pytest.mark.parametrize("linea", ["MOTOS", "NO COMERCIAL"])
async def test_una_linea_no_configurada_es_422_y_no_crea_nada(linea):
    db = FakeAsyncSession(execute_queue=[[_proveedor()], []])

    with pytest.raises(HTTPException) as exc:
        await cargas_api._aplicar_creacion_referencia(
            db, _accion(linea_comercial=linea), _carga())

    assert exc.value.status_code == 422
    assert "línea comercial" in exc.value.detail
    assert db.added_of_type(Referencia) == []


@pytest.mark.parametrize("proveedor", [None, _proveedor(activa=False)])
async def test_un_proveedor_inexistente_o_inactivo_es_422(proveedor):
    db = FakeAsyncSession(execute_queue=[[proveedor] if proveedor else []])

    with pytest.raises(HTTPException) as exc:
        await cargas_api._aplicar_creacion_referencia(
            db, _accion(linea_comercial="Repuestos",
                        proveedor_id=uuid.uuid4()), _carga())

    assert exc.value.status_code == 422
    assert "proveedor" in exc.value.detail
    assert db.added_of_type(Referencia) == []


async def test_una_referencia_que_ya_existe_no_se_duplica():
    existente = Referencia(id=uuid.uuid4(), codigo="BTX4L",
                           proveedor_id=uuid.uuid4(), unidad_empaque=1)
    db = FakeAsyncSession(execute_queue=[[_proveedor()], [existente]])

    assert await cargas_api._aplicar_creacion_referencia(
        db, _accion(linea_comercial="Repuestos"), _carga()) is False
    assert db.added_of_type(Referencia) == []


def _cliente(role, queue):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    sesion = FakeAsyncSession(execute_queue=queue)
    override_motored_db(sesion)
    return TestClient(app), sesion


def test_el_endpoint_acepta_linea_y_proveedor():
    carga = _carga()
    hmcl = _proveedor()
    cliente, sesion = _cliente("COMPRAS", [[], [carga], [hmcl], []])

    respuesta = cliente.post(f"{CARGAS_URL}/{carga.id}/resolver", json={
        "acciones": [{
            "codigo_error": "REFERENCIA_NO_ENCONTRADA", "valor": "BTX4L",
            "accion": "crear_referencia", "linea_comercial": "Repuestos",
            "proveedor_id": str(hmcl.id)}]})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["acciones_aplicadas"] == 1
    [creada] = sesion.added_of_type(Referencia)
    assert creada.linea_comercial == "Repuestos"


def test_el_endpoint_rechaza_una_linea_desconocida_con_422():
    carga = _carga()
    cliente, _ = _cliente("ADMIN", [[], [carga], [_proveedor()]])

    respuesta = cliente.post(f"{CARGAS_URL}/{carga.id}/resolver", json={
        "acciones": [{
            "codigo_error": "REFERENCIA_NO_ENCONTRADA", "valor": "BTX4L",
            "accion": "crear_referencia", "linea_comercial": "Inventada"}]})

    assert respuesta.status_code == 422
    assert "Inventada" in respuesta.json()["detail"]


def _ignorar(cliente, carga, valor="BTX4L"):
    return cliente.post(f"{CARGAS_URL}/{carga.id}/resolver", json={
        "acciones": [{"codigo_error": "REFERENCIA_NO_ENCONTRADA",
                      "valor": valor, "accion": "ignorar"}]})


def test_ignorar_queda_guardado_en_la_carga_sin_repetirse():
    carga = _carga(log={"reemplaza_mes_completo": True})
    cliente, sesion = _cliente("COMPRAS", [[], [carga], [], [carga]])

    assert _ignorar(cliente, carga).status_code == 200
    assert _ignorar(cliente, carga).status_code == 200

    assert carga.log["ignorados"] == [
        {"codigo_error": "REFERENCIA_NO_ENCONTRADA", "valor": "BTX4L"}]
    assert carga.log["reemplaza_mes_completo"] is True
    assert sesion.committed


@pytest.mark.parametrize("estado", ["PENDIENTE", "PROCESANDO"])
def test_ignorar_mientras_se_procesa_es_409(estado):
    carga = _carga(estado=estado)
    cliente, _ = _cliente("ADMIN", [[], [carga]])

    respuesta = _ignorar(cliente, carga)

    assert respuesta.status_code == 409
    assert "procesando" in respuesta.json()["detail"]


def test_lineas_comerciales_de_la_carga_sin_no_comercial():
    carga = _carga()
    cliente, _ = _cliente("COMPRAS", [[], [carga]])

    respuesta = cliente.get(f"{CARGAS_URL}/{carga.id}/lineas-comerciales")

    assert respuesta.status_code == 200, respuesta.text
    valores = [o["valor"] for o in respuesta.json()]
    assert valores == ["Repuestos", "Accesorios"]
