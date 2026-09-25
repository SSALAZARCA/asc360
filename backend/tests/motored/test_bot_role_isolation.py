"""
Phase 5 "Bot auth + core router" (sdd/motored-ventas-perdidas-bot, tasks
5.11/5.12; design D5, spec delta for motored-auth "RBAC role enforcement")
— explicit, cross-cutting proof that `ASESOR_MOSTRADOR` cannot reach ANY
pre-existing Motored web/API surface (masters, ingesta/cargas, usuarios,
parametros), across a representative sample of routers.

This exercises the REAL `get_current_motored_user` dependency end-to-end
(a genuine Motored JWT decoded through the real production routes), NOT a
dependency override of `get_current_motored_user` itself -- Phase 3.11
already established that `get_current_motored_user` rejects
`role=='ASESOR_MOSTRADOR'` with a generic 401 BEFORE any `require_roles`
allow-list ever runs (`test_auth_isolation.py` proves this against one
throwaway route). Overriding `get_current_motored_user` wholesale (the
`test_rbac_matrix.py` convention used for the 4 web roles) would bypass
that exact rejection and give a false pass on endpoints like `GET /cargas`,
which has NO `require_roles` gate at all (any authenticated role may read
it) -- its only protection against `ASESOR_MOSTRADOR` is the deeper
`get_current_motored_user` check itself, so this file only overrides the
swappable DB-lookup seam (`get_motored_user_lookup`), keeping the real
authentication logic intact, and asserts 401 (the real rejection code)
across a representative sample: masters (read/write), cargas listing,
usuarios listing, and parametros write.
"""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.deps import MotoredUser, get_motored_user_lookup
from tests.motored.conftest import FakeAsyncSession, override_motored_db

MOTORED_SECRET = "role-isolation-motored-secret"
ASC360_SECRET = "role-isolation-asc360-secret"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", MOTORED_SECRET)
    monkeypatch.setattr(settings, "SECRET_KEY", ASC360_SECRET)
    yield
    app.dependency_overrides.clear()


async def _fake_asesor_lookup(user_id: str):
    return MotoredUser(user_id=user_id, role="ASESOR_MOSTRADOR")


def _client_as_asesor_via_real_jwt() -> tuple:
    """Real JWT, real `get_current_motored_user` -- only the DB-lookup seam
    (Phase 3's own swappable point) is faked, exactly like
    `test_auth_isolation.py`'s established convention."""
    app.dependency_overrides[get_motored_user_lookup] = lambda: _fake_asesor_lookup
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 8))
    token = create_motored_token(sub="asesor-role-isolation-1", role="ASESOR_MOSTRADOR")
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def test_asesor_mostrador_cannot_read_maestros():
    client, headers = _client_as_asesor_via_real_jwt()
    response = client.get("/api/motored/maestros/sucursales", headers=headers)
    assert response.status_code == 401


def test_asesor_mostrador_cannot_write_maestros():
    client, headers = _client_as_asesor_via_real_jwt()
    response = client.post(
        "/api/motored/maestros/sucursales", json={"nombre": "CALI NORTE"}, headers=headers
    )
    assert response.status_code == 401


def test_asesor_mostrador_cannot_upload_carga():
    client, headers = _client_as_asesor_via_real_jwt()
    response = client.post(
        "/api/motored/maestros/sucursal/carga/validar",
        json={"filas": [{"nombre": "CALI NORTE"}]},
        headers=headers,
    )
    assert response.status_code == 401


def test_asesor_mostrador_cannot_list_cargas():
    """`GET /cargas` has NO `require_roles(...)` gate at all -- any
    authenticated role may read it -- so this specifically proves the
    isolation comes from `get_current_motored_user` itself, not from an
    allow-list that happens to exclude `ASESOR_MOSTRADOR`."""
    client, headers = _client_as_asesor_via_real_jwt()
    response = client.get("/api/motored/cargas", headers=headers)
    assert response.status_code == 401


def test_asesor_mostrador_cannot_list_usuarios():
    client, headers = _client_as_asesor_via_real_jwt()
    response = client.get("/api/motored/usuarios", headers=headers)
    assert response.status_code == 401


def test_asesor_mostrador_cannot_write_parametros():
    client, headers = _client_as_asesor_via_real_jwt()
    response = client.post(
        "/api/motored/parametros",
        json={"clave": "cobertura_default", "valor": 30, "vigente_desde": "2026-01-01"},
        headers=headers,
    )
    assert response.status_code == 401


def test_asesor_mostrador_can_reach_its_own_bot_facing_endpoint(monkeypatch):
    """Control case (spec "ASESOR_MOSTRADOR can only reach bot-facing
    endpoints"): the SAME role, authenticated the bot's own way (secret +
    telegram_id header, not a JWT), DOES reach a bot-facing endpoint --
    proving the 401s above are about cross-surface isolation, not a
    globally broken role.

    Uses `monkeypatch.setattr` (never a bare `setattr`) for every mutated
    setting -- a bare `setattr` here previously leaked `SONIA_BOT_SECRET`/
    `LORE_BOT_SECRET` PERMANENTLY into the rest of the pytest session
    (settings is a module-level singleton), which silently broke unrelated
    `tests/vehicles/` bot-auth assertions that run later in the SAME
    session when the full suite executes as one process -- caught by the
    Phase 5 apply pass's own full-suite safety-net run, not by this file's
    own tests in isolation."""
    import uuid

    from app.motored.models.usuario import Usuario

    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", MOTORED_SECRET)
    monkeypatch.setattr(settings, "SECRET_KEY", ASC360_SECRET)
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "role-isolation-sonia-secret")
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", "role-isolation-lore-secret")

    usuario = Usuario(
        id=uuid.uuid4(),
        nombre="Juan Asesor", email=None, hashed_password=None,
        role="ASESOR_MOSTRADOR", activo=True, status="approved", telegram_id=321,
    )
    usuario.sucursales = []
    override_motored_db(FakeAsyncSession(execute_queue=[[], [usuario]]))
    client = TestClient(app)

    response = client.get(
        "/api/motored/bot/yo",
        headers={"X-Lore-Secret": "role-isolation-lore-secret", "X-Lore-Telegram-Id": "321"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["role"] == "ASESOR_MOSTRADOR"


# ---------------------------------------------------------------------------
# Post-review fix #5 — the REVERSE direction. All tests above prove a real
# Motored JWT for `ASESOR_MOSTRADOR` cannot reach pre-existing JWT-gated
# routes. Missing until now: proof that bot-only headers (`X-Lore-Secret`/
# `X-Lore-Telegram-Id`, no `Authorization: Bearer` at all) are REJECTED by
# those same JWT-gated routes -- i.e. the bot's own auth mechanism cannot
# accidentally satisfy `get_current_motored_user`.
# ---------------------------------------------------------------------------

def test_bot_headers_alone_cannot_reach_jwt_gated_usuarios_listing(monkeypatch):
    """`GET /api/motored/usuarios` is gated by `get_current_motored_user`
    (real JWT decoding, `deps.py`) -- a request carrying only the bot's own
    `X-Lore-Secret`/`X-Lore-Telegram-Id` pair, with NO `Authorization`
    header at all, must still 401. `deps_bot.py` and `deps.py` are
    deliberately isolated auth mechanisms (module docstring); this proves
    the isolation holds in THIS direction too, not just JWT-vs-bot-routes."""
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "role-isolation-sonia-secret")
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", "role-isolation-lore-secret")
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))
    client = TestClient(app)

    response = client.get(
        "/api/motored/usuarios",
        headers={"X-Lore-Secret": "role-isolation-lore-secret", "X-Lore-Telegram-Id": "321"},
    )

    assert response.status_code == 401


def test_bot_headers_alone_cannot_reach_jwt_gated_maestros_sucursales(monkeypatch):
    """Same proof as above, against a DIFFERENT JWT-gated router
    (`maestros.py`) -- cross-router, not a single-endpoint fluke."""
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "role-isolation-sonia-secret")
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", "role-isolation-lore-secret")
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))
    client = TestClient(app)

    response = client.get(
        "/api/motored/maestros/sucursales",
        headers={"X-Lore-Secret": "role-isolation-lore-secret", "X-Lore-Telegram-Id": "321"},
    )

    assert response.status_code == 401
