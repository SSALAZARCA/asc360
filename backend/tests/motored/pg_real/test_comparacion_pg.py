"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B6, ADR-9, decisión
F4-8, spec SC-07..SC-13): comparar un escenario con su corrida real contra un
Postgres real (opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base migrada con `alembic -c alembic_motored.ini upgrade head`. Las
peticiones entran por la app real (ASGI, `httpx`), con el usuario inyectado
y la sesión real; todo dentro de la transacción que revierte `fabrica`.

Dos partes:

- Un mundo chico y exacto: cuatro tiendas, una corrida real y un escenario
  con referencias de un solo lado, una línea excluida, una tienda fallida en
  la real y otra que sólo está en el escenario. Verifica el FULL OUTER JOIN
  (el delta con signo, lo que falta de un lado vale 0), los totales por
  tienda de los dos lados (con el valor sugerido), `solo_diferencias`, el
  filtro por tienda, la paginación, las tiendas no comparables y cada forma
  de emparejamiento inválido (E-CORRIDA-063).
- El volumen real: 47 tiendas por 3.000 referencias en cada lado (282.000
  líneas). Se recorren TODAS las páginas de las diferencias y se verifican
  contra SQL propio; el número de consultas no crece con el tamaño y cada
  página tarda una fracción de segundo.
"""
import datetime
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
from app.motored.models.proveedor import Proveedor
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
LIMITE_SEGUNDOS = 3.0
# Las dos corridas, sus tiendas, las filas y los totales: nunca una consulta
# por tienda ni por referencia.
CONSULTAS_DE_DATOS = 4


async def _sembrar(db):
    """La corrida real (A y B calculadas, C fallida) y el escenario (A, B, C
    y D calculadas), con `r4` sólo en la real, `r5` sólo en el escenario y
    `r6` excluida en el escenario."""
    suf = sv.sufijo_nuevo()
    datos = await sv.base(db, suf)
    a, b, c, d = await sv.tiendas(db, suf, 4)
    real = await sv.corrida(db, datos, suf, 1)
    esc = await sv.corrida(db, datos, suf, 2, escenario=True)
    await sv.estados_de_tiendas(db, real, [
        (a, "OK", "BORRADOR"), (b, "OK", "CERRADO"),
        (c, "FALLIDA", None)])
    await sv.estados_de_tiendas(db, esc, [
        (t, "OK", None) for t in (a, b, c, d)])
    r = {}
    for clave, codigo in (
            ("r1", "00-A"), ("r2", "00-B"), ("r4", "00-D"),
            ("r5", "00-E"), ("r6", "00-F")):
        r[clave] = await sv.referencia_a_mano(db, datos, f"{codigo}-{suf}")
    def lin(corrida, tienda, clave, final, **kw):
        return sv.linea(
            corrida, tienda, r[clave].codigo, r[clave].id, final, **kw)

    db.add_all([
        lin(real, a, "r1", 55, sugerido=50), lin(real, a, "r2", 10),
        lin(real, a, "r4", 4), lin(real, b, "r1", 20),
        lin(real, b, "r2", 0),
        lin(esc, a, "r1", 62), lin(esc, a, "r2", 10),
        lin(esc, a, "r5", 8),
        lin(esc, a, "r6", 50, exclusion="SUSTITUIDA"),
        lin(esc, b, "r1", 20), lin(esc, b, "r2", 5),
        lin(esc, c, "r1", 9), lin(esc, d, "r1", 3)])
    await db.commit()
    return SimpleNamespace(
        suf=suf, datos=datos, real=real, esc=esc, tiendas=(a, b, c, d))


@pytest.fixture
async def mundo(fabrica):  # noqa: F811
    async with fabrica() as db:
        mundo_ = await _sembrar(db)
    app.dependency_overrides[get_motored_db] = _sesion_de(fabrica)
    _como("COMPRAS", mundo_.datos.usuario.id)
    mundo_.fabrica = fabrica
    return mundo_


async def _pedir(mundo, escenario=None, con=None, **params):
    escenario = escenario or mundo.esc
    con = con or mundo.real
    async with _cliente() as cliente:
        return await cliente.get(
            f"{BASE}/{escenario.id}/comparar",
            params={"con": str(con.id), **params})


async def _comparar(mundo, **params):
    respuesta = await _pedir(mundo, **params)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _clave(fila, mundo):
    """`(tienda, código)` sin el sufijo de la siembra."""
    return (fila["sucursal"].split("-")[0],
            fila["codigo"].removesuffix(f"-{mundo.suf}"))


def _por_clave(cuerpo, mundo):
    return {_clave(f, mundo): f for f in cuerpo["filas"]}


# --- Filas (SC-07, SC-08) ---------------------------------------------------


async def test_every_row_has_both_sides_and_a_signed_delta_sc_07(mundo):
    cuerpo = await _comparar(mundo)

    filas = _por_clave(cuerpo, mundo)
    a1 = filas[("T00", "00-A")]
    assert (a1["sugerido_real"], a1["sugerido_prueba"], a1["delta"]) == (
        "50.00", "62.00", "12.00")
    assert a1["pedido_final_real"] == "55.00"
    assert (a1["clase_real"], a1["clase_prueba"]) == ("AF", "AF")
    assert filas[("T00", "00-B")]["delta"] == "0.00"
    assert filas[("T01", "00-A")]["delta"] == "0.00"


async def test_a_reference_on_one_side_counts_as_zero_on_the_other_sc_08(
        mundo):
    filas = _por_clave(await _comparar(mundo), mundo)

    solo_real = filas[("T00", "00-D")]
    assert (solo_real["sugerido_real"], solo_real["sugerido_prueba"],
            solo_real["delta"]) == ("4.00", "0.00", "-4.00")
    assert solo_real["clase_prueba"] is None
    solo_escenario = filas[("T00", "00-E")]
    assert (solo_escenario["sugerido_real"], solo_escenario["delta"]) == (
        "0.00", "8.00")
    assert solo_escenario["pedido_final_real"] == "0.00"
    assert solo_escenario["clase_real"] is None
    # La línea que existe en la real con 0 y en el escenario con 5.
    assert filas[("T01", "00-B")]["delta"] == "5.00"


async def test_the_rows_are_ordered_by_tienda_then_code_and_counted(mundo):
    cuerpo = await _comparar(mundo)

    assert [_clave(f, mundo) for f in cuerpo["filas"]] == [
        ("T00", "00-A"), ("T00", "00-B"), ("T00", "00-D"), ("T00", "00-E"),
        ("T01", "00-A"), ("T01", "00-B")]
    assert (cuerpo["total"], cuerpo["limite"], cuerpo["offset"]) == (
        6, 100, 0)


async def test_excluded_lines_never_appear_nor_count(mundo):
    cuerpo = await _comparar(mundo)

    assert ("T00", "00-F") not in _por_clave(cuerpo, mundo)
    a = cuerpo["totales_por_sucursal"][0]
    assert a["unidades_prueba"] == "80.00"


async def test_the_comparison_reads_the_sugerido_not_the_final(mundo):
    async with mundo.fabrica() as db:
        await db.execute(text(
            "UPDATE corrida_linea SET pedido_final = 999 "
            "WHERE corrida_id = :c"), {"c": mundo.real.id})
        await db.commit()

    cuerpo = await _comparar(mundo)

    a1 = _por_clave(cuerpo, mundo)[("T00", "00-A")]
    assert a1["sugerido_real"] == "50.00" and a1["delta"] == "12.00"
    assert a1["pedido_final_real"] == "999.00"


# --- Totales, filtros y páginas (SC-09, SC-12) ------------------------------


async def test_totals_per_tienda_for_both_sides_sc_09(mundo):
    cuerpo = await _comparar(mundo)

    [a, b] = cuerpo["totales_por_sucursal"]
    assert a["nombre"].startswith("T00")
    assert (a["unidades_real"], a["unidades_prueba"]) == ("64.00", "80.00")
    assert a["diferencia_unidades"] == "16.00"
    assert (a["valor_real"], a["valor_prueba"]) == ("6400.00", "8000.00")
    assert a["diferencia_valor"] == "1600.00"
    assert (b["unidades_real"], b["unidades_prueba"]) == ("20.00", "25.00")
    assert b["diferencia_valor"] == "500.00"


async def test_solo_diferencias_omits_the_identical_rows_sc_12(mundo):
    cuerpo = await _comparar(mundo, solo_diferencias="true")

    assert [_clave(f, mundo) for f in cuerpo["filas"]] == [
        ("T00", "00-A"), ("T00", "00-D"), ("T00", "00-E"), ("T01", "00-B")]
    assert cuerpo["total"] == 4


async def test_totals_ignore_solo_diferencias_and_the_tienda_filter(mundo):
    sola = await _comparar(
        mundo, solo_diferencias="true", sucursal_id=str(mundo.tiendas[1].id))

    assert [_clave(f, mundo) for f in sola["filas"]] == [("T01", "00-B")]
    assert len(sola["totales_por_sucursal"]) == 2
    assert sola["totales_por_sucursal"][0]["unidades_real"] == "64.00"


async def test_the_tienda_filter_keeps_only_that_tienda(mundo):
    cuerpo = await _comparar(mundo, sucursal_id=str(mundo.tiendas[0].id))

    assert {_clave(f, mundo)[0] for f in cuerpo["filas"]} == {"T00"}
    assert cuerpo["total"] == 4


async def test_a_filter_on_a_tienda_that_is_not_comparable_gives_no_rows(
        mundo):
    cuerpo = await _comparar(mundo, sucursal_id=str(mundo.tiendas[2].id))

    assert cuerpo["filas"] == [] and cuerpo["total"] == 0
    assert len(cuerpo["totales_por_sucursal"]) == 2


async def test_paging_walks_the_rows_without_losing_or_repeating_any(mundo):
    primera = await _comparar(mundo, limite=2, offset=0)
    segunda = await _comparar(mundo, limite=2, offset=2)
    tercera = await _comparar(mundo, limite=2, offset=4)

    claves = [
        _clave(f, mundo) for p in (primera, segunda, tercera)
        for f in p["filas"]]
    assert len(claves) == len(set(claves)) == 6
    assert claves == sorted(claves)
    assert {p["total"] for p in (primera, segunda, tercera)} == {6}


async def test_a_page_past_the_end_is_empty_with_the_real_count(mundo):
    cuerpo = await _comparar(mundo, limite=2, offset=40)

    assert cuerpo["filas"] == [] and cuerpo["total"] == 6


# --- Tiendas que no se comparan (SC-13) -------------------------------------


async def test_the_not_comparable_tiendas_are_listed_with_why_sc_13(mundo):
    cuerpo = await _comparar(mundo)

    [fallida, nueva] = cuerpo["no_comparables"]
    assert fallida["nombre"].startswith("T02")
    assert (fallida["estado_real"], fallida["estado_prueba"]) == (
        "FALLIDA", "OK")
    assert "FALLIDA" in fallida["motivo"]
    assert nueva["nombre"].startswith("T03")
    assert (nueva["estado_real"], nueva["estado_prueba"]) == (None, "OK")
    assert "no está en la corrida real" in nueva["motivo"]


async def test_not_comparable_lines_never_enter_rows_or_totals(mundo):
    cuerpo = await _comparar(mundo)

    assert {_clave(f, mundo)[0] for f in cuerpo["filas"]} == {"T00", "T01"}
    assert len(cuerpo["totales_por_sucursal"]) == 2


async def test_the_header_names_both_corridas(mundo):
    cuerpo = await _comparar(mundo)

    assert cuerpo["escenario"] == {
        "id": str(mundo.esc.id), "codigo": mundo.esc.codigo,
        "estado": "BORRADOR", "es_escenario": True}
    assert cuerpo["real"]["id"] == str(mundo.real.id)
    assert cuerpo["real"]["es_escenario"] is False
    assert cuerpo["fecha_corte"] == sv.CORTE.isoformat()


# --- Emparejamiento inválido (SC-10, SC-11) ---------------------------------


async def _rechazo(mundo, **kw):
    respuesta = await _pedir(mundo, **kw)
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-063"
    return respuesta.json()["detail"]["message"]


async def test_another_fecha_corte_is_063_sc_10(mundo):
    async with mundo.fabrica() as db:
        otra = await sv.corrida(
            db, mundo.datos, mundo.suf, 5,
            corte=sv.CORTE + datetime.timedelta(days=7))
        await db.commit()

    mensaje = await _rechazo(mundo, con=otra)

    assert "fecha de corte" in mensaje


async def test_another_proveedor_is_063(mundo):
    async with mundo.fabrica() as db:
        proveedor = Proveedor(
            id=uuid.uuid4(), codigo=f"OTRO-{mundo.suf}", nombre="otro",
            es_principal=False, dias_empaque_default=1,
            dias_transito_default=1, dias_seguridad_default=D("1"))
        db.add(proveedor)
        await db.flush()
        otra = await sv.corrida(
            db, mundo.datos, mundo.suf, 6, proveedor=proveedor)
        await db.commit()

    await _rechazo(mundo, con=otra)


async def test_the_first_corrida_must_be_a_scenario_sc_11(mundo):
    await _rechazo(mundo, escenario=mundo.real, con=mundo.real)


async def test_the_second_corrida_cannot_be_a_scenario_sc_11(mundo):
    async with mundo.fabrica() as db:
        otro = await sv.corrida(
            db, mundo.datos, mundo.suf, 7, escenario=True)
        await db.commit()

    await _rechazo(mundo, con=otro)


async def test_a_real_corrida_that_does_not_exist_is_063_sc_11(mundo):
    respuesta = await _pedir(
        mundo, con=SimpleNamespace(id=uuid.UUID(int=424242)))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-063"


@pytest.mark.parametrize("estado", ["PENDIENTE", "FALLIDA", "ANULADA"])
async def test_a_real_corrida_that_is_not_calculated_is_063(mundo, estado):
    async with mundo.fabrica() as db:
        otra = await sv.corrida(
            db, mundo.datos, mundo.suf, 8, estado=estado)
        await db.commit()

    await _rechazo(mundo, con=otra)


async def test_a_legacy_closed_real_corrida_still_compares(mundo):
    async with mundo.fabrica() as db:
        await db.execute(text(
            "UPDATE corrida SET estado = 'CERRADA' WHERE id = :c"),
            {"c": mundo.real.id})
        await db.commit()

    cuerpo = await _comparar(mundo)

    assert cuerpo["real"]["estado"] == "CERRADA" and cuerpo["total"] == 6


async def test_an_unknown_scenario_is_a_404(mundo):
    respuesta = await _pedir(
        mundo, escenario=SimpleNamespace(id=uuid.UUID(int=424243)))

    assert respuesta.status_code == 404


# --- Volumen: 47 tiendas por 3.000 referencias en cada lado -----------------


@contextmanager
def _contar_consultas():
    """Cuenta las consultas de datos que llegan a la base mientras está
    activo (no la sonda de salud ni los savepoints)."""
    cuenta = {"n": 0}

    def escuchar(conn, cursor, statement, *args, **kwargs):
        sql = statement.lstrip()
        if sql.startswith("SELECT") and "corrida" in sql:
            cuenta["n"] += 1

    event.listen(Engine, "before_cursor_execute", escuchar)
    try:
        yield cuenta
    finally:
        event.remove(Engine, "before_cursor_execute", escuchar)


@pytest.fixture
async def volumen(fabrica):  # noqa: F811
    """La real y el escenario con las mismas líneas; en una de cada cinco el
    escenario pide 3 más."""
    async with fabrica() as db:
        suf = sv.sufijo_nuevo()
        datos = await sv.base(db, suf)
        tiendas = await sv.tiendas(db, suf, TIENDAS)
        await sv.referencias(db, datos.proveedor, suf, REFERENCIAS)
        real = await sv.corrida(db, datos, suf, 1)
        esc = await sv.corrida(db, datos, suf, 2, escenario=True)
        await sv.estados_de_tiendas(
            db, real, [(t, "OK", "BORRADOR") for t in tiendas])
        await sv.estados_de_tiendas(
            db, esc, [(t, "OK", None) for t in tiendas])
        await sv.lineas_en_bloque(db, real, suf)
        await sv.lineas_en_bloque(db, esc, suf, plus=3)
        await db.commit()
    app.dependency_overrides[get_motored_db] = _sesion_de(fabrica)
    _como("COMPRAS", datos.usuario.id)
    return SimpleNamespace(
        fabrica=fabrica, real=real, esc=esc, suf=suf, tiendas=tiendas,
        datos=datos)


async def _recorrer(volumen, **params):
    """Todas las páginas, con lo que tardó y pesó cada una."""
    paginas, offset = [], 0
    async with _cliente() as cliente:
        while True:
            inicio = time.perf_counter()
            respuesta = await cliente.get(
                f"{BASE}/{volumen.esc.id}/comparar",
                params={"con": str(volumen.real.id), "limite": PAGINA,
                        "offset": offset, **params})
            segundos = time.perf_counter() - inicio
            assert respuesta.status_code == 200, respuesta.text
            cuerpo = respuesta.json()
            paginas.append((cuerpo, segundos, len(respuesta.content)))
            offset += PAGINA
            if offset >= cuerpo["total"]:
                return paginas


async def _diferencias(volumen):
    """Cuántas (tienda, referencia) difieren y los totales por tienda, con
    SQL propio."""
    async with volumen.fabrica() as db:
        p = {"r": volumen.real.id, "e": volumen.esc.id}
        diferentes = (await db.execute(text(
            "SELECT count(*) FROM corrida_linea r JOIN corrida_linea e "
            "ON e.sucursal_id = r.sucursal_id "
            "AND e.referencia_id = r.referencia_id AND e.corrida_id = :e "
            "WHERE r.corrida_id = :r "
            "AND e.pedido_sugerido <> r.pedido_sugerido"), p)).scalar_one()
        totales = {
            (str(c), str(s)): (u, v) for c, s, u, v in (await db.execute(
                text(
                    "SELECT corrida_id, sucursal_id, sum(pedido_sugerido), "
                    "sum(round(pedido_sugerido * coalesce(precio, 0), 2)) "
                    "FROM corrida_linea WHERE corrida_id IN (:r, :e) "
                    "GROUP BY corrida_id, sucursal_id"), p)).all()}
    return diferentes, totales


async def test_every_difference_is_found_exactly_once_at_volume(volumen):
    diferentes, _ = await _diferencias(volumen)

    paginas = await _recorrer(volumen, solo_diferencias="true")

    claves = [
        (f["sucursal_id"], f["referencia_id"])
        for c, _, _ in paginas for f in c["filas"]]
    assert 0 < diferentes < TIENDAS * REFERENCIAS
    assert len(claves) == len(set(claves)) == diferentes
    assert all(c["total"] == diferentes for c, _, _ in paginas)
    for c, _, _ in paginas:
        for fila in c["filas"]:
            assert D(fila["delta"]) == D(fila["sugerido_prueba"]) - D(
                fila["sugerido_real"]) != 0


async def test_the_totals_are_the_database_totals_at_volume(volumen):
    _, esperado = await _diferencias(volumen)

    cuerpo = (await _recorrer(volumen, solo_diferencias="true"))[0][0]

    assert len(cuerpo["totales_por_sucursal"]) == TIENDAS
    for t in cuerpo["totales_por_sucursal"]:
        sid = t["sucursal_id"]
        u_real, v_real = esperado[(str(volumen.real.id), sid)]
        u_esc, v_esc = esperado[(str(volumen.esc.id), sid)]
        assert D(t["unidades_real"]) == u_real
        assert D(t["unidades_prueba"]) == u_esc
        assert D(t["valor_real"]) == v_real
        assert D(t["valor_prueba"]) == v_esc
    assert cuerpo["no_comparables"] == []


async def test_the_unfiltered_comparison_counts_every_line_at_volume(
        volumen):
    async with _cliente() as cliente:
        respuesta = await cliente.get(
            f"{BASE}/{volumen.esc.id}/comparar",
            params={"con": str(volumen.real.id), "limite": PAGINA,
                    "offset": 140900})

    cuerpo = respuesta.json()
    assert cuerpo["total"] == TIENDAS * REFERENCIAS
    assert len(cuerpo["filas"]) == PAGINA


async def test_one_page_takes_exactly_four_data_queries(volumen):
    with _contar_consultas() as consultas:
        async with _cliente() as cliente:
            respuesta = await cliente.get(
                f"{BASE}/{volumen.esc.id}/comparar",
                params={"con": str(volumen.real.id),
                        "solo_diferencias": "true"})

    assert respuesta.status_code == 200
    assert consultas["n"] == CONSULTAS_DE_DATOS


async def test_every_page_answers_fast_and_stays_small(volumen):
    paginas = await _recorrer(volumen, solo_diferencias="true", limite=PAGINA)
    una_tienda = await _recorrer(
        volumen, sucursal_id=str(volumen.tiendas[0].id))

    todas = paginas + una_tienda
    lento = max(segundos for _, segundos, _ in todas)
    pesado = max(bytes_ for _, _, bytes_ in todas)
    print(f"\ncomparar {TIENDAS}x{REFERENCIAS}: {len(paginas)} paginas de "
          f"diferencias, max {lento:.3f}s, media "
          f"{sum(s for _, s, _ in paginas) / len(paginas):.3f}s, "
          f"max {pesado / 1024:.0f} KB")
    assert lento < LIMITE_SEGUNDOS
    assert pesado < 1_000_000
