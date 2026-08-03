"""
Tests for `POST /users/` (`create_user`) client deduplication by `identification`.

Regression test for a user-reported bug: service reception (`frontend/app/tg/
reception/page.js`) creates a brand-new client `User` row every time a
vehicle's plate isn't already registered -- even when the same person (same
cedula) already exists as a client from a prior visit with a different
motorcycle. `create_user` only ever deduped on `telegram_id`, never on
`identification`/`phone`, so a returning client bringing a second bike (or a
mistyped/unmatched plate) got a duplicate client record every time.

Fix mirrors the existing, already-shipped pattern in
`distributor_delivery_service._lookup_or_create_client` (ADR 11): look up an
existing `role=client` row by `identification` before inserting. Pure async
unit tests using AsyncMock/MagicMock, matching this repo's established
pattern for endpoint tests (see `test_replace_catalog_code.py`).
"""
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.users import create_user
from app.models.user import Role, UserStatus
from app.schemas.user import UserCreate


def _admin_current_user() -> MagicMock:
    u = MagicMock()
    u.is_admin = True
    u.is_superadmin = True
    u.tenant_id = None
    return u


def _existing_client(identification: str = "123456789") -> MagicMock:
    client = MagicMock()
    client.id = "existing-client-id"
    client.role = Role.client
    client.identification = identification
    client.name = "Cliente Original"
    client.phone = "3000000000"
    return client


async def test_create_user_reuses_existing_client_by_identification():
    """A second 'isNew' reception submission for the same cedula must reuse
    the existing client, not insert a duplicate `User` row."""
    existing = _existing_client("123456789")

    db = AsyncMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=existing)
    db.execute = AsyncMock(return_value=execute_result)
    db.add = MagicMock()

    payload = UserCreate(
        name="Nombre Leído Por OCR",
        role=Role.client,
        identification="123456789",
    )

    result = await create_user(payload, db, None, _admin_current_user())

    assert result is existing
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


async def test_create_user_creates_new_client_when_identification_not_found():
    """A genuinely new cedula must still create a new client -- the fix only
    stops duplicate inserts, it must not stop new clients from being created."""
    db = AsyncMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=execute_result)

    added = []
    db.add = MagicMock(side_effect=lambda obj: added.append(obj))

    payload = UserCreate(
        name="Cliente Nuevo",
        role=Role.client,
        identification="987654321",
        phone="3011111111",
    )

    await create_user(payload, db, None, _admin_current_user())

    assert len(added) == 1
    new_user = added[0]
    assert new_user.identification == "987654321"
    assert new_user.phone == "3011111111"
    db.commit.assert_awaited_once()


async def test_create_user_without_identification_skips_identification_lookup():
    """Callers that don't send `identification` (every pre-existing caller)
    must keep working exactly as before -- no identification-based query,
    straight insert."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()  # must NOT be called: no telegram_id, no identification
    db.add = MagicMock()

    payload = UserCreate(name="Sin Cedula", role=Role.client, phone="3022222222")

    await create_user(payload, db, None, _admin_current_user())

    db.execute.assert_not_called()
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
