"""
tests/services/test_pdf_service_fetch_bytes.py -- RED/GREEN for
`pdf_service.fetch_reception_pdf_bytes` (`sdd/reception-email-notification`
Phase 3, design ADR 1).

Purely additive -- `generate_and_upload_reception_pdf`'s existing
signature/behavior (and the ~35 existing test monkeypatches depending on
it) are untouched by this module. This new function re-fetches the
already-uploaded PDF's bytes from MinIO for the background email-attach
path, parsing only `urlparse(pdf_url).path` and stripping the bucket
prefix -- it never trusts the host portion of the URL (the presigned URL
already has its host rewritten for the bot's benefit, see
`pdf_service.py:143`).
"""
from unittest.mock import MagicMock

import pytest

import app.services.pdf_service as pdf_service


class _FakeMinioResponse:
    def __init__(self, data: bytes):
        self._data = data
        self.closed = False
        self.released = False

    def read(self):
        return self._data

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


class TestFetchReceptionPdfBytesHappyPath:
    def test_returns_bytes_for_a_valid_presigned_url(self, monkeypatch):
        expected_bytes = b"%PDF-1.4 fake bytes"
        captured = {}

        def _fake_get_object(bucket, object_name):
            captured["bucket"] = bucket
            captured["object_name"] = object_name
            return _FakeMinioResponse(expected_bytes)

        monkeypatch.setattr(pdf_service.minio_client, "get_object", _fake_get_object)

        url = (
            f"http://localhost:9000/{pdf_service.BUCKET_NAME}/receptions/2026/8/"
            "act_11111111-1111-1111-1111-111111111111.pdf?X-Amz-Signature=abc"
        )
        result = pdf_service.fetch_reception_pdf_bytes(url)

        assert result == expected_bytes
        assert captured["bucket"] == pdf_service.BUCKET_NAME
        assert captured["object_name"] == "receptions/2026/8/act_11111111-1111-1111-1111-111111111111.pdf"

    def test_closes_and_releases_the_connection(self, monkeypatch):
        response = _FakeMinioResponse(b"bytes")
        monkeypatch.setattr(pdf_service.minio_client, "get_object", lambda *a, **kw: response)

        url = f"http://localhost:9000/{pdf_service.BUCKET_NAME}/receptions/act_1.pdf"
        pdf_service.fetch_reception_pdf_bytes(url)

        assert response.closed is True
        assert response.released is True


class TestFetchReceptionPdfBytesEmptyOrMalformedUrl:
    def test_empty_string_returns_none(self, monkeypatch):
        spy = MagicMock()
        monkeypatch.setattr(pdf_service.minio_client, "get_object", spy)

        assert pdf_service.fetch_reception_pdf_bytes("") is None
        spy.assert_not_called()

    def test_none_returns_none(self, monkeypatch):
        spy = MagicMock()
        monkeypatch.setattr(pdf_service.minio_client, "get_object", spy)

        assert pdf_service.fetch_reception_pdf_bytes(None) is None
        spy.assert_not_called()

    def test_url_without_bucket_prefix_returns_none(self, monkeypatch):
        spy = MagicMock()
        monkeypatch.setattr(pdf_service.minio_client, "get_object", spy)

        assert pdf_service.fetch_reception_pdf_bytes("http://localhost:9000/not-a-real-bucket-path") is None
        spy.assert_not_called()

    def test_completely_malformed_url_returns_none(self, monkeypatch):
        spy = MagicMock()
        monkeypatch.setattr(pdf_service.minio_client, "get_object", spy)

        assert pdf_service.fetch_reception_pdf_bytes("not a url at all") is None
        spy.assert_not_called()


class TestFetchReceptionPdfBytesMinioErrors:
    def test_minio_get_object_raising_returns_none(self, monkeypatch):
        def _raise(*a, **kw):
            raise Exception("minio unreachable")

        monkeypatch.setattr(pdf_service.minio_client, "get_object", _raise)

        url = f"http://localhost:9000/{pdf_service.BUCKET_NAME}/receptions/act_1.pdf"
        # Must not raise.
        assert pdf_service.fetch_reception_pdf_bytes(url) is None
