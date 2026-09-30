"""
Motored Pedidos F3 "Motor" (S8a-3, ADR-10, spec Domain 4) — niveles A1/A2
contra el libro REAL (opt-in).

Corre sólo con `MOTORED_REGRESION_EXCEL` apuntando al libro de referencia
(`PLANTILLA PEDIDO SEPTIEMBRE.xlsx`), que vive fuera del repositorio; sin la
variable se omite. `MOTORED_REGRESION_ACEPTACIONES` (opcional) apunta al JSON
`{código: categoría}` con las diferencias aceptadas a mano.

El libro es referencia de ESTRUCTURA: estos tests no fijan cantidades de
filas ni valores, sólo la fidelidad de las fórmulas.
"""
import os
from pathlib import Path

import pytest

from app.motored.herramientas.regresion.comparador import (
    atributos_de,
    ejecutar_nivel_a1,
    ejecutar_nivel_a2,
    verificar_precondiciones,
)
from app.motored.herramientas.regresion.extractor_excel import leer_libro
from app.motored.herramientas.regresion.rutas import (
    ENV_ACEPTACIONES,
    ENV_EXCEL,
)
from app.motored.herramientas.regresion.taxonomia import (
    SIN_CATEGORIA,
    cargar_aceptaciones,
)
from app.motored.services.motor.tipos import ParametrosMotor

RUTA = os.environ.get(ENV_EXCEL)
pytestmark = [
    pytest.mark.regresion,
    pytest.mark.skipif(not RUTA, reason=f"{ENV_EXCEL} no definida"),
]


@pytest.fixture(scope="module")
def lectura():
    return leer_libro(Path(RUTA))


@pytest.fixture(scope="module")
def aceptaciones():
    ruta = os.environ.get(ENV_ACEPTACIONES)
    return cargar_aceptaciones(Path(ruta)) if ruta else {}


class TestPreset:
    def test_la_sucursal_no_tiene_apertura_dentro_de_la_ventana(
        self, lectura
    ):
        atributos = atributos_de(lectura)
        assert atributos.fecha_apertura is None
        verificar_precondiciones(ParametrosMotor(), atributos)

    def test_el_mes_en_curso_es_excluido_por_defecto(self):
        assert ParametrosMotor().mes_en_curso is None

    def test_el_libro_trae_filas_y_los_factores_de_cobertura(self, lectura):
        assert len(lectura.filas) > 0
        assert set(lectura.coberturas) >= {"AF", "AM", "AS", "DS"}


class TestNivelA1:
    def test_n_a_ad_coincide_exacto_en_todas_las_filas(
        self, lectura, aceptaciones
    ):
        resultado = ejecutar_nivel_a1(lectura, aceptaciones)
        inexplicadas = [
            d for d in resultado.diferencias if d.categoria == SIN_CATEGORIA
        ]
        assert inexplicadas == []
        assert resultado.filas_exactas + resultado.filas_con_diferencias == (
            len(lectura.filas)
        )
        assert resultado.paso


class TestNivelA2:
    def test_toda_diferencia_tiene_categoria(self, lectura, aceptaciones):
        resultado = ejecutar_nivel_a2(lectura, aceptaciones)
        assert SIN_CATEGORIA not in resultado.por_categoria
        assert resultado.paso
