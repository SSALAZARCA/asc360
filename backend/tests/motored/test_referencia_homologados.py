"""
Referencia 9-column layout (owner request 2026-09-28): new multi-value
`homologados` field ("Homologados otras marcas").

Covers the whole vertical slice below the HTTP layer -- shared text helper,
Pydantic schemas (Create/Update/Read), model column, service create/update,
bulk validation, and the Alembic migration (loaded by file path and run
against a mocked `op`, same approach as
`test_migration_ventas_perdidas_panel_audit.py`).
"""
import importlib.util
import uuid
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.dialects.postgresql import ARRAY

from app.motored.models.referencia import Referencia
from app.motored.schemas.referencia import ReferenciaCreate, ReferenciaRead, ReferenciaUpdate
from app.motored.services import maestros
from app.motored.services.texto import split_multivalor
from app.motored.services.validators import validate_rows
from tests.motored.conftest import FakeAsyncSession


class TestSplitMultivalor:
    def test_splits_on_comma_and_semicolon_trims_drops_empties_dedupes_in_order(self):
        assert split_multivalor(" A , B;;A ; ;C,") == ["A", "B", "C"]

    def test_none_and_blank_become_empty_list(self):
        assert split_multivalor(None) == []
        assert split_multivalor("   ") == []

    def test_list_input_is_normalized_the_same_way(self):
        assert split_multivalor([" A", "", "B", "A", None]) == ["A", "B"]

    def test_list_items_containing_separators_are_split_too(self):
        assert split_multivalor(["A;B", "C"]) == ["A", "B", "C"]

    def test_non_string_scalar_is_coerced_to_text(self):
        assert split_multivalor(12345) == ["12345"]


class TestSchemas:
    def test_create_accepts_a_separated_string(self):
        data = ReferenciaCreate(codigo="R1", proveedor_id=uuid.uuid4(), homologados="A; B, A")
        assert data.homologados == ["A", "B"]

    def test_create_defaults_to_empty_list_and_is_not_marked_as_set(self):
        data = ReferenciaCreate(codigo="R1", proveedor_id=uuid.uuid4())
        assert data.homologados == []
        assert "homologados" not in data.model_dump(exclude_unset=True)

    def test_update_explicit_none_clears_to_empty_list(self):
        data = ReferenciaUpdate(homologados=None)
        assert data.model_dump(exclude_unset=True) == {"homologados": []}

    def test_create_no_longer_requires_precio_venta_but_still_accepts_it(self):
        data = ReferenciaCreate(codigo="R1", proveedor_id=uuid.uuid4(), precio_venta=10)
        assert data.precio_venta == 10

    def test_item_longer_than_the_column_limit_is_rejected_at_validation_time(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ReferenciaCreate(codigo="R1", proveedor_id=uuid.uuid4(), homologados="X" * 101)

    def test_list_longer_than_the_max_items_is_rejected_with_a_clear_error(self):
        import pytest
        from pydantic import ValidationError

        from app.motored.schemas.referencia import HOMOLOGADOS_MAX_ITEMS

        assert HOMOLOGADOS_MAX_ITEMS == 50
        ReferenciaCreate(codigo="R1", proveedor_id=uuid.uuid4(), homologados=[f"H{i}" for i in range(50)])
        with pytest.raises(ValidationError) as exc_info:
            ReferenciaCreate(codigo="R1", proveedor_id=uuid.uuid4(), homologados=[f"H{i}" for i in range(51)])
        assert "50" in str(exc_info.value)

    def test_read_tolerates_null_homologados_from_legacy_rows(self):
        row = Referencia(
            id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(), unidad_empaque=1,
            unidad_empaque_advertencia=False, activa=True, homologados=None,
        )
        assert ReferenciaRead.model_validate(row).homologados == []


class TestModel:
    def test_homologados_is_a_non_nullable_postgres_array_of_strings_defaulting_to_empty(self):
        column = Referencia.__table__.c.homologados
        assert isinstance(column.type, ARRAY)
        assert column.nullable is False
        assert column.server_default is not None

    def test_precio_venta_column_is_kept(self):
        assert "precio_venta" in Referencia.__table__.c


class TestService:
    async def test_create_referencia_persists_homologados(self):
        db = FakeAsyncSession()
        data = ReferenciaCreate(codigo="R1", proveedor_id=uuid.uuid4(), homologados=["A", "B"])

        referencia, _ = await maestros.create_referencia(db, data)

        assert referencia.homologados == ["A", "B"]

    async def test_update_referencia_replaces_homologados(self):
        row = Referencia(id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(), unidad_empaque=1, homologados=["A"])
        db = FakeAsyncSession()

        await maestros.update_referencia(db, row, ReferenciaUpdate(homologados="X; Y"))

        assert row.homologados == ["X", "Y"]

    async def test_upsert_without_homologados_column_keeps_existing_value(self):
        existing = Referencia(
            id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(), unidad_empaque=1, homologados=["KEEP"],
        )
        db = FakeAsyncSession(execute_queue=[[existing]])
        data = ReferenciaCreate(codigo="R1", proveedor_id=existing.proveedor_id, nombre="Nuevo")

        await maestros.upsert_referencia(db, data)

        assert existing.homologados == ["KEEP"]


class TestBulkValidation:
    def test_csv_style_string_is_accepted_by_validate_rows(self):
        valid, errors = validate_rows(
            "referencia",
            [{"codigo": "R1", "proveedor_codigo": "HMCL", "proveedor_id": str(uuid.uuid4()), "homologados": "A;B"}],
        )
        assert errors == []
        assert valid[0]["homologados"] == "A;B"  # raw row; the schema normalizes it on write

    def test_blank_homologados_is_treated_as_not_provided(self):
        valid, errors = validate_rows(
            "referencia",
            [{"codigo": "R1", "proveedor_codigo": "HMCL", "proveedor_id": str(uuid.uuid4()), "homologados": ""}],
        )
        assert errors == []
        assert "homologados" not in valid[0]


_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"


def _load_migration():
    matches = list(_VERSIONS_DIR.glob("*_referencia_homologados.py"))
    assert len(matches) == 1, matches
    spec = importlib.util.spec_from_file_location("referencia_homologados_migration", matches[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigration:
    def test_chains_onto_ventas_perdidas_panel_audit_head(self):
        migration = _load_migration()
        assert migration.down_revision == "43191272c816"

    def test_upgrade_adds_non_nullable_array_column_with_empty_default(self):
        migration = _load_migration()
        with patch.object(migration, "op") as op_mock:
            migration.upgrade()

        (table, column), _ = op_mock.add_column.call_args
        assert table == "referencia"
        assert column.name == "homologados"
        assert isinstance(column.type, ARRAY)
        assert column.nullable is False
        assert column.server_default is not None

    def test_upgrade_never_drops_precio_venta(self):
        migration = _load_migration()
        with patch.object(migration, "op") as op_mock:
            migration.upgrade()
        op_mock.drop_column.assert_not_called()

    def test_upgrade_sets_a_local_lock_timeout_before_the_alter(self):
        migration = _load_migration()
        with patch.object(migration, "op") as op_mock:
            migration.upgrade()

        names = [c[0] for c in op_mock.method_calls]
        assert names.index("execute") < names.index("add_column")
        (sql,), _ = op_mock.execute.call_args
        assert "SET LOCAL lock_timeout" in str(sql)

    def test_downgrade_drops_only_homologados(self):
        migration = _load_migration()
        with patch.object(migration, "op") as op_mock:
            migration.downgrade()
        op_mock.drop_column.assert_called_once_with("referencia", "homologados")


class TestSustitutaSameProveedorOnSingleRecordWrites:
    """Business rule (user decision 2026-09-28): the substitute MUST belong to
    the same proveedor. Enforced server-side for the single-record form/API,
    not only in the bulk resolver."""

    async def test_create_with_a_same_proveedor_substitute_is_accepted(self):
        proveedor_id = uuid.uuid4()
        sustituta = Referencia(id=uuid.uuid4(), codigo="OLD", proveedor_id=proveedor_id, unidad_empaque=1)
        db = FakeAsyncSession(execute_queue=[[sustituta]])
        data = ReferenciaCreate(codigo="NEW", proveedor_id=proveedor_id, sustituida_por=sustituta.id)

        referencia, _ = await maestros.create_referencia(db, data)

        assert referencia.sustituida_por == sustituta.id

    async def test_create_with_a_substitute_from_another_proveedor_is_rejected(self):
        import pytest

        sustituta = Referencia(id=uuid.uuid4(), codigo="OLD", proveedor_id=uuid.uuid4(), unidad_empaque=1)
        db = FakeAsyncSession(execute_queue=[[sustituta]])
        data = ReferenciaCreate(codigo="NEW", proveedor_id=uuid.uuid4(), sustituida_por=sustituta.id)

        with pytest.raises(maestros.SustitutaInvalidaError) as exc_info:
            await maestros.create_referencia(db, data)
        assert "Código de referencia sustituta" in str(exc_info.value)
        assert "La referencia sustituta debe ser del mismo proveedor." in str(exc_info.value)
        assert "Homologados" not in str(exc_info.value)
        assert db.added == []

    async def test_create_with_an_unknown_substitute_is_rejected(self):
        import pytest

        db = FakeAsyncSession(execute_queue=[[]])
        data = ReferenciaCreate(codigo="NEW", proveedor_id=uuid.uuid4(), sustituida_por=uuid.uuid4())

        with pytest.raises(maestros.SustitutaInvalidaError):
            await maestros.create_referencia(db, data)

    async def test_update_with_a_substitute_from_another_proveedor_is_rejected_and_row_untouched(self):
        import pytest

        row = Referencia(id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(), unidad_empaque=1, activa=True)
        sustituta = Referencia(id=uuid.uuid4(), codigo="OLD", proveedor_id=uuid.uuid4(), unidad_empaque=1)
        db = FakeAsyncSession(execute_queue=[[sustituta]])

        with pytest.raises(maestros.SustitutaInvalidaError):
            await maestros.update_referencia(db, row, ReferenciaUpdate(sustituida_por=sustituta.id))
        assert row.sustituida_por is None
        assert row.activa is True

    async def test_update_cannot_substitute_a_referencia_by_itself(self):
        import pytest

        row = Referencia(id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(), unidad_empaque=1, activa=True)
        db = FakeAsyncSession(execute_queue=[[row]])

        with pytest.raises(maestros.SustitutaInvalidaError):
            await maestros.update_referencia(db, row, ReferenciaUpdate(sustituida_por=row.id))

    def test_api_returns_422_for_a_substitute_from_another_proveedor(self, monkeypatch):
        from fastapi.testclient import TestClient

        from app.config import settings
        from app.main import app
        from app.motored.services.auth import MotoredUser
        from tests.motored.conftest import override_motored_db, override_motored_user

        monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
        monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "homologados-test-motored-secret")
        monkeypatch.setattr(settings, "SECRET_KEY", "homologados-test-asc360-secret")
        override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
        sustituta = Referencia(id=uuid.uuid4(), codigo="OLD", proveedor_id=uuid.uuid4(), unidad_empaque=1)
        session = FakeAsyncSession(execute_queue=[[], [sustituta]])  # readiness probe, sustituta lookup
        override_motored_db(session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/motored/maestros/referencias",
                    json={"codigo": "NEW", "proveedor_id": str(uuid.uuid4()), "sustituida_por": str(sustituta.id)},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422, response.text
        assert "Código de referencia sustituta" in response.json()["detail"]
        assert session.committed is False
