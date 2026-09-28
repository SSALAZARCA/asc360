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


# ---------------------------------------------------------------------------
# Referencia 9-column layout (owner request 2026-09-28): human headers from the
# server-generated template, homologados multi-value cell, precio_venta dropped
# from the Excel contract, and backward compatibility with older templates.
# ---------------------------------------------------------------------------
REFERENCIA_TEMPLATE_HEADERS = [
    "Código",
    "Código del proveedor",
    "Nombre",
    "Línea comercial",
    "Unidad de empaque",
    "Precio Normal antes de IVA",
    "Precio Público antes de IVA",
    "Código de referencia sustituta",
    "Homologados otras marcas",
]


def test_referencia_template_headers_map_every_column_to_its_canonical_key():
    file_bytes = _build_xlsx_bytes(
        REFERENCIA_TEMPLATE_HEADERS,
        [["REF1", "HMCL", "Filtro", "REPUESTOS", 2, 1000, 1500, "REF0", "YAM-1; HON-2"]],
    )

    rows = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    assert rows == [{
        "codigo": "REF1",
        "proveedor_codigo": "HMCL",
        "nombre": "Filtro",
        "linea_comercial": "REPUESTOS",
        "unidad_empaque": 2,
        "precio_normal": 1000,
        "precio_publico": 1500,
        "sustituida_por_codigo": "REF0",
        "homologados": ["YAM-1", "HON-2"],
    }]


def test_referencia_template_round_trips_through_column_labels():
    """Downloading the template and uploading it untouched must never lose a
    column -- every label written by `column_labels` must parse back."""
    from app.motored.services.carga_excel import column_labels

    labels = column_labels("referencia")
    assert labels == REFERENCIA_TEMPLATE_HEADERS

    file_bytes = _build_xlsx_bytes(labels, [["REF1", "HMCL", None, None, None, None, None, None, None]])
    rows = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    assert rows[0]["codigo"] == "REF1"
    assert rows[0]["proveedor_codigo"] == "HMCL"
    # Blank template columns must reach validation as "not provided", never
    # as explicit values that an upsert-update would write over existing data.
    from app.motored.services.validators import validate_rows

    rows[0]["proveedor_id"] = "00000000-0000-0000-0000-000000000001"
    valid, errors = validate_rows("referencia", rows)
    assert errors == []
    assert set(valid[0]) == {"codigo", "proveedor_codigo", "proveedor_id", "_warnings"}


def test_referencia_headers_tolerate_case_and_surrounding_whitespace():
    file_bytes = _build_xlsx_bytes(
        ["  CÓDIGO ", "código DEL proveedor  ", " homologados OTRAS marcas"],
        [["REF1", "HMCL", "A"]],
    )

    rows = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    assert rows == [{"codigo": "REF1", "proveedor_codigo": "HMCL", "homologados": ["A"]}]


def test_referencia_old_snake_case_headers_still_parse():
    file_bytes = _build_xlsx_bytes(
        [
            "codigo", "proveedor_codigo", "nombre", "linea_comercial", "unidad_empaque",
            "precio_normal", "precio_publico", "sustituida_por_codigo", "homologados",
        ],
        [["REF1", "HMCL", "Filtro", "REPUESTOS", 1, 10, 20, "REF0", "A,B"]],
    )

    rows = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    assert rows[0]["proveedor_codigo"] == "HMCL"
    assert rows[0]["precio_normal"] == 10
    assert rows[0]["precio_publico"] == 20
    assert rows[0]["sustituida_por_codigo"] == "REF0"
    assert rows[0]["homologados"] == ["A", "B"]


def test_referencia_previous_template_labels_still_parse():
    """The template generated before 2026-09-28 used "Precio normal" /
    "Precio al público" / "Precio de venta" -- a previously downloaded
    template must still upload. `precio_venta` is no longer part of the Excel
    contract, so that column is ignored (the DB column is kept untouched)."""
    file_bytes = _build_xlsx_bytes(
        ["Código", "Código del proveedor", "Precio normal", "Precio de venta", "Precio al público"],
        [["REF1", "HMCL", 10, 15, 20]],
    )

    rows = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    assert rows == [{"codigo": "REF1", "proveedor_codigo": "HMCL", "precio_normal": 10, "precio_publico": 20}]


def test_referencia_precio_venta_is_not_in_the_template():
    from app.motored.services.carga_excel import column_labels

    labels = column_labels("referencia")
    assert not any("venta" in label.lower() for label in labels)


def test_homologados_cell_splits_on_comma_and_semicolon_trims_drops_empties_and_dedupes():
    file_bytes = _build_xlsx_bytes(
        ["Código", "Código del proveedor", "Homologados otras marcas"],
        [["REF1", "HMCL", " YAM-1 , HON-2;;YAM-1 ;  ; SUZ-3,"]],
    )

    rows = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    assert rows[0]["homologados"] == ["YAM-1", "HON-2", "SUZ-3"]


def test_blank_homologados_cell_is_passed_through_like_any_other_blank_cell():
    """Same blank-cell contract as every other optional column -- the parser
    never turns a blank cell into a list on its own."""
    file_bytes = _build_xlsx_bytes(
        ["Código", "Código del proveedor", "Homologados otras marcas"],
        [["REF1", "HMCL", None]],
    )

    rows = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    # Exactly what the CSV path produces for a blank cell -- `validate_rows`
    # then drops it as "not provided".
    assert rows[0]["homologados"] == ""


def test_numeric_homologados_cell_is_coerced_to_text():
    file_bytes = _build_xlsx_bytes(
        ["Código", "Código del proveedor", "Homologados otras marcas"],
        [["REF1", "HMCL", 12345]],
    )

    rows = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    assert rows[0]["homologados"] == ["12345"]


def test_blank_boolean_cell_stays_blank_instead_of_becoming_false():
    """A blank "Principal (Sí/No)" cell must not turn into an explicit
    `False` that would demote an existing principal proveedor on upsert."""
    file_bytes = _build_xlsx_bytes(["Código", "Nombre", "Principal (Sí/No)"], [["HMCL", "HMCL", None]])

    rows = parse_excel_rows("proveedor", "proveedores.xlsx", file_bytes)

    assert rows[0]["es_principal"] == ""


def test_whitespace_only_cell_is_blank_too():
    file_bytes = _build_xlsx_bytes(["Nombre", "SIC"], [["CALI NORTE", "   "]])

    rows = parse_excel_rows("sucursal", "sucursales.xlsx", file_bytes)

    assert rows[0]["sic"] == ""


def test_duplicate_headers_for_the_same_field_are_rejected_with_a_clear_error():
    from app.motored.services.carga_excel import ColumnaDuplicadaError

    file_bytes = _build_xlsx_bytes(["Código", "codigo", "Código del proveedor"], [["REF1", "REF2", "HMCL"]])

    with pytest.raises(ColumnaDuplicadaError) as exc_info:
        parse_excel_rows("referencia", "referencias.xlsx", file_bytes)

    assert "Código" in str(exc_info.value)
