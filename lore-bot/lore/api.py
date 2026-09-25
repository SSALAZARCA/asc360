"""Transport for the Motored backend's bot-facing API (`/api/motored/bot/*`).

Auth is a shared secret plus the caller's Telegram id, sent as headers on
every request — never a JWT, never a cookie (see design D5/`deps_bot.py`'s
`get_bot_actor`, which the backend runs server-side for every call this
client makes). Phase 9 adds the registration/admin methods on top of the
`yo()` transport primitive Phase 8 already proved out; every new method
follows the exact same shape (map known error codes to a typed
`LoreApiError`, never let a bare `httpx`/`ValueError` escape).
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


class YaRegistrado(LoreApiError):
    """`POST /registro` was called for a `telegram_id` that already has a Usuario."""


class SucursalNoEncontrada(LoreApiError):
    """`POST /registro`'s `sucursal_id` does not exist (or was deactivated)."""


class CodigoInvalido(LoreApiError):
    """`POST /admin/vincular`'s one-time code is wrong, expired, or already used."""


class TelegramYaVinculado(LoreApiError):
    """`POST /admin/vincular`'s caller `telegram_id` is already linked to a Usuario."""


class BackendCaido(LoreApiError):
    """The backend is unreachable, erroring, or returned an unmapped code."""


_ERROR_CODE_MAP: dict[str, type[LoreApiError]] = {
    "NO_REGISTRADO": NoRegistrado,
    "PENDIENTE": Pendiente,
    "RECHAZADO": Rechazado,
    "FUERA_DE_VENTANA": FueraDeVentana,
    "YA_RESUELTA": YaResuelta,
    "YA_REGISTRADO": YaRegistrado,
    "CODIGO_INVALIDO": CodigoInvalido,
    "TELEGRAM_YA_VINCULADO": TelegramYaVinculado,
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
            raw_code = body.get("code") if isinstance(body, dict) else None
            # gga finding: `code` must be hashable/comparable before it's used
            # as a dict key -- a malformed body (`{"code": ["x"]}`) would
            # otherwise raise a bare, uncaught TypeError from `dict.get`.
            code = raw_code if isinstance(raw_code, str) else None
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

    async def sucursales(self) -> list:
        """`GET /sucursales` — the active-branch picker for self-registration.

        No actor required (design D5: "secret, no actor") — only the shared
        secret is checked."""
        response = await self._request("GET", "/sucursales")
        if response.status_code >= 400:
            raise BackendCaido(f"unmapped HTTP {response.status_code}")
        body = _safe_json(response)
        if not isinstance(body, list):
            raise BackendCaido("non-JSON response body")
        return body

    async def registro(self, *, nombre: str, phone: str, sucursal_id: str) -> dict:
        """`POST /registro` — self-registration. 201 on success (with
        `usuario` + `admin_telegram_ids` to push the approval notification
        to). `_request` already maps 409 `YA_REGISTRADO` via the shared
        error-code map; a 404 `SUCURSAL_NO_ENCONTRADA` is NOT auto-mapped
        (`_request` only intercepts 401/403/409/5xx), so it is handled here,
        the same way `yo()` handles its own 404."""
        response = await self._request(
            "POST",
            "/registro",
            json={"nombre": nombre, "phone": phone, "sucursal_id": sucursal_id},
        )
        if response.status_code == 404:
            body = _safe_json(response)
            raw_code = body.get("code") if isinstance(body, dict) else None
            code = raw_code if isinstance(raw_code, str) else None
            if code == "SUCURSAL_NO_ENCONTRADA":
                raise SucursalNoEncontrada(code)
            raise BackendCaido(f"unmapped HTTP 404 ({code})")
        if response.status_code != 201:
            raise BackendCaido(f"unmapped HTTP {response.status_code}")
        body = _safe_json(response)
        if not isinstance(body, dict):
            raise BackendCaido("non-JSON response body")
        return body

    async def vincular(self, codigo: str) -> dict:
        """`POST /admin/vincular` — consumes an ADMIN's one-time linking
        code generated on the web Usuarios screen (Phase 4). `_request`
        already maps 409 `CODIGO_INVALIDO`/`TELEGRAM_YA_VINCULADO`."""
        response = await self._request("POST", "/admin/vincular", json={"codigo": codigo})
        if response.status_code != 200:
            raise BackendCaido(f"unmapped HTTP {response.status_code}")
        body = _safe_json(response)
        if not isinstance(body, dict):
            raise BackendCaido("non-JSON response body")
        return body

    async def _resolver_solicitud(self, path: str) -> dict:
        """Shared by `aprobar_solicitud`/`rechazar_solicitud` — both call the
        SAME backend endpoint shape and the SAME `_request` error mapping
        (409 `YA_RESUELTA`), so there is no reason to duplicate this body."""
        response = await self._request("POST", path)
        if response.status_code != 200:
            raise BackendCaido(f"unmapped HTTP {response.status_code}")
        body = _safe_json(response)
        if not isinstance(body, dict):
            raise BackendCaido("non-JSON response body")
        return body

    async def aprobar_solicitud(self, usuario_id: str) -> dict:
        """`POST /admin/solicitudes/{usuario_id}/aprobar` — the SAME
        transition the web Usuarios screen triggers (design D5). Only an
        admin's own bot session can reach this in practice, because the
        backend's `require_bot_admin` re-resolves the caller's `telegram_id`
        server-side on every call; this client performs no authorization
        check of its own."""
        return await self._resolver_solicitud(f"/admin/solicitudes/{usuario_id}/aprobar")

    async def rechazar_solicitud(self, usuario_id: str) -> dict:
        """`POST /admin/solicitudes/{usuario_id}/rechazar` — see
        `aprobar_solicitud`."""
        return await self._resolver_solicitud(f"/admin/solicitudes/{usuario_id}/rechazar")
