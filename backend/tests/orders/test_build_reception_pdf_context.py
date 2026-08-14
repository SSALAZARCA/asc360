"""
tests/orders/test_build_reception_pdf_context.py -- unit tests for
`_build_reception_pdf_context`, the helper extracted from `orders.py` to
kill a real triplication: `create_service_order`, `verify_otp` and
`bypass_otp` each built the same 5 PDF-context dicts
(order_data/reception_data/vehicle_data/client_data/tenant_data) fed to
`generate_and_upload_reception_pdf` by hand-copying the same block 3 times.

That triplication is not hypothetical risk -- it already bit once: a real
bug (`client_data["identification"]` reading `client.telegram_id` instead
of `client.identification`) lived in exactly these 3 copies before being
fixed, while the 4th sibling (`download_exit_order_pdf`) had it right the
whole time. These tests exist specifically so that bug class can never
silently reappear in the shared helper.

Pure function, no DB/HTTP involved -- fake objects via `SimpleNamespace`
stand in for the ORM/schema objects (`reception`, `vehicle`, `client`,
`tenant`), since the helper only reads plain attributes off them.
"""
from types import SimpleNamespace

from app.api.v1.orders import _build_reception_pdf_context


def _reception(**overrides):
    base = dict(
        mileage_km=1234.5,
        gas_level="3/4",
        customer_notes="Ruido en el motor",
        warranty_warnings="Ninguna",
        intake_answers=["ok"],
        accessories=["casco"],
        general_observations="Todo en orden",
        damage_photos_urls=["http://example.com/foto.jpg"],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _vehicle(**overrides):
    base = dict(model="XTZ 150", plate="ABC12D", vin="VIN123", engine_number="MOT789", color="Rojo")
    base.update(overrides)
    return SimpleNamespace(**base)


def _client(**overrides):
    base = dict(name="Juan Pérez", identification="123456789", email="juan@example.com", phone="3001234567")
    base.update(overrides)
    return SimpleNamespace(**base)


def _tenant(**overrides):
    base = dict(name="Taller Central", nit="900123456", phone="6011234567", ciudad="Bogotá")
    base.update(overrides)
    return SimpleNamespace(**base)


def test_base_fields_common_to_all_three_callers():
    order_data, reception_data, vehicle_data, client_data, tenant_data = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(),
        vehicle=_vehicle(),
        client=_client(),
        tenant=_tenant(),
    )

    assert order_data == {"id": "order-1", "service_type": "preventive"}
    assert reception_data == {
        "mileage_km": 1234.5,
        "gas_level": "3/4",
        "customer_notes": "Ruido en el motor",
        "warranty_warnings": "Ninguna",
        "intake_answers": ["ok"],
        "accessories": ["casco"],
        "general_observations": "Todo en orden",
        "damage_photos_urls": ["http://example.com/foto.jpg"],
    }
    assert vehicle_data == {
        "model": "XTZ 150",
        "plate": "ABC12D",
        "vin": "VIN123",
        "motor": "MOT789",
        "color": "Rojo",
    }
    assert tenant_data == {
        "name": "Taller Central",
        "nit": "900123456",
        "phone": "6011234567",
        "city": "Bogotá",
    }


def test_client_identification_uses_identification_field_not_telegram_id():
    """Regression guard: the exact bug this extraction must never
    reintroduce. `client_data["identification"]` must read
    `client.identification`, never `client.telegram_id` -- a fake client
    object with a DIFFERENT `telegram_id` proves the helper isn't
    accidentally reading the wrong attribute."""
    client = _client(identification="987654321")
    client.telegram_id = "999999999"  # decoy -- must never leak into client_data

    _, _, _, client_data, _ = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(),
        vehicle=_vehicle(),
        client=client,
        tenant=_tenant(),
    )

    assert client_data["identification"] == "987654321"


def test_client_data_full_name_and_email_phone():
    order_data, reception_data, vehicle_data, client_data, tenant_data = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(),
        vehicle=_vehicle(),
        client=_client(),
        tenant=_tenant(),
    )

    assert client_data == {
        "full_name": "Juan Pérez",
        "identification": "123456789",
        "email": "juan@example.com",
        "phone": "3001234567",
    }


def test_no_client_defaults_to_na_label():
    """Matches `verify_otp`/`bypass_otp`'s default when `order.client` is
    None -- both fall back to "N/A", never "Cliente Pendiente"."""
    _, _, _, client_data, _ = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(),
        vehicle=_vehicle(),
        client=None,
        tenant=_tenant(),
    )

    assert client_data == {
        "full_name": "N/A",
        "identification": "N/A",
        "email": None,
        "phone": None,
    }


def test_no_client_label_override_for_create_service_order():
    """`create_service_order` is the one caller that uses "Cliente
    Pendiente" instead of "N/A" when there's no client yet -- an order can
    be created before a client is linked."""
    _, _, _, client_data, _ = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(),
        vehicle=_vehicle(),
        client=None,
        tenant=_tenant(),
        no_client_label="Cliente Pendiente",
    )

    assert client_data["full_name"] == "Cliente Pendiente"
    assert client_data["identification"] == "N/A"  # override only touches full_name


def test_no_vehicle_defaults():
    _, _, vehicle_data, _, _ = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(),
        vehicle=None,
        client=_client(),
        tenant=_tenant(),
    )

    assert vehicle_data == {
        "model": "Desconocido",
        "plate": "N/A",
        "vin": "N/A",
        "motor": None,
        "color": None,
    }


def test_no_tenant_defaults():
    _, _, _, _, tenant_data = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(),
        vehicle=_vehicle(),
        client=_client(),
        tenant=None,
    )

    assert tenant_data == {"name": "UM Colombia", "nit": "", "phone": "", "city": ""}


def test_no_reception_defaults():
    """Matches `verify_otp`/`bypass_otp`'s `if reception else ...`
    fallbacks for an order whose reception row is somehow missing."""
    order_data, reception_data, _, _, _ = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=None,
        vehicle=_vehicle(),
        client=_client(),
        tenant=_tenant(),
    )

    assert reception_data == {
        "mileage_km": 0,
        "gas_level": "",
        "customer_notes": "",
        "warranty_warnings": "",
        "intake_answers": [],
        "accessories": [],
        "general_observations": None,
        "damage_photos_urls": [],
    }


def test_mileage_km_is_cast_to_float():
    """The ORM's `mileage_km` is a `Numeric` column (arrives as
    `Decimal`), unlike the pydantic schema's already-`float` value used by
    `create_service_order` -- the helper always casts, matching
    `verify_otp`/`bypass_otp`'s original `float(reception.mileage_km)`
    behavior for both sources."""
    from decimal import Decimal

    order_data, reception_data, _, _, _ = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(mileage_km=Decimal("456.00")),
        vehicle=_vehicle(),
        client=_client(),
        tenant=_tenant(),
    )

    assert reception_data["mileage_km"] == 456.0
    assert isinstance(reception_data["mileage_km"], float)


def test_extra_order_fields_merged_for_bypass_without_otp():
    """`create_service_order`'s `if not otp_required` branch and
    `bypass_otp` both add `bypass_at`/`bypass_by_name` to `order_data` --
    but with different values (system label vs. the actual authorizer).
    `extra_order_fields` must merge cleanly without the helper needing to
    know these field names itself."""
    order_data, *_ = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(),
        vehicle=_vehicle(),
        client=_client(),
        tenant=_tenant(),
        extra_order_fields={
            "bypass_at": "2026-08-14 10:00",
            "bypass_by_name": "Sistema (OTP desactivado en Configuración)",
        },
    )

    assert order_data == {
        "id": "order-1",
        "service_type": "preventive",
        "bypass_at": "2026-08-14 10:00",
        "bypass_by_name": "Sistema (OTP desactivado en Configuración)",
    }


def test_extra_order_fields_merged_for_otp_acceptance():
    """`verify_otp` adds `accepted_at`/`accepted_phone` instead --
    different keys entirely from the bypass path, same merge mechanism."""
    order_data, *_ = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(),
        vehicle=_vehicle(),
        client=_client(),
        tenant=_tenant(),
        extra_order_fields={"accepted_at": "2026-08-14 10:05", "accepted_phone": "***1234"},
    )

    assert order_data == {
        "id": "order-1",
        "service_type": "preventive",
        "accepted_at": "2026-08-14 10:05",
        "accepted_phone": "***1234",
    }


def test_no_extra_order_fields_leaves_base_dict_untouched():
    """`create_service_order`'s `if otp_required` branch (normal OTP flow,
    no bypass) never adds extra keys -- omitting `extra_order_fields`
    entirely must not blow up and must not add anything."""
    order_data, *_ = _build_reception_pdf_context(
        order_id="order-1",
        service_type="preventive",
        reception=_reception(),
        vehicle=_vehicle(),
        client=_client(),
        tenant=_tenant(),
    )

    assert order_data == {"id": "order-1", "service_type": "preventive"}
