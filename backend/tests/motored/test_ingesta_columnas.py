"""
Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra" (sdd/motored-
pedidos-ingesta, task 3.3) — `services/ingesta/columnas.py`.

Pure, DB-free tests: mapeo de encabezados por NOMBRE (nunca por posición),
detección de fila de encabezado (>=60% de match, spec "Header row is found
past leading title rows"), y plausibilidad de fecha-serial de Excel
(spec "Implausible converted date is an error").
"""
from datetime import date

import pytest

from app.motored.services.ingesta import columnas

COLUMNAS_ESPERADAS = ["fecha", "sucursal", "referencia", "cantidad inv."]


def test_construir_mapa_columnas_maps_by_normalized_name_not_position():
    encabezado = ["Cantidad Inv.", "Fecha", "Sucursal", "Referencia"]

    mapa = columnas.construir_mapa_columnas(encabezado, COLUMNAS_ESPERADAS)

    assert mapa == {"cantidad inv.": 0, "fecha": 1, "sucursal": 2, "referencia": 3}


def test_construir_mapa_columnas_trims_and_ignores_accents_and_case():
    encabezado = ["  FECHA  ", "sucursal", "Referencia", "cantidad_inv."]

    mapa = columnas.construir_mapa_columnas(encabezado, COLUMNAS_ESPERADAS)

    assert set(mapa.keys()) == {"fecha", "sucursal", "referencia", "cantidad inv."}


def test_construir_mapa_columnas_ignores_unknown_extra_columns():
    encabezado = ["fecha", "sucursal", "referencia", "cantidad inv.", "columna_desconocida"]

    mapa = columnas.construir_mapa_columnas(encabezado, COLUMNAS_ESPERADAS)

    assert "columna_desconocida" not in mapa
    assert len(mapa) == 4


def test_encontrar_fila_encabezado_skips_leading_title_rows():
    filas = [
        ["Reporte de ventas"],
        ["Generado el 2026-09-01"],
        [],
        [],
        [],
        ["Fecha", "Sucursal", "Referencia", "Cantidad Inv."],
        ["2026-09-01", "CALI NORTE", "REF1", 3],
    ]

    indice = columnas.encontrar_fila_encabezado(filas, COLUMNAS_ESPERADAS)

    assert indice == 5


def test_encontrar_fila_encabezado_accepts_partial_match_above_threshold():
    # 3 de 4 columnas esperadas = 75% >= 60%.
    filas = [["Fecha", "Sucursal", "Referencia", "Otra cosa"]]

    indice = columnas.encontrar_fila_encabezado(filas, COLUMNAS_ESPERADAS, umbral=0.6)

    assert indice == 0


def test_encontrar_fila_encabezado_raises_when_no_row_matches():
    filas = [["a", "b"], ["c", "d"]]

    with pytest.raises(columnas.EncabezadoNoEncontradoError):
        columnas.encontrar_fila_encabezado(filas, COLUMNAS_ESPERADAS)


def test_convertir_fecha_excel_accepts_plausible_serial():
    # Serial 46000 -> 2025-12-16 aprox, dentro de 2015-2100.
    resultado = columnas.convertir_fecha_excel(46000)

    assert isinstance(resultado, date)
    assert 2015 <= resultado.year <= 2100


def test_convertir_fecha_excel_rejects_year_before_2015():
    with pytest.raises(columnas.FechaExcelImplausibleError):
        columnas.convertir_fecha_excel(1)  # ~1900


def test_convertir_fecha_excel_rejects_year_after_2100():
    with pytest.raises(columnas.FechaExcelImplausibleError):
        columnas.convertir_fecha_excel(100000)  # ~2173


def test_convertir_fecha_excel_boundary_years_are_accepted():
    from datetime import date as _date, timedelta

    epoch = _date(1899, 12, 30)
    serial_2015 = (_date(2015, 1, 1) - epoch).days
    serial_2100 = (_date(2100, 12, 31) - epoch).days

    assert columnas.convertir_fecha_excel(serial_2015).year == 2015
    assert columnas.convertir_fecha_excel(serial_2100).year == 2100
