"""
app/services/reception_email_dispatch.py

sdd/reception-email-notification Phase 5 (design ADR 2, ADR 3). The
FastAPI `BackgroundTasks` entrypoint / saga for reception-PDF email
delivery: fetch bytes -> send -> alert-on-failure only.

ADR 2 -- FastAPI runs `BackgroundTasks` AFTER the response, when the
request's `db` session (opened via `get_db`) is already closed. Passing
that closed session into a background task raises `MissingGreenlet` the
moment it's touched. This function therefore receives PLAIN SCALARS ONLY
(`order_id`, `plate`, `tenant_id`, `recipient`, `client_name`, `pdf_url`)
-- never `db`, never an ORM object -- and opens its OWN session via
`async_session_maker` (`app/database.py`), and ONLY on the failure path,
to resolve `tenant_name` for the Telegram alert. The success/skip paths
never touch the database, so the 99% happy-path case wastes no
connection.

ADR 3 -- this module is the only thing that imports both `pdf_service`
and `notification_service`. `email_service.py` stays pure SMTP transport
with zero DB/Telegram knowledge, and `pdf_service`/`notification_service`
stay ignorant of each other -- keeping the unit-test seam for each
narrow.

Never raises (BR6/BR8): every failure mode here -- an unexpected error
from the fetch/send step, or the failure-alert step itself blowing up --
is caught and logged (exception TYPE only, matching the leak-avoidance
convention already established in `email_service`/`notification_
service`), so a broken mailbox or a broken Telegram bot can never
surface as a failed `POST /orders/`.
"""
import logging
from typing import Optional

from app.database import async_session_maker
from app.models.tenant import Tenant
from app.services import email_service, pdf_service
from app.services.notification_service import notify_reception_email_failure

logger = logging.getLogger(__name__)


async def dispatch_reception_email(
    *,
    order_id: str,
    plate: str,
    tenant_id,
    recipient: Optional[str],
    client_name: str,
    pdf_url: str,
) -> None:
    """FastAPI `BackgroundTasks` entrypoint for one reception's PDF email.

    Flow: `pdf_service.fetch_reception_pdf_bytes` -> `email_service.
    send_reception_pdf_email` -> on `"failed"` only, open a session and
    call `notify_reception_email_failure` (BR7). `"skipped"` (kill-switch
    off, no recipient, or unfetchable/missing PDF bytes -- BR5) and
    `"sent"` both end here with no alert and no DB session opened. Never
    raises.
    """
    try:
        pdf_bytes = pdf_service.fetch_reception_pdf_bytes(pdf_url)
        result = await email_service.send_reception_pdf_email(
            recipient=recipient, client_name=client_name, plate=plate, pdf_bytes=pdf_bytes
        )
    except Exception as exc:
        # Defensive only -- `fetch_reception_pdf_bytes` and
        # `send_reception_pdf_email` are both documented to never raise on
        # their own. This guards the saga against a future regression in
        # either seam so it can never surface as an unhandled exception in
        # a background task.
        logger.error("dispatch_reception_email: unexpected failure (%s)", type(exc).__name__)
        result = "failed"

    if result != "failed":
        return

    try:
        async with async_session_maker() as db:
            tenant = await db.get(Tenant, tenant_id)
            tenant_name = tenant.name if tenant else None
            await notify_reception_email_failure(
                db,
                order_id=order_id,
                plate=plate,
                tenant_id=tenant_id,
                tenant_name=tenant_name,
            )
    except Exception as exc:
        # `notify_reception_email_failure` already never raises on its own
        # (BR8) -- this is the outer safety net for the session open/get
        # itself, so a failed alert can never become a failed reception.
        logger.error("dispatch_reception_email: failure alert itself failed (%s)", type(exc).__name__)
