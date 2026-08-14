"""
tests/services/test_reception_email_dispatch.py -- RED/GREEN for
`app.services.reception_email_dispatch.dispatch_reception_email`
(`sdd/reception-email-notification` Phase 5, design ADR 2/ADR 3).

The saga: gate -> fetch PDF bytes -> send -> alert-on-failure only. Per
ADR 2, the function receives PLAIN SCALARS ONLY and opens its OWN DB
session (via `async_session_maker`) exclusively on the failure path, to
resolve `tenant_name` for the Telegram alert. `pdf_service.
fetch_reception_pdf_bytes` and `email_service.send_reception_pdf_email`
are monkeypatched to spies/fakes -- no live MinIO/SMTP/DB. Never raises
(BR6/BR8), including when the alert call itself blows up.
"""
import uuid

import pytest

from app.services import reception_email_dispatch as dispatch


class _FakeTenant:
    def __init__(self, name):
        self.name = name


class _FakeSession:
    """Minimal fake standing in for the `AsyncSession` opened by
    `async_session_maker()` on the failure path -- the saga only ever
    issues one `db.get(Tenant, tenant_id)` read here."""

    def __init__(self, tenant=None):
        self._tenant = tenant

    async def get(self, model, pk):
        return self._tenant

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _spy_session_maker(tenant=None):
    """Returns a zero-arg factory (matching `async_session_maker`'s own
    signature) that records every call, so tests can assert a session was
    (or was NOT) opened."""
    calls = []

    def _factory():
        calls.append(1)
        return _FakeSession(tenant)

    _factory.calls = calls
    return _factory


def _base_kwargs(**overrides):
    kwargs = dict(
        order_id="order-1",
        plate="ABC123",
        tenant_id=uuid.uuid4(),
        recipient="cliente@example.com",
        client_name="Juan",
        pdf_url="http://localhost:9000/bucket/receptions/act.pdf",
    )
    kwargs.update(overrides)
    return kwargs


class TestFailedSendTriggersAlert:
    async def test_alert_called_once_with_correct_scalars(self, monkeypatch):
        monkeypatch.setattr(dispatch.pdf_service, "fetch_reception_pdf_bytes", lambda url: b"%PDF-1.4")

        async def _fake_send(**kwargs):
            return "failed"

        monkeypatch.setattr(dispatch.email_service, "send_reception_pdf_email", _fake_send)

        session_maker = _spy_session_maker(tenant=_FakeTenant("Taller Central"))
        monkeypatch.setattr(dispatch, "async_session_maker", session_maker)

        captured = {}

        async def _fake_notify(db, **kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(dispatch, "notify_reception_email_failure", _fake_notify)

        tenant_id = uuid.uuid4()
        await dispatch.dispatch_reception_email(
            **_base_kwargs(order_id="order-42", plate="XYZ999", tenant_id=tenant_id)
        )

        assert session_maker.calls == [1]
        assert captured["order_id"] == "order-42"
        assert captured["plate"] == "XYZ999"
        assert captured["tenant_id"] == tenant_id
        assert captured["tenant_name"] == "Taller Central"


class TestSkippedNeverAlerts:
    async def test_skipped_result_does_not_call_alert_or_open_session(self, monkeypatch):
        monkeypatch.setattr(dispatch.pdf_service, "fetch_reception_pdf_bytes", lambda url: b"%PDF-1.4")

        async def _fake_send(**kwargs):
            return "skipped"

        monkeypatch.setattr(dispatch.email_service, "send_reception_pdf_email", _fake_send)

        session_maker = _spy_session_maker()
        monkeypatch.setattr(dispatch, "async_session_maker", session_maker)

        notify_calls = []

        async def _fake_notify(db, **kwargs):
            notify_calls.append(kwargs)

        monkeypatch.setattr(dispatch, "notify_reception_email_failure", _fake_notify)

        await dispatch.dispatch_reception_email(**_base_kwargs())

        assert notify_calls == []
        assert session_maker.calls == []


class TestSuccessNeverOpensSession:
    async def test_sent_result_opens_no_db_session(self, monkeypatch):
        monkeypatch.setattr(dispatch.pdf_service, "fetch_reception_pdf_bytes", lambda url: b"%PDF-1.4")

        async def _fake_send(**kwargs):
            return "sent"

        monkeypatch.setattr(dispatch.email_service, "send_reception_pdf_email", _fake_send)

        session_maker = _spy_session_maker()
        monkeypatch.setattr(dispatch, "async_session_maker", session_maker)

        await dispatch.dispatch_reception_email(**_base_kwargs())

        assert session_maker.calls == []


class TestAlertFailureIsSwallowed:
    async def test_alert_raising_never_propagates(self, monkeypatch):
        monkeypatch.setattr(dispatch.pdf_service, "fetch_reception_pdf_bytes", lambda url: b"%PDF-1.4")

        async def _fake_send(**kwargs):
            return "failed"

        monkeypatch.setattr(dispatch.email_service, "send_reception_pdf_email", _fake_send)

        session_maker = _spy_session_maker(tenant=_FakeTenant("Taller Central"))
        monkeypatch.setattr(dispatch, "async_session_maker", session_maker)

        async def _raising_notify(db, **kwargs):
            raise RuntimeError("telegram is down")

        monkeypatch.setattr(dispatch, "notify_reception_email_failure", _raising_notify)

        # Must not raise.
        await dispatch.dispatch_reception_email(**_base_kwargs())


class TestUnfetchablePdfBytesFallsThroughToEmailServiceContract:
    async def test_none_bytes_is_treated_as_skipped_not_failed(self, monkeypatch):
        """`fetch_reception_pdf_bytes` returning `None` (unfetchable) must
        not be special-cased here -- `email_service.send_reception_pdf_email`
        already returns `"skipped"` for missing `pdf_bytes` (its own
        contract, see `tests/services/test_email_service.py::
        TestMissingInputsSkipSilently::test_no_pdf_bytes_returns_skipped`),
        so this saga just passes the result through: no alert."""
        monkeypatch.setattr(dispatch.pdf_service, "fetch_reception_pdf_bytes", lambda url: None)
        monkeypatch.setattr(dispatch.email_service.settings, "RECEPTION_EMAIL_ENABLED", True)

        session_maker = _spy_session_maker()
        monkeypatch.setattr(dispatch, "async_session_maker", session_maker)

        notify_calls = []

        async def _fake_notify(db, **kwargs):
            notify_calls.append(kwargs)

        monkeypatch.setattr(dispatch, "notify_reception_email_failure", _fake_notify)

        # Uses the REAL `email_service.send_reception_pdf_email` (not
        # mocked) to prove the actual missing-bytes contract, not an
        # assumption about it.
        await dispatch.dispatch_reception_email(**_base_kwargs())

        assert notify_calls == []
        assert session_maker.calls == []
