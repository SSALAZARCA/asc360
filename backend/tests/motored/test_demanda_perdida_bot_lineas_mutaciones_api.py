"""Motored Pedidos — HTTP-layer coverage for `PATCH /api/motored/demanda-
perdida/bot-lineas/{id}` and `POST /api/motored/demanda-perdida/bot-lineas/
{id}/anular` (sdd/motored-ventas-perdidas-panel, Phase 5 "PATCH+POST
endpoints" — S5 commit slice; design D3/D4; tasks 4.4-4.8).

ADMIN-only, no ownership/date-window check (unlike the bot's own
`PATCH /bot/demanda-perdida/lineas/{id}` and `POST /bot/demanda-perdida/
{carga_id}/anular` — an ADMIN acts on ANY line, any date, any advisor).

The PATCH body reuses the bot's own `EditarLineaRequest` (design D3: "This
keeps one bounds rule"), imported straight from `api/bot_demanda_perdida.py`
— never a second, parallel `cantidad` bounds rule. The 404/409 codes mirror
that same bot endpoint's shape (`LINEA_NO_ENCONTRADA`/`LINEA_ANULADA`), minus
its owner/`FUERA_DE_VENTANA` checks, which don't apply to an ADMIN.

Same `FakeAsyncSession`/`AdditiveDemandaPerdidaFakeSession`/`override_motored_
db`/`override_motored_user` convention as `test_demanda_perdida_bot_lineas_
api.py` (GET, Phase 4) and `test_demanda_perdida_bot_anular_linea.py`
(service unit tests, Phase 3). `AdditiveDemandaPerdidaFakeSession` applies
REAL arithmetic semantics to the `demanda_perdida` upsert/update/delete
statements the edit/anular path issues — those never consume the manual
`execute_queue`; only the `DemandaPerdidaBotLinea` SELECT/UPDATE/re-fetch
statements do, in the exact order the endpoint issues them.

`get_motored_db_or_503`'s own `SELECT 1` connectivity probe consumes the
FIRST queued page on every request (same convention documented in the GET
test file) — every `execute_queue` below is prefixed with `[]` for that
reason via the local `_client_with_session`/`_client_as` helpers.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    AdditiveDemandaPerdidaFakeSession,
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

ALL_NON_ADMIN_ROLES = ["COMPRAS", "SUCURSAL", "CONSULTA"]
BOT_LINEAS_URL = "/api/motored/demanda-perdida/bot-lineas"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "bot-lineas-mut-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "bot-lineas-mut-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _client_with_session(role: str, session: "FakeAsyncSession") -> TestClient:
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(session)
    return TestClient(app)


def _client_as(role: str, execute_queue) -> TestClient:
    """`[]` prepended for `get_motored_db_or_503`'s own `SELECT 1` probe —
    same convention as `test_demanda_perdida_bot_lineas_api.py`'s
    `_client_as`."""
    return _client_with_session(role, FakeAsyncSession(execute_queue=[[]] + list(execute_queue)))


def _linea(**overrides) -> DemandaPerdidaBotLinea:
    """Construido a mano (nunca vía `db.add()`) — mismo criterio que
    `_linea()` en `test_demanda_perdida_bot_lineas_api.py`/`test_demanda_
    perdida_bot_anular_linea.py`."""
    base = dict(
        id=uuid.uuid4(),
        carga_id=uuid.uuid4(),
        usuario_id=uuid.uuid4(),
        fecha=date(2026, 9, 20),
        sucursal_id=uuid.uuid4(),
        referencia_id=uuid.uuid4(),
        cantidad=Decimal("3"),
        estado="ACTIVA",
        editado_por=None,
        editado_en=None,
        anulado_por=None,
        anulado_en=None,
        created_at=datetime(2026, 9, 20, 10, 0, 0),
    )
    base.update(overrides)
    return DemandaPerdidaBotLinea(**base)


def _clave(linea: DemandaPerdidaBotLinea) -> tuple:
    return (linea.fecha, linea.sucursal_id, linea.referencia_id, "BOT")


def _fila(
    linea: DemandaPerdidaBotLinea,
    *,
    sucursal_nombre: str = "Sucursal Centro",
    sucursal_activa: bool = True,
    asesor_nombre: str = "Juan Asesor",
    asesor_activo: bool = True,
    referencia_codigo: str = "REF-1",
    referencia_nombre: str = "Referencia Uno",
    carga_log=None,
    editor: "tuple | None" = None,
    anulador: "tuple | None" = None,
) -> tuple:
    """Una fila del re-fetch-con-joins que el PATCH/anular ejecutan tras
    mutar, para construir la respuesta pública — mismo shape de tupla que
    `_fila()` en `test_demanda_perdida_bot_lineas_api.py` (mismos joins,
    reutilizados vía `_stmt_base_bot_lineas`)."""
    editor_id, editor_nombre, editor_activo = editor or (None, None, None)
    anulador_id, anulador_nombre, anulador_activo = anulador or (None, None, None)
    return (
        linea,
        sucursal_nombre,
        sucursal_activa,
        asesor_nombre,
        asesor_activo,
        referencia_codigo,
        referencia_nombre,
        carga_log,
        editor_id,
        editor_nombre,
        editor_activo,
        anulador_id,
        anulador_nombre,
        anulador_activo,
    )


def _nombres_columnas_where(stmt) -> set:
    """Copiado/adaptado de `_extraer_predicados` (convención establecida:
    cada archivo define su propia introspección local) — acá solo interesan
    los NOMBRES de columna filtrados en el WHERE de nivel superior, no sus
    valores, para probar la ausencia de un filtro por `carga_id`."""
    whereclause = getattr(stmt, "whereclause", None)
    if whereclause is None:
        return set()
    clausulas = getattr(whereclause, "clauses", [whereclause])
    nombres = set()
    for clausula in clausulas:
        left = getattr(clausula, "left", None)
        nombre = getattr(left, "key", None)
        if nombre:
            nombres.add(nombre)
    return nombres


def _admin() -> MotoredUser:
    return MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN")


# ---------------------------------------------------------------------------
# PATCH /bot-lineas/{id} — ADMIN-only + validación
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ALL_NON_ADMIN_ROLES)
def test_editar_bot_linea_rechaza_roles_no_admin(role):
    client = _client_as(role, execute_queue=[])

    response = client.patch(f"{BOT_LINEAS_URL}/{uuid.uuid4()}", json={"cantidad": 5})

    assert response.status_code == 403


def test_editar_bot_linea_cantidad_cero_es_422():
    client = _client_as("ADMIN", execute_queue=[])

    response = client.patch(f"{BOT_LINEAS_URL}/{uuid.uuid4()}", json={"cantidad": 0})

    assert response.status_code == 422


def test_editar_bot_linea_cantidad_negativa_es_422():
    client = _client_as("ADMIN", execute_queue=[])

    response = client.patch(f"{BOT_LINEAS_URL}/{uuid.uuid4()}", json={"cantidad": -1})

    assert response.status_code == 422


def test_editar_bot_linea_inexistente_es_404():
    client = _client_as("ADMIN", execute_queue=[[]])  # SELECT ... FOR UPDATE -- 0 filas

    response = client.patch(f"{BOT_LINEAS_URL}/{uuid.uuid4()}", json={"cantidad": 5})

    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "LINEA_NO_ENCONTRADA"}


def test_editar_bot_linea_anulada_es_409():
    linea = _linea(estado="ANULADA")
    client = _client_as("ADMIN", execute_queue=[[linea]])

    response = client.patch(f"{BOT_LINEAS_URL}/{linea.id}", json={"cantidad": 5})

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "LINEA_ANULADA"}


def test_editar_bot_linea_activa_aumenta_cantidad_y_estampa_auditoria():
    linea = _linea(cantidad=Decimal("3"))
    admin_id = uuid.uuid4()
    fila_respuesta = _fila(linea, editor=(admin_id, "Ana Admin", True))
    session = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[[], [linea], [fila_respuesta]],
        filas_iniciales={_clave(linea): Decimal(10)},
    )
    override_motored_user(MotoredUser(user_id=str(admin_id), role="ADMIN"))
    override_motored_db(session)
    client = TestClient(app)

    response = client.patch(f"{BOT_LINEAS_URL}/{linea.id}", json={"cantidad": 5})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cantidad"] == 5.0
    assert body["editado_por"] == {"id": str(admin_id), "nombre": "Ana Admin", "activo": True}
    assert body["editado_en"] is not None
    assert linea.cantidad == Decimal("5")
    assert linea.editado_por == admin_id
    assert linea.editado_en is not None
    # El agregado se movió exactamente por el delta (+2), no por la cantidad completa.
    assert session.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id,
    ) == Decimal(12)


def test_editar_bot_linea_activa_disminuye_cantidad_por_el_delta_exacto():
    linea = _linea(cantidad=Decimal("5"))
    fila_respuesta = _fila(linea)
    session = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[[], [linea], [fila_respuesta]],
        filas_iniciales={_clave(linea): Decimal(10)},
    )
    client = _client_with_session("ADMIN", session)

    response = client.patch(f"{BOT_LINEAS_URL}/{linea.id}", json={"cantidad": 2})

    assert response.status_code == 200, response.text
    assert linea.cantidad == Decimal("2")
    assert session.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id,
    ) == Decimal(7)


def test_editar_bot_linea_delta_cero_no_estampa_ni_toca_agregado():
    linea = _linea(cantidad=Decimal("4"))
    fila_respuesta = _fila(linea)
    session = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[[], [linea], [fila_respuesta]],
        filas_iniciales={_clave(linea): Decimal(10)},
    )
    client = _client_with_session("ADMIN", session)

    response = client.patch(f"{BOT_LINEAS_URL}/{linea.id}", json={"cantidad": 4})

    assert response.status_code == 200, response.text
    assert linea.cantidad == Decimal("4")
    assert linea.editado_por is None
    assert linea.editado_en is None
    assert response.json()["editado_por"] is None
    assert session.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id,
    ) == Decimal(10)


def test_editar_bot_linea_segunda_edicion_por_otro_admin_sobreescribe_sin_historial():
    primer_editor = uuid.uuid4()
    linea = _linea(
        cantidad=Decimal("5"),
        editado_por=primer_editor,
        editado_en=datetime(2026, 9, 21, 8, 0, 0, tzinfo=timezone.utc),
    )
    segundo_admin_id = uuid.uuid4()
    fila_respuesta = _fila(linea, editor=(segundo_admin_id, "Beto Admin", True))
    session = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[[], [linea], [fila_respuesta]],
        filas_iniciales={_clave(linea): Decimal(10)},
    )
    override_motored_user(MotoredUser(user_id=str(segundo_admin_id), role="ADMIN"))
    override_motored_db(session)
    client = TestClient(app)

    response = client.patch(f"{BOT_LINEAS_URL}/{linea.id}", json={"cantidad": 7})

    assert response.status_code == 200, response.text
    assert response.json()["editado_por"]["id"] == str(segundo_admin_id)
    assert linea.editado_por == segundo_admin_id
    assert linea.editado_por != primer_editor


# ---------------------------------------------------------------------------
# POST /bot-lineas/{id}/anular — ADMIN-only + validación
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ALL_NON_ADMIN_ROLES)
def test_anular_bot_linea_rechaza_roles_no_admin(role):
    client = _client_as(role, execute_queue=[])

    response = client.post(f"{BOT_LINEAS_URL}/{uuid.uuid4()}/anular")

    assert response.status_code == 403


def test_anular_bot_linea_inexistente_es_404():
    client = _client_as("ADMIN", execute_queue=[[]])  # SELECT ... FOR UPDATE -- 0 filas

    response = client.post(f"{BOT_LINEAS_URL}/{uuid.uuid4()}/anular")

    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "LINEA_NO_ENCONTRADA"}


def test_anular_bot_linea_ya_anulada_es_409():
    linea = _linea(estado="ACTIVA")
    session = FakeAsyncSession(execute_queue=[[], [linea], []])  # SELECT + claim (0 filas -> perdido)
    client = _client_with_session("ADMIN", session)

    response = client.post(f"{BOT_LINEAS_URL}/{linea.id}/anular")

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "LINEA_ANULADA"}


def test_anular_bot_linea_activa_marca_anulada_y_estampa_auditoria():
    linea = _linea(cantidad=Decimal("4"))
    admin_id = uuid.uuid4()
    fila_respuesta = _fila(linea, anulador=(admin_id, "Ana Admin", True))
    session = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[[], [linea], [linea.id], [fila_respuesta]],
        filas_iniciales={_clave(linea): Decimal(10)},
    )
    override_motored_user(MotoredUser(user_id=str(admin_id), role="ADMIN"))
    override_motored_db(session)
    client = TestClient(app)

    response = client.post(f"{BOT_LINEAS_URL}/{linea.id}/anular")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["estado"] == "ANULADA"
    assert body["anulado_por"] == {"id": str(admin_id), "nombre": "Ana Admin", "activo": True}
    assert body["anulado_en"] is not None
    assert body["agregado_consistente"] is True
    assert linea.estado == "ANULADA"
    assert linea.anulado_por == admin_id
    assert session.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id,
    ) == Decimal(6)


def test_anular_bot_linea_agregado_consistente_false_cuando_falta_la_fila_demanda_perdida():
    """Adaptado del escenario de Phase 3 (`test_returns_false_when_matching_
    aggregate_row_is_missing`): `filas_iniciales` vacío a propósito -- la
    línea igual queda ANULADA, pero `agregado_consistente` surfacea el
    estado inconsistente al cliente del panel."""
    linea = _linea(cantidad=Decimal("2"))
    fila_respuesta = _fila(linea)
    session = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[[], [linea], [linea.id], [fila_respuesta]],
    )
    client = _client_with_session("ADMIN", session)

    response = client.post(f"{BOT_LINEAS_URL}/{linea.id}/anular")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["estado"] == "ANULADA"
    assert body["agregado_consistente"] is False
    assert linea.estado == "ANULADA"


def test_anular_bot_linea_no_toca_lineas_hermanas_de_la_misma_carga():
    """Prueba de regresión MÁS IMPORTANTE de esta fase (design D4): a
    diferencia de `anular_registro_bot` (que anula TODO el header y cada
    línea ACTIVA bajo él), `anular_linea_bot` -- y este endpoint -- solo
    debe tocar la línea puntual recibida. Se prueba en 2 niveles: (1) una
    línea hermana de la MISMA carga nunca se muta (sigue `ACTIVA`, nunca fue
    ni siquiera encolada como resultado de ninguna consulta); (2) ningún
    statement ejecutado por el endpoint filtra por `carga_id` -- si un futuro
    cambio reemplazara por error la llamada por `anular_registro_bot`, este
    test lo detectaría antes de llegar a producción."""
    carga_id = uuid.uuid4()
    linea = _linea(carga_id=carga_id, cantidad=Decimal("4"))
    hermana = _linea(carga_id=carga_id, cantidad=Decimal("2"), estado="ACTIVA")
    fila_respuesta = _fila(linea)
    session = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[[], [linea], [linea.id], [fila_respuesta]],
        filas_iniciales={_clave(linea): Decimal(10), _clave(hermana): Decimal(10)},
    )
    client = _client_with_session("ADMIN", session)

    response = client.post(f"{BOT_LINEAS_URL}/{linea.id}/anular")

    assert response.status_code == 200, response.text
    assert response.json()["carga_id"] == str(carga_id)
    # La hermana nunca fue tocada por ningún código bajo test.
    assert hermana.estado == "ACTIVA"
    assert hermana.anulado_por is None
    # Su aporte al agregado permanece intacto -- solo se revirtió el de `linea`.
    assert session.cantidad_actual(
        fecha=hermana.fecha, sucursal_id=hermana.sucursal_id, referencia_id=hermana.referencia_id,
    ) == Decimal(10)
    # Ningún statement de este endpoint filtra por `carga_id`.
    columnas_consultadas = set()
    for stmt in session.executed_statements:
        columnas_consultadas |= _nombres_columnas_where(stmt)
    assert "carga_id" not in columnas_consultadas
