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
    parse_mes,
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
