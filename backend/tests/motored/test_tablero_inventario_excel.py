"""
KPI's, Inventario: the Excel (`GET /kpis/inventario/excel`) built from the payload of the tab plus the
complete lists. These tests read the workbook back with openpyxl.
"""
import io

import pytest
from openpyxl import load_workbook

from app.motored.services import tablero_inventario_excel as excel

DATOS = {
    "corte": "2026-10-07", "costo_desde": "2026-08-01", "costo_hasta": "2026-10-31", "sin_movimiento_umbral_dias": 180,
    "tarjetas": {"valor": 7780.0},
    "tiendas": [
        {"sucursal_id": "a", "nombre": "Norte", "valor": 4250.0, "dias": 425.5, "rotacion": 0.86,
         "sin_movimiento_valor": 50.0, "disponibilidad_pct": 0.5, "agotadas": 1},
        {"sucursal_id": "b", "nombre": "Sur", "valor": 3530.0, "dias": None, "rotacion": None,
         "sin_movimiento_valor": 520.0, "disponibilidad_pct": None, "agotadas": 0}],
    "lineas": [
        {"linea": "REPUESTOS", "valor": 7320.0, "pct": 0.94, "dias": 90.5, "rotacion": 4.0, "disponibilidad_pct": 0.66},
        {"linea": "Sin línea", "valor": 10.0, "pct": 0.001, "dias": None, "rotacion": None, "disponibilidad_pct": None}],
}
SIN_MOVIMIENTO = [
    {"referencia": "R3-X", "nombre": "Casco", "sucursal_id": "b", "tienda": "Sur", "existencia": 2, "valor": 200.0,
     "dias_sin_venta": 494},
    {"referencia": "R2-X", "nombre": None, "sucursal_id": "a", "tienda": "Norte", "existencia": 4.5, "valor": 200.0,
     "dias_sin_venta": 190}]
AGOTADAS = [
    {"referencia": "R6-X", "nombre": "Aceite", "sucursal_id": "a", "tienda": "Norte", "vendidas": 20, "perdidas": 6,
     "demanda": 26, "transito": 70, "cobertura": 1.0},
    {"referencia": "R2-X", "nombre": None, "sucursal_id": "b", "tienda": "Sur", "vendidas": 7, "perdidas": 3,
     "demanda": 10, "transito": 0, "cobertura": 0.0}]


def _libro(datos=DATOS, tiendas=("Norte", "Sur")):
    return load_workbook(io.BytesIO(excel.construir_libro(datos, SIN_MOVIMIENTO, AGOTADAS, list(tiendas))))


def _filas(hoja):
    return [[c.value for c in fila] for fila in hoja.iter_rows()]


def _tabla(hoja, primera):
    filas = _filas(hoja)
    inicio = next(i for i, f in enumerate(filas) if f[0] == primera)
    return inicio, filas[inicio:]


def test_the_workbook_has_the_four_sheets_in_order():
    assert _libro().sheetnames == ["Tiendas", "Líneas", "Sin movimiento", "Agotadas"]


def test_every_sheet_names_the_corte_the_window_and_the_stores():
    for hoja in _libro().worksheets:
        texto = "\n".join(str(v) for f in _filas(hoja) for v in f if v is not None)
        assert "2026-10-07" in texto and "2026-08-01" in texto and "2026-10-31" in texto
        assert "Norte, Sur" in texto


def test_without_a_store_filter_the_header_says_every_store():
    texto = "\n".join(str(v) for f in _filas(_libro(tiendas=())["Tiendas"]) for v in f if v is not None)
    assert "Todas las tiendas" in texto


def test_the_stores_sheet_has_one_row_per_store_with_numbers_and_percent_formats():
    hoja = _libro()["Tiendas"]
    inicio, tabla = _tabla(hoja, "Tienda")

    assert tabla[0] == ["Tienda", "Valor", "Días de inventario", "Rotación", "Sin movimiento", "Disponibilidad", "Agotadas"]
    assert tabla[1] == ["Norte", 4250.0, 425.5, 0.86, 50.0, 0.5, 1]
    assert tabla[2] == ["Sur", 3530.0, None, None, 520.0, None, 0]
    fila = inicio + 2
    assert hoja.cell(row=fila, column=2).number_format == "#,##0"
    assert hoja.cell(row=fila, column=6).number_format == "0.0%"


def test_the_lines_sheet_has_value_share_days_and_availability():
    _, tabla = _tabla(_libro()["Líneas"], "Línea")

    assert tabla[0] == ["Línea", "Valor", "% del inventario", "Días de inventario", "Rotación", "Disponibilidad"]
    assert tabla[1] == ["REPUESTOS", 7320.0, 0.94, 90.5, 4.0, 0.66] and tabla[2][0] == "Sin línea"


def test_the_idle_sheet_lists_every_pair_and_says_the_threshold():
    hoja = _libro()["Sin movimiento"]
    _, tabla = _tabla(hoja, "Referencia")

    assert tabla[0] == ["Referencia", "Nombre", "Tienda", "Existencia", "Valor", "Días sin venta"]
    assert tabla[1:] == [["R3-X", "Casco", "Sur", 2, 200.0, 494], ["R2-X", None, "Norte", 4.5, 200.0, 190]]
    assert "180" in "\n".join(str(v) for f in _filas(hoja) for v in f if v is not None)


def test_the_stockouts_sheet_has_sold_lost_demand_transit_and_coverage():
    _, tabla = _tabla(_libro()["Agotadas"], "Referencia")

    assert tabla[0] == ["Referencia", "Nombre", "Tienda", "Vendidas", "Perdidas", "Demanda", "En tránsito", "Cobertura del tránsito"]
    assert tabla[1] == ["R6-X", "Aceite", "Norte", 20, 6, 26, 70, 1.0]
    assert tabla[2][7] == 0.0


def test_the_file_name_carries_the_corte():
    assert excel.nombre_de_archivo(DATOS) == "inventario_2026-10-07.xlsx"
    assert excel.nombre_de_archivo({**DATOS, "corte": None}) == "inventario_sin_corte.xlsx"


def test_an_empty_payload_still_builds_a_workbook():
    vacio = {**DATOS, "corte": None, "tiendas": [], "lineas": []}
    libro = load_workbook(io.BytesIO(excel.construir_libro(vacio, [], [], [])))
    assert libro.sheetnames == ["Tiendas", "Líneas", "Sin movimiento", "Agotadas"]


@pytest.mark.parametrize("hoja", ["Tiendas", "Líneas", "Sin movimiento", "Agotadas"])
def test_the_headers_are_bold(hoja):
    ws = _libro()[hoja]
    primera = {"Tiendas": "Tienda", "Líneas": "Línea"}.get(hoja, "Referencia")
    inicio, _ = _tabla(ws, primera)
    assert all(c.font.bold for c in ws[inicio + 1] if c.value is not None)
