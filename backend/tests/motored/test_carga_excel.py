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
