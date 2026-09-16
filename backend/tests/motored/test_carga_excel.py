"""
Batch: `.xlsx` bulk-upload support for masters carga masiva
(sdd/motored-pedidos-cimientos, post-Fase-6, owner brief "Excel upload
capability").

Pure, DB-free tests for `services/carga_excel.py::parse_excel_rows` -- the
server-side `.xlsx` parser that mirrors `BulkUploadModal.js`'s
`COLUMNAS_POR_ENTIDAD` (alias/required config) and produces the SAME
canonical `list[dict]` shape the JSON path already consumes via
`validate_rows`/`procesar_carga`.
"""
import io

import openpyxl
import pytest

from app.config import settings
from app.motored.services.carga_excel import (
    ArchivoExcelInvalidoError,
    ColumnaObligatoriaFaltanteError,
    FormatoNoSoportadoError,
    LimiteFilasExcedidoError,
    parse_excel_rows,
)


def _build_xlsx_bytes(headers, rows):
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_valid_xlsx_parses_into_canonical_rows():
    file_bytes = _build_xlsx_bytes(
        ["Nombre", "SIC", "Días de seguridad"],
        [["CALI NORTE", "S001", 3]],
    )

    rows = parse_excel_rows("sucursal", "sucursales.xlsx", file_bytes)

    assert rows == [{"nombre": "CALI NORTE", "sic": "S001", "dias_seguridad": 3}]


def test_header_aliases_are_case_and_accent_insensitive():
    file_bytes = _build_xlsx_bytes(
        ["nombre", "dias_seguridad"],
        [["CALI NORTE", 2]],
    )

    rows = parse_excel_rows("sucursal", "sucursales.xlsx", file_bytes)

    assert rows == [{"nombre": "CALI NORTE", "dias_seguridad": 2}]


def test_boolean_column_is_coerced_like_the_frontend():
    file_bytes = _build_xlsx_bytes(
        ["Código", "Nombre", "Principal (Sí/No)"],
        [["HMCL", "HMCL", "Sí"], ["OTRO", "Otro", "No"]],
    )

    rows = parse_excel_rows("proveedor", "proveedores.xlsx", file_bytes)

    assert rows[0]["es_principal"] is True
    assert rows[1]["es_principal"] is False


def test_missing_required_column_is_rejected_before_any_row_is_read():
    file_bytes = _build_xlsx_bytes(
        ["SIC", "Días de seguridad"],
        [["S001", 2]],
    )

    with pytest.raises(ColumnaObligatoriaFaltanteError, match="Nombre"):
        parse_excel_rows("sucursal", "sucursales.xlsx", file_bytes)


def test_oversized_row_count_aborts_mid_parse(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_MAX_UPLOAD_ROWS", 1)
    file_bytes = _build_xlsx_bytes(
        ["Nombre"],
        [["UNO"], ["DOS"]],
    )

    with pytest.raises(LimiteFilasExcedidoError):
        parse_excel_rows("sucursal", "sucursales.xlsx", file_bytes)


def test_corrupt_file_raises_a_clean_error_not_an_unhandled_exception():
    with pytest.raises(ArchivoExcelInvalidoError):
        parse_excel_rows("sucursal", "sucursales.xlsx", b"this is not a real xlsx file")


def test_xls_extension_is_explicitly_rejected_with_a_clear_message():
    with pytest.raises(FormatoNoSoportadoError, match=r"\.xls"):
        parse_excel_rows("sucursal", "sucursales.xls", b"whatever")


def test_wrong_extension_is_rejected_before_attempting_to_parse():
    with pytest.raises(FormatoNoSoportadoError):
        parse_excel_rows("sucursal", "sucursales.txt", b"whatever")


def test_empty_sheet_is_rejected_cleanly():
    wb = openpyxl.Workbook()
    buffer = io.BytesIO()
    wb.save(buffer)

    with pytest.raises(ArchivoExcelInvalidoError):
        parse_excel_rows("sucursal", "sucursales.xlsx", buffer.getvalue())


def test_referencia_row_maps_proveedor_codigo_for_the_router_to_resolve():
    file_bytes = _build_xlsx_bytes(
        ["Código", "Código proveedor"],
        [["REF1", "HMCL"]],
    )

    rows = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    assert rows == [{"codigo": "REF1", "proveedor_codigo": "HMCL"}]


def test_numeric_sic_cell_is_coerced_to_string():
    """Bug real reportado: si SIC se escribe como número en Excel (ej. una
    celda con 12345 en vez de "12345"), openpyxl lo devuelve como int, y el
    schema espera `str` -- sin coerción, Pydantic rechaza CADA fila con
    "sic: Input should be a valid string"."""
    file_bytes = _build_xlsx_bytes(
        ["Nombre", "SIC"],
        [["CALI NORTE", 12345]],
    )

    rows = parse_excel_rows("sucursal", "sucursales.xlsx", file_bytes)

    assert rows == [{"nombre": "CALI NORTE", "sic": "12345"}]


def test_comma_decimal_numeric_field_is_normalized_to_period():
    """Si `dias_seguridad` queda guardado como texto con coma decimal
    ("2,5", convención regional en español) en vez de convertirse a un
    número real, `Decimal("2,5")` explota -- se normaliza a "2.5" antes de
    llegar al schema."""
    file_bytes = _build_xlsx_bytes(
        ["Nombre", "Días de seguridad"],
        [["CALI NORTE", "2,5"]],
    )

    rows = parse_excel_rows("sucursal", "sucursales.xlsx", file_bytes)

    assert rows == [{"nombre": "CALI NORTE", "dias_seguridad": "2.5"}]


def test_sic_as_a_decimal_number_is_also_coerced_not_just_integers():
    """El problema nunca fue el separador decimal -- CUALQUIER número
    (entero o con punto) deja de ser texto para Python/Pydantic. Confirma
    que un SIC como 12345.0 (float) se corrige igual que un entero."""
    file_bytes = _build_xlsx_bytes(
        ["Nombre", "SIC"],
        [["CALI NORTE", 12345.0]],
    )

    rows = parse_excel_rows("sucursal", "sucursales.xlsx", file_bytes)

    assert rows[0]["sic"] in ("12345", "12345.0")


def test_numeric_proveedor_codigo_is_coerced_to_string_for_the_router_lookup():
    """`proveedor_codigo` no es un campo del schema Pydantic (lo resuelve
    `api/carga.py::_resolve_proveedor_codigos` contra `Proveedor.codigo`,
    una columna string) -- si Excel lo entrega como número, la búsqueda por
    código fallaría en silencio sin este fix."""
    file_bytes = _build_xlsx_bytes(
        ["Código", "Código proveedor"],
        [["REF1", 1234]],
    )

    rows = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    assert rows == [{"codigo": "REF1", "proveedor_codigo": "1234"}]
