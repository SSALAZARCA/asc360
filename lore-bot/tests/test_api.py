import httpx
import pytest

from lore.api import BackendCaido, BackendClient, NoRegistrado, Pendiente, YaResuelta


def _client(handler, telegram_id=123):
    transport = httpx.MockTransport(handler)
    return BackendClient(telegram_id, base_url="http://test", transport=transport)


async def test_yo_sends_shared_secret_and_telegram_id_headers():
    captured = {}

    def handler(request):
        captured["headers"] = request.headers
        return httpx.Response(
            200,
            json={
                "id": "u1",
                "nombre": "Juan",
                "role": "ASESOR_MOSTRADOR",
                "status": "approved",
                "activo": True,
                "sucursales": [],
            },
        )

    async with _client(handler, telegram_id=555) as client:
        data = await client.yo()

    assert data["nombre"] == "Juan"
    assert captured["headers"]["x-lore-telegram-id"] == "555"
    assert captured["headers"]["x-lore-secret"]  # sent, non-empty


async def test_yo_raises_no_registrado_on_404():
    def handler(request):
        return httpx.Response(404)

    async with _client(handler) as client:
        with pytest.raises(NoRegistrado):
            await client.yo()


async def test_yo_raises_pendiente_on_403_with_code():
    def handler(request):
        return httpx.Response(403, json={"code": "PENDIENTE"})

    async with _client(handler) as client:
        with pytest.raises(Pendiente):
            await client.yo()


async def test_yo_raises_ya_resuelta_on_409_with_code():
    def handler(request):
        return httpx.Response(409, json={"code": "YA_RESUELTA", "status": "approved"})

    async with _client(handler) as client:
        with pytest.raises(YaResuelta):
            await client.yo()


async def test_yo_raises_backend_caido_on_5xx():
    def handler(request):
        return httpx.Response(500)

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.yo()


async def test_yo_raises_backend_caido_on_transport_error():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.yo()


async def test_yo_raises_backend_caido_on_unmapped_403_code():
    # An unrecognized/absent `code` on a 401/403 must never be swallowed —
    # it should surface as a loud, generic "backend misbehaving" error.
    def handler(request):
        return httpx.Response(403, json={})

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.yo()


async def test_yo_raises_backend_caido_on_unmapped_4xx():
    # gga finding: a 400/422 (never returned by /yo today, but not
    # impossible for a future backend change) must not leak a bare
    # httpx.HTTPStatusError past raise_for_status() — a LoreApiError-only
    # caller must still catch it.
    def handler(request):
        return httpx.Response(400, json={"code": "ALGO_INESPERADO"})

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.yo()


async def test_yo_raises_backend_caido_on_non_json_200_body():
    # gga finding: a malformed/empty 200 body must not leak a bare
    # ValueError from response.json() past a LoreApiError-only caller.
    def handler(request):
        return httpx.Response(200, content=b"not json")

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.yo()
