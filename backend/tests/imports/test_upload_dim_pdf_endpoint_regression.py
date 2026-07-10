"""
Approval/regression tests for `upload_dim_pdf`
(`POST /api/v1/imports/moto-units/dim`, `imports.py:2848`), written BEFORE
its Phase 4 extraction (`sdd/imports-oversized-functions-refactor-tier2`).

Covers the endpoint's behavior exactly as it exists today:
  - Non-`.pdf` filenames 422 before parsing.
  - `dim_parser_service.parse_dim_pdf` raising `ValueError` 422s with its
    message.
  - `storage_service.upload_bytes` raising any `Exception` 500s with a
    wrapped message.
  - VIN matching: exact match against `ShipmentMotoUnit.vin_number` first,
    then a strip/upper-normalised fallback.
  - Unmatched VINs are counted and listed verbatim (not normalised) in
    `vins_not_found`.
  - Matched units get `no_acep`/`f_acep`/`no_lev`/`f_lev`/
    `certificado_generado`/`certificado_fecha`/`dim_pdf_object_name` set;
    `f_acep`/`f_lev` are parsed from `YYYY-MM-DD` strings via the endpoint's
    local `_parse_date` helper, which silently returns `None` on malformed
    input (a pre-existing "swallow" this phase adds logging to, without
    changing the returned value).

Run FIRST against pre-refactor `imports.py` to capture baseline behavior,
then again after Phase 4's extraction (hoisting `_parse_dim_date` to module
scope, extracting `_find_moto_unit_by_vin`/`_apply_dim_match_to_unit`) to
confirm byte-for-byte identical responses/status codes/error strings (spec's
Behavior-Preserving Refactor requirement).
"""
from datetime import date

from app.api.v1 import imports as imports_module
from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor, make_moto_unit


def _dim_file():
    return {"file": ("dim.pdf", b"%PDF-1.4 fake bytes", "application/pdf")}


def _patch_upload_ok(monkeypatch):
    async def _fake_upload_bytes(bucket, name, data, content_type=None):
        return None

    monkeypatch.setattr(imports_module.storage_service, "upload_bytes", _fake_upload_bytes)


def _dim_vehicle(vin, no_acep="12345", f_acep="2024-01-15", no_lev="67890", f_lev="2024-02-20"):
    return {"vin": vin, "no_acep": no_acep, "f_acep": f_acep, "no_lev": no_lev, "f_lev": f_lev}


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------

def test_non_pdf_filename_422_before_parsing(monkeypatch):
    called = {"parse": False}
    monkeypatch.setattr(
        imports_module.dim_parser_service,
        "parse_dim_pdf",
        lambda file_bytes: called.__setitem__("parse", True) or [],
    )
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.post(
            "/api/v1/imports/moto-units/dim",
            files={"file": ("dim.xlsx", b"not a pdf", "application/octet-stream")},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Solo se aceptan archivos .pdf"}
    assert called["parse"] is False


# ---------------------------------------------------------------------------
# Parse errors
# ---------------------------------------------------------------------------

def test_parse_dim_pdf_value_error_422(monkeypatch):
    def _raise(file_bytes):
        raise ValueError("El PDF no contiene texto digital (escaneado)")

    monkeypatch.setattr(imports_module.dim_parser_service, "parse_dim_pdf", _raise)
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.post("/api/v1/imports/moto-units/dim", files=_dim_file())

    assert response.status_code == 422
    assert response.json() == {"detail": "El PDF no contiene texto digital (escaneado)"}


# ---------------------------------------------------------------------------
# Storage errors
# ---------------------------------------------------------------------------

def test_storage_upload_error_500(monkeypatch):
    monkeypatch.setattr(
        imports_module.dim_parser_service,
        "parse_dim_pdf",
        lambda file_bytes: [_dim_vehicle("VIN0001")],
    )

    async def _raise(bucket, name, data, content_type=None):
        raise RuntimeError("bucket unreachable")

    monkeypatch.setattr(imports_module.storage_service, "upload_bytes", _raise)
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.post("/api/v1/imports/moto-units/dim", files=_dim_file())

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Error al guardar el PDF en almacenamiento: bucket unreachable"
    }


# ---------------------------------------------------------------------------
# VIN matching
# ---------------------------------------------------------------------------

def test_exact_vin_match_updates_unit_and_counts_matched(monkeypatch):
    unit = make_moto_unit(vin_number="VIN0001EXACT")
    monkeypatch.setattr(
        imports_module.dim_parser_service,
        "parse_dim_pdf",
        lambda file_bytes: [_dim_vehicle("VIN0001EXACT")],
    )
    _patch_upload_ok(monkeypatch)
    # Exact match query returns the unit directly — no normalized fallback query issued.
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.post("/api/v1/imports/moto-units/dim", files=_dim_file())

    assert response.status_code == 200
    body = response.json()
    assert body["matched"] == 1
    assert body["unmatched"] == 0
    assert body["total_in_dim"] == 1
    assert body["vins_not_found"] == []

    assert unit.no_acep == "12345"
    assert unit.f_acep == date(2024, 1, 15)
    assert unit.no_lev == "67890"
    assert unit.f_lev == date(2024, 2, 20)
    assert unit.certificado_generado is True
    assert unit.certificado_fecha is not None
    assert unit.dim_pdf_object_name is not None


def test_normalized_vin_match_falls_back_after_exact_miss(monkeypatch):
    """Raw VIN has stray whitespace/lowercase; exact match misses, then the
    strip/upper-normalised fallback query matches the stored VIN."""
    unit = make_moto_unit(vin_number="VIN0002NORM")
    monkeypatch.setattr(
        imports_module.dim_parser_service,
        "parse_dim_pdf",
        lambda file_bytes: [_dim_vehicle("  vin0002norm  ")],
    )
    _patch_upload_ok(monkeypatch)
    # First execute() (exact match) returns no rows; second (normalized) returns the unit.
    fake_db = FakeAsyncSession(execute_queue=[[], [unit]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.post("/api/v1/imports/moto-units/dim", files=_dim_file())

    assert response.status_code == 200
    body = response.json()
    assert body["matched"] == 1
    assert body["unmatched"] == 0
    assert unit.no_acep == "12345"


def test_unmatched_vin_counted_and_listed_verbatim(monkeypatch):
    monkeypatch.setattr(
        imports_module.dim_parser_service,
        "parse_dim_pdf",
        lambda file_bytes: [_dim_vehicle("  VINGHOST  ")],
    )
    _patch_upload_ok(monkeypatch)
    # Neither exact nor normalized query finds a match.
    fake_db = FakeAsyncSession(execute_queue=[[], []])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.post("/api/v1/imports/moto-units/dim", files=_dim_file())

    assert response.status_code == 200
    body = response.json()
    assert body["matched"] == 0
    assert body["unmatched"] == 1
    assert body["total_in_dim"] == 1
    # Verbatim raw VIN (not normalised) is what gets listed.
    assert body["vins_not_found"] == ["  VINGHOST  "]


def test_malformed_dim_date_string_silently_parses_to_none(monkeypatch):
    """`_parse_date`/`_parse_dim_date` must keep returning `None` on a
    malformed date string (no behavior change) — this phase only adds
    logging around the existing `except Exception: return None`."""
    unit = make_moto_unit(vin_number="VIN0003BADDATE")
    monkeypatch.setattr(
        imports_module.dim_parser_service,
        "parse_dim_pdf",
        lambda file_bytes: [_dim_vehicle("VIN0003BADDATE", f_acep="not-a-date", f_lev="")],
    )
    _patch_upload_ok(monkeypatch)
    fake_db = FakeAsyncSession(execute_queue=[[unit]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.post("/api/v1/imports/moto-units/dim", files=_dim_file())

    assert response.status_code == 200
    assert unit.f_acep is None
    assert unit.f_lev is None
