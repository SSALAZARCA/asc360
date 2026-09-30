"""
Motored Pedidos F3 "Motor" (S8a-1, ADR-10) — taxonomía de diferencias de los
niveles A1/A2 de la regresión contra el Excel: categorías T1..T11, reglas de
clasificación y archivo de aceptaciones. `SIN_CATEGORIA` hace fallar el nivel.
"""
import json

import pytest

from app.motored.herramientas.regresion.taxonomia import (
    CATEGORIAS,
    SIN_CATEGORIA,
    ContextoFila,
    aplicar_aceptacion,
    cargar_aceptaciones,
    clasificar,
)


class TestCategorias:
    def test_estan_t1_a_t11_y_sin_categoria(self):
        esperadas = {f"T{i}" for i in range(1, 12)} | {SIN_CATEGORIA}
        assert set(CATEGORIAS) == esperadas

    def test_cada_categoria_tiene_descripcion_en_espanol(self):
        assert all(len(texto) > 15 for texto in CATEGORIAS.values())

    def test_t4_es_la_s_estatica_que_contradice_q_y_r(self):
        assert "estática" in CATEGORIAS["T4"]
        assert "Q" in CATEGORIAS["T4"] and "R" in CATEGORIAS["T4"]

    def test_t11_es_la_etiqueta_ds_de_la_decision_19(self):
        assert "DS" in CATEGORIAS["T11"]
        assert "DM" in CATEGORIAS["T11"] and "DF" in CATEGORIAS["T11"]


class TestClasificar:
    @pytest.mark.parametrize("columna, contexto, esperada", [
        ("N", ContextoFila(nivel="A2", divisor_distinto=True), "T1"),
        ("AB", ContextoFila(nivel="A2", divisor_distinto=True), "T1"),
        ("S", ContextoFila(estatica_inconsistente=True), "T4"),
        ("AA", ContextoFila(estatica_inconsistente=True), "T4"),
        ("AB", ContextoFila(u_cero=True), "T5"),
        ("S", ContextoFila(d_como_ds=True), "T11"),
        ("S", ContextoFila(nivel="A2", hay_divisor_distinto=True,
                           d_como_ds=True), "T11"),
        ("S", ContextoFila(estatica_inconsistente=True, d_como_ds=True),
         "T4"),
        ("AB", ContextoFila(frontera_medio=True), "T9"),
        ("Q", ContextoFila(frontera_abc=True), "T9"),
        ("Q", ContextoFila(columnas_empate=frozenset({"Q", "S"})), "T3"),
        ("P", ContextoFila(columnas_empate=frozenset({"P"})), "T3"),
        ("O", ContextoFila(nivel="A2", hay_divisor_distinto=True), "T2"),
        ("Q", ContextoFila(nivel="A2", hay_divisor_distinto=True), "T2"),
        ("S", ContextoFila(nivel="A2", hay_divisor_distinto=True), "T2"),
    ])
    def test_reglas(self, columna, contexto, esperada):
        assert clasificar(columna, contexto) == esperada

    @pytest.mark.parametrize("columna, contexto", [
        ("N", ContextoFila()),
        ("N", ContextoFila(nivel="A2", hay_divisor_distinto=True)),
        ("R", ContextoFila(nivel="A2", hay_divisor_distinto=True)),
        ("AB", ContextoFila(nivel="A2", hay_divisor_distinto=True)),
        ("AD", ContextoFila(nivel="A2", hay_divisor_distinto=True)),
        ("AB", ContextoFila(estatica_inconsistente=False, nivel="A1")),
        ("Q", ContextoFila(nivel="A1", hay_divisor_distinto=True)),
        ("P", ContextoFila(columnas_empate=frozenset({"Q"}))),
        ("S", ContextoFila(d_como_ds=False)),
        ("AB", ContextoFila(d_como_ds=True)),
        ("Q", ContextoFila(d_como_ds=True)),
    ])
    def test_sin_regla_que_aplique_es_sin_categoria(self, columna, contexto):
        assert clasificar(columna, contexto) == SIN_CATEGORIA

    def test_el_empate_gana_a_la_cascada_solo_en_las_columnas_que_cambia(self):
        contexto = ContextoFila(
            nivel="A2", hay_divisor_distinto=True,
            columnas_empate=frozenset({"P"}),
        )
        assert clasificar("P", contexto) == "T3"
        assert clasificar("O", contexto) == "T2"

    def test_el_divisor_18_gana_a_la_cascada_y_a_la_s_estatica(self):
        contexto = ContextoFila(
            nivel="A2", divisor_distinto=True, hay_divisor_distinto=True,
            estatica_inconsistente=True,
        )
        assert clasificar("S", contexto) == "T1"

    def test_en_a1_el_divisor_18_ya_esta_reproducido(self):
        contexto = ContextoFila(nivel="A1", divisor_distinto=True)
        assert clasificar("N", contexto) == SIN_CATEGORIA


class TestAceptaciones:
    def test_carga_un_mapa_codigo_categoria(self, tmp_path):
        ruta = tmp_path / "aceptaciones.json"
        ruta.write_text(json.dumps({"REF-1": "T7", "REF-2": "T8"}))
        assert cargar_aceptaciones(ruta) == {"REF-1": "T7", "REF-2": "T8"}

    @pytest.mark.parametrize("contenido", [
        {"REF-1": "T99"}, {"REF-1": SIN_CATEGORIA}, ["REF-1"], {"REF-1": 7},
    ])
    def test_rechaza_categorias_invalidas_o_formas_raras(
        self, tmp_path, contenido
    ):
        ruta = tmp_path / "aceptaciones.json"
        ruta.write_text(json.dumps(contenido))
        with pytest.raises(ValueError):
            cargar_aceptaciones(ruta)

    def test_aplica_solo_a_las_diferencias_sin_categoria(self):
        aceptaciones = {"REF-1": "T7"}
        assert aplicar_aceptacion(SIN_CATEGORIA, "REF-1", aceptaciones) == "T7"
        assert aplicar_aceptacion("T1", "REF-1", aceptaciones) == "T1"
        assert aplicar_aceptacion(
            SIN_CATEGORIA, "REF-2", aceptaciones
        ) == SIN_CATEGORIA
