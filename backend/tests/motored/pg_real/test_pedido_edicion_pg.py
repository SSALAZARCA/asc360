"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, ADR-3, ADR-4,
spec ED-01..ED-29): la edición de líneas contra un Postgres real (opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base migrada con `alembic -c alembic_motored.ini upgrade head`. Reutiliza
el mundo sintético de `test_corridas_api_pg.py` (tres sucursales: UNO con una
línea, DOS con dos, TRES omitida) y entra por la app real (ASGI, `httpx`).
Prueba lo que los dobles no pueden: que el PATCH y el historial son atómicos,
que el valor se recalcula como el motor, los filtros y el DISTINCT ON de la
última edición, los totales "a pedir" junto a los del sugerido y que la
reproducción de una corrida editada sigue idéntica.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_linea_historial import CorridaLineaHistorial
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.services.corridas import edicion
from app.motored.services.corridas import reproduccion as rp
from tests.motored.pg_real.test_corridas_api_pg import (  # noqa: F401
    BASE,
    URL,
    _app_lista,
    _cliente,
    _como,
    _corrida_en_borrador,
    fabrica,
    mundo,
)

pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

PATRON = "94109-12000S"
OTRA = "55555-00001"
D = Decimal


# --- Ayudas -----------------------------------------------------------------


async def _linea_id(mundo, corrida_id, sucursal_id, codigo=PATRON):
    async with mundo.fabrica() as db:
        return (await db.execute(
            select(CorridaLinea.id).where(
                CorridaLinea.corrida_id == uuid.UUID(corrida_id),
                CorridaLinea.sucursal_id == sucursal_id,
                CorridaLinea.codigo_referencia == codigo))).scalar_one()


async def _preparar(mundo):
    """Corrida en BORRADOR y la línea patrón de UNO (sugerido 53)."""
    creada = await _corrida_en_borrador(mundo)
    corrida_id = creada["id"]
    linea = await _linea_id(mundo, corrida_id, mundo.datos.uno.id)
    _como("COMPRAS", mundo.datos.usuario.id)
    return corrida_id, linea


async def _patch(corrida_id, linea_id, cuerpo):
    async with _cliente() as cliente:
        return await cliente.patch(
            f"{BASE}/{corrida_id}/lineas/{linea_id}", json=cuerpo)


async def _ejecutar(mundo, sentencia):
    async with mundo.fabrica() as db:
        await db.execute(sentencia)
        await db.commit()


async def _historial(mundo, linea_id):
    async with mundo.fabrica() as db:
        filas = (await db.execute(
            select(CorridaLineaHistorial)
            .where(CorridaLineaHistorial.linea_id == linea_id)
            .order_by(CorridaLineaHistorial.id))).scalars().all()
    return [(f.valor_anterior, f.valor_nuevo, f.motivo) for f in filas]


async def _valores(mundo, linea_id):
    async with mundo.fabrica() as db:
        fila = (await db.execute(
            select(CorridaLinea.pedido_sugerido, CorridaLinea.pedido_final,
                   CorridaLinea.valor_pedido)
            .where(CorridaLinea.id == linea_id))).one()
    return tuple(fila)


# --- Edición: éxito y valor -------------------------------------------------


async def test_a_successful_edit_updates_value_and_history_ed_01(mundo):
    corrida_id, linea = await _preparar(mundo)

    respuesta = await _patch(corrida_id, linea, {"pedido_final": 60})

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    editada = cuerpo["linea"]
    assert editada["id"] == linea
    assert (editada["pedido_sugerido"], editada["pedido_final"]) == (
        "53.00", "60.00")
    assert editada["valor_pedido"] == "27645.00"
    assert editada["valor_sugerido"] == "24419.75"
    assert editada["editada"] is True and editada["editado_por"] == "Compras"
    assert cuerpo["totales_tienda"] == {
        "unidades_a_pedir": "60.00", "valor_a_pedir": "27645.00",
        "unidades_sugerido": "53.00", "valor_sugerido": "24419.75"}
    assert await _valores(mundo, linea) == (
        D("53.00"), D("60.00"), D("27645.00"))
    assert await _historial(mundo, linea) == [
        (D("53.00"), D("60.00"), "MANUAL")]


async def test_editing_back_to_the_suggestion_ed_02(mundo):
    corrida_id, linea = await _preparar(mundo)
    await _patch(corrida_id, linea, {"pedido_final": 60})

    respuesta = await _patch(corrida_id, linea, {"pedido_final": 53})

    editada = respuesta.json()["linea"]
    assert editada["editada"] is False and editada["editado_por"] == "Compras"
    assert respuesta.json()["totales_tienda"]["valor_a_pedir"] == (
        "24419.75")
    assert await _historial(mundo, linea) == [
        (D("53.00"), D("60.00"), "MANUAL"),
        (D("60.00"), D("53.00"), "MANUAL")]


async def test_the_same_value_is_a_no_op_without_history_ed_03(mundo):
    corrida_id, linea = await _preparar(mundo)

    respuesta = await _patch(corrida_id, linea, {"pedido_final": 53})

    assert respuesta.status_code == 200
    assert respuesta.json()["linea"]["editado_por"] is None
    assert await _historial(mundo, linea) == []


async def test_zero_is_stored_and_the_line_stays_ed_04(mundo):
    corrida_id, linea = await _preparar(mundo)

    respuesta = await _patch(corrida_id, linea, {"pedido_final": 0})

    assert respuesta.json()["linea"]["valor_pedido"] == "0.00"
    assert await _valores(mundo, linea) == (D("53.00"), D("0.00"), D("0.00"))


async def test_a_line_without_price_keeps_value_zero_ed_11(mundo):
    corrida_id, linea = await _preparar(mundo)
    await _ejecutar(mundo, update(CorridaLinea).where(
        CorridaLinea.id == linea).values(precio=None))

    respuesta = await _patch(corrida_id, linea, {"pedido_final": 10})

    assert respuesta.json()["linea"]["valor_pedido"] == "0.00"
    assert respuesta.json()["linea"]["pedido_final"] == "10.00"


# --- Rechazos ---------------------------------------------------------------


@pytest.mark.parametrize("bruto", [-1, 2.5, "abc", None, 10_000_000])
async def test_an_invalid_quantity_is_053_and_changes_nothing_ed_05(
        mundo, bruto):
    corrida_id, linea = await _preparar(mundo)

    respuesta = await _patch(corrida_id, linea, {"pedido_final": bruto})

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-053"
    assert await _valores(mundo, linea) == (
        D("53.00"), D("53.00"), D("24419.75"))
    assert await _historial(mundo, linea) == []


@pytest.mark.parametrize("estado", ["CERRADO", "ENVIADO"])
async def test_a_closed_or_sent_tienda_is_052_ed_06(mundo, estado):
    corrida_id, linea = await _preparar(mundo)
    await _ejecutar(mundo, update(CorridaSucursal).where(
        CorridaSucursal.corrida_id == uuid.UUID(corrida_id),
        CorridaSucursal.sucursal_id == mundo.datos.uno.id,
    ).values(estado_pedido=estado))

    respuesta = await _patch(corrida_id, linea, {"pedido_final": 60})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-052"
    assert await _historial(mundo, linea) == []


async def test_an_annulled_corrida_is_040_ed_06(mundo):
    corrida_id, linea = await _preparar(mundo)
    await _ejecutar(mundo, update(Corrida).where(
        Corrida.id == uuid.UUID(corrida_id)).values(estado="ANULADA"))

    respuesta = await _patch(corrida_id, linea, {"pedido_final": 60})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-040"


async def test_a_scenario_pedido_is_042_ed_07(mundo):
    creada = await _corrida_en_borrador(
        mundo, overrides={"consolidar_sustituidas": True})
    linea = await _linea_id(mundo, creada["id"], mundo.datos.uno.id)
    _como("ADMIN", mundo.datos.usuario.id)

    respuesta = await _patch(creada["id"], linea, {"pedido_final": 60})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-042"
    assert "editar" in respuesta.json()["detail"]["message"]


async def test_an_excluded_line_is_054_ed_08(mundo):
    corrida_id, linea = await _preparar(mundo)
    await _ejecutar(mundo, update(CorridaLinea).where(
        CorridaLinea.id == linea).values(motivo_exclusion="SUSTITUIDA"))

    respuesta = await _patch(corrida_id, linea, {"pedido_final": 60})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-054"


async def test_a_line_of_another_corrida_is_a_404_ed_09(mundo):
    corrida_id, linea = await _preparar(mundo)
    otra = (await _corrida_en_borrador(mundo))["id"]

    respuesta = await _patch(otra, linea, {"pedido_final": 60})

    assert respuesta.status_code == 404
    assert (await _patch(corrida_id, 987654321, {"pedido_final": 1})
            ).status_code == 404
    assert (await _patch(uuid.uuid4(), linea, {"pedido_final": 1})
            ).status_code == 404


async def test_a_closed_sibling_tienda_does_not_block_this_one_ed_09b(mundo):
    corrida_id, uno = await _preparar(mundo)
    dos = await _linea_id(mundo, corrida_id, mundo.datos.dos.id)
    await _ejecutar(mundo, update(CorridaSucursal).where(
        CorridaSucursal.corrida_id == uuid.UUID(corrida_id),
        CorridaSucursal.sucursal_id == mundo.datos.dos.id,
    ).values(estado_pedido="CERRADO"))

    libre = await _patch(corrida_id, uno, {"pedido_final": 60})
    cerrada = await _patch(corrida_id, dos, {"pedido_final": 60})

    assert libre.status_code == 200
    assert cerrada.status_code == 409
    assert cerrada.json()["detail"]["code"] == "E-CORRIDA-052"


async def test_a_stale_esperado_is_066_and_a_fresh_one_passes(mundo):
    corrida_id, linea = await _preparar(mundo)

    viejo = await _patch(
        corrida_id, linea, {"pedido_final": 60, "esperado": "40.00"})
    fresco = await _patch(
        corrida_id, linea, {"pedido_final": 60, "esperado": "53.00"})

    assert viejo.status_code == 409
    assert viejo.json()["detail"]["code"] == "E-CORRIDA-066"
    assert fresco.status_code == 200
    assert await _historial(mundo, linea) == [
        (D("53.00"), D("60.00"), "MANUAL")]


async def test_a_failed_history_insert_rolls_the_edit_back_ed_19(mundo):
    corrida_id, linea = await _preparar(mundo)

    async with mundo.fabrica() as db:
        with pytest.raises(IntegrityError):
            await edicion.editar_linea(
                db, uuid.UUID(corrida_id), linea, 60, None, uuid.uuid4())
        await db.rollback()

    assert await _valores(mundo, linea) == (
        D("53.00"), D("53.00"), D("24419.75"))
    assert await _historial(mundo, linea) == []


# --- Aviso de empaque -------------------------------------------------------


async def test_the_pack_warning_follows_the_quantity_ed_12_to_14(mundo):
    corrida_id, linea = await _preparar(mundo)
    await _ejecutar(mundo, update(CorridaLinea).where(
        CorridaLinea.id == linea).values(unidad_empaque=12))

    fuera = await _patch(corrida_id, linea, {"pedido_final": 30})
    multiplo = await _patch(corrida_id, linea, {"pedido_final": 36})
    cero = await _patch(corrida_id, linea, {"pedido_final": 0})

    assert fuera.json()["linea"]["fuera_de_empaque"] is True
    assert fuera.json()["linea"]["pedido_final"] == "30.00"
    assert multiplo.json()["linea"]["fuera_de_empaque"] is False
    assert cero.json()["linea"]["fuera_de_empaque"] is False


# --- Historial --------------------------------------------------------------


async def test_the_history_is_oldest_first_with_a_consistent_chain(mundo):
    corrida_id, linea = await _preparar(mundo)
    for cantidad in (60, 55):
        await _patch(corrida_id, linea, {"pedido_final": cantidad})

    async with _cliente() as cliente:
        respuesta = await cliente.get(
            f"{BASE}/{corrida_id}/lineas/{linea}/historial")

    filas = respuesta.json()
    assert respuesta.status_code == 200
    assert [(f["valor_anterior"], f["valor_nuevo"]) for f in filas] == [
        ("53.00", "60.00"), ("60.00", "55.00")]
    assert {f["usuario"] for f in filas} == {"Compras"}
    assert {f["motivo"] for f in filas} == {"MANUAL"}


async def test_a_failed_edit_leaves_no_history_ed_18(mundo):
    corrida_id, linea = await _preparar(mundo)

    await _patch(corrida_id, linea, {"pedido_final": -5})
    await _patch(corrida_id, linea, {"pedido_final": 5, "esperado": "1"})

    assert await _historial(mundo, linea) == []


async def test_the_history_of_a_foreign_line_is_a_404(mundo):
    corrida_id, linea = await _preparar(mundo)
    otra = (await _corrida_en_borrador(mundo))["id"]

    async with _cliente() as cliente:
        respuesta = await cliente.get(
            f"{BASE}/{otra}/lineas/{linea}/historial")

    assert respuesta.status_code == 404


# --- Lecturas de líneas -----------------------------------------------------


async def _listar(corrida_id, **params):
    async with _cliente() as cliente:
        respuesta = await cliente.get(
            f"{BASE}/{corrida_id}/lineas", params=params)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def test_q_searches_by_code_and_by_name_case_insensitively_ed_23(
        mundo):
    corrida_id, _ = await _preparar(mundo)
    await _ejecutar(mundo, update(CorridaLinea).where(
        CorridaLinea.corrida_id == uuid.UUID(corrida_id),
        CorridaLinea.codigo_referencia == OTRA,
    ).values(nombre_parte="Bujía de 100% iridio_x"))
    await _ejecutar(mundo, update(CorridaLinea).where(
        CorridaLinea.corrida_id == uuid.UUID(corrida_id),
        CorridaLinea.codigo_referencia == PATRON,
    ).values(nombre_parte="Filtro aceite"))

    por_codigo = await _listar(corrida_id, q="94109")
    por_nombre = await _listar(corrida_id, q="FILTRO")
    con_porcentaje = await _listar(corrida_id, q="100%")
    comodin = await _listar(corrida_id, q="%")
    guion = await _listar(corrida_id, q="iridio_x")
    ninguna = await _listar(corrida_id, q="zzz")

    assert {i["codigo_referencia"] for i in por_codigo["items"]} == {PATRON}
    assert {i["codigo_referencia"] for i in por_nombre["items"]} == {PATRON}
    assert {i["codigo_referencia"] for i in con_porcentaje["items"]} == {OTRA}
    assert {i["codigo_referencia"] for i in comodin["items"]} == {OTRA}
    assert {i["codigo_referencia"] for i in guion["items"]} == {OTRA}
    assert ninguna["total"] == 0


async def test_solo_editadas_counts_the_filtered_set_ed_24(mundo):
    corrida_id, linea = await _preparar(mundo)
    await _patch(corrida_id, linea, {"pedido_final": 60})

    todas = await _listar(corrida_id)
    editadas = await _listar(corrida_id, solo_editadas="true")

    assert todas["total"] == 3
    assert editadas["total"] == 1
    assert editadas["items"][0]["id"] == linea
    assert editadas["items"][0]["editado_por"] == "Compras"


async def test_solo_fuera_empaque_and_combined_filters_ed_25(mundo):
    corrida_id, linea = await _preparar(mundo)
    await _ejecutar(mundo, update(CorridaLinea).where(
        CorridaLinea.corrida_id == uuid.UUID(corrida_id),
    ).values(unidad_empaque=12))
    await _patch(corrida_id, linea, {"pedido_final": 60})  # 60 = 5 x 12
    todas = (await _listar(corrida_id))["items"]
    # Independiente del SQL: positivo y no múltiplo de 12.
    esperadas = {
        i["id"] for i in todas
        if D(i["pedido_final"]) > 0 and D(i["pedido_final"]) % 12 != 0}

    fuera = await _listar(corrida_id, solo_fuera_empaque="true")
    editada_y_fuera = await _listar(
        corrida_id, solo_fuera_empaque="true", solo_editadas="true")
    combinado = await _listar(
        corrida_id, solo_editadas="true", q="94109",
        clase=next(i["clase"] for i in todas if i["id"] == linea))

    assert esperadas and linea not in esperadas
    assert {i["id"] for i in fuera["items"]} == esperadas
    assert fuera["total"] == len(esperadas)
    assert all(i["fuera_de_empaque"] for i in fuera["items"])
    assert editada_y_fuera["total"] == 0
    assert [i["id"] for i in combinado["items"]] == [linea]


async def test_every_listed_line_has_id_and_neutral_marks_when_untouched(
        mundo):
    corrida_id, _ = await _preparar(mundo)

    pagina = await _listar(corrida_id)

    assert pagina["total"] == 3
    for item in pagina["items"]:
        assert isinstance(item["id"], int)
        assert item["editada"] is False and item["editado_por"] is None
        assert item["motivo_edicion"] is None


# --- Totales "a pedir" junto a los del sugerido ------------------------------


async def test_the_detail_keeps_the_suggestion_and_adds_a_pedir_ed_26_27(
        mundo):
    corrida_id, linea = await _preparar(mundo)
    async with _cliente() as cliente:
        antes = (await cliente.get(f"{BASE}/{corrida_id}")).json()
    await _patch(corrida_id, linea, {"pedido_final": 60})
    async with _cliente() as cliente:
        despues = (await cliente.get(f"{BASE}/{corrida_id}")).json()

    assert despues["totales"] == antes["totales"]
    assert despues["resumen"] == antes["resumen"]
    assert despues["resumen_por_clase"] == antes["resumen_por_clase"]
    assert D(despues["totales_a_pedir"]["unidades"]) == (
        D(antes["totales"]["unidades"]) + 7)
    assert D(despues["totales_a_pedir"]["valor"]) == (
        D(antes["totales"]["valor"]) + D("27645.00") - D("24419.75"))
    uno = [r for r in despues["resumen_a_pedir"]
           if r["sucursal_id"] == str(mundo.datos.uno.id)]
    total = next(r for r in uno if r["clase"] == "TOTAL")
    assert D(total["unidades"]) == D("60")
    assert sum(D(r["porcentaje_peso"]) for r in uno
               if r["clase"] != "TOTAL") == D("1")


async def test_a_pedir_equals_the_suggestion_before_any_edit(mundo):
    corrida_id, _ = await _preparar(mundo)

    async with _cliente() as cliente:
        cuerpo = (await cliente.get(f"{BASE}/{corrida_id}")).json()

    assert cuerpo["totales_a_pedir"]["unidades"] == (
        cuerpo["totales"]["unidades"])
    assert D(cuerpo["totales_a_pedir"]["valor"]) == D(
        cuerpo["totales"]["valor"])


# --- Reproducción (ADR-4) ---------------------------------------------------


async def test_an_edited_corrida_still_replays_identical_ed_28(mundo):
    corrida_id, linea = await _preparar(mundo)
    await _patch(corrida_id, linea, {"pedido_final": 99})

    async with mundo.fabrica() as db:
        reporte = await rp.reproducir(db, uuid.UUID(corrida_id))

    assert reporte.identico is True and reporte.diferencias == ()


async def test_a_tampered_suggestion_is_still_detected_ed_29(mundo):
    corrida_id, linea = await _preparar(mundo)
    await _patch(corrida_id, linea, {"pedido_final": 99})
    await _ejecutar(mundo, update(CorridaLinea).where(
        CorridaLinea.id == linea).values(pedido_sugerido=D("1.00")))

    async with mundo.fabrica() as db:
        reporte = await rp.reproducir(db, uuid.UUID(corrida_id))

    assert reporte.identico is False
    assert [d.columna for d in reporte.diferencias] == ["pedido_sugerido"]


async def test_history_rows_cascade_with_their_corrida(mundo):
    corrida_id, linea = await _preparar(mundo)
    await _patch(corrida_id, linea, {"pedido_final": 60})

    await _ejecutar(mundo, Corrida.__table__.delete().where(
        Corrida.id == uuid.UUID(corrida_id)))

    async with mundo.fabrica() as db:
        assert (await db.execute(select(func.count()).select_from(
            CorridaLineaHistorial))).scalar_one() == 0
