"""
Motored Pedidos F3 "Motor" (S8b-3, ADR-10) — `pytest.ini` deja fuera de la
corrida por defecto las pruebas opt-in (`lento`, `pg_real`, `regresion`) y
registra sus marcadores; se activan con `-m` (el último `-m` gana sobre el de
`addopts`).

La expresión de `addopts` se evalúa con el mismo evaluador de marcadores de
pytest, sin recolectar nada: una prueba con uno de esos marcadores queda fuera
y una sin marcadores entra.
"""
import configparser
import shlex
from pathlib import Path

import pytest
from _pytest.mark.expression import Expression

BACKEND = Path(__file__).resolve().parents[2]
ESPERADO = "not lento and not pg_real and not regresion"


def _ini() -> configparser.SectionProxy:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(BACKEND / "pytest.ini", encoding="utf-8")
    return parser["pytest"]


def _expresion() -> str:
    argumentos = shlex.split(_ini()["addopts"])
    assert argumentos[0] == "-m" and len(argumentos) == 2
    return argumentos[1]


def _entra(marcadores: set[str]) -> bool:
    expresion = Expression.compile(_expresion())
    return expresion.evaluate(lambda nombre, **_: nombre in marcadores)


def test_addopts_es_solo_el_filtro_de_marcadores_opt_in():
    assert _expresion() == ESPERADO


@pytest.mark.parametrize("marcador", ["lento", "pg_real", "regresion"])
def test_una_prueba_opt_in_queda_fuera_de_la_corrida_por_defecto(marcador):
    assert _entra({marcador}) is False


def test_una_prueba_sin_marcadores_entra():
    assert _entra(set()) is True


def test_los_tres_marcadores_estan_registrados():
    marcadores = [
        linea.split(":")[0].strip()
        for linea in _ini()["markers"].strip().splitlines()
    ]
    assert marcadores == ["lento", "pg_real", "regresion"]
