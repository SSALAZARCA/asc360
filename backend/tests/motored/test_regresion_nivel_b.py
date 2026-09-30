"""
Motored Pedidos F3 "Motor" (S8b-1, ADR-10, spec Domain 4 nivel B) — pipeline.

El nivel B compara las entradas que la aplicación cargó por la ingesta F2 (E:J
ventas, T precio, U unidad, V inventario, W tránsito, X backorder) contra las
del Excel REVISADO y DESPUÉS las salidas contra el Excel con las reglas del A2.
La Z sale del Excel (sólo el arnés: en F3 la base guarda Z = 0). Aquí se prueba
el núcleo puro con libros sintéticos; el camino contra una base real está en
`pg_real/test_regresion_nivel_b_pg.py`.
"""
from dataclasses import replace
from decimal import Decimal

import pytest

from app.motored.herramientas.regresion.comparador import (
    PrecondicionIncumplida,
    ejecutar_nivel_a2,
    entradas_de,
)
from app.motored.herramientas.regresion.extractor_excel import leer_libro
from app.motored.herramientas.regresion.nivel_b import (
    ejecutar_nivel_b,
    resumen_texto_b,
)
from app.motored.herramientas.regresion.taxonomia import SIN_CATEGORIA
from app.motored.services.motor.tipos import ParametrosMotor
from tests.motored.fixtures.regresion.conjuntos import filas_base
from tests.motored.fixtures.regresion.entradas_app import entradas_app
from tests.motored.fixtures.regresion.libro_sintetico import escribir_libro
from tests.motored.fixtures.regresion.oraculo_excel import CLASES

CODIGO_A = "A-100"
CAMBIO_INVENTARIO = {CODIGO_A: {"inventario": Decimal(11)}}


@pytest.fixture
def lectura(tmp_path):
    ruta = tmp_path / "libro.xlsx"
    escribir_libro(ruta, filas_base(), etiquetas=CLASES)
    return leer_libro(ruta)


class TestEntradasIguales:
    def test_sin_divergencias_las_entradas_no_reportan_nada(self, lectura):
        resultado = ejecutar_nivel_b(lectura, entradas_app(lectura))
        assert resultado.entradas == ()
        assert resultado.filas_excel == resultado.filas_app == 6

    def test_las_salidas_dan_lo_mismo_que_el_a2_aunque_la_base_tenga_z_cero(
        self, lectura
    ):
        resultado = ejecutar_nivel_b(lectura, entradas_app(lectura))
        a2 = ejecutar_nivel_a2(lectura)
        assert resultado.salidas.diferencias == a2.diferencias
        assert resultado.salidas.nivel == "B-salidas"
        assert resultado.paso and resultado.salidas.paso

    def test_la_z_del_excel_entra_al_calculo(self, lectura):
        resultado = ejecutar_nivel_b(lectura, entradas_app(lectura))
        columnas = {
            (d.codigo, d.columna) for d in resultado.salidas.diferencias
        }
        assert ("E-500", "AB") not in columnas


class TestEntradasDistintas:
    @pytest.mark.parametrize(
        "campo, valor, columna",
        [
            ("inventario", Decimal(11), "V"),
            ("transito", Decimal(6), "W"),
            ("backorder", Decimal(1), "X"),
            ("precio", Decimal("101.5"), "T"),
            ("unidad_empaque", 2, "U"),
        ],
    )
    def test_cada_insumo_se_reporta_en_su_columna_del_excel(
        self, lectura, campo, valor, columna
    ):
        app = entradas_app(lectura, cambios={CODIGO_A: {campo: valor}})
        resultado = ejecutar_nivel_b(lectura, app)
        (diferencia,) = resultado.entradas
        assert (diferencia.codigo, diferencia.columna) == (CODIGO_A, columna)
        assert diferencia.categoria == SIN_CATEGORIA
        assert not resultado.paso

    def test_las_ventas_se_reportan_de_la_e_a_la_j(self, lectura):
        ventas = (Decimal(50),) * 5 + (Decimal(60),)
        app = entradas_app(lectura, cambios={CODIGO_A: {"ventas": ventas}})
        (diferencia,) = ejecutar_nivel_b(lectura, app).entradas
        assert diferencia.columna == "J"
        assert (diferencia.valor_excel, diferencia.valor_motor) == (
            "50.0000000000", "60.0000000000"
        )
        assert diferencia.delta == Decimal("10.0000000000")

    def test_una_fila_del_excel_que_falta_en_la_aplicacion(self, lectura):
        app = entradas_app(lectura, quitar={"D-400"})
        resultado = ejecutar_nivel_b(lectura, app)
        (diferencia,) = resultado.entradas
        assert (diferencia.codigo, diferencia.columna) == ("D-400", "FILA")
        assert (diferencia.valor_excel, diferencia.valor_motor) == (
            "presente", "ausente"
        )
        assert diferencia.fila is not None

    def test_una_fila_de_la_aplicacion_que_no_esta_en_el_excel(self, lectura):
        extra = replace(
            entradas_de(lectura)[0], codigo="X-999", ajuste=Decimal(0)
        )
        app = entradas_app(lectura, agregar=[extra])
        resultado = ejecutar_nivel_b(lectura, app)
        (diferencia,) = resultado.entradas
        assert (diferencia.codigo, diferencia.columna) == ("X-999", "FILA")
        assert (diferencia.valor_excel, diferencia.valor_motor) == (
            "ausente", "presente"
        )
        assert diferencia.fila is None

    def test_una_divergencia_aceptada_pasa_con_su_categoria(self, lectura):
        app = entradas_app(lectura, cambios=CAMBIO_INVENTARIO)
        resultado = ejecutar_nivel_b(lectura, app, {CODIGO_A: "T7"})
        assert [d.categoria for d in resultado.entradas] == ["T7"]
        assert SIN_CATEGORIA not in resultado.salidas.por_categoria
        assert resultado.paso

    def test_el_cambio_de_n_mueve_las_demas_filas_como_cascada_t2(
        self, lectura
    ):
        ventas = (Decimal(90),) * 6
        app = entradas_app(lectura, cambios={CODIGO_A: {"ventas": ventas}})
        resultado = ejecutar_nivel_b(lectura, app, {CODIGO_A: "T7"})
        assert resultado.salidas.por_categoria.get("T2", 0) > 0
        assert SIN_CATEGORIA not in resultado.salidas.por_categoria

    def test_una_divergencia_sin_aceptar_deja_sus_salidas_sin_categoria(
        self, lectura
    ):
        app = entradas_app(lectura, cambios=CAMBIO_INVENTARIO)
        resultado = ejecutar_nivel_b(lectura, app)
        assert SIN_CATEGORIA in resultado.salidas.por_categoria
        assert not resultado.paso


class TestPasa:
    def test_una_fila_extra_sin_ventas_falla_solo_por_las_entradas(
        self, lectura
    ):
        extra = replace(
            entradas_de(lectura)[0], codigo="X-000",
            ventas=(Decimal(0),) * 6, ajuste=Decimal(0),
        )
        resultado = ejecutar_nivel_b(
            lectura, entradas_app(lectura, agregar=[extra])
        )
        assert resultado.salidas.paso
        assert not resultado.entradas_pasan
        assert not resultado.paso


class TestCascada:
    @pytest.fixture
    def lectura_sin_18(self, tmp_path):
        """Libro sin filas /18: la cascada sólo puede venir de las entradas."""
        filas = [replace(f, divisor=21) for f in filas_base()]
        ruta = tmp_path / "sin18.xlsx"
        escribir_libro(ruta, filas, etiquetas=CLASES)
        return leer_libro(ruta)

    def test_sin_entradas_distintas_no_hay_cascada(self, lectura_sin_18):
        app = entradas_app(lectura_sin_18)
        resultado = ejecutar_nivel_b(lectura_sin_18, app)
        assert resultado.salidas.diferencias == ()

    def test_con_entradas_distintas_las_demas_filas_son_t2(
        self, lectura_sin_18
    ):
        ventas = (Decimal(90),) * 6
        app = entradas_app(
            lectura_sin_18, cambios={CODIGO_A: {"ventas": ventas}}
        )
        resultado = ejecutar_nivel_b(lectura_sin_18, app, {CODIGO_A: "T7"})
        assert resultado.salidas.por_categoria.get("T2", 0) > 0
        assert SIN_CATEGORIA not in resultado.salidas.por_categoria


class TestPrecondiciones:
    def test_un_switch_encendido_en_la_corrida_no_es_el_preset_legacy(
        self, lectura
    ):
        app = entradas_app(
            lectura, params=ParametrosMotor(consolidar_sustituidas=True)
        )
        with pytest.raises(PrecondicionIncumplida):
            ejecutar_nivel_b(lectura, app)


class TestResumenTexto:
    def test_las_entradas_salen_antes_que_las_salidas(self, lectura):
        app = entradas_app(lectura, cambios=CAMBIO_INVENTARIO)
        lineas = resumen_texto_b(ejecutar_nivel_b(lectura, app))
        posicion_entradas = next(
            i for i, t in enumerate(lineas) if t.startswith("B-entradas")
        )
        posicion_salidas = next(
            i for i, t in enumerate(lineas) if t.startswith("B-salidas")
        )
        assert posicion_entradas < posicion_salidas
        assert any(CODIGO_A in texto and "V" in texto for texto in lineas)

    def test_informa_la_reproduccion_cuando_se_conoce(self, lectura):
        resultado = ejecutar_nivel_b(
            lectura, entradas_app(lectura), reproduccion_identica=True
        )
        lineas = resumen_texto_b(resultado)
        assert any("Reproducción" in texto for texto in lineas)
        assert resultado.reproduccion_identica is True
