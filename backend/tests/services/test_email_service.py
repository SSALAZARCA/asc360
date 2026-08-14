"""
tests/services/test_email_service.py -- RED/GREEN for
`app.services.email_service` (`sdd/reception-email-notification` Phase 2).

Pure SMTP transport, no DB, no Telegram, no MinIO. `aiosmtplib.send` is
monkeypatched to a spy/raiser so these tests never touch a live network.
Mirrors `notification_service.py`'s established contract: best-effort,
never raises, finite explicit timeout, logs exception TYPE only -- never
credentials or the recipient address (BR6/BR9 extended to this
transport).
"""
import logging

import pytest

from app.services import email_service as svc


class _FakeSend:
    """Spy standing in for `aiosmtplib.send` -- captures every kwarg the
    module passes so tests can assert on TLS/timeout without a live
    connection."""

    def __init__(self, raise_exc: Exception = None):
        self.calls = []
        self._raise_exc = raise_exc

    async def __call__(self, message, **kwargs):
        self.calls.append({"message": message, **kwargs})
        if self._raise_exc:
            raise self._raise_exc
        return ({}, "OK")


class TestKillSwitch:
    async def test_flag_off_returns_skipped_and_never_calls_send(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "RECEPTION_EMAIL_ENABLED", False)
        fake_send = _FakeSend()
        monkeypatch.setattr(svc.aiosmtplib, "send", fake_send)

        result = await svc.send_reception_pdf_email(
            recipient="cliente@example.com", client_name="Juan", plate="ABC123", pdf_bytes=b"%PDF-1.4"
        )

        assert result == "skipped"
        assert fake_send.calls == []


class TestMissingInputsSkipSilently:
    async def test_no_recipient_returns_skipped(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "RECEPTION_EMAIL_ENABLED", True)
        fake_send = _FakeSend()
        monkeypatch.setattr(svc.aiosmtplib, "send", fake_send)

        result = await svc.send_reception_pdf_email(
            recipient=None, client_name="Juan", plate="ABC123", pdf_bytes=b"%PDF-1.4"
        )

        assert result == "skipped"
        assert fake_send.calls == []

    async def test_no_pdf_bytes_returns_skipped(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "RECEPTION_EMAIL_ENABLED", True)
        fake_send = _FakeSend()
        monkeypatch.setattr(svc.aiosmtplib, "send", fake_send)

        result = await svc.send_reception_pdf_email(
            recipient="cliente@example.com", client_name="Juan", plate="ABC123", pdf_bytes=None
        )

        assert result == "skipped"
        assert fake_send.calls == []


class TestSendFailureNeverPropagates:
    async def test_smtp_exception_returns_failed_and_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "RECEPTION_EMAIL_ENABLED", True)
        fake_send = _FakeSend(raise_exc=ConnectionRefusedError("boom"))
        monkeypatch.setattr(svc.aiosmtplib, "send", fake_send)

        # Must not raise.
        result = await svc.send_reception_pdf_email(
            recipient="cliente@example.com", client_name="Juan", plate="ABC123", pdf_bytes=b"%PDF-1.4"
        )

        assert result == "failed"


class TestSuccessfulSend:
    async def test_valid_inputs_return_sent(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "RECEPTION_EMAIL_ENABLED", True)
        fake_send = _FakeSend()
        monkeypatch.setattr(svc.aiosmtplib, "send", fake_send)

        result = await svc.send_reception_pdf_email(
            recipient="cliente@example.com", client_name="Juan", plate="ABC123", pdf_bytes=b"%PDF-1.4"
        )

        assert result == "sent"
        assert len(fake_send.calls) == 1


class TestTlsAndTimeoutAreEnforced:
    async def test_starttls_and_finite_timeout_passed_to_aiosmtplib_send(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "RECEPTION_EMAIL_ENABLED", True)
        monkeypatch.setattr(svc.settings, "SMTP_STARTTLS", True)
        monkeypatch.setattr(svc.settings, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(svc.settings, "SMTP_PORT", 587)
        fake_send = _FakeSend()
        monkeypatch.setattr(svc.aiosmtplib, "send", fake_send)

        await svc.send_reception_pdf_email(
            recipient="cliente@example.com", client_name="Juan", plate="ABC123", pdf_bytes=b"%PDF-1.4"
        )

        call = fake_send.calls[0]
        assert call["timeout"] == svc.SMTP_TIMEOUT
        assert isinstance(call["timeout"], float) and call["timeout"] > 0
        assert call["start_tls"] is True
        assert call["hostname"] == "smtp.example.com"
        assert call["port"] == 587

    async def test_implicit_tls_used_when_starttls_disabled(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "RECEPTION_EMAIL_ENABLED", True)
        monkeypatch.setattr(svc.settings, "SMTP_STARTTLS", False)
        fake_send = _FakeSend()
        monkeypatch.setattr(svc.aiosmtplib, "send", fake_send)

        await svc.send_reception_pdf_email(
            recipient="cliente@example.com", client_name="Juan", plate="ABC123", pdf_bytes=b"%PDF-1.4"
        )

        call = fake_send.calls[0]
        assert call["use_tls"] is True
        assert not call.get("start_tls")


class TestSanitizeHeader:
    def test_strips_crlf(self):
        result = svc._sanitize_header("ABC\r\n123")
        assert "\r" not in result and "\n" not in result
        assert result == "ABC123"

    def test_strips_bare_lf(self):
        result = svc._sanitize_header("ABC\n123")
        assert "\n" not in result
        assert result == "ABC123"

    def test_strips_nul(self):
        assert "\x00" not in svc._sanitize_header("ABC\x00123")

    def test_truncates_to_max_len(self):
        result = svc._sanitize_header("a" * 200, max_len=10)
        assert len(result) == 10

    def test_empty_string_returns_empty(self):
        assert svc._sanitize_header("") == ""


class TestNoSecretsInLogsOnFailure:
    async def test_credentials_and_recipient_never_appear_in_caplog(self, monkeypatch, caplog):
        monkeypatch.setattr(svc.settings, "RECEPTION_EMAIL_ENABLED", True)
        monkeypatch.setattr(svc.settings, "SMTP_PASSWORD", "super-secret-password")
        monkeypatch.setattr(svc.settings, "SMTP_USER", "network-mailbox@example.com")
        fake_send = _FakeSend(
            raise_exc=Exception(
                "auth failed for network-mailbox@example.com with password super-secret-password "
                "sending to cliente-secreto@example.com"
            )
        )
        monkeypatch.setattr(svc.aiosmtplib, "send", fake_send)
        caplog.set_level(logging.ERROR, logger=svc.logger.name)

        await svc.send_reception_pdf_email(
            recipient="cliente-secreto@example.com",
            client_name="Juan",
            plate="ABC123",
            pdf_bytes=b"%PDF-1.4",
        )

        assert "super-secret-password" not in caplog.text
        assert "network-mailbox@example.com" not in caplog.text
        assert "cliente-secreto@example.com" not in caplog.text
