"""
Phase 3 "Models/Schemas/Services" — task 3.4 (sdd/motored-pedidos-cimientos).

`services/carga.py`: validate-then-commit bulk upload. Validates the ENTIRE
file first; if even one row is invalid, writes NOTHING and returns every
offending row's error in one response (owner decision #1 / spec "Bulk Excel
upload is all-or-nothing"). A fully valid file commits all rows in a single
transaction, upserting by natural key (owner decision #2).
"""
import uuid

from app.motored.models.sucursal import Sucursal
from app.motored.services import carga
from tests.motored.conftest import FakeAsyncSession


class TestAllOrNothing:
    async def test_one_invalid_row_writes_nothing_and_reports_it(self):
        db = FakeAsyncSession(execute_queue=[[], []])  # 2 valid-lookup queries never consumed if short-circuited
        rows = [
            {"nombre": "CALI NORTE", "sic": "S1"},
            {"nombre": "", "sic": "S2"},
        ]

        resultado = await carga.procesar_carga(db, "sucursal", rows)

        assert resultado.ok is False
        assert len(resultado.errores) == 1
        assert resultado.errores[0].fila == 2
        assert db.added == []
        assert db.committed is False

    async def test_multiple_invalid_rows_all_reported_in_one_response(self):
        db = FakeAsyncSession()
        rows = [
            {"nombre": "", "sic": "S1"},
            {"nombre": None, "sic": "S3"},
        ]

        resultado = await carga.procesar_carga(db, "sucursal", rows)

        assert resultado.ok is False
        assert {e.fila for e in resultado.errores} == {1, 2}
        assert db.added == []

    async def test_fully_valid_file_commits_all_rows_in_one_transaction(self):
        db = FakeAsyncSession(execute_queue=[[], []])  # no existing sucursal for either row
        rows = [
            {"nombre": "CALI NORTE", "codigo_co": "E01", "sic": "S1"},
            {"nombre": "BOGOTA", "codigo_co": "C01", "sic": "S2"},
        ]

        resultado = await carga.procesar_carga(db, "sucursal", rows)

        assert resultado.ok is True
        assert resultado.insertados == 2
        assert len(db.added_of_type(Sucursal)) == 2
        assert db.committed is True


class TestUpsertByNaturalKey:
    async def test_reuploading_matching_row_updates_instead_of_duplicating(self):
        existing = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE", sic=None, activa=True)
        db = FakeAsyncSession(execute_queue=[[existing]])
        rows = [{"nombre": "CALI NORTE", "sic": "S1"}]

        resultado = await carga.procesar_carga(db, "sucursal", rows)

        assert resultado.ok is True
        assert resultado.actualizados == 1
        assert resultado.insertados == 0
        assert existing.sic == "S1"
        assert db.added_of_type(Sucursal) == []


class TestReferenciaCargaCoercesUnidadEmpaque:
    async def test_zero_unidad_empaque_row_is_coerced_and_surfaced_as_warning(self):
        db = FakeAsyncSession(execute_queue=[[], []])  # replace plan: all referencias, all proveedores
        rows = [{"codigo": "REF1", "proveedor_codigo": "HMCL", "proveedor_id": str(uuid.uuid4()), "unidad_empaque": 0}]

        resultado = await carga.procesar_carga(db, "referencia", rows, confirmar_reemplazo=True)

        assert resultado.ok is True
        assert resultado.advertencias, "expected at least one warning for the coerced row"


class TestErroresPreviosBlockEntireWriteAllOrNothing:
    """Ad-hoc bugfix (not tracked under sdd/*): `errores_previos` lets a
    caller (the router's `_resolve_referencia_relaciones`) inject a
    pre-computed resolution error -- it must block the WHOLE write exactly
    like a `validate_rows` error already does, same all-or-nothing
    guarantee (owner decision #1), merged into ONE response."""

    async def test_a_resolution_error_alone_blocks_the_whole_write(self):
        # Zero queries expected -- the merged error list must short-circuit
        # BEFORE any upsert lookup, even though the row itself is otherwise
        # fully valid.
        db = FakeAsyncSession()
        rows = [{"nombre": "CALI NORTE", "sic": "S1"}]
        errores_previos = [{
            "fila": 1,
            "motivo": "El código de 'sustituida_por' 'GHOST' no corresponde a ninguna referencia existente",
        }]

        resultado = await carga.procesar_carga(db, "sucursal", rows, errores_previos=errores_previos)

        assert resultado.ok is False
        assert len(resultado.errores) == 1
        assert resultado.errores[0].motivo == errores_previos[0]["motivo"]
        assert db.added == []
        assert db.committed is False

    async def test_errores_previos_merge_with_validation_errors_in_one_response(self):
        db = FakeAsyncSession()
        rows = [
            {"nombre": "CALI NORTE", "sic": "S1"},  # otherwise valid, blocked only by errores_previos
            {"nombre": ""},  # genuinely invalid on its own
        ]
        errores_previos = [{"fila": 1, "motivo": "resolution error"}]

        resultado = await carga.procesar_carga(db, "sucursal", rows, errores_previos=errores_previos)

        assert resultado.ok is False
        filas_con_error = {e.fila for e in resultado.errores}
        assert filas_con_error == {1, 2}
        assert db.added == []
        assert db.committed is False

    async def test_no_errores_previos_behaves_exactly_as_before(self):
        db = FakeAsyncSession(execute_queue=[[]])
        rows = [{"nombre": "CALI NORTE", "codigo_co": "E01"}]

        resultado = await carga.procesar_carga(db, "sucursal", rows)

        assert resultado.ok is True
        assert db.committed is True
