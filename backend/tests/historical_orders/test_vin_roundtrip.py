"""
tests/historical_orders/test_vin_roundtrip.py — Requirement "Inline Vehicle
Registration": a real, known VIN round-trips through `vin_master_service.
query_vin` (called transitively via `vehicle_service.register_or_update_
vehicle`, AS-IS) into the newly-created `Vehicle`'s `model`/`year` fields,
same pattern as `tests/vehicles/test_vin_master_lookup.py`.

`register_or_update_vehicle`'s VIN-enrichment only fills `model`/`year`
when the caller left them unset (never `color` — that attribute isn't even
read off `VinLookupResult` by the current, contract-locked production
code) and never overwrites a caller-provided value.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

from app.models.order import ServiceStatus, ServiceType
from app.schemas.historical_order import HistoricalOrderCreate
from app.services import historical_order_service as svc

from tests.historical_orders.conftest import (
    FakeHistoricalOrderSession,
    make_moto_unit,
    make_superadmin,
    make_tenant,
)

REAL_VIN = "9C6JC5820PM123456"


def _payload(**overrides) -> HistoricalOrderCreate:
    data = dict(
        tenant_id=uuid.uuid4(),
        vehicle={"plate": "XYZ999", "vin": REAL_VIN},
        client={"name": "Juan Perez", "phone": "3001234567"},
        service_type=ServiceType.regular,
        status=ServiceStatus.received,
        mileage_km=Decimal("500"),
        created_at=datetime(2025, 1, 10, 9, 0),
        completed_at=None,
        delivered_at=None,
        customer_notes=None,
        diagnosis=None,
        general_observations=None,
        technician_id=None,
        acknowledge_duplicate=False,
    )
    data.update(overrides)
    return HistoricalOrderCreate(**data)


class TestVinRoundtripFillsNewVehicle:
    async def test_known_vin_fills_model_and_year_on_a_brand_new_vehicle(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        unit = make_moto_unit(vin_number=REAL_VIN, model="Renegade Sport 200", model_year=2026, color_runt="Azul")

        payload = _payload()
        fake_db = FakeHistoricalOrderSession(
            vehicles=[],  # miss -> create path
            moto_units=[unit],
            tenant=make_tenant(tenant_id=payload.tenant_id),
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())

        from app.models.vehicle import Vehicle
        created_vehicle = next(obj for obj in fake_db.added if isinstance(obj, Vehicle))
        assert created_vehicle.vin == REAL_VIN
        assert created_vehicle.model == "RENEGADE SPORT 200"
        assert created_vehicle.year == 2026
        assert created_vehicle.plate == "XYZ999"
        # Contract-locked behaviour: brand always defaults to "UM" when the
        # superadmin didn't supply one -- `register_or_update_vehicle`
        # never touches brand from the VIN master at all.
        assert created_vehicle.brand == "UM"
        assert order.vehicle_id == created_vehicle.id

    async def test_caller_provided_model_and_year_are_not_overwritten(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        unit = make_moto_unit(vin_number=REAL_VIN, model="Renegade Sport 200", model_year=2026)

        payload = _payload(vehicle={"plate": "XYZ999", "vin": REAL_VIN, "model": "NKD 125", "year": 2020})
        fake_db = FakeHistoricalOrderSession(
            vehicles=[], moto_units=[unit], tenant=make_tenant(tenant_id=payload.tenant_id),
        )

        await svc.create_historical_order(fake_db, payload, make_superadmin())

        from app.models.vehicle import Vehicle
        created_vehicle = next(obj for obj in fake_db.added if isinstance(obj, Vehicle))
        assert created_vehicle.model == "NKD 125"
        assert created_vehicle.year == 2020
