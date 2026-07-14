"""
Regression tests for `get_dim_pdf_url`
(`GET /api/v1/imports/moto-units/{unit_id}/dim-url`, `imports.py`).

Bug fixed: this endpoint only depended on `get_current_user` — ANY
authenticated user, regardless of role, could download a unit's DIM
(customs) PDF. Its sibling upload endpoint (`upload_dim_pdf`) already
requires `role in ("superadmin", "administrativo")`; this closes the same
gate on the read side (business decision: proveedor is explicitly
excluded, unlike other imports-editor actions — see
sdd/packing-list-reupload-requires-rollback's PENDING section).

Covers:
  - superadmin / administrativo can reach the endpoint (role guard passes).
  - proveedor and any non-editor role get 403, before any DB lookup.
  - Unit not found -> 404 (only reachable past the role guard).
  - No DIM uploaded yet (`dim_pdf_object_name` empty) -> 404.
  - Storage miss (`get_bytes` returns falsy) -> 404.
  - Success -> inline PDF StreamingResponse with the expected filename.
"""
import uuid

from app.api.v1 import imports as imports_module
from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_actor, make_imports_editor, make_moto_unit


def _unit_with_dim(**overrides):
    defaults = dict(vin_number="VIN9001", dim_pdf_object_name="lots/x/dim/some.pdf")
    defaults.update(overrides)
    return make_moto_unit(**defaults)


class TestRoleGuard:

    def test_proveedor_is_rejected_403_before_any_db_lookup(self):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        with make_test_client(current_user=make_imports_editor(role="proveedor"), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/moto-units/{uuid.uuid4()}/dim-url")

        assert response.status_code == 403
        assert response.json() == {"detail": "Sin permisos para descargar la DIM"}

    def test_non_editor_role_is_rejected_403(self):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/moto-units/{uuid.uuid4()}/dim-url")

        assert response.status_code == 403
        assert response.json() == {"detail": "Sin permisos para descargar la DIM"}

    def test_superadmin_passes_the_guard(self):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/moto-units/{uuid.uuid4()}/dim-url")

        # Passes the role guard and reaches the next check (unit lookup miss).
        assert response.status_code == 404
        assert response.json() == {"detail": "Unidad no encontrada"}


class TestNotFoundPaths:

    def test_missing_unit_404(self):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/moto-units/{uuid.uuid4()}/dim-url")

        assert response.status_code == 404
        assert response.json() == {"detail": "Unidad no encontrada"}

    def test_dim_not_uploaded_yet_404(self):
        unit = _unit_with_dim(dim_pdf_object_name=None)
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[unit])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/moto-units/{unit.id}/dim-url")

        assert response.status_code == 404
        assert response.json() == {"detail": "Esta unidad no tiene DIM cargada"}

    def test_storage_miss_404(self, monkeypatch):
        unit = _unit_with_dim()
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[unit])

        async def _fake_get_bytes(bucket, object_name):
            return None

        monkeypatch.setattr(imports_module.storage_service, "get_bytes", _fake_get_bytes)

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/moto-units/{unit.id}/dim-url")

        assert response.status_code == 404
        assert response.json() == {"detail": "Archivo DIM no encontrado en almacenamiento"}


class TestSuccess:

    def test_returns_inline_pdf_with_vin_filename(self, monkeypatch):
        unit = _unit_with_dim(vin_number="VIN12345")
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[unit])

        async def _fake_get_bytes(bucket, object_name):
            return b"%PDF-1.4 fake dim"

        monkeypatch.setattr(imports_module.storage_service, "get_bytes", _fake_get_bytes)

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/moto-units/{unit.id}/dim-url")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"] == 'inline; filename="DIM_VIN12345.pdf"'
        assert response.content == b"%PDF-1.4 fake dim"
