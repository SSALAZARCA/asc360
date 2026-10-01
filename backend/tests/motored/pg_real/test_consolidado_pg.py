"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B6, ADR-8, decisión
F4-9, spec CO-01..CO-11): la matriz consolidada contra un Postgres real
(opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base migrada con `alembic -c alembic_motored.ini upgrade head`. Las
peticiones entran por la app real (ASGI, `httpx`), con el usuario inyectado
y la sesión real; todo dentro de la transacción que revierte `fabrica`.

Dos partes:

- Un mundo chico y exacto (tres tiendas con su pedido en BORRADOR, CERRADO y
  ENVIADO, una fallida, una línea excluida y referencias en 0) para cada
  regla: totales por tienda, por referencia y general, paginación que no
  toca los totales, búsqueda, columnas marcadas, estados, ediciones y 404.
- El volumen real: 47 tiendas por 3.000 referencias (141.000 líneas). Se
  recorren TODAS las páginas y se verifica que no falta ni sobra ninguna
  referencia, que las celdas suman los totales de cada tienda, que el
  número de consultas no crece con el tamaño y cuánto tarda cada página.
"""
import time
import uuid
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from app.main import app
from app.motored.database import get_motored_db
from tests.motored.pg_real import siembra_vistas as sv
from tests.motored.pg_real.test_corridas_api_pg import (  # noqa: F401
    BASE,
    URL,
    _app_lista,
    _cliente,
    _como,
    _sesion_de,
    fabrica,
)

pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

D = Decimal
TIENDAS = 47
REFERENCIAS = 3000
PAGINA = 100
# Cada página debe responder holgadamente por debajo de esto (en una
# máquina de desarrollo mide una fracción de segundo).
LIMITE_SEGUNDOS = 3.0
# La corrida, las columnas, la página y sus celdas: nunca una consulta por
# tienda ni por referencia.
CONSULTAS_DE_DATOS = 4


async def _sembrar(db):
    """Cuatro tiendas (BORRADOR, CERRADO, ENVIADO y una fallida) y cinco
    referencias; `R3` en 0 en todas y `R5` sólo como línea excluida."""
    suf = sv.sufijo_nuevo()
    datos = await sv.base(db, suf)
    t0, t1, t2, t3 = await sv.tiendas(db, suf, 4)
    corrida = await sv.corrida(db, datos, suf, 1)
    await sv.estados_de_tiendas(db, corrida, [
        (t0, "OK", "BORRADOR"), (t1, "OK", "CERRADO"),
        (t2, "OK", "ENVIADO"), (t3, "FALLIDA", None)])
    r = {}
    for clave, codigo, nombre in (
            ("r1", "00-A", "Filtro aceite"), ("r2", "00-B", "Bujia"),
            ("r3", "00-C", "Banda"), ("r4", "50%_X", "Tornillo"),
            ("r5", "99-X", "Sustituida")):
        r[clave] = await sv.referencia_a_mano(
            db, datos, f"{codigo}-{suf}", nombre)
    cantidades = (
        (t0, "r1", 5), (t0, "r2", 7), (t0, "r3", 0), (t0, "r4", 2),
        (t1, "r1", 7), (t1, "r2", 0), (t1, "r3", 0),
        (t2, "r1", 0), (t2, "r2", 3), (t2, "r3", 0))
    db.add_all([
        sv.linea(corrida, t, r[k].codigo, r[k].id, q, nombre=r[k].nombre)
        for t, k, q in cantidades])
    db.add(sv.linea(
        corrida, t0, r["r5"].codigo, r["r5"].id, 100,
        exclusion="SUSTITUIDA"))
    await db.commit()
    return SimpleNamespace(
        suf=suf, datos=datos, corrida=corrida, tiendas=(t0, t1, t2, t3),
        r=r)


@pytest.fixture
async def mundo(fabrica):  # noqa: F811
    async with fabrica() as db:
        mundo_ = await _sembrar(db)
    app.dependency_overrides[get_motored_db] = _sesion_de(fabrica)
    _como("COMPRAS", mundo_.datos.usuario.id)
    mundo_.fabrica = fabrica
    return mundo_


async def _ver(mundo, corrida=None, **params):
    corrida = corrida or mundo.corrida
    async with _cliente() as cliente:
        return await cliente.get(
            f"{BASE}/{corrida.id}/consolidado", params=params)


async def _matriz(mundo, **params):
    respuesta = await _ver(mundo, **params)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _codigos(cuerpo, mundo):
    sufijo = f"-{mundo.suf}"
    return [f["codigo"].removesuffix(sufijo) for f in cuerpo["filas"]]


# --- Totales (CO-01, CO-02, CO-08) ------------------------------------------


async def test_totals_per_tienda_per_reference_and_overall_co_01_co_02(mundo):
    cuerpo = await _matriz(mundo)

    columnas = {t["nombre"].split("-")[0]: t for t in cuerpo["tiendas"]}
    assert columnas["T00"]["unidades"] == "14.00"
    assert columnas["T00"]["valor"] == "1400.00"
    assert columnas["T01"]["unidades"] == "7.00"
    assert columnas["T02"]["unidades"] == "3.00"
    assert cuerpo["totales"] == {"unidades": "24.00", "valor": "2400.00"}
    por_codigo = {
        f["codigo"].removesuffix(f"-{mundo.suf}"): f["total"]
        for f in cuerpo["filas"]}
    assert por_codigo == {"00-A": "12.00", "00-B": "10.00", "50%_X": "2.00"}


async def test_the_cells_are_sparse_and_exact_co_02(mundo):
    cuerpo = await _matriz(mundo)

    t0, t1, t2, _ = (str(t.id) for t in mundo.tiendas)
    filas = {
        f["codigo"].removesuffix(f"-{mundo.suf}"): f["celdas"]
        for f in cuerpo["filas"]}
    assert filas["00-A"] == {t0: "5.00", t1: "7.00"}
    assert filas["00-B"] == {t0: "7.00", t2: "3.00"}
    assert filas["50%_X"] == {t0: "2.00"}


async def test_the_rows_carry_code_and_name_sorted_by_code_f4_9(mundo):
    cuerpo = await _matriz(mundo)

    assert _codigos(cuerpo, mundo) == ["00-A", "00-B", "50%_X"]
    assert [f["nombre"] for f in cuerpo["filas"]] == [
        "Filtro aceite", "Bujia", "Tornillo"]


async def test_references_with_nothing_to_order_are_not_rows(mundo):
    cuerpo = await _matriz(mundo)

    assert "00-C" not in _codigos(cuerpo, mundo)
    assert cuerpo["total"] == 3


async def test_excluded_lines_never_appear_nor_count_co_08(mundo):
    cuerpo = await _matriz(mundo)

    assert "99-X" not in _codigos(cuerpo, mundo)
    assert cuerpo["totales"]["unidades"] == "24.00"


# --- Columnas (CO-06, CO-11) ------------------------------------------------


async def test_the_failed_tienda_is_a_flagged_column_without_data_co_06(
        mundo):
    cuerpo = await _matriz(mundo)

    fallida = cuerpo["tiendas"][3]
    assert fallida["estado"] == "FALLIDA"
    assert fallida["codigo"] == "E-CORRIDA-020"
    assert fallida["mensaje"] == "sin empaque"
    assert fallida["unidades"] is None and fallida["valor"] is None
    assert str(mundo.tiendas[3].id) not in {
        k for f in cuerpo["filas"] for k in f["celdas"]}


async def test_each_column_shows_its_pedido_state_co_11(mundo):
    cuerpo = await _matriz(mundo)

    assert [t["estado_pedido"] for t in cuerpo["tiendas"]] == [
        "BORRADOR", "CERRADO", "ENVIADO", None]
    assert [t["nombre"].split("-")[0] for t in cuerpo["tiendas"]] == [
        "T00", "T01", "T02", "T03"]


async def test_the_pedido_state_filter_keeps_only_those_columns(mundo):
    cuerpo = await _matriz(mundo, estado_pedido="CERRADO")

    assert [t["estado_pedido"] for t in cuerpo["tiendas"]] == ["CERRADO"]
    assert cuerpo["totales"]["unidades"] == "7.00"
    assert _codigos(cuerpo, mundo) == ["00-A"]
    assert cuerpo["filas"][0]["total"] == "7.00"


# --- Paginación y búsqueda (CO-03, CO-05) -----------------------------------


async def test_paging_keeps_the_full_totals_co_03(mundo):
    cuerpo = await _matriz(mundo, limite=1, offset=1)

    assert _codigos(cuerpo, mundo) == ["00-B"]
    assert (cuerpo["total"], cuerpo["limite"], cuerpo["offset"]) == (3, 1, 1)
    assert cuerpo["totales"]["unidades"] == "24.00"
    assert [t["unidades"] for t in cuerpo["tiendas"][:3]] == [
        "14.00", "7.00", "3.00"]


async def test_a_page_past_the_end_is_empty_with_the_real_count(mundo):
    cuerpo = await _matriz(mundo, limite=1, offset=10)

    assert cuerpo["filas"] == [] and cuerpo["total"] == 3


async def test_the_search_filters_rows_but_never_the_totals_co_05(mundo):
    cuerpo = await _matriz(mundo, q="bujia")

    assert _codigos(cuerpo, mundo) == ["00-B"]
    assert cuerpo["total"] == 1
    assert cuerpo["totales"]["unidades"] == "24.00"
    assert cuerpo["tiendas"][0]["unidades"] == "14.00"


@pytest.mark.parametrize("q,esperado", [
    ("00-a", ["00-A"]), ("FILTRO", ["00-A"]), ("%", ["50%_X"]),
    ("_X", ["50%_X"]), ("50%_", ["50%_X"]), ("nada", [])])
async def test_the_search_matches_code_or_name_with_escaped_wildcards(
        mundo, q, esperado):
    cuerpo = await _matriz(mundo, q=q)

    assert _codigos(cuerpo, mundo) == esperado


# --- Ediciones, estados y errores (CO-04, CO-10) ----------------------------


async def test_an_edit_is_reflected_in_the_cell_and_the_totals_co_04(mundo):
    async with mundo.fabrica() as db:
        await db.execute(text(
            "UPDATE corrida_linea SET pedido_final = 9, valor_pedido = 900 "
            "WHERE corrida_id = :c AND sucursal_id = :s "
            "AND codigo_referencia LIKE '00-A-%'"),
            {"c": mundo.corrida.id, "s": mundo.tiendas[0].id})
        await db.commit()

    cuerpo = await _matriz(mundo)

    primera = cuerpo["filas"][0]
    assert primera["celdas"][str(mundo.tiendas[0].id)] == "9.00"
    assert primera["total"] == "16.00"
    assert cuerpo["tiendas"][0]["unidades"] == "18.00"
    assert cuerpo["totales"]["unidades"] == "28.00"


async def test_the_matrix_equals_the_sum_of_the_tienda_pedidos_f4_9(mundo):
    cuerpo = await _matriz(mundo)

    suma = D(0)
    async with _cliente() as cliente:
        for tienda in mundo.tiendas[:3]:
            cabecera = (await cliente.get(
                f"{BASE}/{mundo.corrida.id}/sucursales/{tienda.id}")).json()
            suma += D(cabecera["totales"]["unidades_a_pedir"])

    assert D(cuerpo["totales"]["unidades"]) == suma == D("24.00")


async def test_a_corrida_still_calculating_is_an_empty_matrix_co_10(mundo):
    async with mundo.fabrica() as db:
        pendiente = await sv.corrida(
            db, mundo.datos, mundo.suf, 2, estado="PENDIENTE")
        await db.commit()

    cuerpo = await _matriz(mundo, corrida=pendiente)

    assert cuerpo["estado"] == "PENDIENTE"
    assert cuerpo["tiendas"] == [] and cuerpo["filas"] == []
    assert cuerpo["total"] == 0
    assert cuerpo["totales"] == {"unidades": "0.00", "valor": "0.00"}


async def test_a_scenario_can_be_viewed_and_is_marked(mundo):
    async with mundo.fabrica() as db:
        escenario = await sv.corrida(
            db, mundo.datos, mundo.suf, 3, escenario=True)
        t0 = mundo.tiendas[0]
        await sv.estados_de_tiendas(db, escenario, [(t0, "OK", None)])
        db.add(sv.linea(
            escenario, t0, mundo.r["r1"].codigo, mundo.r["r1"].id, 4))
        await db.commit()

    cuerpo = await _matriz(mundo, corrida=escenario)

    assert cuerpo["es_escenario"] is True
    assert cuerpo["tiendas"][0]["estado_pedido"] is None
    assert cuerpo["totales"]["unidades"] == "4.00"


async def test_an_unknown_corrida_is_a_404(mundo):
    respuesta = await _ver(
        mundo, corrida=SimpleNamespace(id=uuid.UUID(int=123456)))

    assert respuesta.status_code == 404


# --- Volumen: 47 tiendas por 3.000 referencias ------------------------------


@contextmanager
def _contar_consultas():
    """Cuenta las consultas de datos de la corrida que llegan a la base
    mientras está activo (no la sonda de salud ni los savepoints)."""
    cuenta = {"n": 0}

    def escuchar(conn, cursor, statement, *args, **kwargs):
        if statement.lstrip().startswith("SELECT corrida"):
            cuenta["n"] += 1

    event.listen(Engine, "before_cursor_execute", escuchar)
    try:
        yield cuenta
    finally:
        event.remove(Engine, "before_cursor_execute", escuchar)


@pytest.fixture
async def volumen(fabrica):  # noqa: F811
    async with fabrica() as db:
        suf = sv.sufijo_nuevo()
        datos = await sv.base(db, suf)
        tiendas = await sv.tiendas(db, suf, TIENDAS)
        await sv.referencias(db, datos.proveedor, suf, REFERENCIAS)
        corrida = await sv.corrida(db, datos, suf, 1)
        await sv.estados_de_tiendas(db, corrida, [
            (t, "OK", ("BORRADOR", "CERRADO", "ENVIADO")[i % 3])
            for i, t in enumerate(tiendas)])
        await sv.lineas_en_bloque(db, corrida, suf, aparte=100)
        await db.commit()
    app.dependency_overrides[get_motored_db] = _sesion_de(fabrica)
    _como("COMPRAS", datos.usuario.id)
    return SimpleNamespace(
        fabrica=fabrica, corrida=corrida, suf=suf, tiendas=tiendas)


async def _esperado(volumen):
    """Lo que dice la base, con SQL propio: referencias con algo que pedir,
    total general y total por tienda de `pedido_final`."""
    async with volumen.fabrica() as db:
        c = {"c": volumen.corrida.id}
        lineas = (await db.execute(text(
            "SELECT count(*) FROM corrida_linea WHERE corrida_id = :c"),
            c)).scalar_one()
        referencias = (await db.execute(text(
            "SELECT count(*) FROM (SELECT 1 FROM corrida_linea "
            "WHERE corrida_id = :c GROUP BY referencia_id "
            "HAVING sum(pedido_final) > 0) x"), c)).scalar_one()
        total = (await db.execute(text(
            "SELECT sum(pedido_final) FROM corrida_linea "
            "WHERE corrida_id = :c"), c)).scalar_one()
        por_tienda = dict((await db.execute(text(
            "SELECT sucursal_id::text, sum(pedido_final) FROM corrida_linea "
            "WHERE corrida_id = :c GROUP BY sucursal_id"), c)).all())
    return SimpleNamespace(
        lineas=lineas, referencias=referencias, total=total,
        por_tienda=por_tienda)


async def _recorrer(volumen, **params):
    """Todas las páginas, con lo que tardó y pesó cada una."""
    paginas, offset = [], 0
    async with _cliente() as cliente:
        while True:
            inicio = time.perf_counter()
            respuesta = await cliente.get(
                f"{BASE}/{volumen.corrida.id}/consolidado",
                params={"limite": PAGINA, "offset": offset, **params})
            segundos = time.perf_counter() - inicio
            assert respuesta.status_code == 200, respuesta.text
            cuerpo = respuesta.json()
            paginas.append((cuerpo, segundos, len(respuesta.content)))
            offset += PAGINA
            if offset >= cuerpo["total"]:
                return paginas


async def test_the_volume_has_the_expected_size(volumen):
    esperado = await _esperado(volumen)

    assert esperado.lineas == TIENDAS * REFERENCIAS == 141000
    assert 0 < esperado.referencias <= REFERENCIAS


async def test_every_page_is_complete_and_no_reference_is_lost(volumen):
    esperado = await _esperado(volumen)

    paginas = await _recorrer(volumen)

    codigos = [f["codigo"] for p, _, _ in paginas for f in p[
        "filas"]]
    assert len(codigos) == len(set(codigos)) == esperado.referencias
    assert codigos == sorted(codigos)
    assert all(p["total"] == esperado.referencias for p, _, _ in paginas)
    assert len(paginas) == -(-esperado.referencias // PAGINA)


async def test_the_totals_are_the_database_totals_at_every_page(volumen):
    esperado = await _esperado(volumen)

    paginas = await _recorrer(volumen)

    for cuerpo, _, _ in paginas:
        assert D(cuerpo["totales"]["unidades"]) == esperado.total
        for tienda in cuerpo["tiendas"]:
            assert D(tienda["unidades"]) == esperado.por_tienda[
                tienda["sucursal_id"]]


async def test_the_cells_add_up_to_the_tienda_and_reference_totals(volumen):
    paginas = await _recorrer(volumen)

    por_tienda = {}
    for cuerpo, _, _ in paginas:
        for fila in cuerpo["filas"]:
            assert sum(D(v) for v in fila["celdas"].values()) == D(
                fila["total"])
            for sid, cantidad in fila["celdas"].items():
                por_tienda[sid] = por_tienda.get(sid, D(0)) + D(cantidad)
    columnas = paginas[0][0]["tiendas"]
    assert len(columnas) == TIENDAS
    for tienda in columnas:
        assert por_tienda[tienda["sucursal_id"]] == D(tienda["unidades"])


async def test_one_page_takes_exactly_four_data_queries(volumen):
    with _contar_consultas() as consultas:
        async with _cliente() as cliente:
            respuesta = await cliente.get(
                f"{BASE}/{volumen.corrida.id}/consolidado")

    assert respuesta.status_code == 200
    assert consultas["n"] == CONSULTAS_DE_DATOS


async def test_every_page_answers_fast_and_stays_small(volumen):
    paginas = await _recorrer(volumen)

    lento = max(segundos for _, segundos, _ in paginas)
    pesado = max(bytes_ for _, _, bytes_ in paginas)
    print(f"\nconsolidado {TIENDAS}x{REFERENCIAS}: {len(paginas)} paginas, "
          f"max {lento:.3f}s, media "
          f"{sum(s for _, s, _ in paginas) / len(paginas):.3f}s, "
          f"max {pesado / 1024:.0f} KB")
    assert lento < LIMITE_SEGUNDOS
    assert pesado < 1_000_000


async def test_the_search_and_the_state_filter_hold_at_volume(volumen):
    busqueda = (await _recorrer(volumen, q="R00"))
    cerradas = (await _recorrer(volumen, estado_pedido="CERRADO"))

    assert all(len(c["tiendas"]) == TIENDAS for c, _, _ in busqueda)
    assert all(
        f["codigo"].startswith("R00") for c, _, _ in busqueda
        for f in c["filas"])
    assert {t["estado_pedido"] for t in cerradas[0][0]["tiendas"]} == {
        "CERRADO"}
    assert len(cerradas[0][0]["tiendas"]) == len(
        [i for i in range(TIENDAS) if i % 3 == 1])
