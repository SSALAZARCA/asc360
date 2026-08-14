"""
app/services/notification_service.py

sdd/vehicle-tenant-checkin-release PR3 (Design Decision 3) -- the backend's
FIRST-EVER direct call to the Telegram Bot API. Until now, only the
separate telegram-bot process (`telegram-bot/bot/handlers/registration.py`,
`_notify_superadmins`) talked to Telegram, via `python-telegram-bot`'s
`context.bot.send_message`. This module calls `httpx` directly instead,
because the conflict this notifies about originates in a synchronous
`POST /orders/` request from the Next.js mini-app -- the bot process is
never in that request path.

Security (explicit user requirement for this PR -- more than the usual
bar, see `sdd/vehicle-tenant-checkin-release/pr3-security-note`):
  - The bot token comes ONLY from `app.config.settings.TELEGRAM_BOT_TOKEN`
    (env-backed via `.env` / compose secrets). Never hardcoded.
  - Every outbound call carries an explicit, finite timeout -- never a
    default/infinite wait.
  - A Telegram failure (timeout, non-2xx, network error) is caught HERE,
    per recipient, and logged WITHOUT `exc_info`/`str(exception)` -- both
    httpx's own exception messages and `HTTPStatusError` embed the full
    request URL, which contains the bot token
    (`https://api.telegram.org/bot{token}/sendMessage`). Logging the
    exception object or its traceback would leak the token into the logs.
    Only the exception's TYPE NAME is logged, nothing else.
  - This function never raises. A failure here must never mask or reverse
    the conflict-block it accompanies (see `api/v1/orders.py`'s
    `create_service_order` and `services/historical_order_service.py`'s
    `_check_claim_conflict` -- the latter never even calls this module,
    see its own docstring).
  - Message bodies carry only the vehicle plate and taller name/city --
    never client name/phone/order id. On this path (a PRE-EMPTIVE block
    before any order or client row is created) there is no client/order
    data to leak even by accident.
"""
import logging
from typing import List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tenant import Tenant
from app.models.user import Role, User, UserStatus

logger = logging.getLogger(__name__)

# httpx's own request logger logs `"%s %s" % (method, request.url)` at INFO
# level -- for this module, request.url embeds the bot token
# (`https://api.telegram.org/bot{token}/sendMessage`). Nothing in this
# codebase currently raises the root/httpx logger above the Python default
# (WARNING), but that invariant lives outside this module and could regress
# silently (e.g. a future `logging.basicConfig(level=INFO)` in `main.py`).
# Pin it here so this module can never leak the token via httpx's logger,
# regardless of what the rest of the app does with logging configuration.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Explicit, finite timeout for every outbound call to Telegram -- a bare
# `httpx.AsyncClient()` defaults to a 5s connect/read/write/pool timeout,
# but that default is NOT guaranteed across httpx versions and must never
# be relied on for a call sitting inline in front of a 409 response a
# human is actively waiting on. Passing a single float applies it to all
# four timeout dimensions (connect/read/write/pool).
TELEGRAM_SEND_TIMEOUT = 3.0

TELEGRAM_API_BASE = "https://api.telegram.org"


async def _get_holding_tenant_telegram_ids(db: AsyncSession, tenant_id) -> List[str]:
    """`jefe_taller` only -- this is a management/ownership event, and the
    `technician` set per taller is unbounded (Design Decision 3)."""
    stmt = select(User).where(
        User.tenant_id == tenant_id,
        User.role == Role.jefe_taller,
        User.status == UserStatus.active,
        User.telegram_id.isnot(None),
    )
    result = await db.execute(stmt)
    return [u.telegram_id for u in result.scalars().all() if u.telegram_id]


async def _get_superadmin_telegram_ids(db: AsyncSession) -> List[str]:
    """Same predicate as `api/v1/endpoints/users.py`'s
    `get_superadmin_telegram_ids` (`role=superadmin, status=active,
    telegram_id IS NOT NULL`) -- factored into this one shared helper so
    the endpoint and this service can never drift apart."""
    stmt = select(User).where(
        User.role == Role.superadmin,
        User.status == UserStatus.active,
        User.telegram_id.isnot(None),
    )
    result = await db.execute(stmt)
    return [u.telegram_id for u in result.scalars().all() if u.telegram_id]


def _conflict_message(plate: str, claim, requesting_tenant: Optional[Tenant]) -> str:
    holder_name = claim.tenant_name or "otro taller"
    holder_city = claim.tenant_city or "ciudad no registrada"
    requester_name = requesting_tenant.name if requesting_tenant else "otro taller"
    requester_city = getattr(requesting_tenant, "ciudad", None) or "ciudad no registrada"
    return (
        "⚠️ Conflicto de reclamo de vehículo\n"
        f"Placa: {plate}\n"
        f"Taller que la tiene: {holder_name} ({holder_city})\n"
        f"Taller que intentó abrir una nueva orden: {requester_name} ({requester_city})"
    )


async def _send_telegram_message(chat_id: str, text: str) -> None:
    """One best-effort POST to Telegram's `sendMessage`. Any failure
    propagates to the caller (`notify_claim_conflict`), which is
    responsible for catching it per-recipient and logging it WITHOUT the
    exception object (see module docstring -- the URL/exception message
    can contain the bot token)."""
    token = settings.TELEGRAM_BOT_TOKEN
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=TELEGRAM_SEND_TIMEOUT) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()


async def notify_claim_conflict(
    db: AsyncSession,
    claim,
    plate: str,
    requesting_tenant: Optional[Tenant],
) -> None:
    """Best-effort dual notification for a blocked claim conflict: the
    holding taller's active `jefe_taller`(s), plus every active superadmin.

    Never raises. Every failure mode -- resolving recipients, or sending
    to any single recipient -- is caught and logged (type name only, no
    token, no full response body) so the caller's 409 is never masked or
    reversed by a Telegram outage."""
    try:
        holder_ids = await _get_holding_tenant_telegram_ids(db, claim.tenant_id)
        superadmin_ids = await _get_superadmin_telegram_ids(db)
    except Exception as exc:
        logger.error(
            "notify_claim_conflict: failed to resolve recipients (%s)",
            type(exc).__name__,
        )
        return

    message = _conflict_message(plate, claim, requesting_tenant)

    for chat_id in [*holder_ids, *superadmin_ids]:
        try:
            await _send_telegram_message(chat_id, message)
        except Exception as exc:
            logger.error(
                "notify_claim_conflict: telegram send failed (%s)",
                type(exc).__name__,
            )


def _email_failure_message(*, order_id, plate: str, tenant_name: Optional[str]) -> str:
    """sdd/reception-email-notification Phase 4 (BR9): order id, plate,
    and taller ONLY -- never the recipient address, credentials, or the
    presigned PDF URL. Same restriction applies to any log line for the
    failure (see `dispatch_reception_email`, which never logs the raw
    exception either)."""
    taller = tenant_name or "taller no identificado"
    return (
        "⚠️ No se pudo enviar el email de recepción\n"
        f"Orden: {order_id}\n"
        f"Placa: {plate}\n"
        f"Taller: {taller}"
    )


async def notify_reception_email_failure(
    db: AsyncSession,
    *,
    order_id,
    plate: str,
    tenant_id,
    tenant_name: Optional[str],
) -> None:
    """Best-effort Telegram alert for a failed reception-PDF email send
    (BR7): the order's taller active `jefe_taller`(s), plus every active
    superadmin -- same fan-out and per-recipient isolation as
    `notify_claim_conflict` above, reusing the same recipient-resolution
    helpers and send primitive as-is (design explicitly rejects
    refactoring `notify_claim_conflict` for this -- no test file covered
    it before this PR, and extracting shared logic for ~6 duplicated
    lines was judged unjustified risk under strict TDD).

    Never raises (BR8): a failure alert that itself fails must never
    become a failed order. Every failure mode -- resolving recipients,
    or sending to any single recipient -- is caught and logged (type
    name only, no PII, see `_email_failure_message`)."""
    try:
        holder_ids = await _get_holding_tenant_telegram_ids(db, tenant_id)
        superadmin_ids = await _get_superadmin_telegram_ids(db)
    except Exception as exc:
        logger.error(
            "notify_reception_email_failure: failed to resolve recipients (%s)",
            type(exc).__name__,
        )
        return

    message = _email_failure_message(order_id=order_id, plate=plate, tenant_name=tenant_name)

    for chat_id in [*holder_ids, *superadmin_ids]:
        try:
            await _send_telegram_message(chat_id, message)
        except Exception as exc:
            logger.error(
                "notify_reception_email_failure: telegram send failed (%s)",
                type(exc).__name__,
            )
