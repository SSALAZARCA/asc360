"""Inventario KPI summary reader: the pure split of the pair rows (SQL in `pg_real`)."""
import datetime
from decimal import Decimal as D

from app.motored.services import kpi_resumen_lectura as lectura

F = datetime.date
C1, C2, C3 = F(2096, 8, 31), F(2096, 9, 30), F(2096, 10, 7)


def test_separar_pares_gives_the_pairs_of_the_corte_with_their_line_and_stock():
    filas = [
        (C3, "s1", "r1", "REPUESTOS", D(15), D(2500)), (C3, "s2", "r2", None, D(2), D(40)),
        (C2, "s1", "r1", "REPUESTOS", D(9), D(900)),
    ]

    pares, _ = lectura.separar_pares(filas, C3, [C2, C3])

    assert pares == [("s1", "r1", "REPUESTOS", D(15), D(2500)), ("s2", "r2", None, D(2), D(40))]


def test_separar_pares_groups_the_value_of_each_pair_by_the_requested_cortes_only():
    filas = [
        (C3, "s1", "r1", "REPUESTOS", D(15), D(2500)), (C2, "s1", "r1", "REPUESTOS", D(9), D(900)),
        (C1, "s1", "r1", "REPUESTOS", D(8), D(800)),
    ]

    _, por_corte = lectura.separar_pares(filas, C3, [C2, C3])

    assert por_corte == {C2: [("s1", "r1", D(900))], C3: [("s1", "r1", D(2500))]}


def test_separar_pares_without_trend_cortes_has_no_pairs_per_corte():
    _, por_corte = lectura.separar_pares([(C3, "s1", "r1", None, D(1), D(5))], C3, [])

    assert por_corte == {}


def test_a_requested_corte_without_pairs_is_an_empty_list_like_the_live_query():
    _, por_corte = lectura.separar_pares([], C3, [C2, C3])

    assert por_corte == {C2: [], C3: []}
