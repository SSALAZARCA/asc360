"""
Phase 5 "Bot auth + core router" (sdd/motored-ventas-perdidas-bot, tasks
5.1-5.5; design D5) — unit coverage for `app/motored/deps_bot.py`: the bot
Lore's own auth mechanism, completely independent of `deps.py`'s JWT path.

`get_bot_actor`/`require_bot_asesor`/`require_bot_admin` are called
DIRECTLY as plain async functions here (no HTTP layer) -- the HTTP-layer
wiring (`GET /yo` etc.) is covered separately in `test_bot_api.py`, mirroring
the existing split between `test_solicitudes.py` (service-level) and
`test_usuarios_api.py` (HTTP-level).
"""
import uuid

import pytest
from fastapi import HTTPException

from app.config import settings
from app.motored.deps_bot import (
    BotActor,
    LORE_UNAVAILABLE_DETAIL,
    _require_bot_roles,
    get_bot_actor,
    get_bot_telegram_id,
    lore_bot_secret_is_safe,
    require_bot_admin,
    require_bot_asesor,
    require_bot_asesor_o_admin,
    require_lore_ready,
)
from app.motored.models.usuario import Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal
from tests.motored.conftest import FakeAsyncSession


@pytest.fixture(autouse=True)
def _secrets(monkeypatch):
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "sonia-secret")
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "asc360-secret")
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", "lore-secret-distinct")
    yield


def _asesor(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Juan Asesor", email=None, hashed_password=None,
        role="ASESOR_MOSTRADOR", activo=True, status="pending", telegram_id=555,
        phone="3001234567",
    )
    base.update(overrides)
    return Usuario(**base)


def _admin(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Ana Admin", email="ana@motoredcolombia.com.co",
        hashed_password="hash", role="ADMIN", activo=True, status="approved",
        telegram_id=444,
    )
    base.update(overrides)
    return Usuario(**base)


# ---------------------------------------------------------------------------
# 5.1 — lore_bot_secret_is_safe()
# ---------------------------------------------------------------------------

def test_lore_bot_secret_is_safe_false_when_empty(monkeypatch):
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", "")
    assert lore_bot_secret_is_safe() is False


def test_lore_bot_secret_is_safe_false_when_equal_to_sonia_secret(monkeypatch):
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", "sonia-secret")
    assert lore_bot_secret_is_safe() is False


def test_lore_bot_secret_is_safe_false_when_equal_to_motored_secret_key(monkeypatch):
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", "motored-secret")
    assert lore_bot_secret_is_safe() is False


def test_lore_bot_secret_is_safe_false_when_equal_to_asc360_secret_key(monkeypatch):
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", "asc360-secret")
    assert lore_bot_secret_is_safe() is False


def test_lore_bot_secret_is_safe_true_when_nonempty_and_distinct():
    assert lore_bot_secret_is_safe() is True


# ---------------------------------------------------------------------------
# 5.2/5.3 — require_lore_ready
# ---------------------------------------------------------------------------

async def test_require_lore_ready_raises_503_when_secret_unsafe(monkeypatch):
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", "")
    with pytest.raises(HTTPException) as exc_info:
        await require_lore_ready()
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == LORE_UNAVAILABLE_DETAIL


async def test_require_lore_ready_passes_silently_when_secret_safe():
    assert await require_lore_ready() is None


# ---------------------------------------------------------------------------
# 5.4 — get_bot_telegram_id
# ---------------------------------------------------------------------------

async def test_get_bot_telegram_id_wrong_secret_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await get_bot_telegram_id(x_lore_secret="wrong-secret", x_lore_telegram_id="123")
    assert exc_info.value.status_code == 401


async def test_get_bot_telegram_id_missing_secret_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await get_bot_telegram_id(x_lore_secret=None, x_lore_telegram_id="123")
    assert exc_info.value.status_code == 401


async def test_get_bot_telegram_id_malformed_id_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        await get_bot_telegram_id(x_lore_secret="lore-secret-distinct", x_lore_telegram_id="not-a-number")
    assert exc_info.value.status_code == 400


async def test_get_bot_telegram_id_valid_returns_int():
    resultado = await get_bot_telegram_id(x_lore_secret="lore-secret-distinct", x_lore_telegram_id="987654321")
    assert resultado == 987654321


# ---------------------------------------------------------------------------
# Post-review fix #3 — get_bot_telegram_id must never 500 on an out-of-range,
# negative, or zero telegram_id (BigInteger max is 9223372036854775807; a
# Python int() parse succeeds far beyond that, but the DB column cannot hold
# it, and a real Telegram user/chat id is always positive).
# ---------------------------------------------------------------------------

async def test_get_bot_telegram_id_larger_than_bigint_max_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        await get_bot_telegram_id(
            x_lore_secret="lore-secret-distinct", x_lore_telegram_id="9223372036854775808"
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {"code": "TELEGRAM_ID_INVALIDO"}


async def test_get_bot_telegram_id_negative_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        await get_bot_telegram_id(x_lore_secret="lore-secret-distinct", x_lore_telegram_id="-1")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {"code": "TELEGRAM_ID_INVALIDO"}


async def test_get_bot_telegram_id_zero_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        await get_bot_telegram_id(x_lore_secret="lore-secret-distinct", x_lore_telegram_id="0")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {"code": "TELEGRAM_ID_INVALIDO"}


async def test_get_bot_telegram_id_bigint_max_itself_is_valid():
    """Triangulation: the boundary value itself must still be ACCEPTED --
    proves the check is `> max`, not an overly aggressive `>= max`."""
    resultado = await get_bot_telegram_id(
        x_lore_secret="lore-secret-distinct", x_lore_telegram_id="9223372036854775807"
    )
    assert resultado == 9223372036854775807


# ---------------------------------------------------------------------------
# 5.4/5.5 — get_bot_actor
# ---------------------------------------------------------------------------

async def test_get_bot_actor_returns_none_when_no_matching_usuario():
    db = FakeAsyncSession(execute_queue=[[]])
    resultado = await get_bot_actor(telegram_id=999, db=db)
    assert resultado is None


async def test_get_bot_actor_returns_botactor_with_sucursal_ids_when_found():
    sucursal_id = uuid.uuid4()
    usuario = _asesor(telegram_id=555)
    usuario.sucursales = [UsuarioSucursal(id=uuid.uuid4(), usuario_id=usuario.id, sucursal_id=sucursal_id)]
    db = FakeAsyncSession(execute_queue=[[usuario]])

    resultado = await get_bot_actor(telegram_id=555, db=db)

    assert isinstance(resultado, BotActor)
    assert resultado.usuario_id == str(usuario.id)
    assert resultado.nombre == "Juan Asesor"
    assert resultado.role == "ASESOR_MOSTRADOR"
    assert resultado.status == "pending"
    assert resultado.telegram_id == 555
    assert resultado.sucursal_ids == [str(sucursal_id)]


async def test_get_bot_actor_falls_back_to_approved_when_status_is_none():
    """Mirrors `obtener_usuario_motored`'s own established fallback: a
    hand-built `Usuario(...)` test fixture with no `status=` kwarg has
    `status is None` at the Python level, not the DB's real
    `server_default`."""
    usuario = _admin(telegram_id=444, status=None)
    usuario.sucursales = []
    db = FakeAsyncSession(execute_queue=[[usuario]])

    resultado = await get_bot_actor(telegram_id=444, db=db)

    assert resultado.status == "approved"


# ---------------------------------------------------------------------------
# 5.5 — require_bot_asesor
# ---------------------------------------------------------------------------

async def test_require_bot_asesor_raises_403_no_registrado_when_actor_none():
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_asesor(actor=None)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {"code": "NO_REGISTRADO"}


async def test_require_bot_asesor_raises_403_no_registrado_when_wrong_role():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Ana", role="ADMIN", status="approved", activo=True, telegram_id=1)
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_asesor(actor=actor)
    assert exc_info.value.detail == {"code": "NO_REGISTRADO"}


async def test_require_bot_asesor_raises_403_pendiente_when_status_pending():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Juan", role="ASESOR_MOSTRADOR", status="pending", activo=True, telegram_id=1)
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_asesor(actor=actor)
    assert exc_info.value.detail == {"code": "PENDIENTE"}


async def test_require_bot_asesor_raises_403_rechazado_when_status_rejected():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Juan", role="ASESOR_MOSTRADOR", status="rejected", activo=True, telegram_id=1)
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_asesor(actor=actor)
    assert exc_info.value.detail == {"code": "RECHAZADO"}


async def test_require_bot_asesor_raises_403_inactivo_when_not_activo():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Juan", role="ASESOR_MOSTRADOR", status="approved", activo=False, telegram_id=1)
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_asesor(actor=actor)
    assert exc_info.value.detail == {"code": "INACTIVO"}


async def test_require_bot_asesor_returns_actor_when_all_checks_pass():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Juan", role="ASESOR_MOSTRADOR", status="approved", activo=True, telegram_id=1)
    assert await require_bot_asesor(actor=actor) is actor


# ---------------------------------------------------------------------------
# 5.5 — require_bot_admin
# ---------------------------------------------------------------------------

async def test_require_bot_admin_raises_403_no_registrado_when_role_is_asesor():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Juan", role="ASESOR_MOSTRADOR", status="approved", activo=True, telegram_id=1)
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_admin(actor=actor)
    assert exc_info.value.detail == {"code": "NO_REGISTRADO"}


async def test_require_bot_admin_returns_actor_when_role_admin_and_approved():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Ana", role="ADMIN", status="approved", activo=True, telegram_id=444)
    assert await require_bot_admin(actor=actor) is actor


# ---------------------------------------------------------------------------
# require_bot_asesor_o_admin — ad-hoc addition (post-Phase-10, product-owner
# request): an ADMIN must be able to reach the same bot-facing demanda-perdida
# surface as an ASESOR_MOSTRADOR, without loosening the role gate for anyone
# else. Same 4-check cascade (existence, role, status, activo) as
# `require_bot_asesor`/`require_bot_admin`, just matched against EITHER role.
# ---------------------------------------------------------------------------


async def test_require_bot_asesor_o_admin_raises_403_no_registrado_when_actor_none():
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_asesor_o_admin(actor=None)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {"code": "NO_REGISTRADO"}


async def test_require_bot_asesor_o_admin_raises_403_no_registrado_when_role_is_neither():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Compras", role="COMPRAS", status="approved", activo=True, telegram_id=1)
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_asesor_o_admin(actor=actor)
    assert exc_info.value.detail == {"code": "NO_REGISTRADO"}


async def test_require_bot_asesor_o_admin_raises_403_pendiente_when_status_pending():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Ana", role="ADMIN", status="pending", activo=True, telegram_id=444)
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_asesor_o_admin(actor=actor)
    assert exc_info.value.detail == {"code": "PENDIENTE"}


async def test_require_bot_asesor_o_admin_raises_403_rechazado_when_status_rejected():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Juan", role="ASESOR_MOSTRADOR", status="rejected", activo=True, telegram_id=1)
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_asesor_o_admin(actor=actor)
    assert exc_info.value.detail == {"code": "RECHAZADO"}


async def test_require_bot_asesor_o_admin_raises_403_inactivo_when_not_activo():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Ana", role="ADMIN", status="approved", activo=False, telegram_id=444)
    with pytest.raises(HTTPException) as exc_info:
        await require_bot_asesor_o_admin(actor=actor)
    assert exc_info.value.detail == {"code": "INACTIVO"}


async def test_require_bot_asesor_o_admin_returns_actor_when_role_asesor_and_approved():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Juan", role="ASESOR_MOSTRADOR", status="approved", activo=True, telegram_id=1)
    assert await require_bot_asesor_o_admin(actor=actor) is actor


async def test_require_bot_asesor_o_admin_returns_actor_when_role_admin_and_approved():
    actor = BotActor(usuario_id=str(uuid.uuid4()), nombre="Ana", role="ADMIN", status="approved", activo=True, telegram_id=444)
    assert await require_bot_asesor_o_admin(actor=actor) is actor


# ---------------------------------------------------------------------------
# Fix-up finding #3 (SUGGESTION, resilience) — `_require_bot_roles` must fail
# LOUDLY at factory-definition time when called with an empty roles tuple,
# instead of silently locking out every caller with a misleading
# NO_REGISTRADO 403 at request time.
# ---------------------------------------------------------------------------


def test_require_bot_roles_empty_tuple_raises_value_error():
    with pytest.raises(ValueError):
        _require_bot_roles(())
