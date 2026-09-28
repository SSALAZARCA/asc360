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

Ad-hoc bugfix (not tracked under sdd/*): `_resolve_referencia_relaciones`
(renamed from `_resolve_proveedor_codigos`) also resolves
`sustituida_por_codigo` -> `sustituida_por`, an OPTIONAL FK -- unlike
`proveedor_codigo` (required, so an unmatched code is naturally caught later
by `validate_rows`'s "campo requerido" check), an unmatched
`sustituida_por_codigo` must produce an EXPLICIT resolution error (same
`{fila, motivo}` shape as a validation error), merged with `validate_rows`'s
own errors in the SAME response -- otherwise a business user's typo would
silently drop the field with zero feedback, violating "todo o nada" (owner
decision #1).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api.carga import _resolve_referencia_relaciones
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
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


class TestResolveReferenciaRelaciones:
    """Direct unit tests for `_resolve_referencia_relaciones` -- same level
    of isolation `test_validators.py` uses for `validate_rows`, so the
    resolver's own contract doesn't need a full HTTP round-trip to verify."""

    async def test_non_referencia_entidad_is_a_no_op_with_zero_queries(self):
        session = FakeAsyncSession(execute_queue=[])
        filas = [{"nombre": "CALI NORTE"}]

        resolved, errores = await _resolve_referencia_relaciones(session, "sucursal", filas)

        assert resolved == filas
        assert errores == []

    async def test_blank_sustituida_por_codigo_is_a_noop_no_query_no_error(self):
        session = FakeAsyncSession(execute_queue=[])
        filas = [{"codigo": "REF1"}]

        resolved, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert errores == []
        assert "sustituida_por" not in resolved[0]

    async def test_matching_sustituida_por_codigo_resolves_to_its_id(self):
        referencia_id = uuid.uuid4()
        proveedor = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", es_principal=True)
        referencia = Referencia(id=referencia_id, codigo="REF-OLD", proveedor_id=proveedor.id, unidad_empaque=1)
        session = FakeAsyncSession(execute_queue=[[proveedor], [referencia]])
        filas = [{"codigo": "REF-NEW", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "REF-OLD"}]

        resolved, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert errores == []
        assert resolved[0]["sustituida_por"] == referencia_id

    async def test_unmatched_sustituida_por_codigo_produces_a_business_readable_resolution_error(self):
        session = FakeAsyncSession(execute_queue=[[]])
        filas = [{"codigo": "REF-NEW", "sustituida_por_codigo": "GHOST"}]

        resolved, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert len(errores) == 1
        assert errores[0]["fila"] == 1
        assert "GHOST" in errores[0]["motivo"]
        assert "sustituida_por" not in resolved[0]

    async def test_resolution_error_fila_is_1_indexed_against_the_original_row_order(self):
        session = FakeAsyncSession(execute_queue=[[]])
        filas = [
            {"codigo": "REF1"},
            {"codigo": "REF2", "sustituida_por_codigo": "GHOST"},
        ]

        resolved, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert len(errores) == 1
        assert errores[0]["fila"] == 2

    async def test_both_relaciones_resolve_together_with_one_query_each(self):
        proveedor_id = uuid.uuid4()
        referencia_id = uuid.uuid4()
        proveedor = Proveedor(id=proveedor_id, codigo="HMCL", nombre="HMCL", es_principal=True)
        referencia = Referencia(id=referencia_id, codigo="REF-OLD", proveedor_id=proveedor_id, unidad_empaque=1)
        session = FakeAsyncSession(execute_queue=[[proveedor], [referencia]])
        filas = [{"codigo": "REF-NEW", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "REF-OLD"}]

        resolved, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert errores == []
        assert resolved[0]["proveedor_id"] == proveedor_id
        assert resolved[0]["sustituida_por"] == referencia_id


class TestSustituidaPorCodigoEndToEnd:
    def test_carga_referencia_blocks_whole_file_on_unmatched_sustituida_por_codigo(self):
        """A resolution error alone (row is otherwise fully valid --
        `proveedor_codigo` resolves cleanly) must block the ENTIRE upload --
        same all-or-nothing guarantee a validation error already has (owner
        decision #1)."""
        proveedor = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", es_principal=True)
        # probe, proveedor_codigo lookup (match), sustituida_por_codigo lookup (no match)
        session = FakeAsyncSession(execute_queue=[[], [proveedor], []])
        override_motored_db(session)

        with TestClient(app) as client:
            response = client.post(
                CARGA_REFERENCIA_URL,
                json={"filas": [{
                    "codigo": "REF1", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "GHOST",
                }]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert len(body["errores"]) == 1
        assert "GHOST" in body["errores"][0]["motivo"]
        assert session.added == []
        assert session.committed is False

    def test_carga_referencia_surfaces_resolution_and_validation_errors_together_in_one_pass(self):
        """Resolution errors and validation errors must show up in the SAME
        response -- never two round-trips to see all problems."""
        session = FakeAsyncSession(execute_queue=[[], []])  # probe, sustituida_por_codigo lookup (no match)
        override_motored_db(session)

        with TestClient(app) as client:
            response = client.post(
                CARGA_REFERENCIA_URL,
                json={
                    "filas": [
                        {"codigo": "REF1", "sustituida_por_codigo": "GHOST"},
                        {"codigo": ""},
                    ],
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        filas_con_error = {e["fila"] for e in body["errores"]}
        assert filas_con_error == {1, 2}
        assert session.committed is False

    def test_validar_carga_referencia_also_surfaces_resolution_errors(self):
        """The `/validar` dry-run must see the same resolution errors as
        `carga` -- both endpoints share the same resolver + merge logic."""
        proveedor = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", es_principal=True)
        # probe, proveedor_codigo lookup (match), sustituida_por_codigo lookup (no match)
        session = FakeAsyncSession(execute_queue=[[], [proveedor], []])
        override_motored_db(session)

        with TestClient(app) as client:
            response = client.post(
                "/api/motored/maestros/referencia/carga/validar",
                json={"filas": [{
                    "codigo": "REF1", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "GHOST",
                }]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert len(body["errores"]) == 1
        assert session.committed is False

    def test_referencia_carga_resolves_sustituida_por_codigo_end_to_end(self):
        proveedor_id = uuid.uuid4()
        proveedor = Proveedor(id=proveedor_id, codigo="HMCL", nombre="HMCL", es_principal=True)
        referencia_id = uuid.uuid4()
        referencia_sustituida = Referencia(
            id=referencia_id, codigo="REF-OLD", proveedor_id=proveedor_id, unidad_empaque=1
        )
        # probe, proveedor-codigo query, sustituida_por_codigo query,
        # get_referencia_by_codigo_proveedor (no match) -> create path
        session = FakeAsyncSession(execute_queue=[[], [proveedor], [referencia_sustituida], []])
        override_motored_db(session)

        with TestClient(app) as client:
            response = client.post(
                CARGA_REFERENCIA_URL,
                json={"filas": [{
                    "codigo": "REF-NEW", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "REF-OLD",
                }]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True, body
        assert body["insertados"] == 1


class TestSustitutaMustBelongToTheSameProveedor:
    """Business rule (user decision 2026-09-28): the substitute MUST belong to
    the same proveedor as the row. Equivalent parts from other proveedores or
    brands go in "Homologados otras marcas", never as sustituta."""

    async def test_same_proveedor_match_wins_over_other_proveedores(self):
        hmcl_id, otros_id = uuid.uuid4(), uuid.uuid4()
        hmcl = Proveedor(id=hmcl_id, codigo="HMCL", nombre="HMCL", es_principal=True)
        same = Referencia(id=uuid.uuid4(), codigo="REF-OLD", proveedor_id=hmcl_id, unidad_empaque=1)
        other = Referencia(id=uuid.uuid4(), codigo="REF-OLD", proveedor_id=otros_id, unidad_empaque=1)
        session = FakeAsyncSession(execute_queue=[[hmcl], [other, same]])
        filas = [{"codigo": "REF-NEW", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "REF-OLD"}]

        resolved, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert errores == []
        assert resolved[0]["sustituida_por"] == same.id

    async def test_match_only_under_another_proveedor_is_a_row_error_pointing_to_homologados(self):
        hmcl = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", es_principal=True)
        other = Referencia(id=uuid.uuid4(), codigo="REF-OLD", proveedor_id=uuid.uuid4(), unidad_empaque=1)
        session = FakeAsyncSession(execute_queue=[[hmcl], [other]])
        filas = [{"codigo": "REF-NEW", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "REF-OLD"}]

        resolved, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert len(errores) == 1
        assert "Código de referencia sustituta" in errores[0]["motivo"]
        assert "REF-OLD" in errores[0]["motivo"]
        assert "Homologados otras marcas" in errores[0]["motivo"]
        assert "sustituida_por" not in resolved[0]

    async def test_unmatched_error_names_the_business_column(self):
        session = FakeAsyncSession(execute_queue=[[]])
        filas = [{"codigo": "REF-NEW", "sustituida_por_codigo": "GHOST"}]

        _, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert "Código de referencia sustituta" in errores[0]["motivo"]
