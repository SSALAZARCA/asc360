"""
Phase 4 "API + Integration" — full-flow integration test (sdd/motored-
pedidos-cimientos). Orchestrator-mandated: at least one realistic
end-to-end test using the REAL `TestClient(app)` (matching Phase 2's
`test_auth_isolation.py` convention) that logs in via the real `/login`
endpoint, uses the real returned token to call a real protected Motored
endpoint, and gets a real 200 -- proving the whole chain (router mount ->
auth -> RBAC -> service -> DB) works together, not just each piece in
isolation.

Deliberately does NOT override `get_current_motored_user` -- only the
innermost DB seam (`get_motored_db`) is faked, via ONE shared
`FakeAsyncSession` reused across both HTTP requests, so the second request's
`Authorization: Bearer <token>` is decoded and resolved by the REAL
`decode_motored_token` + `obtener_usuario_motored` DB-backed lookup
(Phase 3), not a test double.
"""
import uuid

from fastapi.testclient import TestClient

from app.config import settings
from app.core.security import get_password_hash
from app.main import app
from app.motored.models.usuario import MotoredRole, Usuario
from tests.motored.conftest import FakeAsyncSession, override_motored_db


def test_login_then_call_a_real_protected_endpoint_end_to_end(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "full-flow-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "full-flow-asc360-secret")

    usuario = Usuario(
        id=uuid.uuid4(),
        nombre="Ana Salazar",
        email="ana@motoredcolombia.com.co",
        hashed_password=get_password_hash("correcta123"),
        role=MotoredRole.ADMIN,
        activo=True,
    )
    usuario.sucursales = []

    # One shared session across BOTH real HTTP requests below: request 1
    # (login) needs [probe, usuario-by-email]; request 2 (salud) needs
    # [probe, usuario-by-id (real auth lookup), then evaluar_salud's 4
    # queries] -- in that exact order, since it's a real end-to-end call
    # through the genuine dependency graph, not a stubbed shortcut.
    session = FakeAsyncSession(
        execute_queue=[
            [],  # login: get_motored_db_or_503 readiness probe
            [usuario],  # login: select(Usuario).where(email == ...)
            [],  # salud: get_motored_db_or_503 readiness probe (shared per-request)
            [usuario],  # salud: obtener_usuario_motored's select by id
            [],  # salud: sucursal sin sic
            [],  # salud: referencia sin precio
            [],  # salud: unidad_empaque_corregida
            [],  # salud: bodega sin sucursal
        ]
    )
    override_motored_db(session)

    with TestClient(app) as client:
        login_response = client.post(
            "/api/motored/auth/login",
            json={"email": usuario.email, "password": "correcta123"},
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        protected_response = client.get(
            "/api/motored/maestros/salud",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert protected_response.status_code == 200
    body = protected_response.json()
    assert body["estado"] == "verde"
    assert body["hallazgos"] == []

    app.dependency_overrides.clear()
