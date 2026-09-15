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
            {"nombre": "CALI NORTE", "sic": "S1"},
            {"nombre": "BOGOTA", "sic": "S2"},
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
        db = FakeAsyncSession(execute_queue=[[]])
        rows = [{"codigo": "REF1", "proveedor_codigo": "HMCL", "proveedor_id": str(uuid.uuid4()), "unidad_empaque": 0}]

        resultado = await carga.procesar_carga(db, "referencia", rows)

        assert resultado.ok is True
        assert resultado.advertencias, "expected at least one warning for the coerced row"
