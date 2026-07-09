"""
Unit tests for `_serialize_moto_unit` and `_build_moto_unit_filters`
(`backend/app/api/v1/imports.py`) — Phase 3 of
`sdd/imports-oversized-functions-refactor-tier1`.

Pure functions, no DB/HTTP:
- `_serialize_moto_unit` — flattens a `ShipmentMotoUnit` (+ related
  `ShipmentOrder`/`MotoLocation`/`MotoObservation`) into the moto-units
  list's item dict.
- `_build_moto_unit_filters` — WHERE-clause pair builder; asserted here via
  the returned clause LISTS' lengths/identity rather than compiled SQL,
  since no DB/HTTP harness is involved in this file.
"""
from app.api.v1.imports import _build_moto_unit_filters, _serialize_moto_unit
from tests.imports.conftest import (
    make_moto_location,
    make_moto_observation,
    make_moto_unit,
    make_shipment_order,
)


def test_serialize_moto_unit_maps_all_fields():
    order = make_shipment_order(pi_number="E0000950")
    location = make_moto_location(name="BODEGA SUR")
    observation = make_moto_observation(name="EN REVISION")
    unit = make_moto_unit(
        shipment_order=order,
        location=location,
        observation=observation,
        vin_number="VIN-XYZ",
        engine_number="ENG-XYZ",
        model="cb 500",
        model_year=2023,
        item_no=3,
        certificado_generado=True,
        facturado=True,
    )

    result = _serialize_moto_unit(unit)

    assert result["id"] == str(unit.id)
    assert result["shipment_order_id"] == str(unit.shipment_order_id)
    assert result["item_no"] == 3
    assert result["vin_number"] == "VIN-XYZ"
    assert result["engine_number"] == "ENG-XYZ"
    assert result["certificado_generado"] is True
    assert result["facturado"] is True
    assert result["cargado_runt"] is False
    assert result["location_id"] == str(location.id)
    assert result["location_name"] == "BODEGA SUR"
    assert result["observation_id"] == str(observation.id)
    assert result["observation_name"] == "EN REVISION"
    assert result["pi_number"] == "E0000950"
    assert result["model"] == "CB 500"
    assert result["model_year"] == 2023


def test_serialize_moto_unit_without_location_or_observation():
    order = make_shipment_order(pi_number="E0000951", model="ORDER FALLBACK", model_year=2019)
    unit = make_moto_unit(shipment_order=order, location=None, observation=None, model=None, model_year=None)

    result = _serialize_moto_unit(unit)

    assert result["location_id"] is None
    assert result["location_name"] is None
    assert result["observation_id"] is None
    assert result["observation_name"] is None
    assert result["model"] == "ORDER FALLBACK"
    assert result["model_year"] == 2019


def test_serialize_moto_unit_none_shipment_order_defaults_pi_and_model_to_none():
    """Defensive branch (`o = u.shipment_order`, guarded by `if o else None`
    throughout) — locked in even though the endpoint always joins a real
    order today."""
    unit = make_moto_unit(model="raw model")
    unit.shipment_order = None

    result = _serialize_moto_unit(unit)

    assert result["pi_number"] is None
    assert result["model"] == "RAW MODEL"  # unit.model wins, no order to fall back to
    assert result["model_year"] == unit.model_year


def test_build_moto_unit_filters_base_filters_exclude_status_params():
    """`base_filters` never grows from `certificado_generado`/`observation_id`/
    `empadronamiento_fisico_enviado`/`facturado`/`cargado_runt` — only
    `filters` does."""
    import uuid

    base_filters, filters = _build_moto_unit_filters(
        pi_number=None,
        model=None,
        vin=None,
        engine=None,
        certificado_generado=True,
        observation_id=uuid.uuid4(),
        empadronamiento_fisico_enviado=True,
        facturado=True,
        cargado_runt=True,
    )

    assert len(base_filters) == 1  # only `is_spare_part == False`
    assert len(filters) == 1 + 5  # base + all 5 optional status params


def test_build_moto_unit_filters_text_params_extend_base_filters():
    base_filters, filters = _build_moto_unit_filters(
        pi_number="E1",
        model="M1",
        vin="V1",
        engine="EN1",
        certificado_generado=None,
        observation_id=None,
        empadronamiento_fisico_enviado=None,
        facturado=None,
        cargado_runt=None,
    )

    assert len(base_filters) == 1 + 4  # is_spare_part + pi_number/model/vin/engine
    assert len(filters) == len(base_filters)  # no optional status params set -> same clause count
    # `filters = list(base_filters)` copies references, not a new list of
    # equivalent-but-distinct clauses — check element-wise identity rather
    # than `==` (SQLAlchemy's `ColumnElement.__eq__` builds a SQL expression,
    # not a bool, so list `==` is not a safe/meaningful comparison here).
    assert all(f is b for f, b in zip(filters, base_filters))
    assert filters is not base_filters  # but `filters` itself is a distinct list object


def test_build_moto_unit_filters_no_params_returns_only_is_spare_part_clause():
    base_filters, filters = _build_moto_unit_filters(
        pi_number=None, model=None, vin=None, engine=None,
        certificado_generado=None, observation_id=None,
        empadronamiento_fisico_enviado=None, facturado=None, cargado_runt=None,
    )
    assert len(base_filters) == 1
    assert len(filters) == 1
