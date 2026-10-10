"""
Inventory counts, the leader panel's "Contadas" chip, the reference
search and the per-reference detail against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`, database migrated to head;
odd/tasks/motored-conteo-panel-busqueda.md).

Same savepoint harness and scene as `test_conteos_reconteos_pg.py`:
snapshot A=10, B=10, D=3, E=5 (C is outside it). Round 1 by pair UNO:
A = 5 (A3) + 3 (B1) with a voided 4, B = 1, C = 2, D = 3 and one
unknown code. Every request shares one outer transaction, so `now()`
is the same for all readings: the tests move `recibida_en` by hand to
prove the "latest reading first" order.
"""
import uuid

from sqlalchemy import text

from tests.motored.pg_real import test_conteos_reconteos_pg as base
from tests.motored.pg_real.test_conteos_api_pg import (  # noqa: F401
    BASE, llamar, pytestmark,
)

fabrica = base.fabrica
_app_lista = base._app_lista
abierto = base.abierto
escena = base.escena


async def _mas_tarde(fabrica, codigo, minutos):
    """Moves the live readings of `codigo` `minutos` into the future."""
    async with fabrica() as db:
        await db.execute(text(
            "UPDATE conteo_lectura SET recibida_en = recibida_en"
            " + make_interval(mins => :m) WHERE codigo_leido = :c"),
            {"m": minutos, "c": codigo})
        await db.commit()


async def _leer_tabla(mundo, ruta):
    r = await base._lider(mundo, "GET", ruta)
    assert r.status_code == 200, r.text
    return r.json()


def _codigos(cuerpo):
    return [i["codigo"] for i in cuerpo["items"]]


# --- the "contadas" chip -----------------------------------------------------


async def test_counted_lists_every_read_code_latest_first(escena, fabrica):
    await base._ronda_uno(escena)
    cod = escena.codigos
    await _mas_tarde(fabrica, cod["D"], 30)
    await _mas_tarde(fabrica, cod["B"], 10)

    cuerpo = await _leer_tabla(escena, "/diferencias?filtro=contadas")

    codigos = _codigos(cuerpo)
    # D matches its system (no difference) and still shows; E was
    # never read and does not.
    assert codigos[:2] == [cod["D"], cod["B"]]
    assert set(codigos) == {
        cod["A"], cod["B"], cod["C"], cod["D"], escena.desconocido}
    assert cuerpo["contadas"] == 5
    assert all(i["ultima_lectura_en"] for i in cuerpo["items"])


async def test_the_counted_count_reaches_the_panel(escena):
    await base._ronda_uno(escena)

    r = await base._lider(escena, "GET", "/panel")

    assert r.status_code == 200, r.text
    assert r.json()["diferencias_resumen"]["contadas"] == 5


async def test_the_polled_table_carries_the_last_reading(escena):
    await base._ronda_uno(escena)

    cuerpo = await _leer_tabla(escena, "/diferencias")

    items = {i["codigo"]: i for i in cuerpo["items"]}
    assert items[escena.codigos["A"]]["ultima_lectura_en"] is not None
    assert items[escena.codigos["E"]]["ultima_lectura_en"] is None
    assert cuerpo["contadas"] is None


# --- the search --------------------------------------------------------------


async def test_a_hyphen_less_lowercase_code_finds_the_reference(escena):
    await base._ronda_uno(escena)
    codigo = escena.codigos["D"]
    q = codigo.replace("-", "").lower()

    cuerpo = await _leer_tabla(escena, f"/diferencias?q={q}")

    # D has no difference: the search reaches every code of the conteo.
    assert _codigos(cuerpo) == [codigo]
    assert cuerpo["total"] == 5


async def test_part_of_the_name_combines_with_the_chip(escena):
    await base._ronda_uno(escena)
    cod = escena.codigos

    todas = await _leer_tabla(escena, "/diferencias?q=REPUESTO")
    contadas = await _leer_tabla(
        escena, "/diferencias?filtro=contadas&q=repuesto")

    assert set(_codigos(todas)) == {
        cod["A"], cod["B"], cod["C"], cod["D"], cod["E"]}
    assert set(_codigos(contadas)) == {
        cod["A"], cod["B"], cod["C"], cod["D"]}


async def test_an_unknown_code_is_found_by_its_read_code(escena):
    await base._ronda_uno(escena)

    cuerpo = await _leer_tabla(
        escena, f"/diferencias?q={escena.desconocido[:6]}")

    assert _codigos(cuerpo) == [escena.desconocido]


# --- the detail --------------------------------------------------------------


async def test_the_detail_splits_locations_and_skips_voided(escena):
    uno = await base._ronda_uno(escena)
    codigo = escena.codigos["A"]

    cuerpo = await _leer_tabla(
        escena, f"/diferencias/detalle?codigo={codigo}")

    lineas = {ln["ubicacion"]: ln for ln in cuerpo["lineas"]}
    assert set(lineas) == {"Estante A3", "Estante B1"}
    # A3: 5 (the voided 4 is out); B1: 3.
    assert (lineas["Estante A3"]["cantidad"],
            lineas["Estante B1"]["cantidad"]) == ("5.00", "3.00")
    a3 = lineas["Estante A3"]
    assert a3["ronda"] == 1 and a3["sesion"]["id"] == str(uno.id)
    assert a3["sesion"]["etiqueta"].startswith("Pareja 1")
    assert cuerpo["ultima_lectura_en"] is not None


async def test_the_detail_of_an_unread_code_is_empty(escena):
    await base._ronda_uno(escena)

    cuerpo = await _leer_tabla(
        escena, f"/diferencias/detalle?codigo={escena.codigos['E']}")

    assert cuerpo["lineas"] == [] and cuerpo["ultima_lectura_en"] is None


async def test_the_detail_shows_round_two_by_the_assignee(escena, fabrica):
    await base._ronda_uno(escena)
    await base._terminar_ronda(escena)
    rec = await base._reconteos(fabrica, escena)
    codigo = escena.codigos["E"]
    tres = await base._unirse(escena, base.TRES)
    r = await base._asignar(escena, rec[codigo], tres)
    assert r.status_code == 200, r.text
    await base._ubicar(escena, tres, "UBI-A3")
    await base._leer(escena, tres, base._item(
        codigo, "4", reconteo_id=rec[codigo].id))

    cuerpo = await _leer_tabla(
        escena, f"/diferencias/detalle?codigo={codigo}")

    assert [(ln["ronda"], ln["cantidad"], ln["sesion"]["id"])
            for ln in cuerpo["lineas"]] == [(2, "4.00", str(tres.id))]


# --- visibility --------------------------------------------------------------


async def test_another_leader_gets_a_404(escena):
    await base._ronda_uno(escena)
    ajeno = ("LIDER_INVENTARIOS", uuid.uuid4())
    codigo = escena.codigos["A"]

    for ruta in ("/diferencias?filtro=contadas", f"/diferencias?q={codigo}",
                 f"/diferencias/detalle?codigo={codigo}"):
        r = await llamar(
            "GET", f"{BASE}/{escena.conteo.id}{ruta}", ajeno)
        assert r.status_code == 404, (ruta, r.text)


async def test_gerencia_reads_the_detail(escena):
    await base._ronda_uno(escena)

    r = await llamar(
        "GET", f"{BASE}/{escena.conteo.id}/diferencias/detalle"
        f"?codigo={escena.codigos['A']}", ("GERENCIA", uuid.uuid4()))

    assert r.status_code == 200, r.text
