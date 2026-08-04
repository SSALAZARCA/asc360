"""
tests/distributor_deliveries/test_client_geo_normalization.py — client
city/department must be normalized against the DIVIPOLA catalog
(`resolve_geo`), the same way `tenants.py` already normalizes a tenant's
city/department on create AND update. Covers `_lookup_or_create_client`'s
both branches (new client, existing client reused) via `create_delivery`,
plus the `PATCH /distributor/deliveries/{id}` edit path.
"""
from datetime import date

from app.schemas.distributor_delivery import DeliveryEditIn
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    make_client_user,
    make_delivery_vehicle,
    make_distribuidor,
    make_valid_photo,
    VALID_DELIVERY_PAYLOAD,
)


def _payload_with_geo(city: str, department: str):
    from app.schemas.distributor_delivery import DeliveryCreate
    data = dict(VALID_DELIVERY_PAYLOAD)
    data["client"] = {**data["client"], "city": city, "department": department}
    return DeliveryCreate(**data)


class TestNewClientGeoNormalized:
    async def test_lowercase_no_accent_input_normalized_to_official_divipola_casing(self):
        fake_db = FakeDeliverySession()
        payload = _payload_with_geo("medellin", "antioquia")

        await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        from app.models.user import User
        created = [obj for obj in fake_db.added if isinstance(obj, User)][0]
        assert created.city == "MEDELLÍN"
        assert created.department == "ANTIOQUIA"

    async def test_unrecognized_city_falls_back_to_raw_input_without_raising(self):
        fake_db = FakeDeliverySession()
        payload = _payload_with_geo("Ciudad Inventada Que No Existe", "Depto Ficticio")

        await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        from app.models.user import User
        created = [obj for obj in fake_db.added if isinstance(obj, User)][0]
        assert created.city == "Ciudad Inventada Que No Existe"
        assert created.department == "Depto Ficticio"


class TestExistingClientReuseGeoNormalized:
    async def test_reused_client_gets_normalized_geo_on_refresh(self):
        existing_client = make_client_user(identification="123456789")
        fake_db = FakeDeliverySession(users=[existing_client])
        payload = _payload_with_geo("medellin", "antioquia")

        await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert existing_client.city == "MEDELLÍN"
        assert existing_client.department == "ANTIOQUIA"


class TestEditDeliveryGeoNormalized:
    async def test_patching_client_city_and_department_normalizes_both(self):
        client = make_client_user()
        vehicle = make_delivery_vehicle(plate="ABC123", delivery_date=date(2026, 7, 1))
        vehicle.client_id = client.id
        fake_db = FakeDeliverySession(users=[client], vehicles=[vehicle])
        payload = DeliveryEditIn(client_city="medellin", client_department="antioquia")

        await svc.edit_delivery(fake_db, vehicle.id, payload)

        assert client.city == "MEDELLÍN"
        assert client.department == "ANTIOQUIA"

    async def test_patching_only_department_still_normalizes_against_existing_city(self):
        """`resolve_geo` needs both fields to validate the pair -- when only
        `client_department` is in the patch, the existing (already-set)
        `client.city` must be carried through so the pair still resolves,
        mirroring `tenants.py`'s own partial-update `_resolve_geo` call."""
        client = make_client_user()
        client.city = "medellin"
        client.department = "some-old-value"
        vehicle = make_delivery_vehicle(plate="ABC123", delivery_date=date(2026, 7, 1))
        vehicle.client_id = client.id
        fake_db = FakeDeliverySession(users=[client], vehicles=[vehicle])
        payload = DeliveryEditIn(client_department="antioquia")

        await svc.edit_delivery(fake_db, vehicle.id, payload)

        assert client.city == "MEDELLÍN"
        assert client.department == "ANTIOQUIA"
