"""
Inventory counts -- the secrets that let a pair join a count
(odd/motored-conteos-inventario, WU5; design ADR-7, §8.1).

- The link slug goes in `/motored/c/{slug}` (QR and copy-paste). It is 16
  URL-safe characters (96 bits, `secrets.token_urlsafe(12)`): the most the
  `conteo.enlace_slug` column (String(16)) holds. Joining also needs the
  6-digit code, so the slug alone never opens a count.
- The 6-digit code is shown once, when it is generated or rotated. Only
  `HMAC-SHA256(MOTORED_SECRET_KEY, "<conteo_id>:<code>")` is stored, and
  the check uses `hmac.compare_digest`.
- Rotating the code never touches connected pairs: their device sessions
  have their own tokens.
- The public join URL is `<MOTORED_PUBLIC_URL>/motored/c/<slug>` (design
  §10.2); `qr_png` draws it server-side with `qrcode` (the code is never
  inside the QR).
"""
import hashlib
import hmac
import io
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

import qrcode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.models.conteo import ESTADOS_ABIERTOS, Conteo
from app.motored.services.conteos import errores

BYTES_SLUG = 12
BITS_SLUG = BYTES_SLUG * 8
LARGO_SLUG = 16
DIGITOS_CODIGO = 6
_CODIGO = re.compile(r"[0-9]{6}")
RUTA_PAREJA = "/motored/c/"


def nuevo_slug() -> str:
    """16 URL-safe characters with 96 bits of entropy."""
    return secrets.token_urlsafe(BYTES_SLUG)


def nuevo_codigo() -> str:
    """A uniform 6-digit code; leading zeros are kept."""
    return f"{secrets.randbelow(10 ** DIGITOS_CODIGO):06d}"


def hash_codigo(conteo_id: uuid.UUID, codigo: str) -> str:
    """Hex HMAC-SHA256 of the code, bound to its conteo."""
    mensaje = f"{conteo_id}:{codigo}".encode()
    clave = settings.MOTORED_SECRET_KEY.encode()
    return hmac.new(clave, mensaje, hashlib.sha256).hexdigest()


def verificar_codigo(
        conteo_id: uuid.UUID, codigo: Optional[str],
        codigo_hash: Optional[str]) -> bool:
    """True only for the right 6-digit code of this conteo."""
    limpio = codigo.strip() if isinstance(codigo, str) else ""
    if not codigo_hash or not _CODIGO.fullmatch(limpio):
        return False
    return hmac.compare_digest(
        hash_codigo(conteo_id, limpio), codigo_hash)


async def bloquear_conteo(db: AsyncSession, conteo_id: uuid.UUID) -> Conteo:
    """The conteo row under `SELECT ... FOR UPDATE`, or ConteoNoEncontrado.
    Every state change re-reads the estado after taking this lock."""
    conteo = await db.scalar(
        select(Conteo).where(Conteo.id == conteo_id).with_for_update()
        .execution_options(populate_existing=True))
    if conteo is None:
        raise errores.ConteoNoEncontrado()
    return conteo


def asignar_codigo(conteo: Conteo, ahora: datetime) -> str:
    """Stores the hash of a new code on `conteo`; returns the plain code
    (the only time it exists)."""
    codigo = nuevo_codigo()
    conteo.codigo_hash = hash_codigo(conteo.id, codigo)
    conteo.codigo_rotado_en = ahora
    return codigo


async def rotar_codigo(
        db: AsyncSession, conteo_id: uuid.UUID,
        ahora: Optional[datetime] = None) -> str:
    """A new code for an open conteo; the old one stops working at once.
    Returns the plain code. Does not commit."""
    conteo = await bloquear_conteo(db, conteo_id)
    if conteo.estado not in ESTADOS_ABIERTOS:
        raise errores.EstadoInvalido(
            "Solo se puede cambiar el código de un conteo en curso.",
            estado=conteo.estado)
    codigo = asignar_codigo(conteo, ahora or datetime.now(timezone.utc))
    await db.flush()
    return codigo


def url_publica(slug: str) -> str:
    """The pair's join URL; EnlaceSinConfigurar without a public base."""
    base = (settings.MOTORED_PUBLIC_URL or "").strip().rstrip("/")
    if not base:
        raise errores.EnlaceSinConfigurar()
    return f"{base}{RUTA_PAREJA}{slug}"


def qr_png(texto: str) -> bytes:
    """A PNG QR code of `texto`."""
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(texto)
    qr.make(fit=True)
    salida = io.BytesIO()
    qr.make_image().save(salida)
    return salida.getvalue()
