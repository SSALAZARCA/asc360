"""
tests/orders/test_evidence_photo_download.py — `GET /orders/{order_id}/
evidence-photos/{index}`.

`ServiceOrderReception.damage_photos_urls[index]["url"]` is built by
`pdf_service.upload_file_to_minio` with a hardcoded `http://localhost:9000/
...` host — that resolves to the BROWSER's own machine, not the server, so
it never works in production. This proxy endpoint mirrors the SAME
already-working pattern `download_reception_pdf` (this same module) and
`distributor_delivery_service.get_delivery_act_file` use: fetch the
object's bytes internally (`pdf_service.get_pdf_stream_from_minio`) and
stream them back through an authenticated route, so the browser never talks
to MinIO directly.

Guard order mirrors `download_reception_pdf` exactly: `forbid_distribuidor`
(zero DB read) -> load order + reception (404 if missing) -> tenant-
ownership check (403, superadmin bypasses) -> index/entry validity check
(404 for out-of-range or a text-only observation with no `url`) -> fetch
bytes (404 if the object itself is missing from storage).
"""
import uuid
from unittest.mock import AsyncMock, patch

from app.models.order import ServiceOrderReception

from app.services import pdf_service

from tests.conftest import make_test_client
from tests.orders.conftest import FakeActivePlateSession, make_claim_order
from tests.orders.test_forbid_distribuidor import NoTouchSession, make_current_user


def _order_with_photos(tenant_id, photos):
    order = make_claim_order(tenant_id=tenant_id)
    order.reception = ServiceOrderReception(
        id=uuid.uuid4(),
        order_id=order.id,
        mileage_km=1000,
        damage_photos_urls=photos,
    )
    return order


class TestDistribuidorBlockedBeforeAnyQuery:
    def test_403_before_any_query(self):
        distribuidor = make_current_user("parts_dealer")
        with make_test_client(current_user=distribuidor, fake_db_session=NoTouchSession()) as client:
            res = client.get(f"/api/v1/orders/{uuid.uuid4()}/evidence-photos/0")
        assert res.status_code == 403


class TestOwnTenantDownloadsPhoto:
    def test_200_with_correct_bytes_and_content_type(self):
        tenant_id = uuid.uuid4()
        object_uuid = uuid.uuid4()
        order = _order_with_photos(
            tenant_id,
            [{"url": f"http://localhost:9000/um-service-docs/evidences/2026/7/{object_uuid}_foto.jpg", "desc": "Rayón"}],
        )
        fake_db = FakeActivePlateSession(order=order)
        actor = make_current_user("technician", tenant_id=tenant_id)

        with make_test_client(current_user=actor, fake_db_session=fake_db) as client:
            with patch.object(pdf_service, "get_pdf_stream_from_minio", new=AsyncMock(return_value=b"fake-jpg-bytes")):
                res = client.get(f"/api/v1/orders/{order.id}/evidence-photos/0")

        assert res.status_code == 200
        assert res.content == b"fake-jpg-bytes"
        assert res.headers["content-type"] == "image/jpeg"

    def test_fetches_bytes_with_correctly_parsed_object_name(self):
        tenant_id = uuid.uuid4()
        object_uuid = uuid.uuid4()
        order = _order_with_photos(
            tenant_id,
            [{
                "url": (
                    f"http://localhost:9000/um-service-docs/evidences/2026/7/{object_uuid}_foto.png"
                    "?X-Amz-Algorithm=fake&X-Amz-Signature=fake"
                ),
                "desc": "Golpe",
            }],
        )
        fake_db = FakeActivePlateSession(order=order)
        actor = make_current_user("technician", tenant_id=tenant_id)

        with make_test_client(current_user=actor, fake_db_session=fake_db) as client:
            mock_get_bytes = AsyncMock(return_value=b"fake-png-bytes")
            with patch.object(pdf_service, "get_pdf_stream_from_minio", new=mock_get_bytes):
                res = client.get(f"/api/v1/orders/{order.id}/evidence-photos/0")

        assert res.status_code == 200
        mock_get_bytes.assert_awaited_once_with(f"evidences/2026/7/{object_uuid}_foto.png")


class TestDifferentTenantGets403WithoutStorageAccess:
    def test_403_before_any_minio_fetch(self):
        own_tenant = uuid.uuid4()
        other_tenant = uuid.uuid4()
        order = _order_with_photos(
            other_tenant,
            [{"url": "http://localhost:9000/um-service-docs/evidences/2026/7/x_foto.jpg", "desc": "Rayón"}],
        )
        fake_db = FakeActivePlateSession(order=order)
        actor = make_current_user("technician", tenant_id=own_tenant)

        with make_test_client(current_user=actor, fake_db_session=fake_db) as client:
            with patch.object(
                pdf_service, "get_pdf_stream_from_minio", new=AsyncMock(return_value=b"should-not-be-called")
            ) as mock_get_bytes:
                res = client.get(f"/api/v1/orders/{order.id}/evidence-photos/0")

        assert res.status_code == 403
        mock_get_bytes.assert_not_awaited()


class TestSuperadminDownloadsAnyTenantPhoto:
    def test_200_regardless_of_tenant(self):
        other_tenant = uuid.uuid4()
        order = _order_with_photos(
            other_tenant,
            [{"url": "http://localhost:9000/um-service-docs/evidences/2026/7/x_foto.png", "desc": "Rayón"}],
        )
        fake_db = FakeActivePlateSession(order=order)
        actor = make_current_user("superadmin")

        with make_test_client(current_user=actor, fake_db_session=fake_db) as client:
            with patch.object(pdf_service, "get_pdf_stream_from_minio", new=AsyncMock(return_value=b"fake-bytes")):
                res = client.get(f"/api/v1/orders/{order.id}/evidence-photos/0")

        assert res.status_code == 200
        assert res.content == b"fake-bytes"


class TestIndexOutOfRangeReturns404:
    def test_404_when_index_out_of_bounds(self):
        tenant_id = uuid.uuid4()
        order = _order_with_photos(
            tenant_id,
            [{"url": "http://localhost:9000/um-service-docs/evidences/2026/7/x_foto.jpg", "desc": "Rayón"}],
        )
        fake_db = FakeActivePlateSession(order=order)
        actor = make_current_user("technician", tenant_id=tenant_id)

        with make_test_client(current_user=actor, fake_db_session=fake_db) as client:
            res = client.get(f"/api/v1/orders/{order.id}/evidence-photos/5")

        assert res.status_code == 404


class TestOrderNotFoundReturns404:
    def test_404_when_order_does_not_exist(self):
        fake_db = FakeActivePlateSession(order=None)
        actor = make_current_user("technician", tenant_id=uuid.uuid4())

        with make_test_client(current_user=actor, fake_db_session=fake_db) as client:
            res = client.get(f"/api/v1/orders/{uuid.uuid4()}/evidence-photos/0")

        assert res.status_code == 404


class TestTextOnlyEntryReturns404:
    def test_404_when_entry_has_no_url(self):
        tenant_id = uuid.uuid4()
        order = _order_with_photos(tenant_id, [{"type": "text", "desc": "Ninguna"}])
        fake_db = FakeActivePlateSession(order=order)
        actor = make_current_user("technician", tenant_id=tenant_id)

        with make_test_client(current_user=actor, fake_db_session=fake_db) as client:
            res = client.get(f"/api/v1/orders/{order.id}/evidence-photos/0")

        assert res.status_code == 404
