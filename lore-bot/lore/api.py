"""Transport for the Motored backend's bot-facing API (`/api/motored/bot/*`).

Auth is a shared secret plus the caller's Telegram id, sent as headers on
every request — never a JWT, never a cookie (see design D5/`deps_bot.py`'s
`get_bot_actor`, which the backend runs server-side for every call this
client makes). No handler/conversation logic lives here yet — Phase 9+
builds on top of this transport primitive.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from . import config


class LoreApiError(Exception):
    """Base class for every error `BackendClient` can raise."""


class NoRegistrado(LoreApiError):
    """The caller's `telegram_id` has no matching Usuario (404 on /yo)."""


class Pendiente(LoreApiError):
    """The caller's registration is still awaiting approval."""


class Rechazado(LoreApiError):
    """The caller's registration was rejected."""


class FueraDeVentana(LoreApiError):
    """The requested edit/cancel targets a row outside today's window."""


class YaResuelta(LoreApiError):
    """The targeted approval/registration was already resolved by someone else."""


class BackendCaido(LoreApiError):
    """The backend is unreachable, erroring, or returned an unmapped code."""


_ERROR_CODE_MAP: dict[str, type[LoreApiError]] = {
    "NO_REGISTRADO": NoRegistrado,
    "PENDIENTE": Pendiente,
    "RECHAZADO": Rechazado,
    "FUERA_DE_VENTANA": FueraDeVentana,
    "YA_RESUELTA": YaResuelta,
}


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


class BackendClient:
    """Thin async httpx wrapper around `/api/motored/bot`.

    Not shared with, and shares nothing from, `telegram-bot/`'s own
    `services/api.py` — see `tests/test_isolation.py`.
    """

    def __init__(
        self,
        telegram_id: int,
        *,
        base_url: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self._telegram_id = telegram_id
        self._client = httpx.AsyncClient(
            base_url=base_url or config.LORE_API_URL,
            headers={
                "x-lore-secret": config.LORE_BOT_SECRET,
                "x-lore-telegram-id": str(telegram_id),
            },
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "BackendClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise BackendCaido(str(exc)) from exc

        if response.status_code in (401, 403, 409):
            body = _safe_json(response)
            code = body.get("code") if isinstance(body, dict) else None
            error_cls = _ERROR_CODE_MAP.get(code, BackendCaido)
            raise error_cls(code or f"unmapped HTTP {response.status_code}")

        if response.status_code >= 500:
            raise BackendCaido(f"HTTP {response.status_code}")

        return response

    async def yo(self) -> dict:
        """`GET /yo` — resolve the caller's own Usuario, or raise `NoRegistrado`.

        `_request` already maps 401/403/409/5xx to a `LoreApiError`
        subclass; this method must map every OTHER non-2xx status (any
        4xx `_request` doesn't already know about, e.g. 400/422) and any
        2xx response with a non-JSON body to `BackendCaido` too, instead
        of `raise_for_status()`/`response.json()` leaking a bare
        `httpx.HTTPStatusError`/`ValueError` that a `LoreApiError`-only
        caller would not catch."""
        response = await self._request("GET", "/yo")
        if response.status_code == 404:
            raise NoRegistrado("telegram_id not registered")
        if response.status_code >= 400:
            raise BackendCaido(f"unmapped HTTP {response.status_code}")
        body = _safe_json(response)
        if not isinstance(body, dict):
            raise BackendCaido("non-JSON response body")
        return body
