"""
Phase 4 "Approval service + Usuarios UI" (sdd/motored-ventas-perdidas-bot,
tasks 4.3/4.4/4.5; design D5) — HTTP-layer coverage for
`api/motored/usuarios.py`'s new surface:

- `GET /usuarios?status=pending` (pending-requests list)
- `POST /usuarios/{id}/aprobar` | `/rechazar` (ADMIN-only, delegates to
  `services/solicitudes.py::resolver_solicitud` -- design D5 explicitly
  requires the web screen and the bot's own approval buttons to call the
  SAME function, never duplicate the transition logic)
- `POST /usuarios/me/telegram/codigo` | `DELETE /usuarios/me/telegram`
  (ADMIN-only, self-service Telegram linking for push notifications)
- `UsuarioRead` gains `status`/`phone`/`telegram_vinculado`, never the raw
  `telegram_id`; `email` becomes optional (an `ASESOR_MOSTRADOR` row has
  none -- Phase 1's nullable-web-credentials schema).

Same `FakeAsyncSession`/`override_motored_db`/`override_motored_user`/
`motored_client` convention as `test_cargas_api.py`/`test_rbac_matrix.py`.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.usuario import Usuario
from app.motored.services.auth import MotoredUser
from app.motored.services.solicitudes import SolicitudYaResuelta
from tests.motored.conftest import (
    FakeAsyncSession,
    _ExecuteResult,
    override_motored_db,
    override_motored_user,
)

ALL_ROLES = ["ADMIN", "COMPRAS", "SUCURSAL", "CONSULTA"]
USUARIOS_URL = "/api/motored/usuarios"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "usuarios-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "usuarios-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _client_as(role: str, execute_queue, user_id=None) -> TestClient:
    """`[[]]` is prepended for `get_motored_db_or_503`'s own `SELECT 1`
    connectivity probe -- a real per-endpoint dependency the `db` param
    always runs, on top of whatever `execute_queue` the caller supplies for
    the actual business-logic queries (same convention as
    `test_cargas_api.py`'s `_client_as`, which queues a leading `[]` for
    the exact same reason)."""
    override_motored_user(MotoredUser(user_id=user_id or str(uuid.uuid4()), role=role))
    override_motored_db(FakeAsyncSession(execute_queue=[[]] + list(execute_queue)))
    return TestClient(app)


def _asesor_pending(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Juan Asesor", email=None, hashed_password=None,
        role="ASESOR_MOSTRADOR", activo=True, status="pending",
        telegram_id=555, phone="3001234567",
    )
    base.update(overrides)
    return Usuario(**base)


def _admin(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Ana Admin", email="ana@motoredcolombia.com.co",
        hashed_password="hash", role="ADMIN", activo=True, status="approved",
        telegram_id=None,
    )
    base.update(overrides)
    return Usuario(**base)


# ---------------------------------------------------------------------------
# UsuarioRead: nullable email, status/phone/telegram_vinculado, never raw id
# ---------------------------------------------------------------------------

def test_list_usuarios_serializes_asesor_mostrador_row_with_null_email_without_500():
    asesor = _asesor_pending()
    client = _client_as("ADMIN", execute_queue=[[asesor]])

    response = client.get(USUARIOS_URL)

    assert response.status_code == 200, response.text
    body = response.json()[0]
    assert body["email"] is None
    assert body["status"] == "pending"
    assert body["phone"] == "3001234567"
    assert body["telegram_vinculado"] is True
    assert "telegram_id" not in body


def test_list_usuarios_admin_without_telegram_shows_telegram_vinculado_false():
    admin = _admin(telegram_id=None)
    client = _client_as("ADMIN", execute_queue=[[admin]])

    response = client.get(USUARIOS_URL)

    assert response.json()[0]["telegram_vinculado"] is False


# ---------------------------------------------------------------------------
# GET /usuarios?status=pending
# ---------------------------------------------------------------------------

def _extraer_predicados(stmt) -> list:
    """Local copy of `test_cargas_api.py`'s post-review-hardened helper
    (finding #3): walks the compiled top-level AND WHERE clauses and
    returns `(column_name, operator, value)` per direct column-vs-literal
    comparison -- proves REAL filtering behavior, not just bind-param
    presence. Kept as a local, independently-readable copy per this
    suite's own established convention (see `conftest.py`'s
    `FakeAsyncSession` docstring), not a cross-file import.

    Post-Phase-4 review (finding #5) extension: also handles `.is_(True)`/
    `.is_(False)` clauses (e.g. `Usuario.activo.is_(True)`), which compile
    to a literal `IS true`/`IS false` with no bound-param `.value` -- so
    `?status=pending`'s ALSO-`activo` guard can be proven for real too, not
    just its `status` half."""
    whereclause = getattr(stmt, "whereclause", None)
    if whereclause is None:
        return []
    clausulas = getattr(whereclause, "clauses", [whereclause])
    predicados = []
    for clausula in clausulas:
        left = getattr(clausula, "left", None)
        right = getattr(clausula, "right", None)
        operador = getattr(clausula, "operator", None)
        nombre_columna = getattr(left, "key", None)
        if nombre_columna is None or operador is None:
            continue
        if hasattr(right, "value"):
            predicados.append((nombre_columna, operador, right.value))
        elif str(right) in ("true", "false"):
            # `operators.is_(a, b)` calls `a.is_(b)` -- fine for a real
            # SQLAlchemy column/value, but the candidate rows here are
            # plain Python objects, so a raw `bool` has no `.is_()` method.
            # Use direct identity comparison instead for this clause shape.
            predicados.append((nombre_columna, lambda a, b: a is b, str(right) == "true"))
    return predicados


class _FilteringFakeSession(FakeAsyncSession):
    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        if not self._execute_queue:
            raise AssertionError(
                "FakeAsyncSession.execute() called more times than expected "
                "— update the test's execute_queue."
            )
        rows = self._execute_queue.pop(0)
        predicados = _extraer_predicados(stmt)
        if predicados:
            rows = [
                row for row in rows
                if all(
                    hasattr(row, nombre) and operador(getattr(row, nombre), valor)
                    for nombre, operador, valor in predicados
                )
            ]
        return _ExecuteResult(rows)


def test_list_usuarios_status_pending_filters_server_side():
    """Proves real filtering (not just bind-param presence): queues BOTH a
    `pending` and an `approved` row as candidates and asserts only the
    `pending` one survives -- a filter bound to the wrong column, or no
    filter at all, would leak the approved row into this response."""
    pending = _asesor_pending()
    approved = _admin()
    session = _FilteringFakeSession(execute_queue=[[], [pending, approved]])
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    override_motored_db(session)
    client = TestClient(app)

    response = client.get(f"{USUARIOS_URL}?status=pending")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "pending"


def test_list_usuarios_status_pending_excludes_deactivated_rows():
    """WARNING (post-Phase-4 review, finding #5): a `pending` advisor who
    gets deactivated (`DELETE /usuarios/{id}` -> `activo=False`) must not
    keep showing up in the pending-requests list with live Aprobar/
    Rechazar buttons -- clicking either would 409, since `resolver_
    solicitud`'s own claim requires `activo`. Queues BOTH an active-pending
    and a deactivated-pending candidate; only the active one must survive."""
    pending_activo = _asesor_pending()
    pending_inactivo = _asesor_pending(activo=False)
    session = _FilteringFakeSession(execute_queue=[[], [pending_activo, pending_inactivo]])
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    override_motored_db(session)
    client = TestClient(app)

    response = client.get(f"{USUARIOS_URL}?status=pending")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(pending_activo.id)


def test_list_usuarios_no_status_filter_returns_every_row():
    pending = _asesor_pending()
    approved = _admin()
    session = _FilteringFakeSession(execute_queue=[[], [pending, approved]])
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    override_motored_db(session)
    client = TestClient(app)

    response = client.get(USUARIOS_URL)

    assert response.status_code == 200, response.text
    assert len(response.json()) == 2


# ---------------------------------------------------------------------------
# POST /usuarios/{id}/aprobar | /rechazar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ALL_ROLES)
def test_aprobar_restricted_to_admin_only(role):
    asesor = _asesor_pending()
    actor_id = str(uuid.uuid4())
    execute_queue = [[asesor.id], [asesor]] if role == "ADMIN" else [[]]
    client = _client_as(role, execute_queue=execute_queue, user_id=actor_id)

    response = client.post(f"{USUARIOS_URL}/{asesor.id}/aprobar")

    if role == "ADMIN":
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "approved"
    else:
        assert response.status_code == 403


def test_rechazar_updates_status_to_rejected():
    asesor = _asesor_pending()
    actor_id = str(uuid.uuid4())
    client = _client_as("ADMIN", execute_queue=[[asesor.id], [asesor]], user_id=actor_id)

    response = client.post(f"{USUARIOS_URL}/{asesor.id}/rechazar")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"


def test_aprobar_race_second_call_gets_409(monkeypatch):
    """Mirrors `test_cargas_api.py`'s `CargaYaAnuladaError` -> 409
    translation for the analogous `SolicitudYaResuelta` domain error."""
    from app.motored.api import usuarios as usuarios_api

    asesor_id = uuid.uuid4()

    async def _fake_resolver(db, usuario_id, decision, actor_id):
        raise SolicitudYaResuelta("ya resuelta")

    monkeypatch.setattr(usuarios_api.solicitudes, "resolver_solicitud", _fake_resolver)
    client = _client_as("ADMIN", execute_queue=[])

    response = client.post(f"{USUARIOS_URL}/{asesor_id}/aprobar")

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# POST /usuarios/me/telegram/codigo | DELETE /usuarios/me/telegram
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ALL_ROLES)
def test_generar_codigo_telegram_restricted_to_admin_only(role):
    admin = _admin()
    admin_id = str(admin.id)
    execute_queue = [[admin]] if role == "ADMIN" else [[]]
    client = _client_as(role, execute_queue=execute_queue, user_id=admin_id)

    response = client.post(f"{USUARIOS_URL}/me/telegram/codigo")

    if role == "ADMIN":
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["codigo"]) == 8
        assert "expira_en" in body
    else:
        assert response.status_code == 403


def test_generar_codigo_telegram_only_affects_the_acting_admins_own_row():
    """No endpoint lets an ADMIN generate a code for a DIFFERENT user's
    row -- the acted-upon `Usuario` always comes from the authenticated
    actor's own id, never a path/body parameter (design D5: an ADMIN links
    only THEIR OWN telegram_id)."""
    admin = _admin()
    admin_id = str(admin.id)
    client = _client_as("ADMIN", execute_queue=[[admin]], user_id=admin_id)

    response = client.post(f"{USUARIOS_URL}/me/telegram/codigo")

    assert response.status_code == 200, response.text
    assert admin.codigo_vinculacion_hash is not None


def test_desvincular_telegram_clears_own_telegram_id():
    admin = _admin(telegram_id=123456)
    admin_id = str(admin.id)
    client = _client_as("ADMIN", execute_queue=[[admin]], user_id=admin_id)

    response = client.delete(f"{USUARIOS_URL}/me/telegram")

    assert response.status_code == 200, response.text
    assert admin.telegram_id is None
    assert response.json()["telegram_vinculado"] is False


@pytest.mark.parametrize("role", ALL_ROLES)
def test_desvincular_telegram_restricted_to_admin_only(role):
    admin = _admin(telegram_id=123456)
    admin_id = str(admin.id)
    execute_queue = [[admin]] if role == "ADMIN" else [[]]
    client = _client_as(role, execute_queue=execute_queue, user_id=admin_id)

    response = client.delete(f"{USUARIOS_URL}/me/telegram")

    if role == "ADMIN":
        assert response.status_code == 200
    else:
        assert response.status_code == 403
