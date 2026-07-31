"""
Regression tests for `download_attachment_file`
(`GET /api/v1/imports/attachments/{attachment_id}/file`, `imports.py`).

`list_attachments`/`upload_attachment` used to hand the browser a
`presigned_url` built with an undeclared `MINIO_PUBLIC_HOST` env var (dead
infrastructure — zero frontend consumers ever read `presigned_url`). This
proxy endpoint replaces that with the SAME already-working pattern
`get_dim_pdf_url` uses: fetch the object's bytes internally
(`storage_service.get_bytes`) and stream them back through an authenticated
route, so the browser never talks to MinIO directly.

Guard order mirrors `get_dim_pdf_url`: `_require_imports_editor` (role
guard) -> fetch attachment by id (404 if missing) -> fetch bytes (404 if
the object itself is missing from storage) -> success streams the bytes
with the attachment's own content-type and filename.
"""
import uuid

from app.api.v1 import imports as imports_module
from app.models.imports import ImportAttachment

from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_actor, make_imports_editor


def _attachment(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        shipment_order_id=uuid.uuid4(),
        lot_id=None,
        uploaded_by=None,
        file_name="factura.pdf",
        file_type="COMMERCIAL_INVOICE",
        minio_object_name="orders/x/commercial_invoice/some.pdf",
        content_type="application/pdf",
    )
    defaults.update(overrides)
    return ImportAttachment(**defaults)


class TestRoleGuard:

    def test_non_editor_role_gets_403_with_no_db_or_storage_touch(self, monkeypatch):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        called = {"get_bytes": False}

        async def _fake_get_bytes(bucket, object_name):
            called["get_bytes"] = True
            return b"should-not-be-called"

        monkeypatch.setattr(imports_module.storage_service, "get_bytes", _fake_get_bytes)

        with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/attachments/{uuid.uuid4()}/file")

        assert response.status_code == 403
        assert response.json()["detail"] == "Sin permisos para el módulo de importaciones"
        assert called["get_bytes"] is False

    def test_imports_editor_role_passes_the_guard(self):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/attachments/{uuid.uuid4()}/file")

        # Passes the role guard and reaches the next check (attachment lookup miss).
        assert response.status_code == 404


class TestNotFoundPaths:

    def test_missing_attachment_404(self):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/attachments/{uuid.uuid4()}/file")

        assert response.status_code == 404

    def test_storage_miss_404(self, monkeypatch):
        attachment = _attachment()
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[attachment])

        async def _fake_get_bytes(bucket, object_name):
            return None

        monkeypatch.setattr(imports_module.storage_service, "get_bytes", _fake_get_bytes)

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/attachments/{attachment.id}/file")

        assert response.status_code == 404


class TestSuccess:

    def test_returns_bytes_with_content_type_and_filename(self, monkeypatch):
        attachment = _attachment(file_name="Factura Comercial.pdf", content_type="application/pdf")
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[attachment])

        async def _fake_get_bytes(bucket, object_name):
            assert bucket == imports_module.storage_service.IMPORTS_BUCKET
            assert object_name == attachment.minio_object_name
            return b"%PDF-1.4 fake invoice"

        monkeypatch.setattr(imports_module.storage_service, "get_bytes", _fake_get_bytes)

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/attachments/{attachment.id}/file")

        assert response.status_code == 200
        assert response.content == b"%PDF-1.4 fake invoice"
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"] == 'attachment; filename="Factura Comercial.pdf"'

    def test_falls_back_to_octet_stream_when_content_type_missing(self, monkeypatch):
        attachment = _attachment(content_type=None)
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[attachment])

        async def _fake_get_bytes(bucket, object_name):
            return b"raw-bytes"

        monkeypatch.setattr(imports_module.storage_service, "get_bytes", _fake_get_bytes)

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get(f"/api/v1/imports/attachments/{attachment.id}/file")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/octet-stream"
