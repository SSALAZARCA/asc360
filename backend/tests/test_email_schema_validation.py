"""
tests/test_email_schema_validation.py -- RED/GREEN for
`sdd/reception-email-notification` Phase 1 (ADR 7): `ClientEditIn.email`
and `UserCreate.email` must reject a malformed address at capture time
(BR3), while still accepting a valid address or `None`/omitted.

`UserBase.email` is intentionally left untouched (ADR 7) -- tightening it
would retroactively 422 existing `UserOut` reads. Only `UserCreate` is
overridden.
"""
import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate
from app.schemas.vehicle import ClientEditIn


class TestClientEditInEmailValidation:
    def test_malformed_email_is_rejected(self):
        with pytest.raises(ValidationError):
            ClientEditIn(email="not-an-email")

    def test_valid_email_is_accepted(self):
        edit = ClientEditIn(email="cliente@example.com")
        assert edit.email == "cliente@example.com"

    def test_omitted_email_is_accepted(self):
        edit = ClientEditIn(name="Juan")
        assert edit.email is None

    def test_none_email_is_accepted(self):
        edit = ClientEditIn(email=None)
        assert edit.email is None


class TestUserCreateEmailValidation:
    def _base_kwargs(self, **overrides):
        kwargs = {"name": "Juan Perez", "role": "client"}
        kwargs.update(overrides)
        return kwargs

    def test_malformed_email_is_rejected(self):
        with pytest.raises(ValidationError):
            UserCreate(**self._base_kwargs(email="not-an-email"))

    def test_valid_email_is_accepted(self):
        user = UserCreate(**self._base_kwargs(email="cliente@example.com"))
        assert user.email == "cliente@example.com"

    def test_omitted_email_is_accepted(self):
        user = UserCreate(**self._base_kwargs())
        assert user.email is None

    def test_none_email_is_accepted(self):
        user = UserCreate(**self._base_kwargs(email=None))
        assert user.email is None
