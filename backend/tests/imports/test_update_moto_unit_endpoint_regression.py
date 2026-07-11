"""
Approval/regression tests for `update_moto_unit`
(`PATCH /api/v1/imports/moto-units/{unit_id}`, `imports.py:2513`), written
BEFORE its Phase 6 extraction (`sdd/imports-oversized-functions-refactor-tier2`).

Covers the endpoint's behavior exactly as it exists today across its 5
concerns (role gate, generic fields incl. `model` normalization,
color->RUNT resolution, order-transfer with its own superadmin gate,
empadronamiento-fisico toggle, location/observation assignment) plus the
response shape.

Run FIRST against pre-refactor `imports.py` to capture baseline behavior,
then again after Phase 6's extraction (`resolve_color_runt` moved to
`imports_service.py`; `_apply_generic_fields`/`_apply_color_update`/
`_apply_order_transfer`/`_apply_empadronamiento_fisico`/
`_apply_location_observation` extracted in `imports.py`) to confirm
byte-for-byte identical responses/status codes/error strings (spec's
Behavior-Preserving Refactor requirement).
"""
import uuid
from datetime import datetime

from app.api.v1 import imports as imports_module
from tests.conftest import make_test_client
from tests.imports.conftest import (
    FakeAsyncSession,
    make_imports_editor,
    make_moto_location,
    make_moto_observation,
    make_moto_unit,
    make_shipment_order,
)


def _tenant(name="Distribuidor Norte", tenant_id=None):
    from app.models.tenant import Tenant, TenantType
    return Tenant(
        id=tenant_id or uuid.uuid4(),
        name=name,
        subdomain=f"dist-{uuid.uuid4().hex[:8]}",
        tenant_type=TenantType.distribuidor,
    )


def _color_mapping(nombre_runt="ROJO CARMESI"):
    from app.models.imports import ColorRuntMapping
    return ColorRuntMapping(
        id=uuid.uuid4(),
        color_key="ROJO",
        color_original="Rojo",
        nombre_runt=nombre_runt,
    )


# ---------------------------------------------------------------------------
# Role gate / not-found
# ---------------------------------------------------------------------------

def test_non_editor_role_403_before_any_db_query():
    unit = make_moto_unit()
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(
        current_user=make_imports_editor(role="jefe_taller"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}", json={"model_year": 2024}
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Sin permisos para editar unidades"}


def test_unit_not_found_404():
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{uuid.uuid4()}", json={"model_year": 2024}
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Unidad no encontrada"}


# ---------------------------------------------------------------------------
# Generic fields (incl. model normalization)
# ---------------------------------------------------------------------------

def test_generic_fields_are_set_and_model_is_normalized():
    unit = make_moto_unit(model="Old Model")
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={
                "model": "  um   dsr    150  ",
                "engine_number": "ENGNEW01",
                "model_year": 2025,
                "separada_nacionalizacion": True,
                "facturado": True,
                "cargado_runt": True,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert unit.model == "UM DSR 150"
    assert unit.engine_number == "ENGNEW01"
    assert unit.model_year == 2025
    assert unit.separada_nacionalizacion is True
    assert unit.facturado is True
    assert unit.cargado_runt is True
    assert body["model"] == "UM DSR 150"
    assert body["separada_nacionalizacion"] is True


# ---------------------------------------------------------------------------
# Color -> RUNT resolution
# ---------------------------------------------------------------------------

def test_color_update_resolves_runt_when_mapping_found():
    unit = make_moto_unit(color=None, color_runt=None)
    mapping = _color_mapping(nombre_runt="ROJO CARMESI")
    fake_db = FakeAsyncSession(execute_queue=[[unit], [mapping]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}", json={"color": "Rojo"}
        )

    assert response.status_code == 200
    assert unit.color == "Rojo"
    assert unit.color_runt == "ROJO CARMESI"


def test_color_update_leaves_color_runt_none_when_no_mapping():
    unit = make_moto_unit(color=None, color_runt="STALE")
    fake_db = FakeAsyncSession(execute_queue=[[unit], []])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}", json={"color": "COLOR INEXISTENTE"}
        )

    assert response.status_code == 200
    assert unit.color == "COLOR INEXISTENTE"
    assert unit.color_runt is None


# ---------------------------------------------------------------------------
# Order transfer (superadmin-gated)
# ---------------------------------------------------------------------------

def test_order_transfer_non_superadmin_403():
    order = make_shipment_order()
    unit = make_moto_unit(shipment_order=order)
    target = make_shipment_order()
    fake_db = FakeAsyncSession(execute_queue=[[unit]], get_objects=[target])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={"shipment_order_id": str(target.id)},
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Solo superadmin puede transferir unidades entre pedidos"
    }


def test_order_transfer_target_not_found_404():
    order = make_shipment_order()
    unit = make_moto_unit(shipment_order=order)
    missing_target_id = uuid.uuid4()
    fake_db = FakeAsyncSession(execute_queue=[[unit]], get_objects=[])

    with make_test_client(
        current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={"shipment_order_id": str(missing_target_id)},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Pedido destino no encontrado"}


def test_order_transfer_to_spare_part_order_400():
    order = make_shipment_order()
    unit = make_moto_unit(shipment_order=order)
    target = make_shipment_order(is_spare_part=True)
    fake_db = FakeAsyncSession(execute_queue=[[unit]], get_objects=[target])

    with make_test_client(
        current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={"shipment_order_id": str(target.id)},
        )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "El pedido destino debe ser de motocicletas, no de repuestos"
    }


def test_order_transfer_success_updates_order_id_and_source_pi():
    order = make_shipment_order(pi_number="E0000001")
    unit = make_moto_unit(shipment_order=order)
    target = make_shipment_order(pi_number="E0000099", is_spare_part=False)
    fake_db = FakeAsyncSession(execute_queue=[[unit]], get_objects=[target])

    with make_test_client(
        current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={"shipment_order_id": str(target.id)},
        )

    assert response.status_code == 200
    assert unit.shipment_order_id == target.id
    assert unit.source_pi == "E0000099"


def test_order_transfer_same_order_id_is_a_noop_even_for_non_superadmin():
    order = make_shipment_order()
    unit = make_moto_unit(shipment_order=order)
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={"shipment_order_id": str(order.id)},
        )

    # Same order id as current -> transfer branch never triggers, no 403.
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Empadronamiento físico toggle
# ---------------------------------------------------------------------------

def test_empadronamiento_enviado_true_sets_fecha_when_previously_unset():
    unit = make_moto_unit(empadronamiento_fisico_fecha=None)
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={"empadronamiento_fisico_enviado": True},
        )

    assert response.status_code == 200
    assert unit.empadronamiento_fisico_enviado is True
    assert unit.empadronamiento_fisico_fecha is not None


def test_empadronamiento_enviado_true_does_not_overwrite_existing_fecha():
    existing_fecha = datetime(2025, 1, 1, 12, 0, 0)
    unit = make_moto_unit(empadronamiento_fisico_fecha=existing_fecha)
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={"empadronamiento_fisico_enviado": True},
        )

    assert response.status_code == 200
    assert unit.empadronamiento_fisico_fecha == existing_fecha


def test_empadronamiento_enviado_true_with_missing_distribuidor_404():
    unit = make_moto_unit()
    missing_id = uuid.uuid4()
    fake_db = FakeAsyncSession(execute_queue=[[unit], []])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={
                "empadronamiento_fisico_enviado": True,
                "empadronamiento_fisico_distribuidor_id": str(missing_id),
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Distribuidor no encontrado"}


def test_empadronamiento_enviado_true_with_distribuidor_sets_id_and_name():
    unit = make_moto_unit()
    tenant = _tenant(name="Distribuidor Sur")
    fake_db = FakeAsyncSession(execute_queue=[[unit], [tenant]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={
                "empadronamiento_fisico_enviado": True,
                "empadronamiento_fisico_distribuidor_id": str(tenant.id),
            },
        )

    assert response.status_code == 200
    assert unit.empadronamiento_fisico_distribuidor_id == tenant.id
    assert unit.empadronamiento_fisico_distribuidor_nombre == "Distribuidor Sur"


def test_empadronamiento_enviado_false_clears_fecha_and_distribuidor():
    unit = make_moto_unit(
        empadronamiento_fisico_enviado=True,
        empadronamiento_fisico_fecha=datetime(2025, 1, 1),
        empadronamiento_fisico_distribuidor_id=uuid.uuid4(),
        empadronamiento_fisico_distribuidor_nombre="Old Distribuidor",
    )
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={"empadronamiento_fisico_enviado": False},
        )

    assert response.status_code == 200
    assert unit.empadronamiento_fisico_fecha is None
    assert unit.empadronamiento_fisico_distribuidor_id is None
    assert unit.empadronamiento_fisico_distribuidor_nombre is None


# ---------------------------------------------------------------------------
# Location / observation assignment
# ---------------------------------------------------------------------------

def test_location_and_observation_are_assigned_when_provided():
    location = make_moto_location(name="BODEGA NORTE")
    observation = make_moto_observation(name="EN TRANSITO")
    unit = make_moto_unit()
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}",
            json={
                "location_id": str(location.id),
                "observation_id": str(observation.id),
            },
        )

    assert response.status_code == 200
    assert unit.location_id == location.id
    assert unit.observation_id == observation.id


def test_location_id_explicitly_null_clears_it():
    location = make_moto_location(name="BODEGA NORTE")
    unit = make_moto_unit(location=location)
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}", json={"location_id": None}
        )

    assert response.status_code == 200
    assert unit.location_id is None


def test_location_id_omitted_from_payload_leaves_it_untouched():
    location = make_moto_location(name="BODEGA NORTE")
    unit = make_moto_unit(location=location)
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}", json={"model_year": 2024}
        )

    assert response.status_code == 200
    assert unit.location_id == location.id


# ---------------------------------------------------------------------------
# Response shape / persistence
# ---------------------------------------------------------------------------

def test_response_shape_has_all_expected_keys():
    location = make_moto_location(name="BODEGA CENTRAL")
    observation = make_moto_observation(name="OK")
    unit = make_moto_unit(location=location, observation=observation)
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}", json={"model_year": 2026}
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "id", "model", "vin_number", "engine_number", "color", "model_year",
        "empadronamiento_fisico_enviado", "empadronamiento_fisico_fecha",
        "empadronamiento_fisico_distribuidor_id", "empadronamiento_fisico_distribuidor_nombre",
        "location_id", "location_name", "observation_id", "observation_name",
        "separada_nacionalizacion", "facturado", "cargado_runt",
    }
    assert body["location_name"] == "BODEGA CENTRAL"
    assert body["observation_name"] == "OK"


def test_endpoint_calls_commit_and_refresh_itself(monkeypatch):
    """Unlike `download_certificado`, `update_moto_unit` DOES persist
    explicitly — locks in that this endpoint's commit/refresh behavior is
    untouched by the Phase 6 helper extraction."""
    unit = make_moto_unit()

    class _CommitSpySession(FakeAsyncSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.commit_called = False
            self.refresh_called_with = None

        async def commit(self):
            self.commit_called = True
            await super().commit()

        async def refresh(self, obj, attribute_names=None):
            self.refresh_called_with = attribute_names
            await super().refresh(obj, attribute_names=attribute_names)

    fake_db = _CommitSpySession(execute_queue=[[unit]])

    with make_test_client(
        current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db
    ) as client:
        response = client.patch(
            f"/api/v1/imports/moto-units/{unit.id}", json={"model_year": 2024}
        )

    assert response.status_code == 200
    assert fake_db.commit_called is True
    assert fake_db.refresh_called_with == ["location", "observation"]
