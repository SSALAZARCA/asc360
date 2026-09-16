"""
Phase 3 "Models/Schemas/Services" — task 3.3 (sdd/motored-pedidos-cimientos).

`services/maestros.py`: CRUD + soft-delete ONLY (never a real SQL DELETE)
for every master, plus natural-key upsert (`referencia` by
(codigo, proveedor_id), `sucursal` by nombre trimmed, `bodega` by codigo,
`proveedor` by codigo).
"""
import uuid

import pytest

from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.bodega import Bodega
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.bodega import BodegaCreate
from app.motored.schemas.proveedor import ProveedorCreate
from app.motored.schemas.referencia import ReferenciaCreate, ReferenciaUpdate
from app.motored.schemas.sucursal import SucursalCreate
from app.motored.services import maestros
from tests.motored.conftest import FakeAsyncSession


class TestProveedorUpsertByCodigo:
    async def test_upsert_creates_when_no_existing_row(self):
        db = FakeAsyncSession(execute_queue=[[]])  # get_by_codigo -> none found
        data = ProveedorCreate(codigo="HMCL", nombre="HMCL Colombia")

        proveedor, _, created = await maestros.upsert_proveedor(db, data)

        assert proveedor.codigo == "HMCL"
        assert proveedor in db.added
        assert created is True

    async def test_upsert_updates_existing_row_matched_by_codigo(self):
        existing = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="Old Name", activa=True)
        db = FakeAsyncSession(execute_queue=[[existing]])
        data = ProveedorCreate(codigo="HMCL", nombre="New Name")

        proveedor, _, created = await maestros.upsert_proveedor(db, data)

        assert proveedor is existing
        assert proveedor.nombre == "New Name"
        assert proveedor not in db.added  # updated in place, not re-inserted
        assert created is False


class TestSucursalUpsertByNombreTrimmed:
    async def test_create_trims_nombre_before_storing(self):
        db = FakeAsyncSession(execute_queue=[[]])
        data = SucursalCreate(nombre="CALI NORTE   ")

        sucursal, _, created = await maestros.upsert_sucursal(db, data)

        assert sucursal.nombre == "CALI NORTE"
        assert created is True

    async def test_upsert_matches_existing_row_ignoring_trailing_whitespace(self):
        existing = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE", sic=None, activa=True)
        db = FakeAsyncSession(execute_queue=[[existing]])
        data = SucursalCreate(nombre="CALI NORTE   ", sic="S1")

        sucursal, _, created = await maestros.upsert_sucursal(db, data)

        assert sucursal is existing
        assert sucursal.sic == "S1"
        assert created is False


class TestBodegaUpsertByCodigo:
    async def test_upsert_creates_when_missing(self):
        db = FakeAsyncSession(execute_queue=[[]])
        data = BodegaCreate(codigo="BA061")

        bodega, _, created = await maestros.upsert_bodega(db, data)

        assert bodega.codigo == "BA061"
        assert bodega in db.added
        assert created is True


class TestReferenciaCreateCoercesUnidadEmpaque:
    async def test_create_with_zero_unidad_empaque_is_coerced_and_flagged(self):
        db = FakeAsyncSession()
        proveedor_id = uuid.uuid4()
        data = ReferenciaCreate(codigo="REF1", proveedor_id=proveedor_id, unidad_empaque=0)

        referencia, warning = await maestros.create_referencia(db, data)

        assert referencia.unidad_empaque == 1
        assert referencia.unidad_empaque_advertencia is True
        assert warning is not None

    async def test_create_with_valid_unidad_empaque_has_no_warning(self):
        db = FakeAsyncSession()
        data = ReferenciaCreate(codigo="REF1", proveedor_id=uuid.uuid4(), unidad_empaque=24)

        referencia, warning = await maestros.create_referencia(db, data)

        assert referencia.unidad_empaque == 24
        assert referencia.unidad_empaque_advertencia is False
        assert warning is None


class TestReferenciaUpsertByCodigoProveedor:
    async def test_upsert_matches_existing_by_codigo_and_proveedor_id(self):
        proveedor_id = uuid.uuid4()
        existing = Referencia(
            id=uuid.uuid4(), codigo="REF1", proveedor_id=proveedor_id,
            unidad_empaque=1, precio_normal=100, activa=True,
        )
        db = FakeAsyncSession(execute_queue=[[existing]])
        data = ReferenciaCreate(codigo="REF1", proveedor_id=proveedor_id, precio_normal=120)

        referencia, _, created = await maestros.upsert_referencia(db, data)

        assert referencia is existing
        assert referencia.precio_normal == 120
        assert created is False


class TestReferenciaSustitucionDeactivates:
    async def test_setting_sustituida_por_deactivates_the_referencia(self):
        referencia = Referencia(
            id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(),
            unidad_empaque=1, activa=True,
        )
        db = FakeAsyncSession()
        substitute_id = uuid.uuid4()

        updated = await maestros.update_referencia(
            db, referencia, ReferenciaUpdate(sustituida_por=substitute_id)
        )

        assert updated.sustituida_por == substitute_id
        assert updated.activa is False


class TestSoftDeleteNeverHardDeletes:
    async def test_deactivate_sucursal_sets_activa_false_never_deletes(self):
        sucursal = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE", activa=True)
        db = FakeAsyncSession()

        await maestros.deactivate_sucursal(db, sucursal)

        assert sucursal.activa is False

    async def test_deactivate_proveedor_sets_activa_false(self):
        proveedor = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", activa=True)
        db = FakeAsyncSession()

        await maestros.deactivate_proveedor(db, proveedor)

        assert proveedor.activa is False

    async def test_deactivate_bodega_sets_activa_false(self):
        bodega = Bodega(id=uuid.uuid4(), codigo="BA061", activa=True)
        db = FakeAsyncSession()

        await maestros.deactivate_bodega(db, bodega)

        assert bodega.activa is False

    async def test_deactivate_referencia_sets_activa_false(self):
        referencia = Referencia(id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(), unidad_empaque=1, activa=True)
        db = FakeAsyncSession()

        await maestros.deactivate_referencia(db, referencia)

        assert referencia.activa is False

    async def test_maestros_module_never_calls_db_delete(self):
        """Static guard: no function in `services/maestros.py` may ever
        call `db.delete(...)` — deleting a master is ALWAYS `activa = false`
        (owner decision #3 / spec "No endpoint offers hard delete")."""
        import ast
        import inspect

        source = inspect.getsource(maestros)
        tree = ast.parse(source)
        delete_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "delete"
        ]
        assert delete_calls == []


class TestNewSpecFieldsPersistOnCreate:
    """Post-archive correction (sdd/motored-pedidos-cimientos): the 4
    `create_*` functions build their model instance with an explicit field
    list (this codebase's own style, no blind `**kwargs`) -- each list must
    be extended to include the spec fields the original build dropped."""

    async def test_create_sucursal_persists_the_six_new_fields(self):
        db = FakeAsyncSession()
        from datetime import date

        data = SucursalCreate(
            nombre="CALI NORTE",
            dias_empaque=3,
            dias_transito=5,
            bodega_principal="BE051",
            departamento="Valle del Cauca",
            ciudad="Cali",
            fecha_apertura=date(2020, 1, 15),
        )

        sucursal = await maestros.create_sucursal(db, data)

        assert sucursal.dias_empaque == 3
        assert sucursal.dias_transito == 5
        assert sucursal.bodega_principal == "BE051"
        assert sucursal.departamento == "Valle del Cauca"
        assert sucursal.ciudad == "Cali"
        assert sucursal.fecha_apertura == date(2020, 1, 15)

    async def test_create_proveedor_persists_dias_seguridad_default(self):
        db = FakeAsyncSession()
        from decimal import Decimal

        data = ProveedorCreate(codigo="HMCL", nombre="HMCL Colombia", dias_seguridad_default=Decimal("3.0"))

        proveedor = await maestros.create_proveedor(db, data)

        assert proveedor.dias_seguridad_default == Decimal("3.0")

    async def test_create_bodega_persists_descripcion(self):
        db = FakeAsyncSession()
        data = BodegaCreate(codigo="BA061", descripcion="Bodega central")

        bodega = await maestros.create_bodega(db, data)

        assert bodega.descripcion == "Bodega central"

    async def test_create_referencia_persists_nombre_and_linea_comercial(self):
        db = FakeAsyncSession()
        data = ReferenciaCreate(
            codigo="REF1",
            proveedor_id=uuid.uuid4(),
            nombre="FILTRO DE ACEITE",
            linea_comercial="REPUESTOS",
        )

        referencia, _ = await maestros.create_referencia(db, data)

        assert referencia.nombre == "FILTRO DE ACEITE"
        assert referencia.linea_comercial == "REPUESTOS"


class TestDeactivateRecordsAuditTrail:
    async def test_deactivate_writes_an_auditoria_maestro_row(self):
        sucursal = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE", activa=True)
        db = FakeAsyncSession()
        usuario_id = uuid.uuid4()

        await maestros.deactivate_sucursal(db, sucursal, usuario_id=usuario_id)

        audit_rows = db.added_of_type(AuditoriaMaestro)
        assert len(audit_rows) == 1
        assert audit_rows[0].accion == "deactivate"
        assert audit_rows[0].entidad == "sucursal"
        assert audit_rows[0].usuario_id == usuario_id
