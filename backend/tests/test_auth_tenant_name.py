"""
tests/test_auth_tenant_name.py — `_build_token_and_user` must resolve and
include `tenant_name` in the login response, so the frontend can show a
tenant user's own store name read-only (distribuidor/entrega "Tienda"
field) without an extra permission-gated `GET /tenants/` call.
"""
import uuid

import pytest

from app.api.v1 import auth as auth_module
from app.models.user import Role, User, UserStatus


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeAuthSession:
    """Minimal fake session -- only `_build_token_and_user`'s single
    `select(Tenant.name)` query is exercised here."""

    def __init__(self, tenant_name=None):
        self._tenant_name = tenant_name
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return _ScalarResult(self._tenant_name)


def _make_user(tenant_id=None):
    return User(
        id=uuid.uuid4(),
        name="Ana Pérez",
        email="ana@example.com",
        role=Role.parts_dealer,
        status=UserStatus.active,
        tenant_id=tenant_id,
    )


class TestBuildTokenAndUserIncludesTenantName:
    async def test_user_with_tenant_id_gets_tenant_name_resolved(self):
        tenant_id = uuid.uuid4()
        user = _make_user(tenant_id=tenant_id)
        fake_db = FakeAuthSession(tenant_name="Moto Total S.A.S")

        result = await auth_module._build_token_and_user(user, fake_db)

        assert result["user"]["tenant_name"] == "Moto Total S.A.S"
        assert result["user"]["tenant_id"] == str(tenant_id)
        assert len(fake_db.executed_statements) == 1

    async def test_user_with_no_tenant_id_skips_the_query_and_gets_none(self):
        user = _make_user(tenant_id=None)
        fake_db = FakeAuthSession(tenant_name="Should never be read")

        result = await auth_module._build_token_and_user(user, fake_db)

        assert result["user"]["tenant_name"] is None
        assert result["user"]["tenant_id"] is None
        assert len(fake_db.executed_statements) == 0
