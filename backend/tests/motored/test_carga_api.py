"""
Phase 4 "API + Integration" — bulk-upload HTTP surface (sdd/motored-pedidos-
cimientos, task 4.3, ADR-6, owner decision #1).

`services/carga.py::procesar_carga` and `services/validators.py::
validate_rows` are already fully tested in isolation (Phase 3). This file
proves the ROUTER-level behavior specific to Phase 4: the `validar`
dry-run never writes, the `carga` commit path is genuinely all-or-nothing
end-to-end through real HTTP, size/row guards reject before validation
even runs, and -- the one piece of logic this router itself owns per
`services/carga.py`'s documented scope note -- `referencia` rows get their
`proveedor_codigo` resolved to `proveedor_id` before reaching the service.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.proveedor import Proveedor
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

VALIDAR_URL = "/api/motored/maestros/sucursal/carga/validar"
CARGA_URL = "/api/motored/maestros/sucursal/carga"
CARGA_REFERENCIA_URL = "/api/motored/maestros/referencia/carga"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "carga-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "carga-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    yield
    app.dependency_overrides.clear()


def test_validar_with_one_invalid_row_reports_error_and_writes_nothing():
    session = FakeAsyncSession(execute_queue=[[]])  # only the readiness probe
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            VALIDAR_URL,
            json={"filas": [{"nombre": "CALI NORTE"}, {"nombre": ""}]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert len(body["errores"]) == 1
    assert session.added == []
    assert session.committed is False


def test_validar_with_fully_valid_file_writes_nothing_either():
    """`validar` is a DRY RUN -- even a fully valid file must not write,
    that is exactly what distinguishes it from `carga`."""
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(VALIDAR_URL, json={"filas": [{"nombre": "CALI NORTE"}]})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert session.added == []
    assert session.committed is False


def test_carga_with_one_invalid_row_rejects_whole_file_and_writes_nothing():
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            CARGA_URL,
            json={"filas": [{"nombre": "CALI NORTE"}, {"nombre": ""}]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert len(body["errores"]) == 1
    assert session.added == []
    assert session.committed is False


def test_carga_with_fully_valid_file_commits_atomically():
    # probe + get_sucursal_by_nombre (no match) -> create path, one commit
    session = FakeAsyncSession(execute_queue=[[], []])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(CARGA_URL, json={"filas": [{"nombre": "CALI NORTE  "}]})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["insertados"] == 1
    assert session.committed is True


def test_carga_rejects_oversized_row_count_before_validating(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_MAX_UPLOAD_ROWS", 1)
    # Only the readiness probe (`get_motored_db_or_503`, resolved by FastAPI
    # as a request dependency regardless of what the handler body does)
    # touches the session -- the row-count guard must reject before any
    # business query (validation or upsert) is ever issued.
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            CARGA_URL,
            json={"filas": [{"nombre": "A"}, {"nombre": "B"}]},
        )

    assert response.status_code == 422
    assert session.added == []
    assert session.committed is False


def test_carga_rejects_malformed_content_length_header_cleanly():
    """A hand-crafted, non-numeric `Content-Length` must not crash the guard
    with an unhandled `ValueError` -- it's the first thing this endpoint
    checks, before any real validation or DB access."""
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            CARGA_URL,
            json={"filas": [{"nombre": "CALI NORTE"}]},
            headers={"Content-Length": "not-a-number"},
        )

    assert response.status_code == 400
    assert session.added == []
    assert session.committed is False


def test_referencia_carga_resolves_proveedor_codigo_to_proveedor_id():
    """The router's own documented responsibility (per `services/carga.py`'s
    scope note): resolve `proveedor_codigo` -> `proveedor_id` in ONE query
    before handing rows to `procesar_carga`, which requires `proveedor_id`
    already present."""
    proveedor_id = uuid.uuid4()
    proveedor = Proveedor(id=proveedor_id, codigo="HMCL", nombre="HMCL", es_principal=True)
    # probe, proveedor-codigo-resolution query, get_referencia_by_codigo_proveedor (no match)
    session = FakeAsyncSession(execute_queue=[[], [proveedor], []])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            CARGA_REFERENCIA_URL,
            json={"filas": [{"codigo": "REF1", "proveedor_codigo": "HMCL"}]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True, body
    assert body["insertados"] == 1
