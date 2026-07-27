"""
tests/services/test_pdf_service_date_fallback.py — Decision 4 of the
Historical Order Entry design: `pdf_service.py:71`'s hardcoded
`datetime.now()` becomes `order_data.get("date") or datetime.now()...` —
one line, additive default only.

Covers BOTH halves of that decision:
  1. Parity — all 4 real call sites in the codebase (`orders.py:147`,
     `orders.py:~1745`, `orders.py:~1901`, `add_mock_pdf.py:41`) build
     `order_data` WITHOUT a `"date"` key. Their rendered `"date"` context
     value must stay exactly what it is today: `datetime.now()`, formatted
     `%Y-%m-%d %H:%M` — untouched by this change.
  2. The new capability (RED until `pdf_service.py:71` is edited): when
     `order_data` DOES carry a `"date"` key (as the historical-order
     service, PR2, will pass), the template context must use THAT value
     verbatim instead of overwriting it with `datetime.now()`.

Heavy external dependencies (MinIO upload, WeasyPrint's real HTML->PDF
render) are stubbed so this test is fast and has no network dependency —
only the Jinja template's `render(context)` call is intercepted, which is
the one place `order_data.get("date")` actually reaches.
"""
import re
from datetime import datetime

import pytest

import app.services.pdf_service as pdf_service


class _FakeTemplate:
    def __init__(self):
        self.captured_context = None

    def render(self, context):
        self.captured_context = context
        return "<html><body>fake reception act</body></html>"


@pytest.fixture(autouse=True)
def _stub_heavy_dependencies(monkeypatch):
    """Removes network/CPU-heavy work from every test in this module:
    MinIO bucket check/upload (no live server in the test env) and the
    real WeasyPrint render (irrelevant here — only the context dict passed
    to `template.render()` is under test)."""
    monkeypatch.setattr(pdf_service, "ensure_bucket_exists", lambda: None)
    monkeypatch.setattr(pdf_service.minio_client, "put_object", lambda *a, **kw: None)
    monkeypatch.setattr(
        pdf_service.minio_client, "presigned_get_object", lambda *a, **kw: "http://minio:9000/fake.pdf"
    )


def _base_dicts(order_data_extra: dict) -> tuple:
    order_data = {"id": "test-order", "service_type": "regular", **order_data_extra}
    reception_data = {"mileage_km": 1000, "gas_level": "Lleno"}
    vehicle_data = {"model": "DSR", "plate": "ABC123", "vin": "VIN0001"}
    client_data = {"full_name": "Juan Perez", "email": None, "phone": None}
    return order_data, reception_data, vehicle_data, client_data


_DATE_FORMAT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


@pytest.mark.parametrize(
    "order_data_extra",
    [
        {},  # POST /orders/ (orders.py:112) — no "date" key today
        {"accepted_at": "2026-07-01 10:00", "accepted_phone": "***1234"},  # OTP-accept regen (orders.py:~1710)
        {"bypass_at": "2026-07-01 10:00", "bypass_by_name": "Jefe"},  # OTP-bypass regen (orders.py:~1866)
    ],
)
async def test_existing_call_sites_without_a_date_key_keep_datetime_now_fallback(monkeypatch, order_data_extra):
    fake_template = _FakeTemplate()
    monkeypatch.setattr(pdf_service.jinja_env, "get_template", lambda name: fake_template)

    order_data, reception_data, vehicle_data, client_data = _base_dicts(order_data_extra)
    await pdf_service.generate_and_upload_reception_pdf(order_data, reception_data, vehicle_data, client_data)

    rendered_date = fake_template.captured_context["date"]
    assert _DATE_FORMAT_RE.match(rendered_date)
    # Same minute as "now" — proves it's still the live-timestamp fallback,
    # not some stale/default value.
    assert rendered_date[:16] == datetime.now().strftime("%Y-%m-%d %H:%M")


async def test_a_supplied_date_key_is_used_verbatim_instead_of_datetime_now(monkeypatch):
    fake_template = _FakeTemplate()
    monkeypatch.setattr(pdf_service.jinja_env, "get_template", lambda name: fake_template)

    historical_date = "2025-01-10 09:00"
    order_data, reception_data, vehicle_data, client_data = _base_dicts({"date": historical_date})
    await pdf_service.generate_and_upload_reception_pdf(order_data, reception_data, vehicle_data, client_data)

    assert fake_template.captured_context["date"] == historical_date
