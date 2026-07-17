"""
tests/test_settings_require_otp.py — `GET`/`PUT /settings/require-otp`.

Network-wide (not per-tenant) on/off switch for OTP-at-intake, backed by a
single `SystemConfig` row (key `require_otp`, value `"true"`/`"false"` as
text). Both endpoints are superadmin-only, mirroring the existing
`parts-similarity-threshold` pair in `app/api/v1/settings.py`.
"""
import uuid
from unittest.mock import MagicMock

from tests.conftest import make_test_client
from app.models.system_config import SystemConfig


def make_superadmin() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


def make_jefe_taller() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="jefe_taller", tenant_id=str(uuid.uuid4()), name="Jefe")


class FakeSettingsSession:
    """Minimal fake for the `require-otp` endpoints: a single `db.get(SystemConfig, key)`
    read, and on PUT either mutates the existing record or `db.add`s a new one."""

    def __init__(self, existing_value: str | None = None):
        self._record = SystemConfig(key="require_otp", value=existing_value) if existing_value is not None else None
        self.added: list = []
        self.committed = False

    async def get(self, model, pk):
        if model is SystemConfig and pk == "require_otp":
            return self._record
        return None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def test_get_require_otp_defaults_true_when_no_row():
    with make_test_client(make_superadmin(), FakeSettingsSession(existing_value=None)) as client:
        res = client.get("/api/v1/settings/require-otp")
        assert res.status_code == 200
        assert res.json() == {"require_otp": True}


def test_get_require_otp_reflects_saved_false():
    with make_test_client(make_superadmin(), FakeSettingsSession(existing_value="false")) as client:
        res = client.get("/api/v1/settings/require-otp")
        assert res.status_code == 200
        assert res.json() == {"require_otp": False}


def test_get_require_otp_forbidden_for_non_superadmin():
    with make_test_client(make_jefe_taller(), FakeSettingsSession(existing_value=None)) as client:
        res = client.get("/api/v1/settings/require-otp")
        assert res.status_code == 403


def test_put_require_otp_forbidden_for_non_superadmin():
    with make_test_client(make_jefe_taller(), FakeSettingsSession(existing_value=None)) as client:
        res = client.put("/api/v1/settings/require-otp", json={"require_otp": False})
        assert res.status_code == 403


def test_put_require_otp_creates_row_when_absent():
    session = FakeSettingsSession(existing_value=None)
    with make_test_client(make_superadmin(), session) as client:
        res = client.put("/api/v1/settings/require-otp", json={"require_otp": False})
        assert res.status_code == 200
        assert res.json() == {"require_otp": False}
        assert len(session.added) == 1
        assert session.added[0].key == "require_otp"
        assert session.added[0].value == "false"
        assert session.committed is True


def test_put_require_otp_updates_existing_row_true_to_false():
    session = FakeSettingsSession(existing_value="true")
    with make_test_client(make_superadmin(), session) as client:
        res = client.put("/api/v1/settings/require-otp", json={"require_otp": False})
        assert res.status_code == 200
        assert session._record.value == "false"
        assert session.added == []  # updated in place, not re-added


def test_put_require_otp_updates_existing_row_false_to_true():
    session = FakeSettingsSession(existing_value="false")
    with make_test_client(make_superadmin(), session) as client:
        res = client.put("/api/v1/settings/require-otp", json={"require_otp": True})
        assert res.status_code == 200
        assert res.json() == {"require_otp": True}
        assert session._record.value == "true"
