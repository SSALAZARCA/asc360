"""
Motored budgets (odd/motored-presupuestos-gerencia, T2): pure parsing and
validation of the budget upload. No database: the lookups (cedulas, sucursales)
arrive as a `Catalogos` value, so every rule is exercised directly.

Rules covered: Mes formats, Presupuesto parsing, cedula must match a vendedor
(inactive-only is a warning), Tienda by name/alias (inactive or unknown is an
error), repeated cedula in the same month, and the dry-run summary.
"""
import datetime
import io
import uuid

import openpyxl
import pytest

from app.motored.services.carga_excel import ColumnaObligatoriaFaltanteError, parse_excel_rows
from app.motored.services.presupuestos_archivo import (
    Catalogos,
    mes_de_fila,
    parse_anio,
    parse_mes,
    parse_mes_numero,
    parse_monto,
    resumir,
    validar_filas,
)

D = datetime.date
CALI = uuid.uuid4()
BOGOTA = uuid.uuid4()
CERRADA = uuid.uuid4()


def _catalogos():
    return Catalogos(
        cedula_activa={"111": True, "222": True, "333": False},
        sucursal_por_texto={"CALI": CALI, "SEDE VIEJA": CALI, "BOGOTA": BOGOTA, "CERRADA": CERRADA},
        sucursal_activa={CALI: True, BOGOTA: True, CERRADA: False},
        sucursal_nombre={CALI: "Cali", BOGOTA: "Bogotá", CERRADA: "Cerrada"},
        version_actual={D(2026, 10, 1): 2},
    )


def _fila(cedula="111", mes="2026-10", tienda="Cali", presupuesto="1500000"):
    return {"cedula": cedula, "mes": mes, "tienda": tienda, "presupuesto": presupuesto}


class TestParseMes:
    @pytest.mark.parametrize("valor, esperado", [
        ("2026-10", D(2026, 10, 1)),
        ("10/2026", D(2026, 10, 1)),
        ("1/2027", D(2027, 1, 1)),
        (" 2026-03 ", D(2026, 3, 1)),
        (datetime.datetime(2026, 10, 17), D(2026, 10, 1)),
        (D(2026, 10, 31), D(2026, 10, 1)),
        ("2026-10-01 00:00:00", D(2026, 10, 1)),
    ])
    def test_accepted_formats_normalize_to_first_of_month(self, valor, esperado):
        assert parse_mes(valor) == esperado

    @pytest.mark.parametrize("valor", ["", None, "octubre 2026", "2026-13", "13/2026", "10-2026", "abc", "2026"])
    def test_other_formats_are_rejected(self, valor):
        with pytest.raises(ValueError):
            parse_mes(valor)


class TestParseMonto:
    @pytest.mark.parametrize("valor, esperado", [
        ("1500000", 1500000),
        (1500000, 1500000),
        (1500000.0, 1500000),
        ("1500000.0", 1500000),
        ("1.500.000", 1500000),
        ("1,500,000", 1500000),
        (" 900 ", 900),
    ])
    def test_integer_pesos(self, valor, esperado):
        assert parse_monto(valor) == esperado

    def test_the_maximum_is_accepted_and_anything_above_is_rejected(self):
        assert parse_monto(10 ** 11) == 10 ** 11
        for valor in (10 ** 11 + 1, "100.000.000.001", 1e12):
            with pytest.raises(ValueError, match="no puede superar"):
                parse_monto(valor)

    @pytest.mark.parametrize("valor", ["", None, "0", 0, "-5", -5, "abc", "1500.5", 1500.5, "12 000 abc"])
    def test_rejects_non_positive_and_non_numeric(self, valor):
        with pytest.raises(ValueError):
            parse_monto(valor)


class TestValidarFilas:
    def test_valid_row_produces_a_line(self):
        resultado = validar_filas([_fila()], _catalogos())

        assert resultado.errores == [] and resultado.warnings == []
        [linea] = resultado.lineas
        assert (linea.fila, linea.mes, linea.cedula, linea.sucursal_id, linea.monto) == (
            1, D(2026, 10, 1), "111", CALI, 1500000)

    def test_cedula_is_cleaned(self):
        resultado = validar_filas([_fila(cedula="1.11"), _fila(cedula="222.0", mes="2026-11")], _catalogos())

        assert [linea.cedula for linea in resultado.lineas] == ["111", "222"]

    def test_unknown_cedula_is_a_row_error(self):
        resultado = validar_filas([_fila(cedula="999")], _catalogos())

        assert resultado.lineas == []
        assert resultado.errores == [
            {"fila": 1, "columna": "Cédula", "mensaje": "La cédula 999 no corresponde a ningún vendedor"}]

    def test_invalid_cedula_text_is_a_row_error(self):
        resultado = validar_filas([_fila(cedula="12ab")], _catalogos())

        assert resultado.errores[0]["columna"] == "Cédula"
        assert "solo números" in resultado.errores[0]["mensaje"]

    def test_inactive_only_vendedor_is_a_warning_and_still_loads(self):
        resultado = validar_filas([_fila(cedula="333")], _catalogos())

        assert len(resultado.lineas) == 1 and resultado.errores == []
        assert resultado.warnings == [
            {"fila": 1, "columna": "Cédula", "mensaje": "La cédula 333 corresponde a un vendedor inactivo"}]

    def test_tienda_by_alias_and_accent_insensitive(self):
        resultado = validar_filas(
            [_fila(tienda="sede  vieja"), _fila(cedula="222", tienda="MR bogotá")], _catalogos())

        assert [linea.sucursal_id for linea in resultado.lineas] == [CALI, BOGOTA]

    def test_unknown_tienda_is_a_row_error(self):
        resultado = validar_filas([_fila(tienda="Narnia")], _catalogos())

        assert resultado.errores == [
            {"fila": 1, "columna": "Tienda", "mensaje": "La tienda 'Narnia' no existe"}]

    def test_inactive_tienda_is_a_row_error(self):
        resultado = validar_filas([_fila(tienda="Cerrada")], _catalogos())

        assert resultado.errores == [
            {"fila": 1, "columna": "Tienda", "mensaje": "La tienda 'Cerrada' está inactiva"}]

    def test_bad_mes_and_bad_monto_are_row_errors_one_per_column(self):
        resultado = validar_filas([_fila(mes="octubre", presupuesto="0")], _catalogos())

        assert [(e["fila"], e["columna"]) for e in resultado.errores] == [(1, "Mes"), (1, "Presupuesto")]

    def test_same_cedula_twice_in_the_same_month_errors_both_rows(self):
        resultado = validar_filas(
            [_fila(), _fila(cedula="222"), _fila(tienda="Bogotá", mes="10/2026")], _catalogos())

        assert resultado.lineas[0].cedula == "222"
        assert [(e["fila"], e["columna"]) for e in resultado.errores] == [(1, "Cédula"), (3, "Cédula")]
        assert "repetida" in resultado.errores[0]["mensaje"]

    def test_same_cedula_in_different_months_is_fine(self):
        resultado = validar_filas([_fila(), _fila(mes="2026-11")], _catalogos())

        assert resultado.errores == [] and len(resultado.lineas) == 2


class TestResumir:
    def test_summary_per_month_with_store_totals_and_current_version(self):
        catalogos = _catalogos()
        resultado = validar_filas([
            _fila(cedula="111", tienda="Cali", presupuesto="1000000"),
            _fila(cedula="222", tienda="Cali", presupuesto="500000"),
            _fila(cedula="333", tienda="Bogotá", presupuesto="700000"),
            _fila(cedula="111", mes="2026-11", tienda="Bogotá", presupuesto="900000"),
        ], catalogos)

        resumen = resumir(resultado, catalogos)

        assert resumen["valido"] is True
        assert resumen["filas"] == 4
        octubre, noviembre = resumen["meses"]
        assert octubre == {
            "mes": "2026-10", "asesores": 3, "total": 2200000, "reemplaza_version": 2,
            "por_tienda": [
                {"sucursal_id": str(BOGOTA), "tienda": "Bogotá", "asesores": 1, "total": 700000},
                {"sucursal_id": str(CALI), "tienda": "Cali", "asesores": 2, "total": 1500000},
            ],
        }
        assert noviembre["mes"] == "2026-11" and noviembre["reemplaza_version"] is None
        assert resumen["errores"] == [] and len(resumen["warnings"]) == 1

    def test_any_error_makes_the_file_invalid(self):
        catalogos = _catalogos()

        resumen = resumir(validar_filas([_fila(), _fila(cedula="999")], catalogos), catalogos)

        assert resumen["valido"] is False and len(resumen["errores"]) == 1
        assert resumen["filas"] == 2


def _xlsx(filas, encabezados=("Cédula", "Mes", "Tienda", "Presupuesto")):
    libro = openpyxl.Workbook()
    libro.active.append(list(encabezados))
    for fila in filas:
        libro.active.append(fila)
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


class TestExcelParsing:
    def test_headers_are_case_and_accent_insensitive(self):
        contenido = _xlsx([[111, "2026-10", "Cali", 1500000]], encabezados=("CEDULA", "mes", "tienda", "presupuesto"))

        filas = parse_excel_rows("presupuesto", "p.xlsx", contenido)

        assert [f["cedula"] for f in filas] == ["111"]  # numeric cell arrives as text

    def test_excel_date_cell_and_numeric_amount_validate_end_to_end(self):
        contenido = _xlsx([[111.0, datetime.datetime(2026, 10, 1), "Cali", 1500000.0]])

        filas = parse_excel_rows("presupuesto", "p.xlsx", contenido)
        resultado = validar_filas(filas, _catalogos())

        assert resultado.errores == []
        assert (resultado.lineas[0].mes, resultado.lineas[0].monto) == (D(2026, 10, 1), 1500000)

    def test_missing_column_is_rejected(self):
        contenido = _xlsx([], encabezados=("Cédula", "Mes", "Tienda"))

        with pytest.raises(ColumnaObligatoriaFaltanteError):
            parse_excel_rows("presupuesto", "p.xlsx", contenido)


def _xlsx_bytes(encabezados, filas):
    libro = openpyxl.Workbook()
    libro.active.append(list(encabezados))
    for fila in filas:
        libro.active.append(list(fila))
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _validar_xlsx_bytes(encabezados, filas):
    contenido = _xlsx_bytes(encabezados, filas)
    canonicas = parse_excel_rows("presupuesto", "p.xlsx", contenido)
    return validar_filas(canonicas, _catalogos())


class TestAnioMesDosColumnas:
    @pytest.mark.parametrize("valor, esperado", [
        (2026, 2026), ("2026", 2026), ("2026.0", 2026), (2026.0, 2026),
    ])
    def test_year_accepts_numbers_and_numeric_text(self, valor, esperado):
        assert parse_anio(valor) == esperado

    @pytest.mark.parametrize("valor", [26, "26", "20266", "", None, "abc",
                                       2026.5, True])
    def test_year_needs_four_digits(self, valor):
        with pytest.raises(ValueError, match="4 dígitos"):
            parse_anio(valor)

    @pytest.mark.parametrize("valor, esperado", [
        (10, 10), ("10", 10), ("10.0", 10), (10.0, 10), ("07", 7), (" 1 ", 1),
    ])
    def test_month_number_accepts_excel_floats(self, valor, esperado):
        assert parse_mes_numero(valor) == esperado

    @pytest.mark.parametrize("valor", [0, 13, "0", "abc", "", None, 1.5])
    def test_month_number_out_of_range(self, valor):
        with pytest.raises(ValueError, match="de 1 a 12$"):
            parse_mes_numero(valor)

    @pytest.mark.parametrize("valor", [
        "2026-07", "07/2026", "2026-07-01 00:00:00",
        datetime.datetime(2026, 7, 1),
    ])
    def test_full_month_with_year_column_explains_both_layouts(self, valor):
        with pytest.raises(ValueError, match="quite la columna Año"):
            parse_mes_numero(valor)

    def test_row_with_anio_key_uses_two_columns(self):
        assert mes_de_fila({"anio": "2026.0", "mes": "10.0"}) == D(2026, 10, 1)

    def test_row_without_anio_key_keeps_legacy_parsing(self):
        assert mes_de_fila({"mes": "2026-07"}) == D(2026, 7, 1)

    def test_errors_name_the_offending_column(self):
        filas = [_fila(mes="13"), _fila(mes="2026-07")]
        for fila in filas:
            fila["anio"] = "2026"
        filas[1]["cedula"] = "222"
        filas.append({**_fila(cedula="333"), "anio": "26"})
        resultado = validar_filas(filas, _catalogos())

        assert [(e["fila"], e["columna"]) for e in resultado.errores] == [
            (1, "Mes"), (2, "Mes"), (3, "Año")]
        assert resultado.errores[0]["mensaje"] == (
            "El mes debe ser un número de 1 a 12")
        assert resultado.errores[2]["mensaje"] == (
            "El año debe tener 4 dígitos (ej. 2026)")

    def test_blank_year_cell_is_an_error_when_the_column_exists(self):
        resultado = validar_filas([{**_fila(mes="10"), "anio": ""}],
                                  _catalogos())

        assert resultado.errores[0]["columna"] == "Año"


class TestArchivoExcelDosLayouts:
    def test_new_layout_from_xlsx_with_excel_floats(self):
        resultado = _validar_xlsx_bytes(
            ("Año", "Mes", "Cédula", "Tienda", "Presupuesto"),
            [(2026.0, 10.0, "111", "Cali", 1500000),
             ("2026", "10.0", "222", "Bogotá", 1200000)])

        assert resultado.errores == []
        assert {x.mes for x in resultado.lineas} == {D(2026, 10, 1)}

    @pytest.mark.parametrize("encabezado", ["Ano", "AÑO", "año", "Year"])
    def test_year_header_aliases(self, encabezado):
        resultado = _validar_xlsx_bytes(
            (encabezado, "Mes", "Cédula", "Tienda", "Presupuesto"),
            [(2026, 10, "111", "Cali", 1500000)])

        assert resultado.errores == []

    def test_legacy_file_with_month_as_text_still_loads(self):
        resultado = _validar_xlsx_bytes(
            ("Cédula", "Mes", "Tienda", "Presupuesto"),
            [("111", "2026-07", "Cali", 1500000)])

        assert resultado.errores == []
        assert resultado.lineas[0].mes == D(2026, 7, 1)

    def test_legacy_file_with_date_cell_and_latin_text(self):
        resultado = _validar_xlsx_bytes(
            ("Cédula", "Mes", "Tienda", "Presupuesto"),
            [("111", datetime.datetime(2026, 7, 15), "Cali", 1),
             ("222", "07/2026", "Cali", 2)])

        assert resultado.errores == []
        assert {x.mes for x in resultado.lineas} == {D(2026, 7, 1)}

    def test_mixed_layout_reports_a_clear_row_error(self):
        resultado = _validar_xlsx_bytes(
            ("Año", "Mes", "Cédula", "Tienda", "Presupuesto"),
            [(2026, "2026-07", "111", "Cali", 1500000)])

        assert resultado.lineas == []
        assert resultado.errores[0]["columna"] == "Mes"
        assert "quite la columna Año" in resultado.errores[0]["mensaje"]
