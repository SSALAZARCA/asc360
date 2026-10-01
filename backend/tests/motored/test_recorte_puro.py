"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B5a,
ADR-6, spec TP-15..TP-23, decisiones F4-12, A2 y A3): la propuesta de
recorte al tope de presupuesto de UNA tienda, como función pura.

Reglas bajo prueba:
- Sólo se recortan las clases C y luego B; A, D y lo demás no se tocan.
- Dentro de la clase se corta UN empaque a la vez, la línea que conserva la
  cobertura final MÁS ALTA después del corte (N nula o 0 = infinita), con
  re-ranking tras cada paso. Empate: código ascendente.
- A3: el primer paso de una línea que no es múltiplo del empaque la baja al
  múltiplo de abajo (25 con empaque 12 -> 24 -> 12 -> 0). Esto REEMPLAZA el
  "12, 12, 1" del texto de TP-20 (la decisión 422 manda sobre la spec).
- Se corta hasta el primer valor <= tope; aritmética exacta con `Fraction`.
"""
import ast
import dataclasses
import random
import time
from fractions import Fraction
from pathlib import Path

import pytest

from app.motored.services.corridas import recorte
from app.motored.services.corridas.recorte import (
    LineaRecortable,
    PropuestaRecorte,
    Recorte,
    proponer_recorte,
)

_RAIZ = Path(__file__).resolve().parents[2]


def _linea(
    linea_id, codigo, clase="C", pedido=10, unidad=10, precio=1, y=0, n=10,
):
    return LineaRecortable(
        linea_id=linea_id,
        codigo=codigo,
        clase_abc=clase,
        pedido=Fraction(pedido),
        unidad_empaque=unidad,
        precio=None if precio is None else Fraction(precio),
        y=Fraction(y),
        n=None if n is None else Fraction(n),
    )


def _finales(propuesta):
    return {r.codigo: r.pedido_propuesto for r in propuesta.recortes}


# --- Bajo el tope: propuesta vacía (TP-08) ----------------------------------


def test_a_pedido_under_the_cap_has_an_empty_proposal():
    lineas = [_linea(1, "A1", pedido=30), _linea(2, "B1", pedido=40)]

    propuesta = proponer_recorte(lineas, Fraction(100))

    assert propuesta.recortes == ()
    assert propuesta.valor_actual == 70
    assert propuesta.valor_final == 70
    assert propuesta.exceso == 0
    assert propuesta.exceso_residual == 0
    assert propuesta.tope == 100


def test_a_pedido_exactly_at_the_cap_is_not_over_it():
    propuesta = proponer_recorte([_linea(1, "C1", pedido=70)], Fraction(70))

    assert propuesta.recortes == ()
    assert propuesta.exceso == 0


def test_no_lines_at_all_is_an_empty_proposal():
    propuesta = proponer_recorte([], Fraction(10))

    assert propuesta.recortes == ()
    assert propuesta.valor_actual == 0 and propuesta.valor_final == 0


def test_the_current_value_counts_every_class_and_no_price_as_zero():
    lineas = [
        _linea(1, "A1", clase="A", pedido=10, precio=5),
        _linea(2, "D1", clase="D", pedido=4, precio=5),
        _linea(3, "C1", clase="C", pedido=10, precio=None),
        _linea(4, "C2", clase="C", pedido=10, precio=2),
    ]

    propuesta = proponer_recorte(lineas, Fraction(1000))

    assert propuesta.valor_actual == 10 * 5 + 4 * 5 + 10 * 2


# --- Clases: C antes que B; A y D jamás (TP-15, TP-16, TP-17, A2) ----------


def test_class_c_is_cut_before_class_b():
    lineas = [
        _linea(1, "B1", clase="B", pedido=100),
        _linea(2, "C1", clase="C", pedido=100),
    ]

    propuesta = proponer_recorte(lineas, Fraction(150))

    assert _finales(propuesta) == {"C1": 50}
    assert propuesta.valor_final == 150
    assert propuesta.exceso == 50 and propuesta.exceso_residual == 0


def test_class_b_is_cut_only_after_class_c_is_exhausted():
    lineas = [
        _linea(1, "B1", clase="B", pedido=100),
        _linea(2, "C1", clase="C", pedido=30),
    ]

    propuesta = proponer_recorte(lineas, Fraction(80))

    assert _finales(propuesta) == {"C1": 0, "B1": 80}
    assert propuesta.valor_final == 80


def test_class_a_is_never_cut_and_the_excess_stays_as_residual():
    lineas = [
        _linea(1, "A1", clase="A", pedido=100),
        _linea(2, "C1", clase="C", pedido=20),
    ]

    propuesta = proponer_recorte(lineas, Fraction(50))

    assert _finales(propuesta) == {"C1": 0}
    assert propuesta.valor_final == 100
    assert propuesta.exceso == 70
    assert propuesta.exceso_residual == 50


def test_only_class_a_lines_means_no_cuts_and_the_full_excess_remains():
    propuesta = proponer_recorte(
        [_linea(1, "A1", clase="A", pedido=100)], Fraction(60))

    assert propuesta.recortes == ()
    assert propuesta.exceso_residual == 40


def test_class_d_lines_are_never_cut_even_with_a_manual_quantity():
    """A2: el sugerido de una D es 0; esto protege lo que añada COMPRAS."""
    lineas = [
        _linea(1, "D1", clase="D", pedido=60),
        _linea(2, "C1", clase="C", pedido=10),
    ]

    propuesta = proponer_recorte(lineas, Fraction(40))

    assert _finales(propuesta) == {"C1": 0}
    assert propuesta.valor_final == 60
    assert propuesta.exceso_residual == 20


@pytest.mark.parametrize("clase", [None, "", "X", "c", "CF"])
def test_a_line_without_a_trimmable_class_is_never_cut(clase):
    propuesta = proponer_recorte(
        [_linea(1, "Z1", clase=clase, pedido=100)], Fraction(10))

    assert propuesta.recortes == ()
    assert propuesta.exceso_residual == 90


def test_c_and_b_cut_to_zero_reach_the_cap_without_touching_a():
    lineas = [
        _linea(1, "A1", clase="A", pedido=50),
        _linea(2, "B1", clase="B", pedido=20),
        _linea(3, "C1", clase="C", pedido=20),
    ]

    propuesta = proponer_recorte(lineas, Fraction(50))

    assert _finales(propuesta) == {"B1": 0, "C1": 0}
    assert propuesta.valor_final == 50
    assert propuesta.exceso_residual == 0


def test_when_c_and_b_cannot_reach_the_cap_the_residual_is_positive():
    lineas = [
        _linea(1, "A1", clase="A", pedido=50),
        _linea(2, "B1", clase="B", pedido=20),
        _linea(3, "C1", clase="C", pedido=20),
    ]

    propuesta = proponer_recorte(lineas, Fraction(30))

    assert propuesta.valor_final == 50
    assert propuesta.exceso_residual == 20


# --- Orden: cobertura posterior más alta, con re-ranking (TP-18) ----------


def test_the_line_with_the_highest_post_cut_coverage_goes_first():
    lineas = [
        _linea(1, "Y1", pedido=30, unidad=10, n=10),   # post 2.0
        _linea(2, "X1", pedido=40, unidad=10, n=10),   # post 3.0
    ]

    propuesta = proponer_recorte(lineas, Fraction(60))

    assert _finales(propuesta) == {"X1": 30}
    assert propuesta.valor_final == 60


def test_the_ranking_is_recomputed_after_every_step():
    """X (3.0) y Y (2.0). Pasos: X, X (empate 2.0 -> código), Y, X."""
    lineas = [
        _linea(1, "X1", pedido=40, unidad=10, n=10),
        _linea(2, "Y1", pedido=30, unidad=10, n=10),
    ]

    propuesta = proponer_recorte(lineas, Fraction(30))

    assert _finales(propuesta) == {"X1": 10, "Y1": 20}
    assert propuesta.valor_final == 30


def test_the_current_stock_y_enters_the_post_cut_coverage():
    lineas = [
        _linea(1, "P1", pedido=20, unidad=10, y=10, n=10),   # (10+20-10)/10
        _linea(2, "Q1", pedido=30, unidad=10, y=0, n=10),    # (0+30-10)/10
        _linea(3, "R1", pedido=20, unidad=10, y=0, n=10),    # (0+20-10)/10
    ]

    propuesta = proponer_recorte(lineas, Fraction(60))

    assert _finales(propuesta) == {"P1": 10}


def test_a_null_or_zero_demand_line_is_cut_first():
    lineas = [
        _linea(1, "A1", pedido=100, n=1),            # cobertura enorme
        _linea(2, "B1", pedido=50, n=None),
        _linea(3, "C1", pedido=50, n=0),
    ]

    propuesta = proponer_recorte(lineas, Fraction(190))

    assert propuesta.recortes[0].codigo == "B1"
    assert _finales(propuesta) == {"B1": 40}


def test_a_zero_demand_line_beats_a_finite_one_and_ties_go_by_code():
    lineas = [
        _linea(1, "K1", pedido=50, n=1),
        _linea(2, "J1", pedido=30, n=0),
        _linea(3, "H1", pedido=30, n=None),
    ]

    propuesta = proponer_recorte(lineas, Fraction(40))

    # H1 y J1 son infinitas: se agotan por código antes de tocar K1.
    assert _finales(propuesta) == {"H1": 0, "J1": 0, "K1": 40}


# --- Se detiene en el tope (TP-19) ----------------------------------------


def test_it_stops_at_the_first_step_that_reaches_the_cap():
    lineas = [_linea(1, "C1", pedido=100, unidad=10, precio=1)]

    propuesta = proponer_recorte(lineas, Fraction(75))

    assert _finales(propuesta) == {"C1": 70}
    assert propuesta.valor_final == 70
    assert propuesta.valor_final <= propuesta.tope


def test_a_cap_reached_exactly_needs_no_extra_step():
    lineas = [_linea(1, "C1", pedido=100, unidad=10, precio=1)]

    propuesta = proponer_recorte(lineas, Fraction(80))

    assert _finales(propuesta) == {"C1": 80}
    assert propuesta.valor_final == 80


def test_the_value_freed_follows_the_price():
    lineas = [_linea(1, "C1", pedido=100, unidad=10, precio=7)]

    propuesta = proponer_recorte(lineas, Fraction(560))

    recorte_c1 = propuesta.recortes[0]
    assert isinstance(recorte_c1, Recorte)
    assert recorte_c1.pedido_actual == 100
    assert recorte_c1.pedido_propuesto == 80
    assert recorte_c1.valor_recortado == 20 * 7
    assert recorte_c1.clase_abc == "C"
    assert recorte_c1.linea_id == 1
    assert propuesta.valor_final == 560


# --- Líneas que no son múltiplo del empaque (TP-20, A3) -------------------


@pytest.mark.parametrize("tope, final", [
    (24, 24),   # un paso: 25 -> 24
    (23, 12),   # dos pasos: 24 -> 12
    (11, 0),    # tres pasos: 12 -> 0
])
def test_a_non_multiple_line_first_snaps_down_to_a_whole_pack(tope, final):
    lineas = [_linea(1, "C1", pedido=25, unidad=12, precio=1)]

    propuesta = proponer_recorte(lineas, Fraction(tope))

    assert _finales(propuesta) == {"C1": final}


def test_a_line_smaller_than_its_pack_goes_to_zero_in_one_step():
    lineas = [_linea(1, "C1", pedido=5, unidad=12, precio=1)]

    propuesta = proponer_recorte(lineas, Fraction(4))

    assert _finales(propuesta) == {"C1": 0}
    assert propuesta.valor_final == 0


def test_a_multiple_of_the_pack_loses_a_whole_pack_per_step():
    lineas = [_linea(1, "C1", pedido=36, unidad=12, precio=1)]

    propuesta = proponer_recorte(lineas, Fraction(30))

    assert _finales(propuesta) == {"C1": 24}


def test_a_pack_that_is_not_positive_cuts_the_whole_line():
    lineas = [_linea(1, "C1", pedido=9, unidad=0, precio=1)]

    propuesta = proponer_recorte(lineas, Fraction(5))

    assert _finales(propuesta) == {"C1": 0}


# --- Sin precio (TP-21) ----------------------------------------------------


def test_lines_without_a_price_are_skipped_and_counted():
    lineas = [
        _linea(1, "C1", pedido=10, precio=None),
        _linea(2, "C2", pedido=10, precio=0),
        _linea(3, "C3", pedido=0, precio=None),
        _linea(4, "C4", pedido=100, precio=1),
    ]

    propuesta = proponer_recorte(lineas, Fraction(50))

    assert propuesta.lineas_sin_precio == 2
    assert _finales(propuesta) == {"C4": 50}


def test_no_price_lines_cannot_free_value_so_the_excess_stays():
    lineas = [
        _linea(1, "C1", pedido=100, precio=None),
        _linea(2, "A1", clase="A", pedido=100, precio=1),
    ]

    propuesta = proponer_recorte(lineas, Fraction(40))

    assert propuesta.recortes == ()
    assert propuesta.lineas_sin_precio == 1
    assert propuesta.exceso_residual == 60


def test_a_line_with_nothing_to_order_is_not_a_candidate():
    lineas = [
        _linea(1, "C1", pedido=0, precio=9),
        _linea(2, "C2", pedido=100, precio=1),
    ]

    propuesta = proponer_recorte(lineas, Fraction(50))

    assert {r.codigo for r in propuesta.recortes} == {"C2"}


# --- Desempate y determinismo (TP-22, TP-23) -------------------------------


def test_ties_are_broken_by_ascending_code_not_by_input_order():
    base = [
        _linea(1, "C-30", pedido=20),
        _linea(2, "C-10", pedido=20),
        _linea(3, "C-20", pedido=20),
    ]

    for orden in ([0, 1, 2], [2, 1, 0], [1, 2, 0]):
        lineas = [base[i] for i in orden]
        propuesta = proponer_recorte(lineas, Fraction(40))
        assert _finales(propuesta) == {"C-10": 10, "C-20": 10}, orden


def test_equal_codes_fall_back_to_the_line_id():
    lineas = [
        _linea(9, "C1", pedido=20),
        _linea(4, "C1", pedido=20),
    ]

    propuesta = proponer_recorte(lineas, Fraction(30))

    por_id = {r.linea_id: r.pedido_propuesto for r in propuesta.recortes}
    assert por_id == {4: 10}


def test_the_same_input_gives_the_same_proposal_in_any_order():
    azar = random.Random(7)
    lineas = [
        _linea(
            i, f"R{i:03d}", clase=azar.choice("BC"),
            pedido=azar.choice([12, 24, 36, 48]), unidad=12,
            precio=azar.randint(1, 9), y=azar.randint(0, 20),
            n=azar.choice([None, 0, 3, 7]),
        )
        for i in range(60)
    ]
    tope = Fraction(300)
    primera = proponer_recorte(lineas, tope)

    for _ in range(5):
        azar.shuffle(lineas)
        assert proponer_recorte(lineas, tope) == primera


def test_the_cuts_come_back_ordered_by_code_then_line_id():
    lineas = [
        _linea(3, "C3", pedido=20), _linea(1, "C1", pedido=20),
        _linea(2, "C2", pedido=20),
    ]

    propuesta = proponer_recorte(lineas, Fraction(0))

    assert [r.codigo for r in propuesta.recortes] == ["C1", "C2", "C3"]


# --- Aritmética exacta ------------------------------------------------------


def test_prices_with_repeating_decimals_stay_exact():
    lineas = [_linea(1, "C1", pedido=9, unidad=3, precio=Fraction(1, 3))]

    propuesta = proponer_recorte(lineas, Fraction(2))

    assert propuesta.valor_actual == 3
    assert propuesta.valor_final == 2
    assert propuesta.recortes[0].valor_recortado == Fraction(1)
    assert isinstance(propuesta.valor_final, Fraction)
    assert _finales(propuesta) == {"C1": 6}


def test_fractional_quantities_are_cut_exactly():
    lineas = [_linea(1, "C1", pedido=Fraction(21, 2), unidad=5, precio=2)]

    propuesta = proponer_recorte(lineas, Fraction(10))

    # 10.5 -> 10 (primer paso al múltiplo de abajo): valor 20 > 10 -> 5 -> 0.
    assert _finales(propuesta) == {"C1": 5}
    assert propuesta.valor_final == 10


# --- Estructura -------------------------------------------------------------


def test_the_results_are_frozen_and_hold_tuples():
    propuesta = proponer_recorte(
        [_linea(1, "C1", pedido=100)], Fraction(50))

    assert isinstance(propuesta, PropuestaRecorte)
    assert isinstance(propuesta.recortes, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        propuesta.exceso = 0
    with pytest.raises(dataclasses.FrozenInstanceError):
        propuesta.recortes[0].pedido_propuesto = 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        _linea(1, "C1").pedido = 3


def test_a_proposal_never_mutates_its_input():
    lineas = [_linea(1, "C1", pedido=100), _linea(2, "B1", clase="B")]
    copia = list(lineas)

    proponer_recorte(lineas, Fraction(20))

    assert lineas == copia


# --- Rendimiento (3 000 líneas) ---------------------------------------------


def _tienda_grande():
    azar = random.Random(11)
    lineas = [
        _linea(
            i, f"REF-{i:05d}", clase=azar.choice("ABCCCD"),
            pedido=12 * azar.randint(1, 10), unidad=12,
            precio=azar.randint(1000, 9000), y=azar.randint(0, 200),
            n=azar.choice([None, 0, 5, 20, 80]),
        )
        for i in range(3000)
    ]
    total = sum(x.pedido * x.precio for x in lineas)
    return lineas, total * Fraction(97, 100)


def test_three_thousand_lines_are_trimmed_in_under_50_ms():
    lineas, tope = _tienda_grande()

    mejor = min(_cronometrar(lineas, tope) for _ in range(3))

    assert mejor < 0.050, f"{mejor * 1000:.1f} ms"


def _cronometrar(lineas, tope):
    inicio = time.perf_counter()
    propuesta = proponer_recorte(lineas, tope)
    duracion = time.perf_counter() - inicio
    assert len(propuesta.recortes) > 50   # el escenario sí recorta
    assert propuesta.valor_final <= tope
    return duracion


# --- Pureza y Python 3.11 ---------------------------------------------------


def _arbol():
    ruta = _RAIZ / "app/motored/services/corridas/recorte.py"
    return ast.parse(ruta.read_text(encoding="utf-8"), feature_version=(3, 11))


def _importados():
    nombres = set()
    for nodo in ast.walk(_arbol()):
        if isinstance(nodo, ast.Import):
            nombres |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom):
            nombres.add(nodo.module or "")
    return nombres


def test_the_trim_module_imports_no_database_code():
    importados = _importados()

    assert importados, "el módulo debe importar al menos fractions"
    assert "fractions" in importados
    prohibidos = ("sqlalchemy", "app.motored.models", "app.motored.database",
                  "fastapi", "asyncio")
    for nombre in importados:
        assert not nombre.startswith(prohibidos), nombre


def test_the_trim_module_exposes_the_documented_api():
    assert recorte.proponer_recorte is proponer_recorte
    assert dataclasses.is_dataclass(LineaRecortable)
    assert dataclasses.is_dataclass(Recorte)
    assert dataclasses.is_dataclass(PropuestaRecorte)
