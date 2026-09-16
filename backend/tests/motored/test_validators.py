"""
Phase 3 "Models/Schemas/Services" — task 3.2 (RED) / 3.3-3.4 (GREEN)
(sdd/motored-pedidos-cimientos).

Pure, DB-free validation rules locked by the proposal/spec:
- `referencia.unidad_empaque` 0/null -> coerced to 1 + a warning identifying
  the row (never stored as 0).
- `sucursal.nombre` is trimmed before storage/comparison.
- A bulk-row validator accumulates ALL row errors in a single pass -- it
  never fail-fasts on the first bad row.
"""
import uuid

from app.motored.services.validators import (
    coerce_unidad_empaque,
    normalize_sucursal_nombre,
    validate_rows,
)


class TestCoerceUnidadEmpaque:
    def test_zero_is_coerced_to_one_with_warning(self):
        value, warning = coerce_unidad_empaque(0)
        assert value == 1
        assert warning is not None

    def test_none_is_coerced_to_one_with_warning(self):
        value, warning = coerce_unidad_empaque(None)
        assert value == 1
        assert warning is not None

    def test_valid_positive_value_is_unchanged_with_no_warning(self):
        value, warning = coerce_unidad_empaque(12)
        assert value == 12
        assert warning is None

    def test_negative_value_is_coerced_to_one_with_warning(self):
        value, warning = coerce_unidad_empaque(-3)
        assert value == 1
        assert warning is not None


class TestNormalizeSucursalNombre:
    def test_trailing_and_leading_whitespace_is_trimmed(self):
        assert normalize_sucursal_nombre("CALI NORTE   ") == "CALI NORTE"
        assert normalize_sucursal_nombre("   CALI NORTE") == "CALI NORTE"

    def test_already_clean_name_is_unchanged(self):
        assert normalize_sucursal_nombre("CALI NORTE") == "CALI NORTE"


class TestValidateRowsAccumulatesAllErrors:
    def test_one_invalid_row_out_of_many_is_reported_alone(self):
        rows = [
            {"nombre": "CALI NORTE", "sic": "S1"},
            {"nombre": "", "sic": "S2"},
            {"nombre": "BOGOTA", "sic": "S3"},
        ]
        valid, errors = validate_rows("sucursal", rows)
        assert len(errors) == 1
        assert errors[0]["fila"] == 2  # 1-indexed, second row
        assert len(valid) == 2

    def test_multiple_invalid_rows_are_all_reported_in_one_pass(self):
        rows = [
            {"nombre": "", "sic": "S1"},
            {"nombre": "BOGOTA", "sic": None},
            {"nombre": None, "sic": "S3"},
        ]
        valid, errors = validate_rows("sucursal", rows)
        # Missing `nombre` on rows 1 and 3 are both reported -- not just the
        # first one found. `sic` missing alone is not a hard validation
        # error at ingest (it is a health-board WARNING, not a blocking
        # ingest failure), so only rows 1 and 3 fail here.
        filas_con_error = {e["fila"] for e in errors}
        assert filas_con_error == {1, 3}
        assert len(valid) == 1

    def test_fully_valid_file_has_zero_errors(self):
        rows = [
            {"nombre": "CALI NORTE", "sic": "S1"},
            {"nombre": "BOGOTA", "sic": "S2"},
        ]
        valid, errors = validate_rows("sucursal", rows)
        assert errors == []
        assert len(valid) == 2

    def test_referencia_rows_validate_required_fields(self):
        # `proveedor_id` is required for schema construction (this function's
        # documented contract: by the time a row reaches `validate_rows`, the
        # router has already resolved proveedor_codigo -> proveedor_id) --
        # every row here supplies a real one so this test stays focused on
        # the required-field check it's named for, not proveedor_id's shape.
        proveedor_id = str(uuid.uuid4())
        rows = [
            {"codigo": "REF1", "proveedor_codigo": "HMCL", "proveedor_id": proveedor_id, "unidad_empaque": 10},
            {"codigo": "", "proveedor_codigo": "HMCL", "proveedor_id": proveedor_id, "unidad_empaque": 5},
            {"codigo": "REF3", "proveedor_codigo": "", "proveedor_id": proveedor_id, "unidad_empaque": 5},
        ]
        valid, errors = validate_rows("referencia", rows)
        filas_con_error = {e["fila"] for e in errors}
        assert filas_con_error == {2, 3}
        assert len(valid) == 1

    def test_referencia_row_with_null_unidad_empaque_is_valid_but_flagged(self):
        # A missing unidad_empaque is NOT a validation error -- it gets
        # coerced to 1 with a warning downstream, it never rejects the row.
        rows = [{
            "codigo": "REF1", "proveedor_codigo": "HMCL",
            "proveedor_id": str(uuid.uuid4()), "unidad_empaque": 0,
        }]
        valid, errors = validate_rows("referencia", rows)
        assert errors == []
        assert len(valid) == 1
        assert valid[0]["unidad_empaque"] == 1
        assert valid[0]["_warnings"]

    def test_bulk_upload_schema_construction_accepts_the_new_spec_fields(self):
        """Post-archive correction: `_SCHEMA_BY_ENTIDAD` just instantiates the
        real Pydantic `*Create` schema per entity, so the new spec fields
        (sucursal's 6, referencia's `linea_comercial`/renamed `nombre`,
        proveedor's `dias_seguridad_default`, bodega's `descripcion`) must be
        accepted with zero changes to `validate_rows` itself -- this is the
        explicit verification the task called for ("verify with a test,
        don't just assume")."""
        sucursal_rows = [{
            "nombre": "CALI NORTE", "sic": "S1",
            "dias_empaque": 3, "dias_transito": 5, "bodega_principal": "BE051",
            "departamento": "Valle del Cauca", "ciudad": "Cali", "fecha_apertura": "2020-01-15",
        }]
        valid, errors = validate_rows("sucursal", sucursal_rows)
        assert errors == []
        assert len(valid) == 1

        proveedor_rows = [{"codigo": "HMCL", "nombre": "HMCL Colombia", "dias_seguridad_default": 3.0}]
        valid, errors = validate_rows("proveedor", proveedor_rows)
        assert errors == []
        assert len(valid) == 1

        bodega_rows = [{"codigo": "BA061", "descripcion": "Bodega central"}]
        valid, errors = validate_rows("bodega", bodega_rows)
        assert errors == []
        assert len(valid) == 1

        referencia_rows = [{
            "codigo": "REF1", "proveedor_codigo": "HMCL", "proveedor_id": str(uuid.uuid4()),
            "nombre": "FILTRO DE ACEITE", "linea_comercial": "REPUESTOS", "unidad_empaque": 10,
        }]
        valid, errors = validate_rows("referencia", referencia_rows)
        assert errors == []
        assert len(valid) == 1
        assert valid[0]["nombre"] == "FILTRO DE ACEITE"
        assert valid[0]["linea_comercial"] == "REPUESTOS"

    def test_referencia_row_with_malformed_proveedor_id_is_a_validation_error(self):
        # A field that's present (passes the blank-check) but the wrong
        # shape (not a real UUID) must be caught HERE, during validation --
        # not discovered later inside the write loop, after "safe to write"
        # has already been decided (that would break todo-o-nada: some rows
        # could already be added to the session before the crash).
        rows = [{
            "codigo": "REF1", "proveedor_codigo": "HMCL",
            "proveedor_id": "not-a-real-uuid", "unidad_empaque": 10,
        }]
        valid, errors = validate_rows("referencia", rows)
        assert valid == []
        assert len(errors) == 1
        assert errors[0]["fila"] == 1
