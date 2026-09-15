"""
Phase 3 "Models/Schemas/Services" — task 3.6, master-edit audit trail
(sdd/motored-pedidos-cimientos, §7.15). Scope locked by the proposal:
masters only, not a general audit-everything system.
"""
import uuid

from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.services import auditoria
from tests.motored.conftest import FakeAsyncSession


class TestDiffAndAudit:
    def test_only_changed_fields_produce_a_row(self):
        db = FakeAsyncSession()
        entidad_id = uuid.uuid4()

        rows = auditoria.diff_and_audit(
            db, "sucursal", entidad_id, usuario_id=None,
            before={"nombre": "CALI NORTE", "sic": "S1"},
            after={"nombre": "CALI NORTE", "sic": "S2"},
        )

        assert len(rows) == 1
        assert rows[0].campo == "sic"
        assert rows[0].valor_anterior == "S1"
        assert rows[0].valor_nuevo == "S2"
        assert rows[0] in db.added

    def test_no_changes_produces_no_rows(self):
        db = FakeAsyncSession()

        rows = auditoria.diff_and_audit(
            db, "sucursal", uuid.uuid4(), usuario_id=None,
            before={"nombre": "CALI NORTE"}, after={"nombre": "CALI NORTE"},
        )

        assert rows == []
        assert db.added == []


class TestAuditCreateAndDeactivate:
    def test_audit_create_writes_one_row(self):
        db = FakeAsyncSession()
        entidad_id = uuid.uuid4()
        usuario_id = uuid.uuid4()

        row = auditoria.audit_create(db, "referencia", entidad_id, usuario_id)

        assert isinstance(row, AuditoriaMaestro)
        assert row.accion == "create"
        assert row.entidad_id == entidad_id
        assert row.usuario_id == usuario_id

    def test_audit_deactivate_records_activa_transition(self):
        db = FakeAsyncSession()

        row = auditoria.audit_deactivate(db, "proveedor", uuid.uuid4())

        assert row.accion == "deactivate"
        assert row.campo == "activa"
        assert row.valor_anterior == "True"
        assert row.valor_nuevo == "False"
