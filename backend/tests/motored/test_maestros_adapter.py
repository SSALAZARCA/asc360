"""
Motored Pedidos — Fase 2 "Ingesta", Phase 9 "Adapter + API" (PR9), task 9.1
(sdd/motored-pedidos-ingesta; design ADR-5, spec "Bulk Excel upload is
all-or-nothing" / "carga_error model and CSV export").

`services/ingesta/maestros_adapter.py` routes `MAESTRO_*` carga types to
Fase 1's UNMODIFIED masters validator (`carga_excel.parse_excel_rows` +
`carga.procesar_carga`/`validators.validate_rows`) and mirrors any
resulting `CargaResultado.errores` into `carga_error`, so the shared
errors grid/`errores.csv` are uniform across both execution policies
(ADR-5: "reporting is shared, execution semantics are not").
"""
import io
import uuid

import openpyxl
import pytest

from app.motored.models.bodega import Bodega
from app.motored.models.carga_error import CargaError
from app.motored.services.carga_excel import ColumnaObligatoriaFaltanteError
from app.motored.services.ingesta import maestros_adapter
from tests.motored.conftest import FakeAsyncSession


def _build_xlsx_bytes(headers, rows):
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class TestResolverEntidad:
    def test_maestro_referencias_maps_to_referencia(self):
        assert maestros_adapter.resolver_entidad("MAESTRO_REFERENCIAS") == "referencia"

    def test_maestro_bodegas_maps_to_bodega(self):
        assert maestros_adapter.resolver_entidad("MAESTRO_BODEGAS") == "bodega"

    def test_unsupported_tipo_raises(self):
        """`VENTAS` (movimiento) y `MAESTRO_SUCURSALES`/`MAESTRO_PROVEEDORES`
        (siguen en la carga masiva propia de Fase 1, spec "Sucursal/proveedor
        uploads are absent from this history") no son parte de la historia
        compartida ADR-5 enruta acá."""
        with pytest.raises(maestros_adapter.TipoMaestroNoSoportadoError):
            maestros_adapter.resolver_entidad("VENTAS")

        with pytest.raises(maestros_adapter.TipoMaestroNoSoportadoError):
            maestros_adapter.resolver_entidad("MAESTRO_SUCURSALES")


class TestProcesarMaestroValido:
    async def test_valid_file_is_routed_to_fase1_validator_and_commits(self):
        carga_id = uuid.uuid4()
        file_bytes = _build_xlsx_bytes(["Código", "Descripción"], [["BA061", "Bodega principal"]])
        db = FakeAsyncSession(execute_queue=[[]])  # no existing bodega for that codigo

        resultado = await maestros_adapter.procesar_maestro(
            db, carga_id, "MAESTRO_BODEGAS", "bodegas.xlsx", file_bytes
        )

        assert resultado.ok is True
        assert resultado.insertados == 1
        assert len(db.added_of_type(Bodega)) == 1
        assert db.committed is True
        assert db.added_of_type(CargaError) == []


class TestProcesarMaestroInvalido:
    async def test_invalid_row_mirrors_errors_into_carga_error_and_commits(self):
        carga_id = uuid.uuid4()
        file_bytes = _build_xlsx_bytes(
            ["Código", "Descripción"],
            [["BA061", "Bodega principal"], ["", "Sin código"]],
        )
        db = FakeAsyncSession()

        resultado = await maestros_adapter.procesar_maestro(
            db, carga_id, "MAESTRO_BODEGAS", "bodegas.xlsx", file_bytes
        )

        assert resultado.ok is False
        assert db.added_of_type(Bodega) == []  # todo-o-nada: Fase 1 no escribió nada

        errores_persistidos = db.added_of_type(CargaError)
        assert len(errores_persistidos) == 1
        error = errores_persistidos[0]
        assert error.carga_id == carga_id
        assert error.fila == 2
        assert error.codigo_error == maestros_adapter.CODIGO_ERROR_VALIDACION_MAESTRO
        assert "codigo" in error.mensaje
        assert db.committed is True

    async def test_no_carga_error_rows_when_file_is_fully_valid(self):
        """El commit de errores es simétrico: sólo ocurre cuando
        `CargaResultado.ok` es `False` -- un archivo totalmente válido no
        agrega ninguna fila a `carga_error`."""
        carga_id = uuid.uuid4()
        file_bytes = _build_xlsx_bytes(["Código"], [["BA061"]])
        db = FakeAsyncSession(execute_queue=[[]])

        await maestros_adapter.procesar_maestro(
            db, carga_id, "MAESTRO_BODEGAS", "bodegas.xlsx", file_bytes
        )

        assert db.added_of_type(CargaError) == []


class TestPropagacionDeErroresDeParseo:
    async def test_missing_mandatory_column_propagates_untouched(self):
        """Un archivo sin la columna obligatoria (`Código`) es un error de
        PARSEO (Fase 1, `parse_excel_rows`), no de validación por-fila --
        este adaptador no lo intercepta ni lo traduce a `carga_error`, lo
        deja propagar intacto (mismo contrato que Fase 1 ya tenía)."""
        carga_id = uuid.uuid4()
        file_bytes = _build_xlsx_bytes(["Descripción"], [["Bodega principal"]])
        db = FakeAsyncSession()

        with pytest.raises(ColumnaObligatoriaFaltanteError):
            await maestros_adapter.procesar_maestro(
                db, carga_id, "MAESTRO_BODEGAS", "bodegas.xlsx", file_bytes
            )

        assert db.added == []
        assert db.committed is False
