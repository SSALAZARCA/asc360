"""
Approval/regression tests for `download_certificado`
(`GET /api/v1/imports/moto-units/{unit_id}/certificado`, `imports.py:2976`),
written BEFORE its Phase 5 extraction (`sdd/imports-oversized-functions-refactor-tier2`).

Covers the endpoint's behavior exactly as it exists today:
  - Unit not found -> 404.
  - Related order not found -> 404.
  - DIM not yet uploaded (`certificado_generado` False) -> 422.
  - Missing required fields (model, model_year, engine_number, vin_number,
    color_runt, using the unit>order fallback for model/model_year) -> 422
    with a single joined message listing every missing field, in the fixed
    order the endpoint checks them.
  - Successful generation: unit>order fallback values are written onto the
    unit BEFORE calling `certificate_service.generate_certificado_bytes`, a
    matching `VehicleModel` is adapted into a `_SpecsProxy`-shaped object
    (only when `cilindrada != "N/A"`), the endpoint calls
    `certificate_service.generate_certificado_bytes` with that object (or
    `None` when no usable match exists), and returns the generated PDF bytes
    with an `attachment` Content-Disposition header.
  - CRITICAL quirk (spec's "preserves implicit auto-commit" scenario): the
    endpoint must NOT call `db.commit()`/`db.refresh()` itself — the unit's
    `model`/`model_year` mutation relies solely on `get_db`'s implicit
    commit-on-success wrapper. `FakeAsyncSession.commit()` raises if called
    unexpectedly is NOT asserted directly (the fake's `commit()` is a no-op
    stub even when unused), so this is instead asserted via a dedicated
    spy-wrapped session that records whether `commit()` was invoked.

Run FIRST against pre-refactor `imports.py` to capture baseline behavior,
then again after Phase 5's extraction (`_validate_certificado_required_fields`
+ module-scope `_SpecsProxy`) to confirm byte-for-byte identical
responses/status codes/error strings (spec's Behavior-Preserving Refactor
requirement).
"""
import uuid

from app.api.v1 import imports as imports_module
from tests.conftest import make_test_client
from tests.imports.conftest import (
    FakeAsyncSession,
    make_actor,
    make_moto_unit,
    make_shipment_order,
)


class _CommitSpySession(FakeAsyncSession):
    """Wraps `FakeAsyncSession` to record whether `commit()`/`refresh()`
    were ever invoked, without changing their (no-op) behavior."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commit_called = False
        self.refresh_called = False

    async def commit(self):
        self.commit_called = True
        await super().commit()

    async def refresh(self, obj, attribute_names=None):
        self.refresh_called = True
        await super().refresh(obj, attribute_names=attribute_names)


def _patch_generate_ok(monkeypatch, pdf_bytes=b"%PDF-1.4 fake certificate", capture=None):
    def _fake_generate(unit, order, vehicle_model, color_runt=""):
        if capture is not None:
            capture["unit"] = unit
            capture["order"] = order
            capture["vehicle_model"] = vehicle_model
            capture["color_runt"] = color_runt
        return pdf_bytes

    monkeypatch.setattr(imports_module.certificate_service, "generate_certificado_bytes", _fake_generate)


def _complete_unit(**overrides):
    defaults = dict(
        vin_number="VIN9001",
        engine_number="ENG9001",
        model="UM DSR 150",
        model_year=2024,
        color="ROJO",
        color_runt="ROJO",
        certificado_generado=True,
    )
    defaults.update(overrides)
    return make_moto_unit(**defaults)


# ---------------------------------------------------------------------------
# 404s
# ---------------------------------------------------------------------------

def test_unit_not_found_404():
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get(f"/api/v1/imports/moto-units/{uuid.uuid4()}/certificado")

    assert response.status_code == 404
    assert response.json() == {"detail": "Unidad no encontrada"}


def test_related_order_not_found_404():
    unit = _complete_unit()
    # Detach the unit from any resolvable order: `db.get(ShipmentOrder, ...)`
    # must miss even though `unit.shipment_order_id` is set.
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[unit])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get(f"/api/v1/imports/moto-units/{unit.id}/certificado")

    assert response.status_code == 404
    assert response.json() == {"detail": "Pedido asociado no encontrado"}


# ---------------------------------------------------------------------------
# DIM not uploaded yet
# ---------------------------------------------------------------------------

def test_dim_not_uploaded_422():
    order = make_shipment_order()
    unit = _complete_unit(shipment_order=order, certificado_generado=False)
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[unit, order])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get(f"/api/v1/imports/moto-units/{unit.id}/certificado")

    assert response.status_code == 422
    assert response.json() == {
        "detail": "La DIM no ha sido cargada para esta unidad. Cargá primero el PDF de la DIM."
    }


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------

def test_all_fields_missing_lists_every_missing_field_in_order():
    order = make_shipment_order(model=None, model_year=None)
    unit = _complete_unit(
        shipment_order=order,
        model=None,
        model_year=None,
        engine_number=None,
        vin_number=None,
        color=None,
        color_runt=None,
    )
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[unit, order])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get(f"/api/v1/imports/moto-units/{unit.id}/certificado")

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Faltan datos obligatorios para generar el empadronamiento: "
            "modelo de la motocicleta, año modelo, número de motor, "
            "número de chasis (VIN), color 'vacío' no registrado en tabla RUNT."
        )
    }


def test_color_runt_missing_reports_the_units_raw_color_value():
    order = make_shipment_order()
    unit = _complete_unit(shipment_order=order, color="AZUL PETROLEO", color_runt=None)
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[unit, order])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get(f"/api/v1/imports/moto-units/{unit.id}/certificado")

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Faltan datos obligatorios para generar el empadronamiento: "
            "color 'AZUL PETROLEO' no registrado en tabla RUNT."
        )
    }


# ---------------------------------------------------------------------------
# Successful generation
# ---------------------------------------------------------------------------

def test_success_falls_back_to_order_model_and_writes_fallback_onto_unit(monkeypatch):
    order = make_shipment_order(model="UM RENEGADE SPORT S", model_year=2022)
    unit = _complete_unit(shipment_order=order, model=None, model_year=None)
    capture = {}
    _patch_generate_ok(monkeypatch, capture=capture)
    # `select(VehicleModel)` returns no rows -> no spec match -> vm_obj stays None.
    fake_db = FakeAsyncSession(execute_queue=[[]], get_objects=[unit, order])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get(f"/api/v1/imports/moto-units/{unit.id}/certificado")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="Certificado_{unit.vin_number}.pdf"'
    )
    assert response.content == b"%PDF-1.4 fake certificate"

    # Fallback values were written onto the unit before generation.
    assert unit.model == "UM RENEGADE SPORT S"
    assert unit.model_year == 2022
    assert capture["unit"] is unit
    assert capture["order"] is order
    assert capture["vehicle_model"] is None
    assert capture["color_runt"] == unit.color_runt


def test_success_builds_specs_proxy_from_matched_vehicle_model(monkeypatch):
    from app.models.imports import VehicleModel

    order = make_shipment_order()
    unit = _complete_unit(shipment_order=order, model="UM DSR 150")
    vm = VehicleModel(
        id=uuid.uuid4(),
        model_name="UM DSR 150",
        brand="UM",
        cilindrada="150cc",
        potencia="10HP",
        peso="120kg",
        vueltas_aire="N/A",
        posicion_cortina="N/A",
        sistemas_control="CATALIZADOR / CANISTER",
        fuel_system="CARBURADOR",
    )
    capture = {}
    _patch_generate_ok(monkeypatch, capture=capture)
    fake_db = FakeAsyncSession(execute_queue=[[vm]], get_objects=[unit, order])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get(f"/api/v1/imports/moto-units/{unit.id}/certificado")

    assert response.status_code == 200
    vm_obj = capture["vehicle_model"]
    assert vm_obj is not None
    assert vm_obj.cilindrada == "150cc"
    assert vm_obj.potencia == "10HP"
    assert vm_obj.peso == "120kg"
    assert vm_obj.vueltas_aire == "N/A"
    assert vm_obj.posicion_cortina == "N/A"
    assert vm_obj.sistemas_control == "CATALIZADOR / CANISTER"
    assert vm_obj.fuel_system == "CARBURADOR"


def test_success_no_specs_proxy_when_match_has_no_cilindrada(monkeypatch):
    """`encontrar_specs_para_modelo` returns its all-`'N/A'` defaults dict
    when nothing matches — the endpoint must NOT build a `_SpecsProxy` from
    a defaults dict (`vm_obj` stays `None`)."""
    order = make_shipment_order()
    unit = _complete_unit(shipment_order=order, model="MODELO INEXISTENTE XYZ")
    capture = {}
    _patch_generate_ok(monkeypatch, capture=capture)
    # No VehicleModel rows at all -> encontrar_specs_para_modelo returns defaults (cilindrada='N/A').
    fake_db = FakeAsyncSession(execute_queue=[[]], get_objects=[unit, order])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get(f"/api/v1/imports/moto-units/{unit.id}/certificado")

    assert response.status_code == 200
    assert capture["vehicle_model"] is None


def test_success_does_not_call_commit_or_refresh_itself(monkeypatch):
    """Locks in the spec's 'preserves implicit auto-commit' quirk: the
    endpoint mutates `unit.model`/`unit.model_year` in place but relies
    entirely on `get_db`'s wrapper to persist — it must not call
    `db.commit()`/`db.refresh()` on its own."""
    order = make_shipment_order(model="UM DSR 150", model_year=2024)
    unit = _complete_unit(shipment_order=order, model=None, model_year=None)
    _patch_generate_ok(monkeypatch)
    fake_db = _CommitSpySession(execute_queue=[[]], get_objects=[unit, order])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get(f"/api/v1/imports/moto-units/{unit.id}/certificado")

    assert response.status_code == 200
    assert fake_db.commit_called is False
    assert fake_db.refresh_called is False
