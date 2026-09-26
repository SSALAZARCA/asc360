"""Unit tests for `lore.vision` — Method B (photo) reference extraction
(Phase 11, tasks 11.1-11.5).

Strict TDD: written BEFORE `lore/vision.py` exists (confirmed RED via
`ModuleNotFoundError`). Mirrors this project's established test-double
conventions: no real HTTP/OpenAI calls, `AsyncMock`/`MagicMock` doubles,
`monkeypatch` for module-level singletons (same pattern as
`test_handlers_captura.py`'s `_cliente` seam).
"""
import json
from unittest.mock import AsyncMock

import httpx
import openai
import pytest

from lore import config, vision


def _api_status_error(cls, status_code: int, mensaje: str = "boom"):
    """Builds a real `openai.APIStatusError` subclass instance — these
    require a genuine `httpx.Response`/`httpx.Request` pair, not a bare
    string, to construct."""
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return cls(mensaje, response=response, body=None)


# --- _obtener_cliente (task 11.1) -------------------------------------------


def test_obtener_cliente_usa_api_key_explicita_nunca_el_constructor_sin_argumentos(monkeypatch):
    """`AsyncOpenAI(api_key=config.LORE_OPENAI_API_KEY)` — NEVER the no-arg
    constructor, which would silently read `OPENAI_API_KEY` (Sonia's own
    key) from the environment. A lazy singleton (rather than a module-level
    call at import time) is a judgment call made for testability — the
    behavior/isolation contract is identical either way."""
    llamadas = []

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            llamadas.append(kwargs)

    monkeypatch.setattr(vision, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr(vision, "_cliente_singleton", None)

    cliente = vision._obtener_cliente()

    assert llamadas == [{"api_key": config.LORE_OPENAI_API_KEY, "timeout": vision._OPENAI_TIMEOUT_SEGUNDOS}]
    assert isinstance(cliente, FakeAsyncOpenAI)


def test_obtener_cliente_usa_timeout_explicito_y_corto(monkeypatch):
    """Fix-up finding #1 (CRITICAL, resilience): the OpenAI SDK's own default
    read timeout is ~600s, and this bot dispatches updates sequentially (no
    concurrent_updates=True -- see main.py::build_application's own
    docstring) -- a single hung OpenAI call would stall EVERY advisor's
    /registrar, /correcciones, /start, admin approvals, etc. for up to ~10
    minutes per attempt. An explicit, short timeout makes a hang fail fast
    into the existing retry/backoff path instead."""
    llamadas = []

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            llamadas.append(kwargs)

    monkeypatch.setattr(vision, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr(vision, "_cliente_singleton", None)

    vision._obtener_cliente()

    assert llamadas[0]["timeout"] == 20.0


def test_obtener_cliente_reusa_la_misma_instancia(monkeypatch):
    llamadas = []

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            llamadas.append(kwargs)

    monkeypatch.setattr(vision, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr(vision, "_cliente_singleton", None)

    primera = vision._obtener_cliente()
    segunda = vision._obtener_cliente()

    assert primera is segunda
    assert len(llamadas) == 1


# --- _llamar_con_reintentos (task 11.1) -------------------------------------


async def test_llamar_con_reintentos_succeeds_on_first_try():
    async def coro_factory():
        return "ok"

    resultado = await vision._llamar_con_reintentos(coro_factory, max_retries=2)

    assert resultado == "ok"


async def test_llamar_con_reintentos_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(vision.asyncio, "sleep", AsyncMock())

    intentos = {"n": 0}

    async def coro_factory():
        intentos["n"] += 1
        if intentos["n"] < 2:
            raise RuntimeError("boom")
        return "ok"

    resultado = await vision._llamar_con_reintentos(coro_factory, max_retries=2)

    assert resultado == "ok"
    assert intentos["n"] == 2


async def test_llamar_con_reintentos_raises_vision_error_when_exhausted(monkeypatch):
    monkeypatch.setattr(vision.asyncio, "sleep", AsyncMock())

    async def coro_factory():
        raise RuntimeError("boom")

    with pytest.raises(vision.VisionError):
        await vision._llamar_con_reintentos(coro_factory, max_retries=2)


async def test_llamar_con_reintentos_uses_config_default_when_not_given(monkeypatch):
    monkeypatch.setattr(vision.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(config, "LORE_OPENAI_MAX_RETRIES", 1)

    intentos = {"n": 0}

    async def coro_factory():
        intentos["n"] += 1
        raise RuntimeError("boom")

    with pytest.raises(vision.VisionError):
        await vision._llamar_con_reintentos(coro_factory)

    assert intentos["n"] == 2  # 1 intento inicial + 1 reintento


# --- _llamar_con_reintentos: retryable vs non-retryable (fix-up finding #2) -


async def test_llamar_con_reintentos_authentication_error_raises_immediately_zero_retries(monkeypatch):
    """Fix-up finding #2 (CRITICAL, resilience): an auth failure (e.g. a
    rotated/bad LORE_OPENAI_API_KEY) fails IDENTICALLY on every retry —
    retrying burns 2 retries + backoff sleeps for zero benefit, and (combined
    with finding #1's sequential dispatch) needlessly extends the bot-wide
    freeze window. Must raise VisionError on the FIRST attempt."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr(vision.asyncio, "sleep", sleep_mock)

    llamada = AsyncMock(side_effect=_api_status_error(openai.AuthenticationError, 401))

    with pytest.raises(vision.VisionError):
        await vision._llamar_con_reintentos(llamada, max_retries=2)

    llamada.assert_awaited_once()
    sleep_mock.assert_not_awaited()


async def test_llamar_con_reintentos_bad_request_error_raises_immediately_zero_retries(monkeypatch):
    """Same rationale as the AuthenticationError test above — a malformed
    request (400) is guaranteed to fail identically on every retry."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr(vision.asyncio, "sleep", sleep_mock)

    llamada = AsyncMock(side_effect=_api_status_error(openai.BadRequestError, 400))

    with pytest.raises(vision.VisionError):
        await vision._llamar_con_reintentos(llamada, max_retries=2)

    llamada.assert_awaited_once()
    sleep_mock.assert_not_awaited()


async def test_llamar_con_reintentos_rate_limit_error_still_retries(monkeypatch):
    """Regression proof (fix-up finding #2): a 429 RateLimitError must keep
    retrying exactly like before this fix — only non-retryable error types
    changed behavior."""
    monkeypatch.setattr(vision.asyncio, "sleep", AsyncMock())

    intentos = {"n": 0}

    async def coro_factory():
        intentos["n"] += 1
        if intentos["n"] < 2:
            raise _api_status_error(openai.RateLimitError, 429)
        return "ok"

    resultado = await vision._llamar_con_reintentos(coro_factory, max_retries=2)

    assert resultado == "ok"
    assert intentos["n"] == 2


async def test_llamar_con_reintentos_5xx_status_error_still_retries(monkeypatch):
    monkeypatch.setattr(vision.asyncio, "sleep", AsyncMock())

    intentos = {"n": 0}

    async def coro_factory():
        intentos["n"] += 1
        if intentos["n"] < 2:
            raise _api_status_error(openai.InternalServerError, 500)
        return "ok"

    resultado = await vision._llamar_con_reintentos(coro_factory, max_retries=2)

    assert resultado == "ok"
    assert intentos["n"] == 2


# --- parsear_respuesta (task 11.4/11.5 — the real PII firewall) ------------


def test_parsear_respuesta_drops_injected_customer_fields():
    """Even if the model ignores the prompt's own restriction and injects
    customer-identifying keys, `Candidato` has no field to hold them — this
    is the actual enforcement, not the prompt wording."""
    raw = json.dumps(
        {
            "referencias": [
                {
                    "codigo": "ABC-123",
                    "nombre": "Filtro de aceite",
                    "cliente": "Juan Perez",
                    "cedula": "1234567890",
                    "telefono": "3001234567",
                }
            ]
        }
    )

    candidatos = vision.parsear_respuesta(raw)

    assert len(candidatos) == 1
    candidato = candidatos[0]
    assert candidato.codigo == "ABC-123"
    assert candidato.nombre == "Filtro de aceite"
    assert not hasattr(candidato, "cliente")
    assert not hasattr(candidato, "cedula")
    assert not hasattr(candidato, "telefono")
    assert set(vars(candidato).keys()) == {"codigo", "nombre"}


def test_parsear_respuesta_rejects_bad_codigo_pattern():
    raw = json.dumps(
        {
            "referencias": [
                {"codigo": "válido-1", "nombre": None},  # tiene acento -> inválido
                {"codigo": "A", "nombre": None},  # muy corto
                {"codigo": "X" * 41, "nombre": None},  # muy largo
                {"codigo": "OK-123", "nombre": None},
            ]
        }
    )

    candidatos = vision.parsear_respuesta(raw)

    assert [c.codigo for c in candidatos] == ["OK-123"]


def test_parsear_respuesta_caps_at_30_items():
    raw = json.dumps(
        {"referencias": [{"codigo": f"COD{i:03d}", "nombre": None} for i in range(40)]}
    )

    candidatos = vision.parsear_respuesta(raw)

    assert len(candidatos) == 30


def test_parsear_respuesta_dedupes_case_insensitively():
    raw = json.dumps(
        {
            "referencias": [
                {"codigo": "abc", "nombre": None},
                {"codigo": "ABC", "nombre": "Filtro"},
                {"codigo": "AbC", "nombre": None},
            ]
        }
    )

    candidatos = vision.parsear_respuesta(raw)

    assert len(candidatos) == 1
    assert candidatos[0].codigo == "abc"


def test_parsear_respuesta_empty_referencias_returns_empty_list():
    """A SUCCESSFUL call recognizing nothing — a DIFFERENT outcome from a
    `VisionError` (the call itself failing). See `test_handlers_captura.py`'s
    `recibir_foto` tests for how these two modes are handled distinctly."""
    raw = json.dumps({"referencias": []})

    assert vision.parsear_respuesta(raw) == []


def test_parsear_respuesta_malformed_json_returns_empty_list_not_raise():
    assert vision.parsear_respuesta("not json at all") == []


def test_parsear_respuesta_missing_referencias_key_returns_empty_list():
    assert vision.parsear_respuesta(json.dumps({"otra_cosa": []})) == []


def test_parsear_respuesta_non_string_codigo_is_skipped():
    raw = json.dumps({"referencias": [{"codigo": 123, "nombre": None}, {"codigo": "OK-1", "nombre": None}]})

    candidatos = vision.parsear_respuesta(raw)

    assert [c.codigo for c in candidatos] == ["OK-1"]


def test_parsear_respuesta_truncates_long_nombre():
    raw = json.dumps({"referencias": [{"codigo": "OK-1", "nombre": "X" * 200}]})

    candidatos = vision.parsear_respuesta(raw)

    assert len(candidatos[0].nombre) == 120


# --- extraer_referencias (task 11.2 — image transport) ----------------------


class _FakeFile:
    def __init__(self, contenido: bytes):
        self._contenido = contenido
        # A real python-telegram-bot `File` also has `.file_path` — present
        # here specifically so a regression that reads it instead of
        # downloading bytes would be caught by `test_extraer_referencias_
        # never_uses_file_path_url` below.
        self.file_path = "https://api.telegram.org/file/botSECRET-TOKEN/photos/x.jpg"

    async def download_as_bytearray(self):
        return bytearray(self._contenido)


class _FakeChoice:
    def __init__(self, content: str):
        self.message = type("_Msg", (), {"content": content})()


class _FakeCompletionResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


async def test_extraer_referencias_sends_base64_data_uri_never_file_path(monkeypatch):
    """Task 11.2 — the EXACT SAME bug class already found/fixed for Sonia's
    bot this session (`telegram-bot/bot/services/ai.py::photo_to_data_uri`):
    `file.file_path` embeds `LORE_BOT_TOKEN` and must NEVER be sent to
    OpenAI."""
    capturado = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            capturado.update(kwargs)
            return _FakeCompletionResponse(json.dumps({"referencias": []}))

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(vision, "_obtener_cliente", lambda: FakeClient())

    fake_file = _FakeFile(b"\x89PNGfake-image-bytes")
    result = await vision.extraer_referencias(fake_file)

    assert result == []
    contenido = capturado["messages"][0]["content"]
    image_part = next(p for p in contenido if p["type"] == "image_url")
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert "SECRET-TOKEN" not in url
    assert "api.telegram.org" not in url


async def test_extraer_referencias_uses_expected_call_params(monkeypatch):
    capturado = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            capturado.update(kwargs)
            return _FakeCompletionResponse(json.dumps({"referencias": []}))

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(vision, "_obtener_cliente", lambda: FakeClient())

    await vision.extraer_referencias(_FakeFile(b"bytes"))

    assert capturado["model"] == vision._MODELO
    assert capturado["temperature"] == 0
    assert capturado["response_format"] == {"type": "json_object"}
    assert capturado["max_tokens"] == vision._MAX_TOKENS_RESPUESTA


async def test_extraer_referencias_raises_vision_error_when_download_fails():
    """Fix-up finding #3 (CRITICAL, reliability): `download_as_bytearray()`
    used to run outside any try/except — a Telegram download failure
    (expired file_id, transient network error) escaped as a raw, unhandled
    exception instead of `VisionError`, bypassing `captura.py::recibir_foto`'s
    `except vision.VisionError` fallback-to-MANUAL path entirely."""

    class _FailingFile:
        file_path = "https://api.telegram.org/file/botSECRET-TOKEN/photos/x.jpg"

        async def download_as_bytearray(self):
            raise RuntimeError("telegram download boom")

    with pytest.raises(vision.VisionError):
        await vision.extraer_referencias(_FailingFile())


async def test_extraer_referencias_raises_vision_error_when_image_too_large():
    """Fix-up finding #6 (SUGGESTION, risk + resilience) — cheap defensive
    bound on image size before base64-encoding, even though Telegram's own
    client already compresses photos sent via `filters.PHOTO`."""
    demasiado_grande = b"x" * (vision._MAX_IMAGEN_BYTES + 1)

    with pytest.raises(vision.VisionError):
        await vision.extraer_referencias(_FakeFile(demasiado_grande))


async def test_extraer_referencias_raises_vision_error_after_exhausted_retries(monkeypatch):
    monkeypatch.setattr(vision.asyncio, "sleep", AsyncMock())

    class FakeCompletions:
        async def create(self, **kwargs):
            raise RuntimeError("openai boom")

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(vision, "_obtener_cliente", lambda: FakeClient())

    with pytest.raises(vision.VisionError):
        await vision.extraer_referencias(_FakeFile(b"bytes"))
