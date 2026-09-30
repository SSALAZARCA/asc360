"""
Motored Pedidos F3 "Motor" (S8a-1, ADR-10, spec Domain 4) — comparador de los
niveles A1 (fidelidad de fórmulas) y A2 (comportamiento del producto).

A1 alimenta el motor con los insumos cacheados del Excel y el override
`AjustesPrueba` (divisor por referencia y orden físico) y exige coincidencia
exacta; A2 usa divisor 21 y el orden del motor, y toda diferencia debe
llevar una categoría de la taxonomía. Los libros son sintéticos.
"""
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.motored.herramientas.regresion.comparador import (
    FECHA_CORTE_ARNES,
    Diferencia,
    PrecondicionIncumplida,
    _categoria_derivada,
    ajustes_a1,
    atributos_de,
    ejecutar_nivel_a1,
    ejecutar_nivel_a2,
    entradas_de,
    verificar_precondiciones,
)
from app.motored.herramientas.regresion.extractor_excel import leer_libro
from app.motored.herramientas.regresion.taxonomia import SIN_CATEGORIA
from app.motored.services.motor.tipos import MesEnCurso, ParametrosMotor
from tests.motored.fixtures.regresion.conjuntos import (
    CODIGO_18,
    CODIGO_MOVIDO,
    filas_base,
    filas_con_empate,
)
from tests.motored.fixtures.regresion.libro_sintetico import escribir_libro
from tests.motored.fixtures.regresion.oraculo_excel import (
    CLASES,
    FilaSintetica,
)


def _leer(tmp_path, filas, **opciones):
    ruta = tmp_path / "libro.xlsx"
    escribir_libro(ruta, filas, **opciones)
    return leer_libro(ruta)


def _columnas(resultado, codigo):
    return {d.columna: d for d in resultado.diferencias if d.codigo == codigo}


def _filas_frontera():
    """X-50 cae en neto 49.5 exacto (SS 87.5 - Y 38): pedido exacto 50."""
    return [
        FilaSintetica("X-50", (50,) * 6, precio=100.0, inventario=38),
        FilaSintetica("Y-20", (20,) * 6, precio=10.0),
        FilaSintetica("Z-10", (10,) * 6, precio=10.0),
    ]


class TestPrecondiciones:
    def _atributos(self, tmp_path, **cambios):
        atributos = atributos_de(_leer(tmp_path, filas_base()))
        return replace(atributos, **cambios)

    def test_el_preset_legacy_y_manizales_sin_apertura_pasan(self, tmp_path):
        atributos = atributos_de(_leer(tmp_path, filas_base()))
        assert atributos.fecha_apertura is None
        assert atributos.fecha_corte == FECHA_CORTE_ARNES
        assert atributos.dias_entre_pedidos == Decimal(30)
        verificar_precondiciones(ParametrosMotor(), atributos)

    @pytest.mark.parametrize("cambios", [
        {"incluir_demanda_perdida": True},
        {"consolidar_sustituidas": True},
        {"modo_redondeo": "ARRIBA"},
        {"mes_en_curso": MesEnCurso("PONDERADO", 14, 30, 3)},
    ])
    def test_un_switch_encendido_no_es_el_preset_legacy(
        self, tmp_path, cambios
    ):
        atributos = atributos_de(_leer(tmp_path, filas_base()))
        with pytest.raises(PrecondicionIncumplida, match="legacy"):
            verificar_precondiciones(ParametrosMotor(**cambios), atributos)

    def test_apertura_dentro_de_la_ventana_cambia_el_divisor(self, tmp_path):
        atributos = self._atributos(tmp_path, fecha_apertura=date(2026, 6, 1))
        with pytest.raises(PrecondicionIncumplida, match="apertura"):
            verificar_precondiciones(ParametrosMotor(), atributos)

    def test_apertura_anterior_a_la_ventana_es_aceptable(self, tmp_path):
        atributos = self._atributos(tmp_path, fecha_apertura=date(2020, 1, 1))
        verificar_precondiciones(ParametrosMotor(), atributos)

    def test_dias_entre_pedidos_distinto_de_30_no_es_legacy(self, tmp_path):
        atributos = self._atributos(
            tmp_path, dias_entre_pedidos=Decimal(7)
        )
        with pytest.raises(PrecondicionIncumplida, match="dias_entre"):
            verificar_precondiciones(ParametrosMotor(), atributos)


class TestInsumos:
    def test_entradas_reproducen_los_insumos_del_excel(self, tmp_path):
        lectura = _leer(tmp_path, filas_base())
        entradas = entradas_de(lectura)
        codigos = [f.codigo for f in lectura.filas]
        assert [e.codigo for e in entradas] == codigos
        segunda = entradas[1]
        assert segunda.ventas == (Decimal(22),) * 6
        assert segunda.unidad_empaque == 12
        assert segunda.precio == Decimal("55.5")
        assert (segunda.inventario, segunda.backorder) == (40, 3)
        assert entradas[4].ajuste == Decimal(15)
        assert entradas[3].precio is None
        assert all(e.perdidas == (Decimal(0),) * 6 for e in entradas)

    def test_atributos_salen_de_meses_de_cobertura(self, tmp_path):
        atributos = atributos_de(_leer(tmp_path, filas_base()))
        assert atributos.nombre == "SUCURSAL SINTETICA"
        assert (atributos.dias_empaque, atributos.dias_transito) == (
            Decimal(3), Decimal(2),
        )
        assert atributos.dias_seguridad == Decimal("2.5")

    def test_ajustes_a1_llevan_el_divisor_18_y_el_orden_fisico(self, tmp_path):
        lectura = _leer(tmp_path, filas_base())
        ajustes = ajustes_a1(lectura)
        assert dict(ajustes.divisor_por_referencia) == {CODIGO_18: 18}
        assert list(ajustes.orden_explicito) == [
            f.codigo for f in lectura.filas
        ]


class TestNivelA1:
    def test_coincide_exacto_en_todas_las_filas(self, tmp_path):
        lectura = _leer(tmp_path, filas_base(), etiquetas=CLASES)
        resultado = ejecutar_nivel_a1(lectura)
        assert resultado.nivel == "A1"
        assert resultado.filas_excel == 6
        assert resultado.filas_exactas == 6
        assert resultado.diferencias == ()
        assert resultado.exacto and resultado.paso

    def test_el_orden_fisico_resuelve_el_empate(self, tmp_path):
        lectura = _leer(tmp_path, filas_con_empate(), etiquetas=CLASES)
        assert ejecutar_nivel_a1(lectura).exacto

    def test_la_fila_con_ajuste_positivo_pide_exactamente_z(self, tmp_path):
        lectura = _leer(tmp_path, filas_base(), etiquetas=CLASES)
        assert lectura.filas[4].pedido == Decimal(15)
        assert ejecutar_nivel_a1(lectura).exacto

    def test_la_fila_cf_ausente_del_resumen_es_t10(self, tmp_path):
        lectura = _leer(tmp_path, filas_base())
        resultado = ejecutar_nivel_a1(lectura)
        assert not resultado.exacto and resultado.paso
        assert {d.categoria for d in resultado.diferencias} == {"T10"}
        codigos = {d.codigo for d in resultado.diferencias}
        assert {"CF", "TOTAL"} <= codigos
        assert {d.columna for d in resultado.diferencias} <= {
            "RES_unidades", "RES_referencias", "RES_valor", "RES_peso",
        }
        ausente = _columnas(resultado, "CF")["RES_unidades"]
        assert ausente.valor_excel == "ausente"
        assert resultado.filas_con_diferencias == 0
        assert resultado.por_categoria == {"T10": len(resultado.diferencias)}

    def test_dentro_de_la_tolerancia_no_hay_diferencia(self, tmp_path):
        base = filas_base()
        lectura = _leer(
            tmp_path, base, etiquetas=CLASES,
            sobrescribe={"A-100": {"AA": self._ss("A-100", tmp_path) + 4e-7}},
        )
        assert ejecutar_nivel_a1(lectura).exacto

    def test_fuera_de_la_tolerancia_es_sin_categoria(self, tmp_path):
        lectura = _leer(
            tmp_path, filas_base(), etiquetas=CLASES,
            sobrescribe={"A-100": {"AA": self._ss("A-100", tmp_path) + 6e-7}},
        )
        resultado = ejecutar_nivel_a1(lectura)
        diferencia = _columnas(resultado, "A-100")["AA"]
        assert diferencia.categoria == SIN_CATEGORIA
        assert abs(diferencia.delta) > Decimal("5e-7")
        assert not resultado.paso and resultado.filas_con_diferencias == 1

    def _ss(self, codigo, tmp_path):
        lectura = _leer(tmp_path, filas_base(), etiquetas=CLASES)
        return float(
            next(f for f in lectura.filas if f.codigo == codigo)
            .stock_objetivo
        )

    def test_el_pedido_no_admite_ninguna_tolerancia(self, tmp_path):
        lectura = _leer(
            tmp_path, filas_base(), etiquetas=CLASES,
            sobrescribe={"A-100": {"AB": 1}},
        )
        resultado = ejecutar_nivel_a1(lectura)
        assert _columnas(resultado, "A-100")["AB"].categoria == SIN_CATEGORIA
        assert resultado.por_categoria[SIN_CATEGORIA] >= 1

    def test_una_clase_distinta_se_reporta_como_texto(self, tmp_path):
        lectura = _leer(
            tmp_path, filas_base(), etiquetas=CLASES,
            sobrescribe={"A-100": {"Q": "B"}},
        )
        diferencia = _columnas(ejecutar_nivel_a1(lectura), "A-100")["Q"]
        assert (diferencia.valor_excel, diferencia.valor_motor) == ("B", "A")
        assert diferencia.delta is None


class TestDiferenciasDeEstructura:
    def test_s_estatica_inconsistente_es_t4_en_las_columnas_que_arrastra(
        self, tmp_path
    ):
        filas = filas_base()
        filas[0] = FilaSintetica(
            "A-100", (50,) * 6, precio=100.0, inventario=10, transito=5,
            clase_estatica="BM",
        )
        lectura = _leer(tmp_path, filas, etiquetas=CLASES)
        assert lectura.filas[0].clase_abc + lectura.filas[0].clase_fms == "AF"
        resultado = ejecutar_nivel_a1(lectura)
        columnas = _columnas(resultado, "A-100")
        assert {"S", "AA", "AB", "AC", "AD"} <= set(columnas)
        assert {d.categoria for d in columnas.values()} == {"T4"}
        assert resultado.paso and not resultado.exacto
        totales = [d for d in resultado.diferencias if d.fila is None]
        assert totales and {d.categoria for d in totales} == {"T4"}

    def test_u_cero_en_el_excel_explica_una_diferencia_de_pedido_como_t5(
        self, tmp_path
    ):
        filas = filas_base()
        filas[3] = FilaSintetica("D-400", (5,) * 6, precio=3.0, unidad=0)
        lectura = _leer(
            tmp_path, filas, etiquetas=CLASES,
            sobrescribe={"D-400": {"AB": 7}},
        )
        assert lectura.filas[3].unidad_empaque == 0
        columnas = _columnas(ejecutar_nivel_a1(lectura), "D-400")
        assert columnas["AB"].categoria == "T5"

    def test_fila_que_el_motor_no_calcula_es_sin_categoria(self, tmp_path):
        filas = filas_base() + [
            FilaSintetica("Z-000", (0,) * 6, precio=5.0, inventario=3)
        ]
        resultado = ejecutar_nivel_a1(
            _leer(tmp_path, filas, etiquetas=CLASES)
        )
        diferencia = _columnas(resultado, "Z-000")["FILA"]
        assert diferencia.categoria == SIN_CATEGORIA
        assert (diferencia.valor_excel, diferencia.valor_motor) == (
            "presente", "ausente",
        )
        assert not resultado.paso

    def test_la_aceptacion_explicita_hace_pasar_la_fila(self, tmp_path):
        filas = filas_base() + [
            FilaSintetica("Z-000", (0,) * 6, precio=5.0, inventario=3)
        ]
        lectura = _leer(tmp_path, filas, etiquetas=CLASES)
        resultado = ejecutar_nivel_a1(lectura, {"Z-000": "T7"})
        assert _columnas(resultado, "Z-000")["FILA"].categoria == "T7"
        assert resultado.paso and not resultado.exacto
        assert resultado.filas_por_categoria == {"T7": 1}

    def test_frontera_de_medio_entre_excel_y_motor_es_t9(self, tmp_path):
        lectura = _leer(
            tmp_path, _filas_frontera(), etiquetas=CLASES,
            sobrescribe={"X-50": {"AB": 49, "AC": 4900.0, "AD": 1.74}},
        )
        assert lectura.filas[0].pedido == Decimal(49)
        resultado = ejecutar_nivel_a1(lectura)
        columnas = _columnas(resultado, "X-50")
        assert set(columnas) == {"AB", "AC", "AD"}
        assert {d.categoria for d in columnas.values()} == {"T9"}
        assert columnas["AB"].valor_motor == "50.0000000000"

    def test_sin_frontera_de_medio_el_mismo_error_no_es_t9(self, tmp_path):
        filas = _filas_frontera()
        filas[0] = FilaSintetica(
            "X-50", (50,) * 6, precio=100.0, inventario=38.25,
        )
        lectura = _leer(
            tmp_path, filas, etiquetas=CLASES,
            sobrescribe={"X-50": {"AB": 48, "AC": 4800.0}},
        )
        columnas = _columnas(ejecutar_nivel_a1(lectura), "X-50")
        assert columnas["AB"].categoria == SIN_CATEGORIA

    def test_cobertura_distinta_del_excel_se_reporta_por_clase(
        self, tmp_path
    ):
        lectura = _leer(tmp_path, filas_base(), etiquetas=CLASES)
        lectura = replace(lectura, coberturas={
            **lectura.coberturas, "AF": Decimal("1.8"),
        })
        resultado = ejecutar_nivel_a1(lectura)
        diferencia = _columnas(resultado, "AF")["E3:N3"]
        assert diferencia.categoria == SIN_CATEGORIA
        assert abs(diferencia.delta) == Decimal("0.05")


class TestCategoriaDerivada:
    def _diferencia(self, categoria, columna="AB"):
        return Diferencia("X", 1, columna, "1", "2", None, categoria)

    def test_una_sola_categoria_se_hereda(self):
        filas = [self._diferencia("T4"), self._diferencia("T4", "S")]
        assert _categoria_derivada(filas) == "T4"

    @pytest.mark.parametrize("par", [
        ("T1", "T9"), ("T4", "T3"), ("T5", "T1"), ("T9", "T4"),
    ])
    def test_varias_categorias_distintas_son_cascada(self, par):
        filas = [self._diferencia(par[0]), self._diferencia(par[1], "S")]
        assert _categoria_derivada(filas) == "T2"

    def test_sin_filas_que_cambien_totales_no_hay_categoria(self):
        assert _categoria_derivada([self._diferencia("T1", "O")]) == (
            SIN_CATEGORIA
        )


class TestNivelA2:
    def test_divisor_21_solo_cambia_c300_y_su_cascada(self, tmp_path):
        lectura = _leer(tmp_path, filas_base(), etiquetas=CLASES)
        resultado = ejecutar_nivel_a2(lectura)
        assert resultado.nivel == "A2"
        assert resultado.paso and not resultado.exacto
        categorias = {d.categoria for d in resultado.diferencias}
        assert categorias == {"T1", "T2"}
        assert _columnas(resultado, CODIGO_18)["N"].categoria == "T1"

    def test_la_clase_de_b200_se_mueve_por_cascada_sin_cambiar_su_pedido(
        self, tmp_path
    ):
        lectura = _leer(tmp_path, filas_base(), etiquetas=CLASES)
        columnas = _columnas(ejecutar_nivel_a2(lectura), CODIGO_MOVIDO)
        assert (columnas["Q"].valor_excel, columnas["Q"].valor_motor) == (
            "A", "B",
        )
        assert columnas["S"].categoria == "T2"
        assert "AB" not in columnas and "N" not in columnas

    def test_el_peso_de_todas_las_filas_cambia_por_cascada(self, tmp_path):
        lectura = _leer(tmp_path, filas_base(), etiquetas=CLASES)
        resultado = ejecutar_nivel_a2(lectura)
        con_peso = {d.codigo for d in resultado.diferencias
                    if d.columna == "O"}
        assert con_peso == {f.codigo for f in lectura.filas}
        assert resultado.filas_con_diferencias == 6

    def test_una_diferencia_de_n_fuera_de_la_taxonomia_falla(self, tmp_path):
        lectura = _leer(
            tmp_path, filas_base(), etiquetas=CLASES,
            sobrescribe={"A-100": {"N": 50.5}},
        )
        resultado = ejecutar_nivel_a2(lectura)
        assert _columnas(resultado, "A-100")["N"].categoria == SIN_CATEGORIA
        assert not resultado.paso

    def test_la_clase_unica_del_empate_es_t3(self, tmp_path):
        lectura = _leer(tmp_path, filas_con_empate(), etiquetas=CLASES)
        resultado = ejecutar_nivel_a2(lectura)
        assert {d.codigo for d in resultado.diferencias} == {
            "G-1", "G-2", "AF", "CF",
        }
        assert {d.categoria for d in resultado.diferencias} == {"T3"}
        columnas = {
            d.columna for d in resultado.diferencias if d.fila is not None
        }
        assert columnas == {"P", "Q", "S"}
        assert resultado.paso

    def test_un_empate_en_orden_ascendente_solo_cambia_la_clase_por_t3(
        self, tmp_path
    ):
        filas = [
            FilaSintetica("H-0", (40,) * 6, precio=10.0),
            FilaSintetica("G-1", (20,) * 6, precio=10.0),
            FilaSintetica("G-2", (20,) * 6, precio=10.0),
            FilaSintetica("K-18", (9,) * 6, precio=10.0, divisor=18),
            FilaSintetica("I-9", (2,) * 6, precio=10.0),
        ]
        resultado = ejecutar_nivel_a2(
            _leer(tmp_path, filas, etiquetas=CLASES)
        )
        empatadas = [
            d for d in resultado.diferencias if d.codigo in {"G-1", "G-2"}
        ]
        assert {d.columna for d in empatadas} == {"O", "P", "Q", "S"}
        assert {
            d.columna for d in empatadas if d.categoria == "T2"
        } == {"O", "P"}
        assert {
            d.columna for d in empatadas if d.categoria == "T3"
        } == {"Q", "S"}

    def test_solo_lo_que_cambia_el_desempate_es_t3_y_el_resto_es_cascada(
        self, tmp_path
    ):
        filas = [
            FilaSintetica("H-0", (40,) * 6, precio=10.0),
            FilaSintetica("G-2", (20,) * 6, precio=10.0),
            FilaSintetica("G-1", (20,) * 6, precio=10.0),
            FilaSintetica("K-18", (9,) * 6, precio=10.0, divisor=18),
            FilaSintetica("I-9", (2,) * 6, precio=10.0),
        ]
        resultado = ejecutar_nivel_a2(
            _leer(tmp_path, filas, etiquetas=CLASES)
        )
        for codigo in ("G-1", "G-2"):
            columnas = _columnas(resultado, codigo)
            assert columnas["P"].categoria == "T3"
            assert columnas["O"].categoria == "T2"
        assert _columnas(resultado, "H-0")["P"].categoria == "T2"

    def test_los_conteos_por_categoria_suman_las_diferencias(self, tmp_path):
        lectura = _leer(tmp_path, filas_base(), etiquetas=CLASES)
        resultado = ejecutar_nivel_a2(lectura)
        assert sum(resultado.por_categoria.values()) == len(
            resultado.diferencias
        )
        assert resultado.por_categoria["T1"] >= 1
        assert set(resultado.filas_por_categoria) <= {"T1", "T2"}

    def test_el_resumen_en_cascada_hereda_la_categoria_de_las_filas(
        self, tmp_path
    ):
        lectura = _leer(tmp_path, filas_base(), etiquetas=CLASES)
        resumen = [
            d for d in ejecutar_nivel_a2(lectura).diferencias
            if d.fila is None and d.columna.startswith("RES_")
        ]
        assert resumen, "el divisor 18 cambia los pedidos y el resumen"
        assert {d.categoria for d in resumen} == {"T2"}
