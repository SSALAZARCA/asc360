import httpx
import pytest

from lore.api import (
    BackendCaido,
    BackendClient,
    CargaNoEncontrada,
    CodigoInvalido,
    FueraDeVentana,
    IdempotencyKeyEnUso,
    LineaAnulada,
    LineaNoEncontrada,
    NoRegistrado,
    Pendiente,
    ReferenciaNoEncontrada,
    RegistroInconsistente,
    SucursalNoAutorizada,
    SucursalNoEncontrada,
    TelegramYaVinculado,
    YaAnulada,
    YaRegistrado,
    YaResuelta,
)


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


async def test_yo_raises_backend_caido_on_non_string_code():
    # gga finding: a malformed `code` (not a string) must not crash
    # dict.get() with an uncaught TypeError -- it must fall through to the
    # same generic BackendCaido as an unmapped/absent code.
    def handler(request):
        return httpx.Response(403, json={"code": ["not", "a", "string"]})

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


# --- sucursales() -----------------------------------------------------------


async def test_sucursales_returns_the_active_branch_list():
    def handler(request):
        assert request.url.path == "/sucursales"
        return httpx.Response(200, json=[{"id": "s1", "nombre": "Bogotá"}])

    async with _client(handler) as client:
        data = await client.sucursales()

    assert data == [{"id": "s1", "nombre": "Bogotá"}]


async def test_sucursales_raises_backend_caido_on_non_list_body():
    def handler(request):
        return httpx.Response(200, json={"not": "a list"})

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.sucursales()


async def test_sucursales_raises_backend_caido_on_5xx():
    def handler(request):
        return httpx.Response(500)

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.sucursales()


# --- registro() --------------------------------------------------------------


async def test_registro_sends_payload_and_returns_body_on_201():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        return httpx.Response(
            201,
            json={
                "usuario": {"id": "u1", "nombre": "Ana", "role": "ASESOR_MOSTRADOR", "status": "pending"},
                "admin_telegram_ids": [111, 222],
            },
        )

    async with _client(handler) as client:
        data = await client.registro(nombre="Ana", phone="3001234567", sucursal_id="s1")

    assert captured["path"] == "/registro"
    assert data["usuario"]["status"] == "pending"
    assert data["admin_telegram_ids"] == [111, 222]


async def test_registro_raises_ya_registrado_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "YA_REGISTRADO"})

    async with _client(handler) as client:
        with pytest.raises(YaRegistrado):
            await client.registro(nombre="Ana", phone="3001234567", sucursal_id="s1")


async def test_registro_raises_sucursal_no_encontrada_on_404():
    def handler(request):
        return httpx.Response(404, json={"code": "SUCURSAL_NO_ENCONTRADA"})

    async with _client(handler) as client:
        with pytest.raises(SucursalNoEncontrada):
            await client.registro(nombre="Ana", phone="3001234567", sucursal_id="s1")


async def test_registro_raises_backend_caido_on_unmapped_404():
    def handler(request):
        return httpx.Response(404, json={"code": "ALGO_INESPERADO"})

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.registro(nombre="Ana", phone="3001234567", sucursal_id="s1")


async def test_registro_raises_backend_caido_on_unmapped_status():
    def handler(request):
        return httpx.Response(422, json={"detail": "bad payload"})

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.registro(nombre="Ana", phone="3001234567", sucursal_id="s1")


# --- vincular() ---------------------------------------------------------------


async def test_vincular_returns_body_on_200():
    def handler(request):
        return httpx.Response(200, json={"id": "u2", "nombre": "Admin Uno", "role": "ADMIN"})

    async with _client(handler) as client:
        data = await client.vincular("ABC12345")

    assert data["nombre"] == "Admin Uno"


async def test_vincular_raises_codigo_invalido_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "CODIGO_INVALIDO"})

    async with _client(handler) as client:
        with pytest.raises(CodigoInvalido):
            await client.vincular("BAD")


async def test_vincular_raises_telegram_ya_vinculado_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "TELEGRAM_YA_VINCULADO"})

    async with _client(handler) as client:
        with pytest.raises(TelegramYaVinculado):
            await client.vincular("ABC12345")


async def test_vincular_raises_backend_caido_on_unmapped_status():
    def handler(request):
        return httpx.Response(500)

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.vincular("ABC12345")


# --- aprobar_solicitud() / rechazar_solicitud() -------------------------------


async def test_aprobar_solicitud_returns_body_on_200():
    def handler(request):
        assert request.url.path == "/admin/solicitudes/u1/aprobar"
        return httpx.Response(
            200,
            json={"usuario_id": "u1", "status": "approved", "nombre": "Ana", "telegram_id_solicitante": 999},
        )

    async with _client(handler) as client:
        data = await client.aprobar_solicitud("u1")

    assert data["status"] == "approved"
    assert data["telegram_id_solicitante"] == 999


async def test_aprobar_solicitud_raises_ya_resuelta_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "YA_RESUELTA"})

    async with _client(handler) as client:
        with pytest.raises(YaResuelta):
            await client.aprobar_solicitud("u1")


async def test_rechazar_solicitud_returns_body_on_200():
    def handler(request):
        assert request.url.path == "/admin/solicitudes/u1/rechazar"
        return httpx.Response(
            200,
            json={"usuario_id": "u1", "status": "rejected", "nombre": "Ana", "telegram_id_solicitante": 999},
        )

    async with _client(handler) as client:
        data = await client.rechazar_solicitud("u1")

    assert data["status"] == "rejected"


async def test_rechazar_solicitud_raises_ya_resuelta_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "YA_RESUELTA"})

    async with _client(handler) as client:
        with pytest.raises(YaResuelta):
            await client.rechazar_solicitud("u1")


async def test_aprobar_solicitud_raises_backend_caido_on_unmapped_status():
    def handler(request):
        return httpx.Response(500)

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.aprobar_solicitud("u1")


# --- resolver_referencias() ---------------------------------------------------


async def test_resolver_referencias_returns_resueltas_and_no_resueltas():
    def handler(request):
        assert request.url.path == "/referencias/resolver"
        return httpx.Response(
            200,
            json={
                "resueltas": [{"entrada": "ABC", "referencia_id": "r1", "codigo": "ABC", "nombre": "Filtro"}],
                "no_resueltas": ["ZZZ"],
            },
        )

    async with _client(handler) as client:
        data = await client.resolver_referencias(["ABC", "ZZZ"])

    assert data["resueltas"][0]["codigo"] == "ABC"
    assert data["no_resueltas"] == ["ZZZ"]


async def test_resolver_referencias_raises_backend_caido_on_unmapped_status():
    def handler(request):
        return httpx.Response(422, json={"detail": "codigos no puede estar vacío"})

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.resolver_referencias([])


async def test_resolver_referencias_raises_backend_caido_on_5xx():
    def handler(request):
        return httpx.Response(500)

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.resolver_referencias(["ABC"])


# --- registrar_demanda_perdida() ----------------------------------------------


async def test_registrar_demanda_perdida_sends_idempotency_header_and_returns_body():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["idempotency_key"] = request.headers.get("idempotency-key")
        return httpx.Response(
            201,
            json={"carga_id": "c1", "sucursal_id": "s1", "fecha": "2026-09-25", "estado": "APLICADO", "lineas": []},
        )

    async with _client(handler) as client:
        data = await client.registrar_demanda_perdida(
            sucursal_id="s1",
            metodo="MANUAL",
            lineas=[{"referencia_id": "r1", "cantidad": 3}],
            idempotency_key="11111111-1111-1111-1111-111111111111",
        )

    assert captured["path"] == "/demanda-perdida"
    assert captured["idempotency_key"] == "11111111-1111-1111-1111-111111111111"
    assert data["carga_id"] == "c1"


async def test_registrar_demanda_perdida_replay_returns_200():
    def handler(request):
        return httpx.Response(
            200,
            json={"carga_id": "c1", "sucursal_id": "s1", "fecha": "2026-09-25", "estado": "APLICADO", "lineas": []},
        )

    async with _client(handler) as client:
        data = await client.registrar_demanda_perdida(
            sucursal_id="s1", metodo="MANUAL", lineas=[{"referencia_id": "r1", "cantidad": 3}],
            idempotency_key="11111111-1111-1111-1111-111111111111",
        )

    assert data["carga_id"] == "c1"


async def test_registrar_demanda_perdida_raises_sucursal_no_autorizada_on_403():
    def handler(request):
        return httpx.Response(403, json={"code": "SUCURSAL_NO_AUTORIZADA"})

    async with _client(handler) as client:
        with pytest.raises(SucursalNoAutorizada):
            await client.registrar_demanda_perdida(
                sucursal_id="s1", metodo="MANUAL", lineas=[{"referencia_id": "r1", "cantidad": 3}],
                idempotency_key="k",
            )


async def test_registrar_demanda_perdida_raises_idempotency_key_en_uso_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "IDEMPOTENCY_KEY_EN_USO"})

    async with _client(handler) as client:
        with pytest.raises(IdempotencyKeyEnUso):
            await client.registrar_demanda_perdida(
                sucursal_id="s1", metodo="MANUAL", lineas=[{"referencia_id": "r1", "cantidad": 3}],
                idempotency_key="k",
            )


async def test_registrar_demanda_perdida_raises_registro_inconsistente_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "REGISTRO_INCONSISTENTE"})

    async with _client(handler) as client:
        with pytest.raises(RegistroInconsistente):
            await client.registrar_demanda_perdida(
                sucursal_id="s1", metodo="MANUAL", lineas=[{"referencia_id": "r1", "cantidad": 3}],
                idempotency_key="k",
            )


async def test_registrar_demanda_perdida_raises_referencia_no_encontrada_on_404():
    def handler(request):
        return httpx.Response(404, json={"code": "REFERENCIA_NO_ENCONTRADA"})

    async with _client(handler) as client:
        with pytest.raises(ReferenciaNoEncontrada):
            await client.registrar_demanda_perdida(
                sucursal_id="s1", metodo="MANUAL", lineas=[{"referencia_id": "r1", "cantidad": 3}],
                idempotency_key="k",
            )


async def test_registrar_demanda_perdida_raises_sucursal_no_encontrada_on_404():
    def handler(request):
        return httpx.Response(404, json={"code": "SUCURSAL_NO_ENCONTRADA"})

    async with _client(handler) as client:
        with pytest.raises(SucursalNoEncontrada):
            await client.registrar_demanda_perdida(
                sucursal_id="s1", metodo="MANUAL", lineas=[{"referencia_id": "r1", "cantidad": 3}],
                idempotency_key="k",
            )


async def test_registrar_demanda_perdida_raises_backend_caido_on_unmapped_404():
    def handler(request):
        return httpx.Response(404, json={"code": "ALGO_INESPERADO"})

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.registrar_demanda_perdida(
                sucursal_id="s1", metodo="MANUAL", lineas=[{"referencia_id": "r1", "cantidad": 3}],
                idempotency_key="k",
            )


async def test_registrar_demanda_perdida_raises_backend_caido_on_5xx():
    def handler(request):
        return httpx.Response(500)

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.registrar_demanda_perdida(
                sucursal_id="s1", metodo="MANUAL", lineas=[{"referencia_id": "r1", "cantidad": 3}],
                idempotency_key="k",
            )


# --- listar_hoy() --------------------------------------------------------------


async def test_listar_hoy_returns_the_actor_own_today_registrations():
    def handler(request):
        assert request.url.path == "/demanda-perdida/hoy"
        return httpx.Response(200, json=[{"carga_id": "c1", "lineas": []}])

    async with _client(handler) as client:
        data = await client.listar_hoy()

    assert data == [{"carga_id": "c1", "lineas": []}]


async def test_listar_hoy_raises_backend_caido_on_non_list_body():
    def handler(request):
        return httpx.Response(200, json={"not": "a list"})

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.listar_hoy()


async def test_listar_hoy_raises_backend_caido_on_5xx():
    def handler(request):
        return httpx.Response(500)

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.listar_hoy()


# --- editar_linea() --------------------------------------------------------------


async def test_editar_linea_returns_body_on_200():
    def handler(request):
        assert request.url.path == "/demanda-perdida/lineas/l1"
        return httpx.Response(200, json={"linea_id": "l1", "cantidad": 7.0})

    async with _client(handler) as client:
        data = await client.editar_linea("l1", 7)

    assert data["cantidad"] == 7.0


async def test_editar_linea_raises_linea_no_encontrada_on_404():
    def handler(request):
        return httpx.Response(404, json={"code": "LINEA_NO_ENCONTRADA"})

    async with _client(handler) as client:
        with pytest.raises(LineaNoEncontrada):
            await client.editar_linea("l1", 7)


async def test_editar_linea_raises_fuera_de_ventana_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "FUERA_DE_VENTANA"})

    async with _client(handler) as client:
        with pytest.raises(FueraDeVentana):
            await client.editar_linea("l1", 7)


async def test_editar_linea_raises_linea_anulada_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "LINEA_ANULADA"})

    async with _client(handler) as client:
        with pytest.raises(LineaAnulada):
            await client.editar_linea("l1", 7)


async def test_editar_linea_raises_backend_caido_on_unmapped_404():
    def handler(request):
        return httpx.Response(404, json={"code": "ALGO_INESPERADO"})

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.editar_linea("l1", 7)


# --- anular_registro() --------------------------------------------------------


async def test_anular_registro_returns_body_on_200():
    def handler(request):
        assert request.url.path == "/demanda-perdida/c1/anular"
        return httpx.Response(200, json={"carga_id": "c1", "estado": "ANULADO"})

    async with _client(handler) as client:
        data = await client.anular_registro("c1")

    assert data["estado"] == "ANULADO"


async def test_anular_registro_raises_carga_no_encontrada_on_404():
    def handler(request):
        return httpx.Response(404, json={"code": "CARGA_NO_ENCONTRADA"})

    async with _client(handler) as client:
        with pytest.raises(CargaNoEncontrada):
            await client.anular_registro("c1")


async def test_anular_registro_raises_fuera_de_ventana_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "FUERA_DE_VENTANA"})

    async with _client(handler) as client:
        with pytest.raises(FueraDeVentana):
            await client.anular_registro("c1")


async def test_anular_registro_raises_ya_anulada_on_409():
    def handler(request):
        return httpx.Response(409, json={"code": "YA_ANULADA"})

    async with _client(handler) as client:
        with pytest.raises(YaAnulada):
            await client.anular_registro("c1")


async def test_anular_registro_raises_backend_caido_on_unmapped_404():
    def handler(request):
        return httpx.Response(404, json={"code": "ALGO_INESPERADO"})

    async with _client(handler) as client:
        with pytest.raises(BackendCaido):
            await client.anular_registro("c1")
