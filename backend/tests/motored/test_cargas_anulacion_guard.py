"""
Motored Pedidos F3 "Motor", S7 (sdd/motored-pedidos-motor, ADR-11, spec
"Anulación guard for cargas"): `POST /cargas/{id}/anular` de una carga EXCEL
pasa por `guardas.aplicar_guard_anulacion`.

Las consultas de la guarda se prueban en `test_corrida_guardas.py` y contra
Postgres en `pg_real`. Acá se prueba el CABLEADO: cuándo se llama (sólo EXCEL
y sólo si la carga no estaba anulada), qué responde el endpoint ante un
bloqueo E-CARGA-050 (409 con el código, carga intacta, sin commit) y que sin
corridas el camino de F2 no cambia.
"""
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import CompileError

from app.config import settings
from app.main import app
from app.motored.api import cargas as cargas_api
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import codigos
from app.motored.services.corridas.codigos import ErrorCorrida
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

URL = "/api/motored/cargas"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "guard-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "guard-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _carga(estado="APLICADO", origen="EXCEL", tipo="DEMANDA_PERDIDA"):
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen=origen,
        nombre_archivo="perdida.xlsx", hash_sha256="a" * 64,
        ruta_objeto="x", bytes=1, estado=estado, filas_leidas=0,
        filas_validas=0, filas_rechazadas=0, lotes_staged=0,
        ultimo_lote_aplicado=0, subido_por=uuid.uuid4(),
        created_at=datetime(2026, 9, 21, 10))


def _cliente(cola, rol="ADMIN"):
    sesion = FakeAsyncSession(execute_queue=cola)
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    override_motored_db(sesion)
    return TestClient(app), sesion


def _sql(sentencia) -> str:
    """SQL con literales; los JSONB no tienen renderizador literal, así que
    esas sentencias se muestran con sus marcadores."""
    try:
        return str(sentencia.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True}))
    except CompileError:
        return str(sentencia.compile(dialect=postgresql.dialect()))


# Cola de la anulación real: sonda, carga, y las tres consultas de la guarda
# (bloqueo FOR UPDATE, pedido bloqueante, invalidación) antes del DELETE.
# `cerrada` lleva filas `(corrida, tienda, estado_pedido)`.
def _cola(cerrada=(), invalidadas=(), carga=None):
    return [[], [carga], [], list(cerrada), list(invalidadas), []]


def test_without_corridas_the_annulment_proceeds_as_in_f2():
    carga = _carga()
    cliente, sesion = _cliente(_cola(carga=carga))

    respuesta = cliente.post(f"{URL}/{carga.id}/anular")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "ANULADO"
    assert carga.estado == "ANULADO" and sesion.committed


def test_the_guard_locks_the_carga_before_anything_else():
    carga = _carga()
    cliente, sesion = _cliente(_cola(carga=carga))

    cliente.post(f"{URL}/{carga.id}/anular")

    # 0 sonda, 1 carga, 2 FOR UPDATE, 3 pedido bloqueante, 4 invalidación,
    # 5 DELETE del staging.
    sentencias = [_sql(s) for s in sesion.executed_statements]
    assert "FOR UPDATE" in sentencias[2]
    assert "corrida" in sentencias[3] and "CERRADA" in sentencias[3]
    assert "'CERRADO', 'ENVIADO'" in sentencias[3]
    assert sentencias[4].startswith("UPDATE corrida")
    assert sentencias[5].startswith("DELETE FROM carga_fila_staging")


def test_a_closed_tienda_blocks_the_annulment_naming_tienda_and_corrida():
    carga = _carga()
    cliente, _ = _cliente(_cola(
        cerrada=[("PED-2026-S39-001", "Manizales", "CERRADO")],
        carga=carga))

    respuesta = cliente.post(f"{URL}/{carga.id}/anular")

    assert respuesta.status_code == 409
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == codigos.E_CARGA_ANULACION_BLOQUEADA
    assert detalle["message"] == (
        "La carga la usa el pedido cerrado de Manizales (corrida "
        "PED-2026-S39-001) y no se puede anular.")


def test_a_legacy_cerrada_corrida_still_blocks_with_its_codigo():
    carga = _carga()
    cliente, _ = _cliente(_cola(
        cerrada=[("PED-2026-S39-001", None, None)], carga=carga))

    respuesta = cliente.post(f"{URL}/{carga.id}/anular")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["message"] == (
        "La carga la usa la corrida cerrada PED-2026-S39-001 y no se puede "
        "anular.")


def test_a_blocked_annulment_leaves_the_carga_untouched():
    carga = _carga()
    cliente, sesion = _cliente(_cola(
        cerrada=[("PED-2026-S39-001", "Manizales", "ENVIADO")],
        carga=carga))

    cliente.post(f"{URL}/{carga.id}/anular")

    assert carga.estado == "APLICADO"
    assert not sesion.committed and sesion.rolled_back
    assert len(sesion.executed_statements) == 4
    assert not any(
        "DELETE" in _sql(s) for s in sesion.executed_statements)


def test_live_corridas_are_invalidated_and_the_annulment_proceeds():
    carga = _carga()
    cliente, sesion = _cliente(_cola(
        invalidadas=["PED-2026-S39-002", "ESC-2026-S39-001"], carga=carga))

    respuesta = cliente.post(f"{URL}/{carga.id}/anular")

    assert respuesta.status_code == 200, respuesta.text
    assert carga.estado == "ANULADO" and sesion.committed
    assert "invalidada" in _sql(sesion.executed_statements[4])


def test_the_guard_is_called_once_with_the_carga_for_an_excel_origin(
        monkeypatch):
    carga = _carga()
    llamadas = []

    async def guarda(db, recibida):
        llamadas.append(recibida)
        return []

    monkeypatch.setattr(cargas_api, "aplicar_guard_anulacion", guarda)
    cliente, _ = _cliente([[], [carga], []])

    respuesta = cliente.post(f"{URL}/{carga.id}/anular")

    assert respuesta.status_code == 200, respuesta.text
    assert llamadas == [carga]


def test_the_bot_branch_never_reaches_the_guard(monkeypatch):
    carga = _carga(origen="BOT")

    async def guarda(db, recibida):
        raise AssertionError("la rama BOT no pasa por la guarda")

    async def anular_bot(db, recibida, actor, validar_ventana=False):
        recibida.estado = "ANULADO"

    monkeypatch.setattr(cargas_api, "aplicar_guard_anulacion", guarda)
    monkeypatch.setattr(
        cargas_api.demanda_perdida_bot_mod, "anular_registro_bot",
        anular_bot)
    cliente, _ = _cliente([[], [carga]])

    respuesta = cliente.post(f"{URL}/{carga.id}/anular")

    assert respuesta.status_code == 200, respuesta.text


def test_an_already_annulled_carga_is_a_409_before_the_guard(monkeypatch):
    carga = _carga(estado="ANULADO")

    async def guarda(db, recibida):
        raise AssertionError("no se evalúa una carga ya anulada")

    monkeypatch.setattr(cargas_api, "aplicar_guard_anulacion", guarda)
    cliente, _ = _cliente([[], [carga]])

    respuesta = cliente.post(f"{URL}/{carga.id}/anular")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "La carga ya está anulada."


def test_any_other_coded_error_of_the_guard_is_not_swallowed(monkeypatch):
    carga = _carga()

    async def guarda(db, recibida):
        raise ErrorCorrida("E-CORRIDA-099", "otro error")

    monkeypatch.setattr(cargas_api, "aplicar_guard_anulacion", guarda)
    cliente, sesion = _cliente([[], [carga]])

    respuesta = cliente.post(f"{URL}/{carga.id}/anular")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-099"
    assert carga.estado == "APLICADO" and not sesion.committed


@pytest.mark.parametrize("rol", ["SUCURSAL", "CONSULTA"])
def test_read_only_roles_cannot_annul(rol):
    carga = _carga()
    cliente, _ = _cliente([[]], rol=rol)

    assert cliente.post(f"{URL}/{carga.id}/anular").status_code == 403
