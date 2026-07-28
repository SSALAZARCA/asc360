"""
Pins a real bug found while fixing the VIN lookup used by the reception
flow and Datos Rápidos: `vehicle_service.py` has two OTHER, older
VIN-enrichment call sites that were never covered by any test.

- `register_or_update_vehicle` (runs on every vehicle registration, e.g.
  Sonia's reception flow) read `vin_data.brand`, an attribute that never
  existed on anything `vin_master_service.query_vin` ever returned -- it
  was dormant only because `query_vin` always returned `None` (the dead
  `VinMaster` table). Once `query_vin` started returning real
  `VinLookupResult`s from `ShipmentMotoUnit`, this would have crashed with
  `AttributeError` the first time a new vehicle was registered with a VIN
  that matched a real packing-list unit.
- `get_vehicle_by_plate`'s warranty-info enrichment read
  `vin_data.model_name`/`.model_code`/`.garantia_*` -- these DO exist on
  the real `VinMaster` model (a separate table for manufacturer warranty
  terms, still never populated by any import flow), but NOT on the new
  `VinLookupResult`. Fixed by giving it its own service method
  (`query_warranty_vin`, querying `VinMaster` directly) instead of sharing
  `query_vin`.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import app.services.vin_master_service as vin_master_service_module
from app.services.vehicle_service import vehicle_service
from app.services.vin_master_service import VinLookupResult
from app.schemas.vehicle import VehicleCreate

vms = vin_master_service_module.vin_master_service


def make_vehicle_in(**overrides) -> VehicleCreate:
    data = dict(
        plate="ABC123", vin="9C6JC5820PM123456", brand="UM",
        model="", color=None, year=None,
    )
    data.update(overrides)
    return VehicleCreate(**data)


def make_lookup(**overrides) -> VinLookupResult:
    data = dict(
        id=uuid.uuid4(), vin="9C6JC5820PM123456", engine_number="E1",
        model="RENEGADE SPORT 200S", year=2026, color="Rojo",
    )
    data.update(overrides)
    return VinLookupResult(**data)


def patch_repository(monkeypatch, **overrides):
    defaults = dict(
        get_by_plate=AsyncMock(return_value=None),
        create=AsyncMock(side_effect=lambda db, v: v),
    )
    defaults.update(overrides)
    monkeypatch.setattr(vehicle_service, "repository", MagicMock(**defaults))


class TestRegisterOrUpdateVehicleVinEnrichment:
    async def test_fills_model_and_year_without_crashing(self, monkeypatch):
        patch_repository(monkeypatch)
        monkeypatch.setattr(vms, "query_vin", AsyncMock(return_value=make_lookup()))

        vehicle_in = make_vehicle_in(model="", year=None)
        result = await vehicle_service.register_or_update_vehicle(
            AsyncMock(), vehicle_in,
        )

        assert result.model == "RENEGADE SPORT 200S"
        assert result.year == 2026

    async def test_does_not_overwrite_caller_provided_model_or_year(self, monkeypatch):
        patch_repository(monkeypatch)
        monkeypatch.setattr(vms, "query_vin", AsyncMock(return_value=make_lookup()))

        vehicle_in = make_vehicle_in(model="NKD 125", year=2020)
        result = await vehicle_service.register_or_update_vehicle(
            AsyncMock(), vehicle_in,
        )

        assert result.model == "NKD 125"
        assert result.year == 2020

    async def test_no_vin_skips_the_lookup_entirely(self, monkeypatch):
        patch_repository(monkeypatch)
        query_vin = AsyncMock()
        monkeypatch.setattr(vms, "query_vin", query_vin)

        vehicle_in = make_vehicle_in(vin=None)
        await vehicle_service.register_or_update_vehicle(
            AsyncMock(), vehicle_in,
        )

        query_vin.assert_not_called()


class TestGetVehicleByPlateWarrantyEnrichment:
    async def test_enriches_warranty_info_without_crashing(self, monkeypatch):
        vehicle = SimpleNamespace(
            vin="9C6JC5820PM123456", brand=None, model=None, year=None, color=None,
        )
        patch_repository(monkeypatch, get_by_plate=AsyncMock(return_value=vehicle))

        vin_master_row = SimpleNamespace(
            model_name="Renegade 200", model_code="RNG200", year=2024, color="Rojo",
            garantia_motor_km=50000, garantia_motor_meses=60,
            garantia_general_km=3000, garantia_general_meses=36,
        )
        monkeypatch.setattr(vms, "query_warranty_vin", AsyncMock(return_value=vin_master_row))

        result = await vehicle_service.get_vehicle_by_plate(AsyncMock(), "ABC123")

        assert result.brand == "Renegade 200"
        assert result.model == "RNG200"
        assert result.year == 2024
        assert result.color == "Rojo"
        assert result.warranty_info == {
            "motor_km": 50000, "motor_months": 60,
            "general_km": 3000, "general_months": 36,
        }

    async def test_no_match_leaves_the_vehicle_untouched(self, monkeypatch):
        vehicle = SimpleNamespace(
            vin="9C6JC5820PM123456", brand="UM", model="Renegade 200",
            year=2023, color="Rojo",
        )
        patch_repository(monkeypatch, get_by_plate=AsyncMock(return_value=vehicle))
        monkeypatch.setattr(vms, "query_warranty_vin", AsyncMock(return_value=None))

        result = await vehicle_service.get_vehicle_by_plate(AsyncMock(), "ABC123")

        assert result.brand == "UM"
        assert not hasattr(result, "warranty_info")
