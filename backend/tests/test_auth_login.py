"""
tests/test_auth_login.py — `POST /api/v1/auth/login` (`login_for_access_token`).

Regression coverage for a production incident: `users.email` has no
uniqueness constraint (by design -- a person can legitimately be both a
`client` and a `parts_dealer`/distribuidor, registered as two separate
`User` rows sharing the same email: they became a client first, then
separately registered as a distributor). The endpoint used to fetch the
match with `scalar_one_or_none()`, which raises
`sqlalchemy.exc.MultipleResultsFound` (surfaced as an unhandled 500)
whenever 2+ rows share an email -- locking the affected user out of login
entirely, before any password check even runs.

Business rule (explicit, verbatim from the owner): "si es distribuidor y es
cliente siempre para login prima como distribuidor, no tiene que verificar
cliente" -- whenever a `parts_dealer` row exists among the email's matches,
login ALWAYS uses that row exclusively; no other row (nor its password) is
even considered.
"""
import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import MultipleResultsFound

from app.core.limiter import limiter
from app.core.security import get_password_hash
from app.database import get_db
from app.main import app
from app.models.user import Role, User, UserStatus

LOGIN_URL = "/api/v1/auth/login"


class _FakeLoginResult:
    """Mimics the subset of SQLAlchemy's `Result` the endpoint uses --
    including `scalar_one_or_none()`'s real `MultipleResultsFound` behavior
    for 2+ rows, so pre-fix runs of these tests reproduce the actual
    production crash instead of a stand-in failure."""

    def __init__(self, users):
        self._users = list(users)

    def scalar_one_or_none(self):
        if not self._users:
            return None
        if len(self._users) == 1:
            return self._users[0]
        raise MultipleResultsFound(
            "Multiple rows were found when exactly one was required"
        )

    def scalars(self):
        return self

    def all(self):
        return self._users


class FakeLoginDbSession:
    """Minimal fake session -- only the endpoint's `select(User)...` query
    is exercised here (every test user below has `tenant_id=None`, so
    `_build_token_and_user` never issues its own `tenant_name` query)."""

    def __init__(self, users):
        self._users = users
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return _FakeLoginResult(self._users)


@contextmanager
def _client_for(users):
    fake_db = FakeLoginDbSession(users)

    async def _override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """`/login` is rate-limited (10/minute per IP) and every test in this
    module hits it from the same `TestClient` host -- reset the in-memory
    limiter state between tests so they stay independent of each other and
    of any other test module's calls to this endpoint."""
    limiter.reset()
    yield


def _make_user(
    role,
    email="ana@example.com",
    password="secret123",
    status_=UserStatus.active,
    user_id=None,
):
    return User(
        id=user_id or uuid.uuid4(),
        name="Ana Pérez",
        email=email,
        role=role,
        status=status_,
        hashed_password=get_password_hash(password),
        tenant_id=None,
    )


class TestLoginDualRolePartsDealerPriority:
    """The core fix: a `parts_dealer` row sharing an email with any other
    row is always authoritative for login."""

    def test_dual_role_same_password_logs_in_as_parts_dealer(self):
        client_row = _make_user(Role.client, password="shared-pass")
        dealer_row = _make_user(Role.parts_dealer, password="shared-pass")

        with _client_for([client_row, dealer_row]) as client:
            resp = client.post(
                LOGIN_URL,
                json={"email": "ana@example.com", "password": "shared-pass"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["role"] == "parts_dealer"
        assert body["user"]["id"] == str(dealer_row.id)

    def test_dual_role_password_matching_only_client_row_fails_401(self):
        """The submitted password matches the CLIENT row's hash but not the
        DEALER row's. Per the explicit business rule, login must never fall
        through to check the client row's password -- it must fail."""
        client_row = _make_user(Role.client, password="client-only-pass")
        dealer_row = _make_user(Role.parts_dealer, password="dealer-only-pass")

        with _client_for([client_row, dealer_row]) as client:
            resp = client.post(
                LOGIN_URL,
                json={"email": "ana@example.com", "password": "client-only-pass"},
            )

        assert resp.status_code == 401
        assert "access_token" not in resp.json()


class TestLoginSingleRowUnchanged:
    def test_single_row_normal_login_still_works(self):
        row = _make_user(Role.client, password="mypassword")

        with _client_for([row]) as client:
            resp = client.post(
                LOGIN_URL,
                json={"email": "ana@example.com", "password": "mypassword"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["role"] == "client"
        assert body["user"]["id"] == str(row.id)


class TestLoginZeroRowsUnchanged:
    def test_zero_matching_rows_returns_401_credenciales_incorrectas(self):
        with _client_for([]) as client:
            resp = client.post(
                LOGIN_URL,
                json={"email": "nadie@example.com", "password": "whatever"},
            )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Credenciales incorrectas"


class TestLoginDefensiveMultiRowNoDealer:
    """No known real-world case, but must not crash: 2+ rows share an email
    and none is `parts_dealer`."""

    def test_two_non_dealer_rows_no_crash_uses_the_row_whose_password_matches(self):
        row_a = _make_user(Role.client, password="pass-a")
        row_b = _make_user(Role.client, password="pass-b")

        with _client_for([row_a, row_b]) as client:
            resp = client.post(
                LOGIN_URL,
                json={"email": "ana@example.com", "password": "pass-b"},
            )

        assert resp.status_code == 200
        assert resp.json()["user"]["id"] == str(row_b.id)
