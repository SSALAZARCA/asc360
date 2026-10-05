"""
Motored Pedidos: the totals of a whole corrida against a real Postgres
(opt-in, `MOTORED_TEST_PG_URL` on a database migrated with
`alembic -c alembic_motored.ini upgrade head`).

One small exact world: three stores, a referencia ordered in two stores,
one at zero, one unpriced line and one excluded line. The totals of the
detail must equal the sum of the per-store "A pedir" of that same detail;
the list carries the same figures, reads them inside its page query (the
query count does not grow with the page), gives an escenario the same
rule and leaves a corrida still calculating without totals.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.main import app
from app.motored.database import get_motored_db
from app.motored.services.corridas import consultas
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
# (store, referencia, quantity, price): `r3` is zero, `r2` in `t1` has no
# price. 24 units; (5 + 7 + 7 + 2) x 100 = 2100; r1, r2 and r4 = 3 refs.
CANTIDADES = (
    (0, "r1", 5, "100.00"), (0, "r2", 7, "100.00"), (0, "r3", 0, "100.00"),
    (1, "r1", 7, "100.00"), (1, "r2", 3, None), (2, "r4", 2, "100.00"))
ESPERADO = {"valor_total": "2100.00", "referencias": 3, "unidades": "24.00"}


def _lineas(db, corrida, tiendas, r) -> None:
    db.add_all([
        sv.linea(corrida, tiendas[t], r[k].codigo, r[k].id, q, precio=p)
        for t, k, q, p in CANTIDADES])
    db.add(sv.linea(
        corrida, tiendas[0], r["r5"].codigo, r["r5"].id, 100,
        exclusion="SUSTITUIDA"))


async def _corrida_llena(db, datos, suf, tiendas, r, orden, **campos):
    corrida = await sv.corrida(db, datos, suf, orden, **campos)
    await sv.estados_de_tiendas(
        db, corrida, [(t, "OK", "BORRADOR") for t in tiendas])
    _lineas(db, corrida, tiendas, r)
    return corrida


async def _sembrar(db):
    suf = sv.sufijo_nuevo()
    datos = await sv.base(db, suf)
    tiendas = await sv.tiendas(db, suf, 3)
    r = {}
    for clave in ("r1", "r2", "r3", "r4", "r5"):
        r[clave] = await sv.referencia_a_mano(db, datos, f"{clave}-{suf}")
    real = await _corrida_llena(db, datos, suf, tiendas, r, 1)
    escenario = await _corrida_llena(
        db, datos, suf, tiendas, r, 2, escenario=True)
    calculando = await _corrida_llena(
        db, datos, suf, tiendas, r, 3, estado="CALCULANDO")
    await db.commit()
    return SimpleNamespace(
        datos=datos, real=real, escenario=escenario, calculando=calculando)


@pytest.fixture
async def mundo(fabrica):  # noqa: F811
    async with fabrica() as db:
        mundo_ = await _sembrar(db)
    app.dependency_overrides[get_motored_db] = _sesion_de(fabrica)
    _como("COMPRAS", mundo_.datos.usuario.id)
    mundo_.fabrica = fabrica
    return mundo_


async def _get(ruta, **params):
    async with _cliente() as cliente:
        respuesta = await cliente.get(ruta, params=params)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def test_the_detail_totals_equal_the_sum_of_the_stores(mundo):
    cuerpo = await _get(f"{BASE}/{mundo.real.id}")

    tiendas = cuerpo["sucursales"]
    assert cuerpo["totales_corrida"] == ESPERADO
    assert sum(D(t["valor_a_pedir"]) for t in tiendas) == D("2100.00")
    assert sum(D(t["unidades_a_pedir"]) for t in tiendas) == D("24.00")


async def test_an_escenario_computes_the_same_way(mundo):
    cuerpo = await _get(f"{BASE}/{mundo.escenario.id}")

    assert cuerpo["totales_corrida"] == ESPERADO


async def test_a_corrida_still_calculating_has_no_totals(mundo):
    cuerpo = await _get(f"{BASE}/{mundo.calculando.id}")

    assert cuerpo["totales_corrida"] is None


async def test_the_list_carries_the_same_totals(mundo):
    cuerpo = await _get(BASE, proveedor_id=str(mundo.datos.proveedor.id))

    por_id = {i["id"]: i["totales_corrida"] for i in cuerpo["items"]}
    assert por_id == {
        str(mundo.real.id): ESPERADO, str(mundo.escenario.id): ESPERADO,
        str(mundo.calculando.id): None}


def _contar_selects():
    cuenta = {"n": 0}

    def escuchar(conn, cursor, statement, *args, **kwargs):
        if statement.lstrip().upper().startswith("SELECT"):
            cuenta["n"] += 1

    return cuenta, escuchar


async def _consultas_de_pagina(mundo, limite):
    cuenta, escuchar = _contar_selects()
    event.listen(Engine, "before_cursor_execute", escuchar)
    try:
        async with mundo.fabrica() as db:
            items, _ = await consultas.listar(
                db, alcance=None, proveedor_id=mundo.datos.proveedor.id,
                estado=None, desde=None, hasta=None, escenario=None,
                limite=limite, offset=0)
    finally:
        event.remove(Engine, "before_cursor_execute", escuchar)
    assert len(items) == limite
    return cuenta["n"]


async def test_the_list_aggregate_does_not_grow_with_the_page(mundo):
    una = await _consultas_de_pagina(mundo, 1)
    tres = await _consultas_de_pagina(mundo, 3)

    assert una == tres == 3
