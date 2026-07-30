"""
tests/distributor_deliveries/test_act_file_download.py — follow-up bugfix
(2026-07-30): `GET /distributor/deliveries/{vehicle_id}/act-file`.

`pdf_service.upload_file_to_minio` hardcodes `http://localhost:9000/...` as
the stored `Vehicle.delivery_act_url` -- that host resolves to the BROWSER's
own machine, not the server, so a browser can never fetch it directly in
production. This proxy endpoint mirrors the SAME already-working pattern
`orders.py`'s `download_reception_pdf` and `imports.py`'s `get_dim_pdf_url`
use: fetch the object's bytes internally (`pdf_service.
get_pdf_stream_from_minio`) and stream them back through an authenticated
route, so the browser never talks to MinIO directly.

Guard order mirrors `download_reception_pdf` exactly: role guard (zero DB
read) -> fetch vehicle (404 if missing) -> tenant-ownership check (403,
superadmin bypasses) -> act-file-exists check (404) -> fetch bytes (404 if
the object itself is missing from storage).
"""
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_current_user
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    NoTouchSession,
    make_delivery_vehicle,
    make_distribuidor,
    make_jefe_taller,
    make_superadmin,
)


def _override(fake_db, actor):
    async def _get_db():
        yield fake_db
    app.dependency_overrides[get_db] = _get_db

    async def _get_current_user():
        return actor
    app.dependency_overrides[get_current_user] = _get_current_user


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _get(vehicle_id):
    with TestClient(app) as client:
        return client.get(f"/api/v1/distributor/deliveries/{vehicle_id}/act-file")


class TestDistribuidorDownloadsOwnTenantAct:
    def test_returns_200_with_bytes_and_content_type(self):
        tenant_id = uuid.uuid4()
        vehicle = make_delivery_vehicle(registered_by_tenant_id=tenant_id)
        vehicle.delivery_act_url = (
            "http://localhost:9000/um-service-docs/evidences/2026/7/"
            f"{uuid.uuid4()}_acta.jpg"
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        _override(fake_db, make_distribuidor(tenant_id=tenant_id))

        try:
            with patch.object(
                svc, "get_pdf_stream_from_minio", new=AsyncMock(return_value=b"fake-jpg-bytes")
            ):
                res = _get(vehicle.id)
            assert res.status_code == 200
            assert res.content == b"fake-jpg-bytes"
            assert res.headers["content-type"] == "image/jpeg"
        finally:
            _teardown()

    def test_fetches_bytes_with_the_correctly_parsed_object_name(self):
        tenant_id = uuid.uuid4()
        object_uuid = uuid.uuid4()
        vehicle = make_delivery_vehicle(registered_by_tenant_id=tenant_id)
        vehicle.delivery_act_url = (
            f"http://localhost:9000/um-service-docs/evidences/2026/7/{object_uuid}_acta.pdf"
            "?X-Amz-Algorithm=fake&X-Amz-Signature=fake"
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        _override(fake_db, make_distribuidor(tenant_id=tenant_id))

        try:
            mock_get_bytes = AsyncMock(return_value=b"fake-pdf-bytes")
            with patch.object(svc, "get_pdf_stream_from_minio", new=mock_get_bytes):
                res = _get(vehicle.id)
            assert res.status_code == 200
            mock_get_bytes.assert_awaited_once_with(f"evidences/2026/7/{object_uuid}_acta.pdf")
        finally:
            _teardown()


class TestDistribuidorGets403ForADifferentDistribuidorasVehicle:
    def test_403_before_any_file_storage_access(self):
        own_tenant = uuid.uuid4()
        other_tenant = uuid.uuid4()
        vehicle = make_delivery_vehicle(registered_by_tenant_id=other_tenant)
        vehicle.delivery_act_url = "http://localhost:9000/um-service-docs/evidences/2026/7/x_acta.jpg"
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        _override(fake_db, make_distribuidor(tenant_id=own_tenant))

        try:
            with patch.object(
                svc, "get_pdf_stream_from_minio", new=AsyncMock(return_value=b"should-not-be-called")
            ) as mock_get_bytes:
                res = _get(vehicle.id)
            assert res.status_code == 403
            mock_get_bytes.assert_not_awaited()
        finally:
            _teardown()


class TestSuperadminDownloadsAnyDistribuidorasAct:
    def test_returns_200_regardless_of_registered_by_tenant_id(self):
        other_tenant = uuid.uuid4()
        vehicle = make_delivery_vehicle(registered_by_tenant_id=other_tenant)
        vehicle.delivery_act_url = "http://localhost:9000/um-service-docs/evidences/2026/7/x_acta.png"
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        _override(fake_db, make_superadmin())

        try:
            with patch.object(
                svc, "get_pdf_stream_from_minio", new=AsyncMock(return_value=b"fake-png-bytes")
            ):
                res = _get(vehicle.id)
            assert res.status_code == 200
            assert res.content == b"fake-png-bytes"
            assert res.headers["content-type"] == "image/png"
        finally:
            _teardown()


class TestVehicleWithNoDeliveryActUrlReturns404:
    def test_404_when_delivery_act_url_is_none(self):
        tenant_id = uuid.uuid4()
        vehicle = make_delivery_vehicle(registered_by_tenant_id=tenant_id)
        # delivery_act_url left at its ORM default (None).
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        _override(fake_db, make_distribuidor(tenant_id=tenant_id))

        try:
            res = _get(vehicle.id)
            assert res.status_code == 404
        finally:
            _teardown()


class TestNonexistentVehicleIdReturns404:
    def test_404_when_vehicle_does_not_exist(self):
        fake_db = FakeDeliverySession(vehicles=[])
        _override(fake_db, make_distribuidor())

        try:
            res = _get(uuid.uuid4())
            assert res.status_code == 404
        finally:
            _teardown()


class TestDistribuidorWithNoTenantAssignedIsForbidden:
    def test_403_even_when_vehicle_also_has_no_registered_tenant(self):
        """A Distribuidor with no Distribuidora assigned yet (`tenant_id is
        None`) must NEVER be treated as matching a vehicle that also has no
        `registered_by_tenant_id` -- `None != None` is `False` in plain
        Python, so an unguarded equality check would silently let them
        through. Mirrors the same NULL-comparison lesson already learned in
        `list_deliveries` (an explicit early-check, not implicit equality)."""
        vehicle = make_delivery_vehicle(registered_by_tenant_id=None)
        vehicle.delivery_act_url = "http://localhost:9000/um-service-docs/evidences/2026/7/x_acta.jpg"
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        _override(fake_db, make_distribuidor(tenant_id=None))

        try:
            with patch.object(
                svc, "get_pdf_stream_from_minio", new=AsyncMock(return_value=b"should-not-be-called")
            ) as mock_get_bytes:
                res = _get(vehicle.id)
            assert res.status_code == 403
            mock_get_bytes.assert_not_awaited()
        finally:
            _teardown()


class TestNonDistribuidorNonSuperadminGets403WithZeroDbTouch:
    def test_jefe_taller_gets_403_with_no_db_touch(self):
        _override(NoTouchSession(), make_jefe_taller())

        try:
            res = _get(uuid.uuid4())
            assert res.status_code == 403
        finally:
            _teardown()
