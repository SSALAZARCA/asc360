"""
app/services/email_service.py

sdd/reception-email-notification Phase 2. Pure SMTP transport for the
reception PDF email attachment -- no DB, no Telegram, no MinIO. Mirrors
`notification_service.py`'s established contract for best-effort,
credential-safe outbound sends:
  - Credentials come ONLY from `app.config.settings` (env-backed). Never
    hardcoded, never logged.
  - Every send carries an explicit, finite timeout (`SMTP_TIMEOUT`).
  - TLS is always enforced -- either STARTTLS (`SMTP_STARTTLS=True`,
    typically port 587) or implicit TLS (`SMTP_STARTTLS=False`,
    typically port 465). Exactly one of `start_tls`/`use_tls` is passed
    as `True` on every call.
  - This function never raises. Any failure (connect, auth, transport)
    is caught HERE and logged with the exception's TYPE NAME only --
    never the raw exception, credentials, or recipient address, since
    SMTP exception messages can embed the mailbox address/password used
    to authenticate (same leak vector `notification_service.py`
    documents for the Telegram bot token).
  - `"skipped"` covers the kill-switch (`RECEPTION_EMAIL_ENABLED=False`,
    ADR 5 -- checked HERE, not by callers) and missing inputs
    (no recipient / no PDF bytes). Callers must NOT alert on
    `"skipped"` -- only on `"failed"` (BR5 vs BR7).
  - Client-supplied values reaching a header (plate, client name) are
    passed through `_sanitize_header` first: CR/LF/NUL stripped so a
    crafted plate/name can never inject extra SMTP headers (RFC 5322
    header injection).
"""
import logging
import re
from email.message import EmailMessage
from typing import Literal, Optional

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)

# Explicit, finite timeout for the outbound SMTP connection -- aiosmtplib's
# own default (60s) is too long to trust on a background task that should
# fail fast and let the failure-alert path take over.
SMTP_TIMEOUT = 10.0

SendResult = Literal["sent", "skipped", "failed"]

_HEADER_STRIP_RE = re.compile(r"[\r\n\x00]")
_WHITESPACE_RE = re.compile(r"\s+")


def _sanitize_header(value: str, max_len: int = 120) -> str:
    """Strip CR/LF/NUL (RFC 5322 header injection), collapse remaining
    whitespace, and truncate. Every client-supplied value reaching an
    email header or the subject line goes through this."""
    if not value:
        return ""
    stripped = _HEADER_STRIP_RE.sub("", value)
    collapsed = _WHITESPACE_RE.sub(" ", stripped).strip()
    return collapsed[:max_len]


def _build_message(*, recipient: str, client_name: str, plate: str, pdf_bytes: bytes) -> EmailMessage:
    safe_plate = _sanitize_header(plate)
    safe_name = _sanitize_header(client_name) or "cliente"

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = recipient
    message["Subject"] = f"Comprobante de recepción — {safe_plate}"
    message.set_content(
        f"Hola {safe_name},\n\nAcá está tu comprobante de recepción, adjunto en PDF."
    )
    message.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=f"recepcion_{safe_plate}.pdf",
    )
    return message


async def send_reception_pdf_email(
    *,
    recipient: Optional[str],
    client_name: str,
    plate: str,
    pdf_bytes: Optional[bytes],
) -> SendResult:
    """Never raises.

    `"skipped"` => kill-switch off, no recipient, or no PDF bytes. Not a
    failure -- callers must not alert on it (BR5).
    `"failed"` => transport error. Callers must alert
    (`notification_service.notify_reception_email_failure`, BR7).
    """
    if not settings.RECEPTION_EMAIL_ENABLED:
        return "skipped"
    if not recipient or not pdf_bytes:
        return "skipped"

    try:
        message = _build_message(
            recipient=recipient, client_name=client_name, plate=plate, pdf_bytes=pdf_bytes
        )
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_STARTTLS,
            use_tls=not settings.SMTP_STARTTLS,
            timeout=SMTP_TIMEOUT,
        )
        return "sent"
    except Exception as exc:
        logger.error(
            "send_reception_pdf_email: send failed (%s)",
            type(exc).__name__,
        )
        return "failed"
