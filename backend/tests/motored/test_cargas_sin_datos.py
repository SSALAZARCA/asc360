"""
Motored: declare "no data at this date" for BACKORDER, FACTURAS_PEDIDOS and
INGRESOS_FACTURAS (odd/tasks/motored-cargas-sin-datos.md, T1).

A declaration is an APLICADO `carga_archivo` with zero rows and no file. It
must satisfy the corrida preflight exactly like an uploaded carga, stay
auditable (user and date) and be anulable like any other EXCEL carga.
"""
import asyncio
import datetime
import uuid
from datetime import timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import parametros_corrida as pcorr
from app.motored.services.corridas import vigencia
from app.motored.services.corridas.vigencia import CargaVista, HechosVigencia
from app.motored.services.ingesta import sin_datos
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

URL = "/api/motored/cargas"
AHORA = datetime.datetime(2026, 9, 21, 15, tzinfo=timezone.utc)
HOY = datetime.date(2026, 9, 21)
CORTE = HOY


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "sd-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "sd-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _cliente(cola, rol="ADMIN"):
    sesion = FakeAsyncSession(execute_queue=cola)
    usuario = MotoredUser(user_id=str(uuid.uuid4()), role=rol)
    override_motored_user(usuario)
    override_motored_db(sesion)
    return TestClient(app), sesion, usuario


async def _declarar(tipo, fecha=HOY, cola=None):
    sesion = FakeAsyncSession(execute_queue=cola if cola is not None
                              else [[], []])
    usuario_id = uuid.uuid4()
    carga = await sin_datos.declarar_sin_datos(
        sesion, tipo, fecha, usuario_id, ahora=AHORA)
    return carga, sesion, usuario_id


# --- Validation --------------------------------------------------------------


@pytest.mark.parametrize("tipo", ["VENTAS", "INVENTARIO", "", "OTRO"])
async def test_only_the_three_declarable_types_are_accepted(tipo):
    with pytest.raises(sin_datos.DeclaracionInvalida) as info:
        await _declarar(tipo)
    assert "backorder" in str(info.value)


async def test_a_future_date_is_rejected():
    manana = HOY + datetime.timedelta(days=1)
    with pytest.raises(sin_datos.DeclaracionInvalida) as info:
        await _declarar("BACKORDER", manana)
    assert "futuro" in str(info.value)


async def test_any_past_date_is_accepted():
    carga, _, _ = await _declarar(
        "FACTURAS_PEDIDOS", datetime.date(2025, 1, 31))
    assert carga.periodo_desde == datetime.date(2025, 1, 31)


async def test_a_live_declaration_for_the_same_type_and_date_conflicts():
    with pytest.raises(sin_datos.DeclaracionEnConflicto) as info:
        await _declarar("INGRESOS_FACTURAS", cola=[[uuid.uuid4()]])
    assert "Ya hay una declaración" in str(info.value)


async def test_backorder_rows_at_that_cutoff_conflict():
    with pytest.raises(sin_datos.DeclaracionEnConflicto) as info:
        await _declarar("BACKORDER", cola=[[], [uuid.uuid4()]])
    assert "Anulá" in str(info.value)


async def test_facturas_never_look_at_backorder_rows():
    _, sesion, _ = await _declarar("FACTURAS_PEDIDOS", cola=[[]])
    assert len(sesion.executed_statements) == 1


# --- Creation ----------------------------------------------------------------


async def test_the_declaration_is_an_applied_carga_with_zero_rows():
    carga, sesion, usuario_id = await _declarar("BACKORDER")

    assert sesion.added == [carga]
    assert carga.tipo == "BACKORDER"
    assert carga.estado == "APLICADO"
    assert carga.origen == "EXCEL"
    assert carga.nombre_archivo == "Sin datos (declarado)"
    assert carga.periodo_desde == HOY and carga.periodo_hasta == HOY
    assert (carga.filas_leidas, carga.filas_validas,
            carga.filas_rechazadas) == (0, 0, 0)
    assert carga.aplicado_en == AHORA
    assert carga.subido_por == usuario_id
    assert carga.log == {"sin_datos": True}
    assert carga.bytes == 0


async def test_the_declaration_never_looks_like_an_uploaded_file():
    carga, _, _ = await _declarar("BACKORDER")
    assert carga.hash_sha256 == sin_datos.SIN_ARCHIVO
    assert carga.ruta_objeto == sin_datos.SIN_ARCHIVO
    assert len(carga.hash_sha256) != 64


# --- Endpoint ----------------------------------------------------------------


def test_the_endpoint_creates_and_commits_the_declaration():
    cliente, sesion, usuario = _cliente([[], [], []])

    respuesta = cliente.post(
        f"{URL}/sin-datos",
        json={"tipo": "BACKORDER", "fecha": "2026-09-01"})

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "APLICADO"
    assert cuerpo["sin_datos"] is True
    assert cuerpo["nombre_archivo"] == "Sin datos (declarado)"
    assert cuerpo["periodo_desde"] == "2026-09-01"
    assert sesion.committed
    assert str(sesion.added[0].subido_por) == usuario.user_id


def test_the_endpoint_rejects_an_unknown_type_in_spanish():
    cliente, sesion, _ = _cliente([[]])

    respuesta = cliente.post(
        f"{URL}/sin-datos", json={"tipo": "VENTAS", "fecha": "2026-09-01"})

    assert respuesta.status_code == 422
    assert "backorder" in respuesta.json()["detail"]
    assert not sesion.added and not sesion.committed


def test_the_endpoint_rejects_a_future_date():
    cliente, sesion, _ = _cliente([[]])
    futura = (datetime.date.today() + datetime.timedelta(days=3))

    respuesta = cliente.post(
        f"{URL}/sin-datos",
        json={"tipo": "BACKORDER", "fecha": futura.isoformat()})

    assert respuesta.status_code == 422
    assert "futuro" in respuesta.json()["detail"]
    assert not sesion.committed


def test_the_endpoint_answers_409_on_a_conflict():
    cliente, sesion, _ = _cliente([[], [uuid.uuid4()]])

    respuesta = cliente.post(
        f"{URL}/sin-datos",
        json={"tipo": "FACTURAS_PEDIDOS", "fecha": "2026-09-01"})

    assert respuesta.status_code == 409
    assert not sesion.committed


@pytest.mark.parametrize("rol", ["SUCURSAL", "CONSULTA"])
def test_read_only_roles_cannot_declare(rol):
    cliente, sesion, _ = _cliente([[], [], []], rol=rol)

    respuesta = cliente.post(
        f"{URL}/sin-datos",
        json={"tipo": "BACKORDER", "fecha": "2026-09-01"})

    assert respuesta.status_code == 403
    assert not sesion.added


def test_compras_can_declare():
    cliente, _, _ = _cliente([[], [], []], rol="COMPRAS")

    respuesta = cliente.post(
        f"{URL}/sin-datos",
        json={"tipo": "INGRESOS_FACTURAS", "fecha": "2026-09-01"})

    assert respuesta.status_code == 201, respuesta.text


def test_the_list_marks_declarations_and_not_uploaded_files():
    archivo = _carga_subida()
    declarada, _, _ = _run(_declarar("BACKORDER"))
    cliente, _, _ = _cliente([[], [declarada, archivo]], rol="CONSULTA")

    respuesta = cliente.get(f"{URL}?tipo=BACKORDER")

    assert respuesta.status_code == 200
    assert [c["sin_datos"] for c in respuesta.json()] == [True, False]


# --- Anular ------------------------------------------------------------------


def test_a_declaration_can_be_annulled_through_the_regular_flow():
    declarada, _, _ = _run(_declarar("BACKORDER"))
    cliente, sesion, _ = _cliente([[], [declarada], [], [], [], []])

    respuesta = cliente.post(f"{URL}/{declarada.id}/anular")

    assert respuesta.status_code == 200, respuesta.text
    assert declarada.estado == "ANULADO" and sesion.committed


# --- Preflight ---------------------------------------------------------------


def _params():
    fila = ParametroMetodologia(
        id=uuid.uuid4(), clave="modo_mes_en_curso", valor="EXCLUIDO",
        vigente_desde=datetime.date(2026, 1, 1), sucursal_id=None)
    vigentes = parametros.VigentesMotor.desde_filas([fila], CORTE)
    return pcorr.construir_parametros_corrida(vigentes, [])


def _vista(carga):
    """The same projection `vigencia.cargar_hechos` reads from the row."""
    return CargaVista(
        carga_id=carga.id, tipo=carga.tipo, estado=carga.estado,
        periodo_desde=carga.periodo_desde,
        periodo_hasta=carga.periodo_hasta, aplicado_en=carga.aplicado_en,
        fecha_max_detectada=None)


def _vista_subida(tipo, fecha):
    instante = datetime.datetime(
        fecha.year, fecha.month, fecha.day, 12, tzinfo=timezone.utc)
    return CargaVista(
        carga_id=uuid.uuid4(), tipo=tipo, estado="APLICADO",
        periodo_desde=fecha, periodo_hasta=fecha, aplicado_en=instante,
        fecha_max_detectada=fecha)


def _cargas_al_dia():
    ayer = CORTE - datetime.timedelta(days=1)
    return [
        _vista_subida("VENTAS", datetime.date(2026, 3, 1)),
        CargaVista(
            uuid.uuid4(), "VENTAS", "APLICADO", datetime.date(2026, 3, 1),
            datetime.date(2026, 9, 14),
            datetime.datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            datetime.date(2026, 9, 14)),
        _vista_subida("INVENTARIO", ayer),
    ]


@pytest.mark.parametrize(
    "tipo,clave",
    [("BACKORDER", "backorder"), ("FACTURAS_PEDIDOS", "facturas"),
     ("INGRESOS_FACTURAS", "ingresos")])
def test_the_preflight_accepts_a_declaration_of_each_type(tipo, clave):
    declarada, _, _ = _run(_declarar(tipo))
    otros = {
        "BACKORDER", "FACTURAS_PEDIDOS", "INGRESOS_FACTURAS"} - {tipo}
    cargas = _cargas_al_dia() + [_vista(declarada)] + [
        _vista_subida(t, CORTE) for t in otros]
    hechos = HechosVigencia(tuple(cargas), True, True)

    resultado = vigencia.evaluar_vigencia(hechos, CORTE, _params())

    assert resultado.cargas_usadas[clave] == (declarada.id,)
    assert resultado.antiguedad[clave]["antiguedad_dias"] == 0


def test_an_annulled_declaration_no_longer_counts():
    declarada, _, _ = _run(_declarar("BACKORDER"))
    declarada.estado = "ANULADO"
    cargas = _cargas_al_dia() + [
        _vista(declarada),
        _vista_subida("FACTURAS_PEDIDOS", CORTE),
        _vista_subida("INGRESOS_FACTURAS", CORTE)]
    hechos = HechosVigencia(tuple(cargas), True, True)

    with pytest.raises(vigencia.ErrorVigencia) as info:
        vigencia.evaluar_vigencia(hechos, CORTE, _params())

    assert info.value.detalle["antiguedad"]["backorder"]["carga_id"] is None


# --- Helpers -----------------------------------------------------------------


def _run(corutina):
    return asyncio.run(corutina)


def _carga_subida():
    return CargaArchivo(
        id=uuid.uuid4(), tipo="BACKORDER", origen="EXCEL",
        nombre_archivo="backorder.xlsx", hash_sha256="a" * 64,
        ruta_objeto="x", bytes=1, estado="APLICADO", filas_leidas=3,
        filas_validas=3, filas_rechazadas=0, lotes_staged=1,
        ultimo_lote_aplicado=1, subido_por=uuid.uuid4(),
        periodo_desde=HOY, periodo_hasta=HOY, log={"x": 1},
        created_at=datetime.datetime(2026, 9, 21, 10))
