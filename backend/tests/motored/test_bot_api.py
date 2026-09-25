"""
Phase 5 "Bot auth + core router" (sdd/motored-ventas-perdidas-bot, tasks
5.6-5.10; design D5) — HTTP-layer coverage for `/api/motored/bot/*`:

- `GET /yo`, `GET /sucursales`
- `POST /registro`
- `POST /admin/vincular`
- `POST /admin/solicitudes/{id}/aprobar` | `/rechazar`

Same `FakeAsyncSession`/`override_motored_db`/`motored_client` convention as
`test_usuarios_api.py`/`test_cargas_api.py` -- but this router does NOT use
`get_current_motored_user` (no JWT for the bot): auth is the
`X-Lore-Secret`/`X-Lore-Telegram-Id` header pair, so tests set those headers
directly instead of `override_motored_user`.

Critical security property under test (flagged explicitly by the
orchestrator): the acting ADMIN's identity for `/admin/vincular` and
`/admin/solicitudes/{id}/aprobar|rechazar` MUST come from the
`telegram_id`-looked-up `BotActor`, NEVER from a client-supplied id in the
request body -- neither endpoint even accepts such a field, and
`test_aprobar_solicitud_bot_actor_id_derived_from_telegram_lookup_not_request`
proves the exact value passed to `resolver_solicitud`.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.main import app
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services.solicitudes import SolicitudYaResuelta
from tests.motored.conftest import FakeAsyncSession, _ExecuteResult, override_motored_db

BOT_URL = "/api/motored/bot"
LORE_SECRET = "bot-test-lore-secret"


@pytest.fixture(autouse=True)
def _lore_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "bot-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "bot-test-asc360-secret")
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "bot-test-sonia-secret")
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", LORE_SECRET)
    yield
    app.dependency_overrides.clear()


def _headers(telegram_id, secret=LORE_SECRET) -> dict:
    return {"X-Lore-Secret": secret, "X-Lore-Telegram-Id": str(telegram_id)}


def _client_with_queue(execute_queue) -> TestClient:
    """`[[]]` is prepended for `get_motored_db_or_503`'s own `SELECT 1`
    connectivity probe -- same convention as `test_usuarios_api.py`'s
    `_client_as`."""
    session = FakeAsyncSession(execute_queue=[[]] + list(execute_queue))
    override_motored_db(session)
    return TestClient(app)


def _asesor(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Juan Asesor", email=None, hashed_password=None,
        role="ASESOR_MOSTRADOR", activo=True, status="pending", telegram_id=555,
        phone="3001234567",
    )
    base.update(overrides)
    usuario = Usuario(**base)
    if not hasattr(usuario, "sucursales") or usuario.sucursales is None:
        usuario.sucursales = []
    return usuario


def _admin(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Ana Admin", email="ana@motoredcolombia.com.co",
        hashed_password="hash", role="ADMIN", activo=True, status="approved",
        telegram_id=444,
    )
    base.update(overrides)
    usuario = Usuario(**base)
    usuario.sucursales = []
    return usuario


def _extraer_predicados(stmt) -> list:
    """Local copy of the established `_extraer_predicados` convention
    (`test_usuarios_api.py`) -- walks the compiled top-level AND WHERE
    clauses to prove REAL filtering, not just bind-param presence.

    Post-review fix #4 addition: `col.is_not(None)`/`col.is_(None)` compile
    to a `BinaryExpression` whose `right` is a `NULL` literal -- neither a
    bind param (no `.value`) nor `true`/`false` -- so the two existing
    branches silently skipped it, meaning a query's `IS NOT NULL` filter
    was never actually exercised by `_FilteringFakeSession`. Needed to make
    `test_registro_creates_pending_asesor_and_returns_admin_telegram_ids`
    prove the `Usuario.telegram_id.is_not(None)` filter for real instead of
    just returning whatever rows were queued verbatim."""
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
        if type(right).__name__ == "Null":
            es_is_not = getattr(operador, "__name__", "") == "is_not"
            if es_is_not:
                predicados.append((nombre_columna, lambda a, b: a is not None, None))
            else:
                predicados.append((nombre_columna, lambda a, b: a is None, None))
        elif hasattr(right, "value"):
            predicados.append((nombre_columna, operador, right.value))
        elif str(right) in ("true", "false"):
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


class _FakeAdminTelegramRow(int):
    """Post-review fix #4: a minimal fake `Row` for `registrarse`'s
    `select(Usuario.telegram_id).where(role==ADMIN, telegram_id.is_not(None),
    activo.is_(True))` query. It is an `int` subclass -- so a row that
    SURVIVES filtering still round-trips as a real JSON int through
    `admin_telegram_ids` in the response, exactly like a real
    `scalars().all()` projection would -- while also exposing `.role`/
    `.activo`/`.telegram_id` so `_extraer_predicados`/`_FilteringFakeSession`
    can apply the SAME WHERE-clause filtering the real query does. `.role`
    is set to the real `MotoredRole` enum member (not the plain string the
    rest of this file's `_admin`/`_asesor` fixtures use for other tests) --
    a real Postgres `Enum` column round-trips as the enum member, and the
    query's bind param is `MotoredRole.ADMIN` itself, which does not `==` a
    plain string (`MotoredRole` is a bare `enum.Enum`, not a `str` mixin)."""

    def __new__(cls, *, telegram_id, role, activo):
        obj = super().__new__(cls, telegram_id or 0)
        obj.telegram_id = telegram_id
        obj.role = role
        obj.activo = activo
        return obj


# ---------------------------------------------------------------------------
# GET /yo (task 5.6)
# ---------------------------------------------------------------------------

def test_yo_returns_404_when_telegram_id_not_registered():
    client = _client_with_queue([[]])
    response = client.get(f"{BOT_URL}/yo", headers=_headers(111))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NO_REGISTRADO"


def test_yo_returns_actor_info_when_registered():
    sucursal_id = uuid.uuid4()
    usuario = _asesor(telegram_id=222)
    from app.motored.models.usuario_sucursal import UsuarioSucursal

    usuario.sucursales = [UsuarioSucursal(id=uuid.uuid4(), usuario_id=usuario.id, sucursal_id=sucursal_id)]
    client = _client_with_queue([[usuario]])

    response = client.get(f"{BOT_URL}/yo", headers=_headers(222))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(usuario.id)
    assert body["nombre"] == "Juan Asesor"
    assert body["role"] == "ASESOR_MOSTRADOR"
    assert body["status"] == "pending"
    assert body["sucursales"] == [str(sucursal_id)]


def test_yo_wrong_secret_returns_401():
    client = _client_with_queue([])
    response = client.get(f"{BOT_URL}/yo", headers=_headers(222, secret="wrong-secret"))
    assert response.status_code == 401


def test_yo_malformed_telegram_id_returns_400():
    client = _client_with_queue([])
    response = client.get(
        f"{BOT_URL}/yo", headers={"X-Lore-Secret": LORE_SECRET, "X-Lore-Telegram-Id": "not-a-number"}
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /sucursales (task 5.6)
# ---------------------------------------------------------------------------

def test_sucursales_returns_only_active_branches():
    activa = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE", activa=True)
    inactiva = Sucursal(id=uuid.uuid4(), nombre="SUCURSAL VIEJA", activa=False)
    session = _FilteringFakeSession(execute_queue=[[], [activa, inactiva]])
    override_motored_db(session)
    client = TestClient(app)

    response = client.get(f"{BOT_URL}/sucursales", headers=_headers(333))

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["nombre"] == "CALI NORTE"


def test_sucursales_wrong_secret_returns_401():
    client = _client_with_queue([])
    response = client.get(f"{BOT_URL}/sucursales", headers=_headers(333, secret="wrong"))
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /registro (task 5.7/5.8)
# ---------------------------------------------------------------------------

def test_registro_creates_pending_asesor_and_returns_admin_telegram_ids():
    """Post-review fix #4: was hollow -- it queued `[111, 222]` on the plain
    `FakeAsyncSession` and asserted them back verbatim, so it would have
    passed identically even if `admin_telegram_ids`'s query filtered on
    nothing at all, or the wrong column. Rewritten on `_FilteringFakeSession`
    with a mixed dataset covering all 3 filter predicates
    (`role==ADMIN`, `telegram_id.is_not(None)`, `activo.is_(True)`): only
    the true positive must survive."""
    sucursal_id = uuid.uuid4()
    admin_activo_vinculado = _FakeAdminTelegramRow(telegram_id=111, role=MotoredRole.ADMIN, activo=True)
    asesor_vinculado = _FakeAdminTelegramRow(
        telegram_id=222, role=MotoredRole.ASESOR_MOSTRADOR, activo=True
    )
    admin_inactivo_vinculado = _FakeAdminTelegramRow(
        telegram_id=333, role=MotoredRole.ADMIN, activo=False
    )
    admin_sin_telegram = _FakeAdminTelegramRow(telegram_id=None, role=MotoredRole.ADMIN, activo=True)
    session = _FilteringFakeSession(
        execute_queue=[
            [],  # readiness probe
            [],  # duplicate-telegram_id pre-check: no existing Usuario
            [admin_activo_vinculado, asesor_vinculado, admin_inactivo_vinculado, admin_sin_telegram],
        ]
    )
    override_motored_db(session)
    client = TestClient(app)
    payload = {"nombre": "Juan Perez", "phone": "3001234567", "sucursal_id": str(sucursal_id)}

    response = client.post(f"{BOT_URL}/registro", json=payload, headers=_headers(999))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["usuario"]["status"] == "pending"
    assert body["usuario"]["role"] == "ASESOR_MOSTRADOR"
    assert body["admin_telegram_ids"] == [111]

    from app.motored.models.usuario import Usuario as UsuarioModel
    from app.motored.models.usuario_sucursal import UsuarioSucursal as UsuarioSucursalModel

    creados = session.added_of_type(UsuarioModel)
    assert len(creados) == 1
    assert creados[0].telegram_id == 999
    assert creados[0].phone == "3001234567"
    vinculos = session.added_of_type(UsuarioSucursalModel)
    assert len(vinculos) == 1
    assert vinculos[0].sucursal_id == sucursal_id


def test_registro_duplicate_telegram_id_returns_409():
    existente = _asesor(telegram_id=999)
    client = _client_with_queue([[existente]])
    payload = {"nombre": "Juan Perez", "phone": "3001234567", "sucursal_id": str(uuid.uuid4())}

    response = client.post(f"{BOT_URL}/registro", json=payload, headers=_headers(999))

    assert response.status_code == 409


def test_registro_concurrent_duplicate_telegram_id_commit_race_returns_409_not_500():
    """Post-review fix #1 (BLOCKER, 2 lenses): two near-simultaneous
    `/registro` calls with the SAME `telegram_id` both pass the
    existence-check `SELECT` before either commits -- the second
    `db.commit()` then violates `uq_usuario_telegram_id` for real. This
    must become the SAME clean 409 the sequential check already returns,
    never an unhandled `IntegrityError` -> raw 500."""
    session = FakeAsyncSession(
        execute_queue=[[], []],  # readiness probe, then the pre-check finds nothing
        raise_integrity_error=IntegrityError(
            "INSERT usuario", {}, Exception('duplicate key value violates unique constraint "uq_usuario_telegram_id"')
        ),
    )
    override_motored_db(session)
    client = TestClient(app)
    payload = {"nombre": "Juan Perez", "phone": "3001234567", "sucursal_id": str(uuid.uuid4())}

    response = client.post(f"{BOT_URL}/registro", json=payload, headers=_headers(999))

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "YA_REGISTRADO"
    assert session.rolled_back is True


def test_registro_nonexistent_sucursal_id_returns_404_not_500():
    """Post-review fix #1 (BLOCKER, 2 lenses): a `sucursal_id` that does not
    exist (or was deactivated between `GET /sucursales` and this call)
    violates the `UsuarioSucursal` FK -- also an unhandled `IntegrityError`
    -> 500 before this fix. Must become a clean 4xx."""
    session = FakeAsyncSession(
        execute_queue=[[], []],
        raise_integrity_error=IntegrityError(
            "INSERT usuario_sucursal",
            {},
            Exception(
                'insert or update on table "usuario_sucursal" violates foreign key '
                'constraint "usuario_sucursal_sucursal_id_fkey"'
            ),
        ),
    )
    override_motored_db(session)
    client = TestClient(app)
    payload = {"nombre": "Juan Perez", "phone": "3001234567", "sucursal_id": str(uuid.uuid4())}

    response = client.post(f"{BOT_URL}/registro", json=payload, headers=_headers(999))

    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "SUCURSAL_NO_ENCONTRADA"
    assert session.rolled_back is True


@pytest.mark.parametrize("nombre", ["", "Al"])
def test_registro_nombre_too_short_returns_422(nombre):
    client = _client_with_queue([])
    payload = {"nombre": nombre, "phone": "3001234567", "sucursal_id": str(uuid.uuid4())}

    response = client.post(f"{BOT_URL}/registro", json=payload, headers=_headers(1))

    assert response.status_code == 422


@pytest.mark.parametrize("phone", ["abc", "123456", "1234567890123456"])
def test_registro_invalid_phone_returns_422(phone):
    client = _client_with_queue([])
    payload = {"nombre": "Ana Perez", "phone": phone, "sucursal_id": str(uuid.uuid4())}

    response = client.post(f"{BOT_URL}/registro", json=payload, headers=_headers(1))

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /admin/vincular (task 5.9)
# ---------------------------------------------------------------------------

def test_vincular_admin_success_links_telegram_id_and_clears_code():
    admin = _admin(telegram_id=None)
    codigo = "AB23CD45"
    admin.codigo_vinculacion_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
    admin.codigo_vinculacion_expira = datetime.now(timezone.utc) + timedelta(minutes=5)
    # [existing-telegram-id check -> none, claim UPDATE -> id, reselect]
    client = _client_with_queue([[], [admin.id], [admin]])

    response = client.post(f"{BOT_URL}/admin/vincular", json={"codigo": codigo}, headers=_headers(777))

    assert response.status_code == 200, response.text
    assert admin.telegram_id == 777
    assert admin.codigo_vinculacion_hash is None


def test_vincular_admin_telegram_id_already_used_returns_409():
    ya_vinculado = _admin(telegram_id=777)
    client = _client_with_queue([[ya_vinculado]])

    response = client.post(f"{BOT_URL}/admin/vincular", json={"codigo": "SOMECODE"}, headers=_headers(777))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TELEGRAM_YA_VINCULADO"


def test_vincular_admin_concurrent_codes_same_telegram_id_race_returns_409_not_500():
    """Post-review fix #2 (BLOCKER, 2 lenses): the router's pre-check only
    catches a `telegram_id` that's ALREADY linked -- it does nothing for two
    CONCURRENT `/vincular` calls presenting two DIFFERENT, both-still-valid
    codes for the SAME not-yet-linked `telegram_id`. Each call's own atomic
    claim (scoped by `codigo_vinculacion_hash`, not by `telegram_id`) can
    independently succeed its own `UPDATE ... RETURNING`, and the SECOND
    one then violates `uq_usuario_telegram_id` for real. Must become the
    SAME clean 409 `TELEGRAM_YA_VINCULADO` the pre-check already returns,
    never an unhandled `IntegrityError` -> raw 500."""
    session = FakeAsyncSession(
        execute_queue=[
            [],  # readiness probe
            [],  # pre-check: telegram_id not linked yet (both racers see this)
            IntegrityError(
                "UPDATE usuario",
                {},
                Exception('duplicate key value violates unique constraint "uq_usuario_telegram_id"'),
            ),
        ]
    )
    override_motored_db(session)
    client = TestClient(app)

    response = client.post(f"{BOT_URL}/admin/vincular", json={"codigo": "AB23CD45"}, headers=_headers(777))

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "TELEGRAM_YA_VINCULADO"
    assert session.rolled_back is True


def test_vincular_admin_invalid_or_expired_code_returns_409():
    # [existing-telegram-id check -> none, claim UPDATE -> 0 rows]
    client = _client_with_queue([[], []])

    response = client.post(f"{BOT_URL}/admin/vincular", json={"codigo": "BADCODE1"}, headers=_headers(888))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CODIGO_INVALIDO"


def test_vincular_admin_wrong_secret_returns_401():
    client = _client_with_queue([])
    response = client.post(
        f"{BOT_URL}/admin/vincular", json={"codigo": "AB23CD45"}, headers=_headers(777, secret="wrong")
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /admin/solicitudes/{id}/aprobar | /rechazar (task 5.10)
# ---------------------------------------------------------------------------

def test_aprobar_solicitud_bot_success():
    admin = _admin(telegram_id=444)
    asesor = _asesor(telegram_id=555, status="pending")
    # [actor lookup -> admin, claim UPDATE -> id, reselect -> asesor]
    client = _client_with_queue([[admin], [asesor.id], [asesor]])

    response = client.post(f"{BOT_URL}/admin/solicitudes/{asesor.id}/aprobar", headers=_headers(444))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved"
    assert body["telegram_id_solicitante"] == 555


def test_rechazar_solicitud_bot_success():
    admin = _admin(telegram_id=444)
    asesor = _asesor(telegram_id=555, status="pending")
    client = _client_with_queue([[admin], [asesor.id], [asesor]])

    response = client.post(f"{BOT_URL}/admin/solicitudes/{asesor.id}/rechazar", headers=_headers(444))

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"


def test_aprobar_solicitud_bot_non_admin_actor_gets_403_no_registrado():
    actor_asesor = _asesor(telegram_id=444, status="approved")
    target = _asesor(telegram_id=555)
    client = _client_with_queue([[actor_asesor]])

    response = client.post(f"{BOT_URL}/admin/solicitudes/{target.id}/aprobar", headers=_headers(444))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "NO_REGISTRADO"


def test_aprobar_solicitud_bot_pending_admin_actor_gets_403():
    """An admin whose OWN account is somehow not yet approved must not be
    able to resolve anyone else's request (defense-in-depth, mirrors
    `require_bot_asesor`'s cascade)."""
    admin_pendiente = _admin(telegram_id=444, status="pending")
    target = _asesor(telegram_id=555)
    client = _client_with_queue([[admin_pendiente]])

    response = client.post(f"{BOT_URL}/admin/solicitudes/{target.id}/aprobar", headers=_headers(444))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PENDIENTE"


def test_aprobar_solicitud_bot_race_returns_409_ya_resuelta():
    admin = _admin(telegram_id=444)
    target_id = uuid.uuid4()
    client = _client_with_queue([[admin], []])  # claim UPDATE affects 0 rows

    response = client.post(f"{BOT_URL}/admin/solicitudes/{target_id}/aprobar", headers=_headers(444))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "YA_RESUELTA"


def test_aprobar_solicitud_bot_actor_id_derived_from_telegram_lookup_not_request(monkeypatch):
    """Security-critical (flagged by the orchestrator): `resolver_solicitud`
    trusts whatever `actor_id` it is given -- this router is the FIRST
    caller with no JWT, so `actor_id` must come from the telegram_id-looked
    -up, role/status-verified `BotActor`, never from the request body (this
    endpoint doesn't even have a body field for it)."""
    from app.motored.api import bot as bot_api

    admin = _admin(telegram_id=444)
    target_id = uuid.uuid4()
    captured = {}

    async def _fake_resolver(db, usuario_id, decision, actor_id):
        captured["actor_id"] = actor_id
        captured["usuario_id"] = usuario_id
        captured["decision"] = decision
        return _asesor(id=usuario_id, telegram_id=555, status=decision)

    monkeypatch.setattr(bot_api.solicitudes, "resolver_solicitud", _fake_resolver)
    client = _client_with_queue([[admin]])

    response = client.post(f"{BOT_URL}/admin/solicitudes/{target_id}/aprobar", headers=_headers(444))

    assert response.status_code == 200, response.text
    assert captured["actor_id"] == admin.id
    assert captured["usuario_id"] == target_id
    assert captured["decision"] == "approved"


def test_rechazar_solicitud_bot_wrong_secret_returns_401():
    client = _client_with_queue([])
    response = client.post(
        f"{BOT_URL}/admin/solicitudes/{uuid.uuid4()}/rechazar", headers=_headers(444, secret="wrong")
    )
    assert response.status_code == 401
