"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B3a, ADR-1, spec
CI-01..CI-24, DM-04): el ciclo de vida del pedido por tienda contra un
Postgres real (opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base migrada con `alembic -c alembic_motored.ini upgrade head`. Reutiliza
el mundo sintético de `test_corridas_api_pg.py` (tres sucursales: UNO con una
línea, DOS con dos, TRES omitida) y entra por la app real (ASGI, `httpx`).
Prueba lo que los dobles no pueden: que cerrar y reabrir escriben el estado y
el evento juntos, que una tienda no toca a otra, el todo o nada del lote, el
resumen y los filtros de la lista, la cabecera y la línea de tiempo, que una
corrida invalidada igual se puede reabrir y la retención.
"""
import datetime
import uuid

import pytest
from sqlalchemy import func, insert, select, update

from app.config import settings
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_envio import CorridaEnvio
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.pedido_evento import PedidoEvento
from app.motored.services.corridas import ejecucion as ej
from app.motored.services.corridas import retencion_corridas as rc
from tests.motored.pg_real.test_corridas_api_pg import (  # noqa: F401
    BASE,
    CORTE,
    URL,
    _anular_carga,
    _app_lista,
    _cliente,
    _como,
    _corrida_en_borrador,
    fabrica,
    mundo,
)
from tests.motored.pg_real.test_pedido_edicion_pg import _linea_id, _patch

pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]


# --- Ayudas -----------------------------------------------------------------


async def _corrida(mundo, **cuerpo):
    """Una corrida calculada; deja al usuario como COMPRAS."""
    creada = await _corrida_en_borrador(mundo, **cuerpo)
    _como("COMPRAS", mundo.datos.usuario.id)
    return creada["id"]


async def _post(ruta, cuerpo=None):
    async with _cliente() as cliente:
        return await cliente.post(ruta, json=cuerpo)


async def _get(ruta, **params):
    async with _cliente() as cliente:
        return await cliente.get(ruta, params=params)


def _tienda(corrida_id, sucursal_id, accion=None):
    ruta = f"{BASE}/{corrida_id}/sucursales/{sucursal_id}"
    return f"{ruta}/{accion}" if accion else ruta


async def _estados(mundo, corrida_id):
    """`{nombre: estado_pedido}` de las tiendas de la corrida."""
    async with mundo.fabrica() as db:
        filas = (await db.execute(
            select(CorridaSucursal.sucursal_id,
                   CorridaSucursal.estado_pedido)
            .where(CorridaSucursal.corrida_id == uuid.UUID(corrida_id))
            .execution_options(populate_existing=True))).all()
    datos = mundo.datos
    nombres = {datos.uno.id: "UNO", datos.dos.id: "DOS",
               datos.tres.id: "TRES"}
    return {nombres[sid]: estado for sid, estado in filas}


async def _eventos(mundo, corrida_id, sucursal_id=None):
    async with mundo.fabrica() as db:
        consulta = select(PedidoEvento).where(
            PedidoEvento.corrida_id == uuid.UUID(corrida_id))
        if sucursal_id is not None:
            consulta = consulta.where(
                PedidoEvento.sucursal_id == sucursal_id)
        filas = (await db.execute(
            consulta.order_by(PedidoEvento.id))).scalars().all()
    return [(f.sucursal_id, f.evento, f.motivo, f.usuario_id) for f in filas]


async def _ejecutar(mundo, sentencia):
    async with mundo.fabrica() as db:
        await db.execute(sentencia)
        await db.commit()


# --- Estado inicial y cerrar ------------------------------------------------


async def test_only_the_ok_tiendas_start_in_borrador_ci_01(mundo):
    corrida_id = await _corrida(mundo)

    assert await _estados(mundo, corrida_id) == {
        "UNO": "BORRADOR", "DOS": "BORRADOR", "TRES": None}


async def test_closing_one_tienda_leaves_the_others_alone_ci_05(mundo):
    corrida_id = await _corrida(mundo)
    uno = mundo.datos.uno.id

    respuesta = await _post(_tienda(corrida_id, uno, "cerrar"))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "corrida_id": corrida_id, "sucursal_id": str(uno),
        "estado_pedido": "CERRADO"}
    assert await _estados(mundo, corrida_id) == {
        "UNO": "CERRADO", "DOS": "BORRADOR", "TRES": None}
    assert await _eventos(mundo, corrida_id) == [
        (uno, "CERRADO", None, mundo.datos.usuario.id)]
    async with mundo.fabrica() as db:
        corrida = await db.get(Corrida, uuid.UUID(corrida_id))
    assert corrida.estado == "BORRADOR" and corrida.cerrada_en is None


async def test_a_second_close_of_the_same_tienda_is_064(mundo):
    corrida_id = await _corrida(mundo)
    uno = mundo.datos.uno.id
    await _post(_tienda(corrida_id, uno, "cerrar"))

    otra = await _post(_tienda(corrida_id, uno, "cerrar"))

    assert otra.status_code == 409
    assert otra.json()["detail"]["code"] == "E-CORRIDA-064"
    assert len(await _eventos(mundo, corrida_id)) == 1


async def test_a_tienda_without_pedido_cannot_be_closed_ci_04(mundo):
    corrida_id = await _corrida(mundo)

    respuesta = await _post(_tienda(corrida_id, mundo.datos.tres.id, "cerrar"))

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-065"
    assert await _eventos(mundo, corrida_id) == []


async def test_an_unknown_tienda_or_corrida_is_a_404(mundo):
    corrida_id = await _corrida(mundo)

    tienda = await _post(_tienda(corrida_id, uuid.uuid4(), "cerrar"))
    corrida = await _post(_tienda(uuid.uuid4(), mundo.datos.uno.id, "cerrar"))
    lote = await _post(f"{BASE}/{uuid.uuid4()}/cerrar")

    assert (tienda.status_code, corrida.status_code, lote.status_code) == (
        404, 404, 404)


async def test_close_all_closes_every_borrador_tienda_in_one_go(mundo):
    corrida_id = await _corrida(mundo)
    uno, dos = mundo.datos.uno.id, mundo.datos.dos.id

    respuesta = await _post(f"{BASE}/{corrida_id}/cerrar")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert sorted(cuerpo["cerradas"]) == sorted([str(uno), str(dos)])
    assert (cuerpo["estado"], cuerpo["ya_cerradas"]) == ("BORRADOR", 0)
    assert await _estados(mundo, corrida_id) == {
        "UNO": "CERRADO", "DOS": "CERRADO", "TRES": None}
    assert {e[0] for e in await _eventos(mundo, corrida_id)} == {uno, dos}


async def test_close_all_skips_the_tiendas_already_closed_ci_06(mundo):
    corrida_id = await _corrida(mundo)
    await _post(_tienda(corrida_id, mundo.datos.uno.id, "cerrar"))

    respuesta = await _post(f"{BASE}/{corrida_id}/cerrar")

    assert respuesta.json()["cerradas"] == [str(mundo.datos.dos.id)]
    assert respuesta.json()["ya_cerradas"] == 1


async def test_a_named_batch_is_all_or_nothing_naming_the_offender_ci_07(
        mundo):
    corrida_id = await _corrida(mundo)
    uno, dos = mundo.datos.uno.id, mundo.datos.dos.id
    await _post(_tienda(corrida_id, dos, "cerrar"))

    respuesta = await _post(
        f"{BASE}/{corrida_id}/cerrar",
        {"sucursal_ids": [str(uno), str(dos)]})

    assert respuesta.status_code == 409
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "E-CORRIDA-064"
    assert "DOS" in detalle["message"]
    assert detalle["detalle"]["sucursal_id"] == str(dos)
    assert await _estados(mundo, corrida_id) == {
        "UNO": "BORRADOR", "DOS": "CERRADO", "TRES": None}
    assert len(await _eventos(mundo, corrida_id)) == 1


async def test_a_named_batch_with_a_tienda_without_pedido_closes_nothing(
        mundo):
    corrida_id = await _corrida(mundo)
    uno, tres = mundo.datos.uno.id, mundo.datos.tres.id

    respuesta = await _post(
        f"{BASE}/{corrida_id}/cerrar",
        {"sucursal_ids": [str(uno), str(tres)]})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-065"
    assert (await _estados(mundo, corrida_id))["UNO"] == "BORRADOR"


async def test_a_named_batch_that_closes_two_tiendas_ci_06(mundo):
    corrida_id = await _corrida(mundo)
    ids = [mundo.datos.uno.id, mundo.datos.dos.id]

    respuesta = await _post(
        f"{BASE}/{corrida_id}/cerrar",
        {"sucursal_ids": [str(i) for i in ids]})

    assert respuesta.status_code == 200, respuesta.text
    assert sorted(respuesta.json()["cerradas"]) == sorted(map(str, ids))
    assert respuesta.json()["ya_cerradas"] == 0


# --- Escenarios y estados del cálculo ---------------------------------------


async def test_a_scenario_never_has_pedidos_and_refuses_every_action_042(
        mundo):
    corrida_id = await _corrida(
        mundo, overrides={"consolidar_sustituidas": True})
    uno = mundo.datos.uno.id
    _como("COMPRAS", mundo.datos.usuario.id)

    cerrar = await _post(_tienda(corrida_id, uno, "cerrar"))
    lote = await _post(f"{BASE}/{corrida_id}/cerrar")
    reabrir = await _post(
        _tienda(corrida_id, uno, "reabrir"), {"motivo": "x"})

    for respuesta, accion in ((cerrar, "cerrar"), (lote, "cerrar"),
                              (reabrir, "reabrir")):
        assert respuesta.status_code == 409, respuesta.text
        assert respuesta.json()["detail"]["code"] == "E-CORRIDA-042"
        assert accion in respuesta.json()["detail"]["message"]
    assert await _estados(mundo, corrida_id) == {
        "UNO": None, "DOS": None, "TRES": None}


async def test_compras_cannot_launch_a_scenario_but_admin_can_062(mundo):
    _como("COMPRAS", mundo.datos.usuario.id)
    cuerpo = {"fecha_corte": CORTE.isoformat(),
              "overrides": {"consolidar_sustituidas": True}}
    async with mundo.fabrica() as db:
        antes = (await db.execute(select(func.count(Corrida.id)))).scalar()

    prohibida = await _post(BASE, cuerpo)
    vacia = await _post(BASE, {**cuerpo, "overrides": {}})
    _como("ADMIN", mundo.datos.usuario.id)
    permitida = await _post(BASE, cuerpo)

    assert prohibida.status_code == 403
    assert prohibida.json()["detail"]["code"] == "E-CORRIDA-062"
    assert vacia.status_code == 202, vacia.text
    assert vacia.json()["es_escenario"] is False
    assert permitida.status_code == 202, permitida.text
    assert permitida.json()["es_escenario"] is True
    async with mundo.fabrica() as db:
        despues = (await db.execute(select(func.count(Corrida.id)))).scalar()
    assert despues == antes + 2


async def test_an_annulled_corrida_refuses_to_close_040(mundo):
    corrida_id = await _corrida(mundo)
    await _post(f"{BASE}/{corrida_id}/anular", {"motivo": "datos viejos"})

    respuesta = await _post(_tienda(corrida_id, mundo.datos.uno.id, "cerrar"))

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-040"


async def test_a_legacy_cerrada_corrida_is_still_operable(mundo):
    corrida_id = await _corrida(mundo)
    await _ejecutar(mundo, update(Corrida).where(
        Corrida.id == uuid.UUID(corrida_id)).values(estado="CERRADA"))

    respuesta = await _post(_tienda(corrida_id, mundo.datos.uno.id, "cerrar"))

    assert respuesta.status_code == 200, respuesta.text


# --- Reabrir ----------------------------------------------------------------


async def test_reopening_needs_a_motivo_and_changes_nothing_without_it_ci_17(
        mundo):
    corrida_id = await _corrida(mundo)
    uno = mundo.datos.uno.id
    await _post(_tienda(corrida_id, uno, "cerrar"))

    for cuerpo in (None, {}, {"motivo": "   "}, {"motivo": "x" * 501}):
        respuesta = await _post(_tienda(corrida_id, uno, "reabrir"), cuerpo)
        assert respuesta.status_code == 422, cuerpo
        assert respuesta.json()["detail"]["code"] == "E-CORRIDA-046"

    assert (await _estados(mundo, corrida_id))["UNO"] == "CERRADO"
    assert len(await _eventos(mundo, corrida_id)) == 1


async def test_a_closed_pedido_goes_back_to_borrador_with_who_when_why_ci_15(
        mundo):
    corrida_id = await _corrida(mundo)
    uno = mundo.datos.uno.id
    await _post(_tienda(corrida_id, uno, "cerrar"))

    respuesta = await _post(
        _tienda(corrida_id, uno, "reabrir"),
        {"motivo": "  Corrección de cantidades  "})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado_pedido"] == "BORRADOR"
    assert await _eventos(mundo, corrida_id, uno) == [
        (uno, "CERRADO", None, mundo.datos.usuario.id),
        (uno, "REABIERTO", "Corrección de cantidades",
         mundo.datos.usuario.id)]


async def test_reopening_one_tienda_leaves_the_others_untouched_ci_16(mundo):
    corrida_id = await _corrida(mundo)
    uno, dos = mundo.datos.uno.id, mundo.datos.dos.id
    await _post(f"{BASE}/{corrida_id}/cerrar")
    await _ejecutar(mundo, insert(CorridaEnvio).values(
        corrida_id=uuid.UUID(corrida_id), sucursal_id=dos,
        proveedor_id=mundo.datos.hmcl.id, fecha_corte=CORTE,
        numero_pedido_proveedor="12345", fecha_envio=CORTE,
        enviada_por=mundo.datos.usuario.id))
    await _ejecutar(mundo, update(CorridaSucursal).where(
        CorridaSucursal.corrida_id == uuid.UUID(corrida_id),
        CorridaSucursal.sucursal_id == dos).values(estado_pedido="ENVIADO"))

    respuesta = await _post(
        _tienda(corrida_id, uno, "reabrir"), {"motivo": "ajuste"})

    assert respuesta.status_code == 200, respuesta.text
    assert await _estados(mundo, corrida_id) == {
        "UNO": "BORRADOR", "DOS": "ENVIADO", "TRES": None}


async def test_a_sent_pedido_cannot_be_reopened_and_names_the_order_ci_18(
        mundo):
    corrida_id = await _corrida(mundo)
    dos = mundo.datos.dos.id
    await _post(f"{BASE}/{corrida_id}/cerrar")
    await _ejecutar(mundo, insert(CorridaEnvio).values(
        corrida_id=uuid.UUID(corrida_id), sucursal_id=dos,
        proveedor_id=mundo.datos.hmcl.id, fecha_corte=CORTE,
        numero_pedido_proveedor="12345", fecha_envio=CORTE,
        enviada_por=mundo.datos.usuario.id))
    await _ejecutar(mundo, update(CorridaSucursal).where(
        CorridaSucursal.corrida_id == uuid.UUID(corrida_id),
        CorridaSucursal.sucursal_id == dos).values(estado_pedido="ENVIADO"))

    respuesta = await _post(
        _tienda(corrida_id, dos, "reabrir"), {"motivo": "ajuste"})

    assert respuesta.status_code == 409
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "E-CORRIDA-045" and "12345" in detalle["message"]
    assert (await _estados(mundo, corrida_id))["DOS"] == "ENVIADO"


async def test_reopening_a_borrador_or_an_absent_pedido_is_044_or_065(mundo):
    corrida_id = await _corrida(mundo)
    motivo = {"motivo": "x"}

    borrador = await _post(
        _tienda(corrida_id, mundo.datos.uno.id, "reabrir"), motivo)
    sin_pedido = await _post(
        _tienda(corrida_id, mundo.datos.tres.id, "reabrir"), motivo)

    assert borrador.json()["detail"]["code"] == "E-CORRIDA-044"
    assert sin_pedido.json()["detail"]["code"] == "E-CORRIDA-065"
    assert sin_pedido.status_code == 409


async def test_a_reopened_pedido_is_editable_and_recloses_with_the_edit_ci_21(
        mundo):
    corrida_id = await _corrida(mundo)
    uno = mundo.datos.uno.id
    linea = await _linea_id(mundo, corrida_id, uno)
    await _post(_tienda(corrida_id, uno, "cerrar"))
    cerrado = await _patch(corrida_id, linea, {"pedido_final": 60})

    await _post(_tienda(corrida_id, uno, "reabrir"), {"motivo": "ajuste"})
    editado = await _patch(corrida_id, linea, {"pedido_final": 60})
    await _post(_tienda(corrida_id, uno, "cerrar"))
    cabecera = (await _get(_tienda(corrida_id, uno))).json()

    assert cerrado.status_code == 409
    assert cerrado.json()["detail"]["code"] == "E-CORRIDA-052"
    assert editado.status_code == 200, editado.text
    assert cabecera["estado_pedido"] == "CERRADO"
    assert cabecera["totales"]["unidades_a_pedir"] == "60.00"
    assert cabecera["totales"]["unidades_sugerido"] == "53.00"
    assert [e[1] for e in await _eventos(mundo, corrida_id, uno)] == [
        "CERRADO", "REABIERTO", "CERRADO"]


async def test_reopening_the_last_closed_tienda_lets_the_carga_invalidate_22(
        mundo):
    """B3b (DM-10, DM-11): con una tienda CERRADO la guarda bloquea la
    anulación de la carga; reabierta la última, la anulación sigue, invalida
    la corrida y ninguna tienda se puede cerrar (E-CORRIDA-041)."""
    corrida_id = await _corrida(mundo)
    uno, dos = mundo.datos.uno.id, mundo.datos.dos.id
    await _post(_tienda(corrida_id, uno, "cerrar"))
    bloqueada = await _anular_carga(mundo.datos.cargas.ingresos.id)
    await _post(_tienda(corrida_id, uno, "reabrir"), {"motivo": "ajuste"})
    anulada = await _anular_carga(mundo.datos.cargas.ingresos.id)

    cerrar = await _post(_tienda(corrida_id, dos, "cerrar"))

    assert bloqueada.status_code == 409
    assert bloqueada.json()["detail"]["code"] == "E-CARGA-050"
    assert anulada.status_code == 200, anulada.text
    assert cerrar.status_code == 409
    assert cerrar.json()["detail"]["code"] == "E-CORRIDA-041"


async def test_an_invalidated_corrida_can_still_reopen_but_not_close_ci_22(
        mundo):
    """Una corrida invalidada con una tienda CERRADO ya no se alcanza por la
    API (la guarda lo impide); se emula con un UPDATE, como una carrera
    residual o un dato heredado, para conservar la regla de reabrir."""
    corrida_id = await _corrida(mundo)
    uno, dos = mundo.datos.uno.id, mundo.datos.dos.id
    await _post(_tienda(corrida_id, uno, "cerrar"))
    await _ejecutar(mundo, update(Corrida).where(
        Corrida.id == uuid.UUID(corrida_id)).values(invalidada=True))

    cerrar = await _post(_tienda(corrida_id, dos, "cerrar"))
    reabrir = await _post(
        _tienda(corrida_id, uno, "reabrir"), {"motivo": "carga anulada"})

    assert cerrar.status_code == 409
    assert cerrar.json()["detail"]["code"] == "E-CORRIDA-041"
    assert reabrir.status_code == 200, reabrir.text
    assert (await _estados(mundo, corrida_id))["UNO"] == "BORRADOR"


# --- Lectura: resumen, filtros, cabecera y eventos --------------------------


async def test_the_detail_shows_the_summary_and_each_tienda_pedido_ci_03(
        mundo):
    corrida_id = await _corrida(mundo)
    uno = mundo.datos.uno.id
    await _post(_tienda(corrida_id, uno, "cerrar"))

    cuerpo = (await _get(f"{BASE}/{corrida_id}")).json()

    assert cuerpo["pedidos"] == {
        "total": 2, "borrador": 1, "cerrados": 1, "enviados": 0,
        "sin_pedido": 0}
    por_nombre = {s["sucursal_id"]: s for s in cuerpo["sucursales"]}
    cerrada = por_nombre[str(uno)]
    abierta = por_nombre[str(mundo.datos.dos.id)]
    omitida = por_nombre[str(mundo.datos.tres.id)]
    assert cerrada["estado_pedido"] == "CERRADO"
    assert cerrada["unidades_a_pedir"] == "53.00"
    assert cerrada["ultimo_evento"]["evento"] == "CERRADO"
    assert cerrada["ultimo_evento"]["usuario"] == "Compras"
    assert cerrada["acciones"] == {
        "cerrar": False, "reabrir": True, "editar": False,
        "enviar": True, "corregir_envio": False, "exportar": True}
    assert abierta["estado_pedido"] == "BORRADOR"
    assert abierta["ultimo_evento"] is None
    assert abierta["acciones"]["cerrar"] is True
    assert omitida["estado_pedido"] is None
    assert not any(omitida["acciones"].values())


async def test_the_list_carries_the_summary_and_filters_by_pedido_ci_03(
        mundo):
    corrida_id = await _corrida(mundo)
    uno, dos = mundo.datos.uno.id, mundo.datos.dos.id

    async def codigos(**filtro):
        cuerpo = (await _get(BASE, **filtro)).json()
        return [c["id"] for c in cuerpo["items"]], cuerpo["items"]

    _, items = await codigos()
    assert items[0]["pedidos"] == {
        "total": 2, "borrador": 2, "cerrados": 0, "enviados": 0,
        "sin_pedido": None}
    assert (await codigos(pedidos="abiertos"))[0] == [corrida_id]
    assert (await codigos(pedidos="por_enviar"))[0] == []
    assert (await codigos(pedidos="enviados"))[0] == []

    await _post(_tienda(corrida_id, uno, "cerrar"))
    assert (await codigos(pedidos="por_enviar"))[0] == [corrida_id]
    assert (await codigos(pedidos="abiertos"))[0] == [corrida_id]

    await _post(_tienda(corrida_id, dos, "cerrar"))
    assert (await codigos(pedidos="abiertos"))[0] == []
    assert (await codigos(pedidos="enviados"))[0] == []
    await _ejecutar(mundo, update(CorridaSucursal).where(
        CorridaSucursal.corrida_id == uuid.UUID(corrida_id)).values(
        estado_pedido="ENVIADO"))
    assert (await codigos(pedidos="enviados"))[0] == [corrida_id]
    assert (await codigos(pedidos="por_enviar"))[0] == []
    assert (await _get(BASE, pedidos="todos")).status_code == 422


async def test_the_tienda_header_has_totals_and_the_last_event(mundo):
    corrida_id = await _corrida(mundo)
    uno = mundo.datos.uno.id
    await _post(_tienda(corrida_id, uno, "cerrar"))

    respuesta = await _get(_tienda(corrida_id, uno))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["corrida_codigo"] == "PED-2026-S39-001"
    assert (cuerpo["nombre"], cuerpo["estado"], cuerpo["estado_pedido"]) == (
        mundo.datos.uno.nombre.strip(), "OK", "CERRADO")
    assert cuerpo["sic"] == mundo.datos.uno.sic
    assert cuerpo["totales"]["valor_a_pedir"] == "24419.75"
    assert cuerpo["ultimo_evento"]["usuario"] == "Compras"
    assert cuerpo["acciones"]["reabrir"] is True
    assert (await _get(_tienda(corrida_id, uuid.uuid4()))).status_code == 404
    assert (await _get(_tienda(uuid.uuid4(), uno))).status_code == 404


async def test_the_timeline_lists_the_events_oldest_first(mundo):
    corrida_id = await _corrida(mundo)
    uno = mundo.datos.uno.id
    await _post(_tienda(corrida_id, uno, "cerrar"))
    await _post(_tienda(corrida_id, uno, "reabrir"), {"motivo": "ajuste"})

    respuesta = await _get(_tienda(corrida_id, uno, "eventos"))

    assert respuesta.status_code == 200, respuesta.text
    eventos = respuesta.json()
    assert [(e["evento"], e["motivo"], e["usuario"]) for e in eventos] == [
        ("CERRADO", None, "Compras"), ("REABIERTO", "ajuste", "Compras")]
    vacio = await _get(_tienda(corrida_id, mundo.datos.dos.id, "eventos"))
    assert vacio.json() == []
    assert (await _get(
        _tienda(corrida_id, uuid.uuid4(), "eventos"))).status_code == 404


# --- Retención (B3a.4) ------------------------------------------------------


async def test_the_retention_keeps_corridas_whose_pedido_is_history(
        mundo, monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_DIAS", 45)
    ahora = ej.ahora_utc()
    vieja = (ahora - datetime.timedelta(days=60)).replace(tzinfo=None)
    uno = mundo.datos.uno.id
    ids = {}
    async with mundo.fabrica() as db:
        for clave in ("libre", "con_evento", "cerrada", "enviada"):
            corrida = Corrida(
                id=uuid.uuid4(), codigo=f"RT-{uuid.uuid4().hex[:8]}",
                proveedor_id=mundo.datos.hmcl.id, fecha_corte=CORTE,
                estado="BORRADOR", created_at=vieja)
            db.add(corrida)
            ids[clave] = corrida.id
        await db.flush()
        for clave, estado in (("cerrada", "CERRADO"), ("enviada", "ENVIADO"),
                              ("con_evento", "BORRADOR")):
            db.add(CorridaSucursal(
                corrida_id=ids[clave], sucursal_id=uno, orden=1,
                estado="OK", estado_pedido=estado))
        await db.flush()
        db.add(PedidoEvento(
            corrida_id=ids["con_evento"], sucursal_id=uno,
            evento="CERRADO"))
        db.add(CorridaEnvio(
            corrida_id=ids["enviada"], sucursal_id=uno,
            proveedor_id=mundo.datos.hmcl.id, fecha_corte=CORTE,
            numero_pedido_proveedor="9", fecha_envio=CORTE,
            enviada_por=mundo.datos.usuario.id))
        await db.commit()

    async with mundo.fabrica() as db:
        borradas = await rc.ejecutar_si_corresponde(db, ahora, tamano=10)
    async with mundo.fabrica() as db:
        vivas = set((await db.execute(
            select(Corrida.id).where(Corrida.id.in_(list(ids.values())))
        )).scalars().all())

    assert borradas >= 1
    assert vivas == {ids["con_evento"], ids["cerrada"], ids["enviada"]}
