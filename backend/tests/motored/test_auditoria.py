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


class TestListAndLongValues:
    """`referencia.homologados` (2026-09-28) is the first list-valued master
    field -- audit values must stay readable and fit `String(500)`, and
    clipping must never hide a real change nor cut an item in half."""

    def _audit(self, before, after):
        db = FakeAsyncSession()
        return auditoria.diff_and_audit(db, "referencia", uuid.uuid4(), None, {"homologados": before}, {"homologados": after})

    def test_list_values_are_joined_readably(self):
        rows = self._audit([], ["A", "B"])
        assert rows[0].valor_anterior == ""
        assert rows[0].valor_nuevo == "A, B"

    def test_long_lists_fit_the_column_and_are_cut_on_item_boundaries(self):
        items = [f"ITEM-{i:03d}-{'X' * 20}" for i in range(50)]
        rows = self._audit([], items)
        valor = rows[0].valor_nuevo
        assert len(valor) <= 500
        visible, _, marker = valor.partition(" … ")
        assert all(part in items for part in visible.split(", "))
        shown = len(visible.split(", "))
        assert f"+{len(items) - shown}" in marker

    def test_a_change_beyond_the_cutoff_still_produces_different_audit_values(self):
        before = [f"ITEM-{i:03d}-{'X' * 20}" for i in range(50)]
        after = before[:-1] + ["CHANGED"]
        rows = self._audit(before, after)
        assert len(rows) == 1
        assert rows[0].valor_anterior != rows[0].valor_nuevo
        assert len(rows[0].valor_anterior) <= 500
        assert len(rows[0].valor_nuevo) <= 500

    def test_long_scalar_strings_also_stay_distinguishable(self):
        db = FakeAsyncSession()
        rows = auditoria.diff_and_audit(
            db, "referencia", uuid.uuid4(), None, {"nombre": "A" * 600}, {"nombre": "A" * 599 + "B"},
        )
        assert rows[0].valor_anterior != rows[0].valor_nuevo
        assert len(rows[0].valor_nuevo) <= 500
