"""
tests/services/test_notification_service.py -- RED/GREEN tests for
`notification_service.notify_claim_conflict`
(`sdd/vehicle-tenant-checkin-release` PR3, Design Decision 3): the
backend's first-ever direct Telegram Bot API call.

No live network and no live DB: `_send_telegram_message` is monkeypatched
to a spy for the recipient-fan-out and failure-isolation tests, and
exercised directly against a fake `httpx.AsyncClient` for the
timeout/URL/payload test. `FakeNotificationSession` is a minimal fake
`AsyncSession` dispatching by call ORDER -- `notify_claim_conflict` always
queries the holding taller first, then superadmins (matches production
call order), so no statement-shape dispatch is needed.
"""
import uuid
from types import SimpleNamespace

import httpx
import pytest

from app.models.user import Role, User, UserStatus
from app.repositories.vehicle_repository import VehicleClaim
from app.services import notification_service as svc


def make_user(role, telegram_id="111", tenant_id=None, status=UserStatus.active):
    return User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Test User",
        role=role,
        status=status,
        telegram_id=telegram_id,
    )


def make_claim(tenant_id=None, tenant_name="Taller A", tenant_city="Bogotá"):
    return VehicleClaim(
        tenant_id=tenant_id or uuid.uuid4(),
        tenant_name=tenant_name,
        tenant_city=tenant_city,
        order_id=uuid.uuid4(),
        status="in_progress",
        since=None,
    )


class _ScalarsResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class FakeNotificationSession:
    """Queues query results in the exact order `notify_claim_conflict`
    issues them: holding-taller query first, superadmin query second."""

    def __init__(self, holder_users=None, superadmin_users=None):
        self._queue = [list(holder_users or []), list(superadmin_users or [])]
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return _ScalarsResult(self._queue.pop(0))


def _compiled(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestRecipientFanOut:
    async def test_sends_one_message_per_holder_jefe_and_one_per_superadmin(self, monkeypatch):
        tenant_id = uuid.uuid4()
        holder = make_user(Role.jefe_taller, telegram_id="111", tenant_id=tenant_id)
        superadmin = make_user(Role.superadmin, telegram_id="333", tenant_id=None)

        db = FakeNotificationSession(holder_users=[holder], superadmin_users=[superadmin])
        sent = []

        async def _spy(chat_id, text):
            sent.append(chat_id)

        monkeypatch.setattr(svc, "_send_telegram_message", _spy)

        await svc.notify_claim_conflict(
            db, make_claim(tenant_id=tenant_id), "ABC123", SimpleNamespace(name="Taller B", ciudad="Cali")
        )

        assert sent == ["111", "333"]

    async def test_technician_is_never_a_recipient(self, monkeypatch):
        """The holding-taller query itself excludes `technician` (role ==
        jefe_taller only) -- asserted here at the compiled-SQL level so a
        future edit widening the role filter fails loudly."""
        tenant_id = uuid.uuid4()
        db = FakeNotificationSession(holder_users=[], superadmin_users=[])
        monkeypatch.setattr(svc, "_send_telegram_message", lambda *a, **k: None)

        await svc.notify_claim_conflict(
            db, make_claim(tenant_id=tenant_id), "ABC123", SimpleNamespace(name="Taller B", ciudad="Cali")
        )

        holder_sql = _compiled(db.executed_statements[0])
        assert "'jefe_taller'" in holder_sql
        assert "'technician'" not in holder_sql


class TestQueryShapesMatchExistingSuperadminPredicate:
    async def test_holder_query_scopes_by_tenant_role_status_and_telegram_id(self):
        tenant_id = uuid.uuid4()
        db = FakeNotificationSession(holder_users=[], superadmin_users=[])

        await svc.notify_claim_conflict(
            db, make_claim(tenant_id=tenant_id), "ABC123", SimpleNamespace(name="Taller B", ciudad="Cali")
        )

        holder_sql = _compiled(db.executed_statements[0])
        assert tenant_id.hex in holder_sql.replace("-", "")
        assert "'active'" in holder_sql
        assert "telegram_id IS NOT NULL" in holder_sql

    async def test_superadmin_query_matches_users_endpoint_predicate(self):
        db = FakeNotificationSession(holder_users=[], superadmin_users=[])

        await svc.notify_claim_conflict(
            db, make_claim(), "ABC123", SimpleNamespace(name="Taller B", ciudad="Cali")
        )

        admin_sql = _compiled(db.executed_statements[1])
        assert "'superadmin'" in admin_sql
        assert "'active'" in admin_sql
        assert "telegram_id IS NOT NULL" in admin_sql


class TestSendTelegramMessage:
    async def test_uses_an_explicit_3_second_timeout_and_the_configured_token(self, monkeypatch):
        captured = {}

        class _FakeResponse:
            def raise_for_status(self):
                pass

        class _FakeAsyncClient:
            def __init__(self, timeout=None):
                captured["timeout"] = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc_info):
                return False

            async def post(self, url, json=None):
                captured["url"] = url
                captured["json"] = json
                return _FakeResponse()

        monkeypatch.setattr(svc.httpx, "AsyncClient", _FakeAsyncClient)
        monkeypatch.setattr(svc.settings, "TELEGRAM_BOT_TOKEN", "test-token-123")

        await svc._send_telegram_message("555", "hola")

        assert captured["timeout"] == 3.0
        assert captured["url"] == "https://api.telegram.org/bottest-token-123/sendMessage"
        assert captured["json"] == {"chat_id": "555", "text": "hola"}


class TestNotificationFailureNeverPropagates:
    async def test_one_recipient_failing_does_not_stop_the_others_or_raise(self, monkeypatch):
        tenant_id = uuid.uuid4()
        holder = make_user(Role.jefe_taller, telegram_id="111", tenant_id=tenant_id)
        superadmin = make_user(Role.superadmin, telegram_id="222", tenant_id=None)
        db = FakeNotificationSession(holder_users=[holder], superadmin_users=[superadmin])

        attempted = []

        async def _flaky(chat_id, text):
            attempted.append(chat_id)
            if chat_id == "111":
                raise httpx.TimeoutException("boom")

        monkeypatch.setattr(svc, "_send_telegram_message", _flaky)

        # Must not raise.
        await svc.notify_claim_conflict(
            db, make_claim(tenant_id=tenant_id), "ABC123", SimpleNamespace(name="Taller B", ciudad="Cali")
        )

        assert attempted == ["111", "222"]

    async def test_recipient_resolution_failure_also_never_raises(self):
        class _ExplodingSession:
            async def execute(self, stmt):
                raise RuntimeError("db exploded")

        # Must not raise.
        await svc.notify_claim_conflict(
            _ExplodingSession(), make_claim(), "ABC123", SimpleNamespace(name="Taller B", ciudad="Cali")
        )


class TestTokenNeverLeaksOnFailure:
    async def test_bot_token_never_appears_in_log_output_on_send_failure(self, monkeypatch, caplog):
        import logging

        monkeypatch.setattr(svc.settings, "TELEGRAM_BOT_TOKEN", "super-secret-token-xyz")
        tenant_id = uuid.uuid4()
        holder = make_user(Role.jefe_taller, telegram_id="111", tenant_id=tenant_id)
        db = FakeNotificationSession(holder_users=[holder], superadmin_users=[])

        async def _always_raise(chat_id, text):
            # Mirrors the real leak vector: httpx's own exception message
            # embeds the full request URL, which contains the token.
            raise httpx.ConnectError(
                f"Connection failed for url 'https://api.telegram.org/"
                f"bot{svc.settings.TELEGRAM_BOT_TOKEN}/sendMessage'"
            )

        monkeypatch.setattr(svc, "_send_telegram_message", _always_raise)
        caplog.set_level(logging.ERROR, logger=svc.logger.name)

        await svc.notify_claim_conflict(
            db, make_claim(tenant_id=tenant_id), "ABC123", SimpleNamespace(name="Taller B", ciudad="Cali")
        )

        assert "super-secret-token-xyz" not in caplog.text

    async def test_message_body_carries_no_client_or_order_pii(self):
        message = svc._conflict_message(
            "ABC123", make_claim(tenant_name="Taller A", tenant_city="Bogotá"),
            SimpleNamespace(name="Taller B", ciudad="Cali"),
        )
        assert "ABC123" in message
        assert "Taller A" in message
        assert "Taller B" in message
        # No client/order identifiers exist at this point in the flow
        # (pre-emptive block, before any order/client row is created) --
        # this just pins that the message never grew one by accident.
        for forbidden in ("phone", "client_id", "order_id", "cliente"):
            assert forbidden not in message.lower()


# sdd/reception-email-notification Phase 4: `notify_reception_email_failure`
# reuses `_get_holding_tenant_telegram_ids`/`_get_superadmin_telegram_ids`
# and `_send_telegram_message` exactly as `notify_claim_conflict` does above
# -- same fan-out, same per-recipient isolation, same recipient-resolution
# failure handling. Only the message shape (BR9: order id, plate, taller --
# never recipient address, credentials, or PDF URL) differs.
class TestNotifyReceptionEmailFailureRecipients:
    async def test_alert_reaches_taller_jefe_and_every_superadmin(self, monkeypatch):
        tenant_id = uuid.uuid4()
        jefe = make_user(Role.jefe_taller, telegram_id="111", tenant_id=tenant_id)
        superadmin = make_user(Role.superadmin, telegram_id="333", tenant_id=None)
        db = FakeNotificationSession(holder_users=[jefe], superadmin_users=[superadmin])

        sent = []

        async def _spy(chat_id, text):
            sent.append(chat_id)

        monkeypatch.setattr(svc, "_send_telegram_message", _spy)

        await svc.notify_reception_email_failure(
            db, order_id="order-1", plate="ABC123", tenant_id=tenant_id, tenant_name="Taller B"
        )

        assert sent == ["111", "333"]

    async def test_no_active_jefe_taller_still_alerts_superadmins(self, monkeypatch):
        tenant_id = uuid.uuid4()
        superadmin = make_user(Role.superadmin, telegram_id="333", tenant_id=None)
        db = FakeNotificationSession(holder_users=[], superadmin_users=[superadmin])

        sent = []

        async def _spy(chat_id, text):
            sent.append(chat_id)

        monkeypatch.setattr(svc, "_send_telegram_message", _spy)

        # Must not raise even with zero jefe_taller recipients.
        await svc.notify_reception_email_failure(
            db, order_id="order-1", plate="ABC123", tenant_id=tenant_id, tenant_name="Taller B"
        )

        assert sent == ["333"]


class TestNotifyReceptionEmailFailureNeverPropagates:
    async def test_one_recipient_failing_does_not_stop_the_others_or_raise(self, monkeypatch):
        tenant_id = uuid.uuid4()
        jefe = make_user(Role.jefe_taller, telegram_id="111", tenant_id=tenant_id)
        superadmin = make_user(Role.superadmin, telegram_id="222", tenant_id=None)
        db = FakeNotificationSession(holder_users=[jefe], superadmin_users=[superadmin])

        attempted = []

        async def _flaky(chat_id, text):
            attempted.append(chat_id)
            if chat_id == "111":
                raise httpx.TimeoutException("boom")

        monkeypatch.setattr(svc, "_send_telegram_message", _flaky)

        # Must not raise.
        await svc.notify_reception_email_failure(
            db, order_id="order-1", plate="ABC123", tenant_id=tenant_id, tenant_name="Taller B"
        )

        assert attempted == ["111", "222"]

    async def test_recipient_resolution_failure_returns_quietly(self):
        class _ExplodingSession:
            async def execute(self, stmt):
                raise RuntimeError("db exploded")

        # Must not raise.
        await svc.notify_reception_email_failure(
            _ExplodingSession(), order_id="order-1", plate="ABC123", tenant_id=uuid.uuid4(), tenant_name="Taller B"
        )


class TestNotifyReceptionEmailFailureMessageContent:
    def test_message_contains_order_plate_taller_and_nothing_sensitive(self):
        message = svc._email_failure_message(
            order_id="order-1", plate="ABC123", tenant_name="Taller B"
        )

        assert "order-1" in message
        assert "ABC123" in message
        assert "Taller B" in message

        # BR9: no recipient address, no presigned PDF URL, no credential.
        for forbidden in ("@", "http://", "https://", "password", "token", "secret"):
            assert forbidden not in message.lower()

    async def test_fired_alert_payload_carries_no_sensitive_data(self, monkeypatch):
        tenant_id = uuid.uuid4()
        jefe = make_user(Role.jefe_taller, telegram_id="111", tenant_id=tenant_id)
        db = FakeNotificationSession(holder_users=[jefe], superadmin_users=[])

        captured = {}

        async def _spy(chat_id, text):
            captured["text"] = text

        monkeypatch.setattr(svc, "_send_telegram_message", _spy)

        await svc.notify_reception_email_failure(
            db, order_id="order-1", plate="ABC123", tenant_id=tenant_id, tenant_name="Taller B"
        )

        text = captured["text"].lower()
        for forbidden in ("@", "http://", "https://", "password", "token", "secret"):
            assert forbidden not in text
