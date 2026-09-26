"""Vision-based reference extraction for lost-sale capture, Method B / photo
(design D6, tasks 11.1-11.5).

**PII firewall (load-bearing, do not weaken)**: the prompt below asks the
model for ONLY `{"referencias": [{"codigo": str, "nombre": str|null}]}` and
explicitly forbids customer names/IDs/phones/addresses/prices/quantities/
document numbers — but that wording is defense in depth, NOT the real
enforcement. `parsear_respuesta` is the actual firewall: it reads only the
`referencias` key, and from each item only `codigo`/`nombre`, building a
frozen `Candidato` dataclass that structurally has no field for anything
else. Even a model response that ignores the prompt entirely and injects
`cliente`/`cedula`/`telefono` keys can never propagate them past this
function.

**Client isolation (task 11.1)**: `AsyncOpenAI(api_key=config.LORE_OPENAI_API_KEY)`
— NEVER the no-arg constructor, which would silently fall back to reading
`OPENAI_API_KEY` from the environment (Sonia's own key, per
`telegram-bot/bot/services/ai.py::aclient = AsyncOpenAI()`). This mirrors
the same isolation invariant already enforced everywhere else in this
change (`LORE_BOT_SECRET` vs `SONIA_BOT_SECRET`, `config.py::validar_config`).
Built as a lazy singleton (`_obtener_cliente`), a judgment call made purely
for testability (no `importlib.reload` gymnastics needed to intercept the
constructor call in a test) — behaviorally identical to a module-level
`AsyncOpenAI(api_key=...)` call at import time.

**Image transport (task 11.2)**: the photo is downloaded via
`file.download_as_bytearray()` and sent to OpenAI as a base64 `data:` URI —
NEVER `file.file_path`, which is Telegram's own download URL and embeds
`LORE_BOT_TOKEN` (`https://api.telegram.org/file/bot<TOKEN>/...`). This is
the EXACT SAME bug class already found and fixed for Sonia's bot this
session (`telegram-bot/bot/handlers/reception.py`'s old `photo_file.file_path`
usage, fixed by `telegram-bot/bot/services/ai.py::photo_to_data_uri` — see
Engram memory "Fixed Sonia bot token leak to OpenAI via photo download
URLs") — not repeated here.

**Retry shape (task 11.1)**: `_llamar_con_reintentos` mirrors Sonia's own
`services/ai.py::_call_openai_with_retry` (`2**n` backoff,
`LORE_OPENAI_MAX_RETRIES=2` default), but raises Lore's OWN `VisionError`
on exhaustion — never Sonia's `AIServiceError`.

**Two distinct failure modes (judgment call, flagged — see
`handlers/captura.py::recibir_foto`)**: a `VisionError` means the OpenAI
call itself failed after retries — a transport/service failure. An empty
`Candidato` list from a SUCCESSFUL call means the model recognized nothing
in the photo — a content outcome, not a failure. The caller (`captura.py`)
handles these two outcomes with different messages and different next
states; this module only distinguishes them by raising vs. returning `[]`.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from lore import config

logger = logging.getLogger("lore.vision")

# Task 11.4: reuses the SAME per-batch cap the backend's own
# `resolver_referencias` request schema enforces
# (`backend/app/motored/api/bot_demanda_perdida.py::_MAX_REFERENCIAS_POR_LOTE`)
# and `handlers/captura.py::_MAX_CODIGOS_POR_LOTE` already mirrors for manual
# entry — one shared limit, three independent constants (no shared import
# across the process boundary), never a second, different number.
_MAX_REFERENCIAS_POR_LOTE = 30

_CODIGO_PATTERN = re.compile(r"^[A-Za-z0-9./\- ]{2,40}$")
_NOMBRE_MAX_LEN = 120

# Fix-up finding #1 (CRITICAL, resilience): this bot dispatches Telegram
# updates SEQUENTIALLY (no `concurrent_updates=True` — load-bearing for
# `captura.confirmar`'s double-tap safety, see `main.py::build_application`'s
# own docstring). The OpenAI SDK's own default read timeout is ~600s — a
# single hung call would stall EVERY advisor's `/registrar`, `/correcciones`,
# `/start`, admin approvals, etc. for up to ~10 minutes per attempt, times up
# to 3 attempts with retries. An explicit, short timeout makes a hang fail
# fast into the existing retry/backoff path instead.
_OPENAI_TIMEOUT_SEGUNDOS = 20.0

# Fix-up finding #9 (SUGGESTION, readability): named constants, consistent
# with this module's own established pattern (`_MAX_REFERENCIAS_POR_LOTE`,
# `_CODIGO_PATTERN`, `_NOMBRE_MAX_LEN`) — never inline magic literals.
_MODELO = "gpt-4o"
_MAX_TOKENS_RESPUESTA = 1500

# Fix-up finding #6 (SUGGESTION, risk + resilience) — a cheap defensive bound
# on image size before base64-encoding. Low risk today (Telegram's own
# client compresses photos sent via `filters.PHOTO`), but cheap to guard
# against a malformed/huge payload regardless. ~20MB with margin over
# Telegram's own typical photo-size limits.
_MAX_IMAGEN_BYTES = 20 * 1024 * 1024

_PROMPT = (
    "Estás mirando una foto de una pantalla o un papel con códigos de "
    "referencia de repuestos de motocicleta.\n\n"
    "Extraé ÚNICAMENTE los códigos de referencia visibles y, si es legible, "
    "el nombre de cada repuesto.\n\n"
    "Devolvé EXCLUSIVAMENTE un JSON con esta forma exacta:\n"
    '{"referencias": [{"codigo": "ABC123", "nombre": "FILTRO DE ACEITE"}]}\n\n'
    'Si no reconocés ninguna referencia, devolvé {"referencias": []}.\n\n'
    "REGLAS CRÍTICAS:\n"
    "- NUNCA incluyas nombres de clientes, números de documento/cédula, "
    "teléfonos, direcciones, precios ni cantidades — aunque aparezcan "
    "visibles en la imagen. Esos campos no existen en el esquema de "
    "respuesta de arriba y deben ser ignorados por completo.\n"
    "- No inventes códigos que no veas con claridad.\n"
    "- No incluyas ninguna clave adicional al esquema anterior."
)


class VisionError(Exception):
    """Raised when the OpenAI vision call fails/exhausts its retries."""


@dataclass(frozen=True)
class Candidato:
    """The ONLY shape a vision-extracted candidate can carry. No field for
    any customer-identifying data exists on this class — the real PII
    firewall (see module docstring). `frozen=True` (fix-up finding #10):
    immutability prevents a caller from silently re-adding a stripped field
    onto an instance after the firewall has already sanitized it."""

    codigo: str
    nombre: Optional[str] = None


_cliente_singleton: Optional[AsyncOpenAI] = None


def _obtener_cliente() -> AsyncOpenAI:
    """Lazy singleton — see module docstring for why the API key is always
    passed explicitly. Fix-up finding #1: also passes an explicit, short
    `timeout` — see `_OPENAI_TIMEOUT_SEGUNDOS`'s own comment for why the
    SDK's ~600s default is unacceptable in this sequentially-dispatched
    bot."""
    global _cliente_singleton
    if _cliente_singleton is None:
        _cliente_singleton = AsyncOpenAI(
            api_key=config.LORE_OPENAI_API_KEY, timeout=_OPENAI_TIMEOUT_SEGUNDOS
        )
    return _cliente_singleton


def _es_error_no_reintentable(exc: Exception) -> bool:
    """Fix-up finding #2 (CRITICAL, resilience): distinguishes errors that
    are GUARANTEED to fail identically on every retry (an auth failure, a
    malformed request, or any other non-429 4xx from OpenAI) from genuinely
    transient ones (rate limits, timeouts, connection errors, 5xx). Retrying
    the former burns retries + backoff sleeps for zero benefit — and, given
    this bot's sequential update dispatch (see `_OPENAI_TIMEOUT_SEGUNDOS`'s
    comment), needlessly extends the bot-wide freeze window.

    Order matters: `RateLimitError` (429) is itself an `APIStatusError`
    subclass, so it's checked FIRST to keep it retryable before the generic
    status-code check below would otherwise treat it as a non-retryable 4xx."""
    if isinstance(exc, RateLimitError):
        return False
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return False
    if isinstance(exc, APIStatusError):
        return exc.status_code < 500
    return False


async def _llamar_con_reintentos(coro_factory, max_retries: Optional[int] = None):
    """Same shape as Sonia's `services/ai.py::_call_openai_with_retry`
    (design D6) — `2**n` backoff — but raises `VisionError` (Lore's own
    typed exception) once retries are exhausted, never Sonia's
    `AIServiceError`. Fix-up finding #2: a non-retryable error (see
    `_es_error_no_reintentable`) raises `VisionError` IMMEDIATELY, on the
    first attempt, with zero retries/sleeps."""
    if max_retries is None:
        max_retries = config.LORE_OPENAI_MAX_RETRIES

    for intento in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            if _es_error_no_reintentable(exc):
                logger.error(
                    "vision: error no reintentable (%s), sin reintentos: %s",
                    type(exc).__name__,
                    exc,
                )
                raise VisionError(f"OpenAI rechazó la solicitud: {exc}") from exc
            if intento < max_retries:
                espera = 2**intento
                logger.warning(
                    "vision: reintento %s/%s tras %s — esperando %ss",
                    intento + 1,
                    max_retries + 1,
                    type(exc).__name__,
                    espera,
                )
                await asyncio.sleep(espera)
            else:
                logger.error("vision: agotó %s intentos: %s", max_retries + 1, exc)
                raise VisionError(
                    f"OpenAI no disponible tras {max_retries + 1} intentos"
                ) from exc


def _foto_a_data_uri(bytes_imagen: bytes) -> str:
    """Task 11.2 — same fix already applied to Sonia's bot this session
    (`telegram-bot/bot/services/ai.py::photo_to_data_uri`): NEVER the
    Telegram `file_path` download URL, which embeds `LORE_BOT_TOKEN`.
    Telegram always delivers `photo` as JPEG regardless of the original
    upload format.

    Fix-up finding #6: rejects anything over `_MAX_IMAGEN_BYTES` BEFORE
    encoding — defense in depth against a malformed/huge payload, even
    though Telegram's own client already compresses photos sent this way."""
    if len(bytes_imagen) > _MAX_IMAGEN_BYTES:
        raise VisionError(
            f"La foto pesa más de {_MAX_IMAGEN_BYTES // (1024 * 1024)}MB"
        )
    b64 = base64.b64encode(bytes(bytes_imagen)).decode()
    return f"data:image/jpeg;base64,{b64}"


async def extraer_referencias(file: Any) -> list[Candidato]:
    """Entry point called by `handlers/captura.py::recibir_foto`.

    `file` is a python-telegram-bot `File` (from
    `update.message.photo[-1].get_file()`) — downloaded here as bytes via
    `download_as_bytearray()`, NEVER via `file.file_path` (task 11.2).
    Raises `VisionError` if the OpenAI call itself fails after retries, OR if
    the Telegram download itself fails (fix-up finding #3 — a third distinct
    failure mode this module's own docstring previously did not account for)
    — both are a DIFFERENT outcome from a successful call recognizing zero
    references (an empty list, not an exception — see module docstring)."""
    try:
        bytes_imagen = await file.download_as_bytearray()
    except Exception as exc:
        logger.error("vision: no se pudo descargar la foto de Telegram: %s", exc)
        raise VisionError("no pude descargar esa foto de Telegram") from exc

    data_uri = _foto_a_data_uri(bytes_imagen)

    cliente = _obtener_cliente()

    async def _llamada():
        return await cliente.chat.completions.create(
            model=_MODELO,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _PROMPT},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=_MAX_TOKENS_RESPUESTA,
            temperature=0,
        )

    respuesta = await _llamar_con_reintentos(_llamada)
    crudo = respuesta.choices[0].message.content
    return parsear_respuesta(crudo)


def parsear_respuesta(raw: str) -> list[Candidato]:
    """The real PII firewall (tasks 11.4/11.5) — see module docstring.

    Only the `referencias` key is read; from each item, only `codigo`/
    `nombre` are read, so any other key (`cliente`, `cedula`, `telefono`,
    ...) is silently dropped because `Candidato` has no field to hold it.
    A malformed `codigo` (missing, wrong type, empty, wrong charset, out of
    the 2-40 char range) drops that single entry rather than raising or
    aborting the whole batch. Codes are deduplicated case-insensitively and
    capped at `_MAX_REFERENCIAS_POR_LOTE`. Never raises on malformed JSON or
    an unexpected shape — returns an empty list instead (a parsing failure
    here is content-level, the same "recognized nothing" outcome as a
    genuinely empty `referencias` list, NOT a `VisionError`)."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []

    if not isinstance(data, dict):
        return []

    items = data.get("referencias")
    if not isinstance(items, list):
        return []

    vistos: set[str] = set()
    candidatos: list[Candidato] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        codigo = item.get("codigo")
        if not isinstance(codigo, str):
            continue
        codigo = codigo.strip()
        if not _CODIGO_PATTERN.match(codigo):
            continue
        clave = codigo.upper()
        if clave in vistos:
            continue
        vistos.add(clave)

        nombre = item.get("nombre")
        if isinstance(nombre, str) and nombre.strip():
            nombre = nombre.strip()[:_NOMBRE_MAX_LEN]
        else:
            nombre = None

        candidatos.append(Candidato(codigo=codigo, nombre=nombre))
        if len(candidatos) >= _MAX_REFERENCIAS_POR_LOTE:
            break

    return candidatos
