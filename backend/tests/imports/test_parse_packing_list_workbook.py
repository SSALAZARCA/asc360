"""
Unit tests for the pure `parse_packing_list_workbook` helper (and its two
internal building blocks `_locate_packing_list_sheet` / `_extract_packing_list_rows`)
extracted from `reconcile_lot_packing_list` in Phase 2 of the
backorder-packing-list-reconciliation change.

These are pure-function tests: no DB, no mocks needed — only real .xlsx
bytes built with openpyxl (see tests/imports/conftest.py).
"""
import openpyxl
import pytest

from app.services.imports_service import (
    parse_packing_list_workbook,
    _locate_packing_list_sheet,
)
from tests.imports.conftest import (
    build_packing_list_xlsx,
    build_invoice_xlsx,
    build_malformed_xlsx,
)


class TestParsePackingListFormat:
    """Non-invoice Packing List format (no Unit Price/Amount columns)."""

    def test_parses_simple_packing_list(self):
        file_bytes = build_packing_list_xlsx([
            {"part_number": "abc-001", "description": "Brake pad", "qty": 10},
            {"part_number": "abc-002", "description": "Oil filter", "qty": 5},
        ])
        parsed = parse_packing_list_workbook(file_bytes, "E0000573-SP", models_map={})

        assert parsed.error is None
        assert parsed.is_invoice is False
        assert parsed.items == {("ABC-001", None): 10, ("ABC-002", None): 5}
        assert parsed.prices == {}
        assert len(parsed.rows) == 2
        assert parsed.rows[0].part_number == "ABC-001"
        assert parsed.rows[0].description == "Brake pad"
        assert parsed.rows[0].qty == 10

    def test_part_number_is_normalized(self):
        """normalize_part_number: strip + upper + remove spaces."""
        file_bytes = build_packing_list_xlsx([
            {"part_number": " abc 003 ", "description": "x", "qty": 1},
        ])
        parsed = parse_packing_list_workbook(file_bytes, "E0000573-SP", models_map={})
        assert ("ABC003", None) in parsed.items

    def test_duplicate_part_number_rows_are_aggregated_in_items_but_not_in_rows(self):
        """
        items{} aggregates qty per (part_number, model); rows[] keeps one
        entry PER ROW (needed to create one PackingListItem per row, exactly
        like the pre-refactor inline loop did).
        """
        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 4},
            {"part_number": "ABC-001", "description": "Brake pad (2nd box)", "qty": 6},
        ])
        parsed = parse_packing_list_workbook(file_bytes, "E0000573-SP", models_map={})

        assert parsed.items[("ABC-001", None)] == 10
        assert len(parsed.rows) == 2
        assert [r.qty for r in parsed.rows] == [4, 6]

    def test_blank_part_number_row_is_skipped(self):
        file_bytes = build_packing_list_xlsx([
            {"part_number": None, "description": "no part number", "qty": 1},
            {"part_number": "ABC-001", "description": "valid", "qty": 2},
        ])
        parsed = parse_packing_list_workbook(file_bytes, "E0000573-SP", models_map={})
        assert len(parsed.rows) == 1
        assert parsed.rows[0].part_number == "ABC-001"

    def test_non_numeric_qty_defaults_to_zero(self):
        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "x", "qty": "N/A"},
        ])
        parsed = parse_packing_list_workbook(file_bytes, "E0000573-SP", models_map={})
        assert parsed.items[("ABC-001", None)] == 0


class TestParseInvoiceFormat:
    """Invoice format (has Unit Price / Amount → is_invoice=True)."""

    def test_parses_invoice_with_prices(self):
        file_bytes = build_invoice_xlsx([
            {
                "part_number": "abc-001", "model": "XR150", "description": "Brake pad",
                "description_es": "Pastilla de freno", "qty": 10, "unit_price": 4.5, "amount": 45.0,
            },
        ])
        models_map = {"XR150": "XR150"}
        parsed = parse_packing_list_workbook(file_bytes, "E0000573-SP", models_map)

        assert parsed.error is None
        assert parsed.is_invoice is True
        assert parsed.items == {("ABC-001", "XR150"): 10}
        price = parsed.prices[("ABC-001", "XR150")]
        unit_price, amount, desc_en, desc_es, model_val = price
        assert unit_price == 4.5
        assert amount == 45.0
        assert desc_en == "Brake pad"
        assert desc_es == "Pastilla de freno"
        assert model_val == "XR150"

    def test_model_normalization_is_case_insensitive(self):
        """models_map keys are UPPER(canonical); _normalize_model looks up by upper()."""
        file_bytes = build_invoice_xlsx([
            {"part_number": "ABC-001", "model": "xr150l", "description": "x", "qty": 1, "unit_price": 1.0, "amount": 1.0},
        ])
        models_map = {"XR150L": "XR150L"}
        parsed = parse_packing_list_workbook(file_bytes, "E0000573-SP", models_map)
        assert ("ABC-001", "XR150L") in parsed.items

    def test_same_part_different_models_are_separate_keys(self):
        file_bytes = build_invoice_xlsx([
            {"part_number": "ABC-001", "model": "XR150", "description": "x", "qty": 5, "unit_price": 1.0, "amount": 5.0},
            {"part_number": "ABC-001", "model": "CB190", "description": "x", "qty": 3, "unit_price": 1.0, "amount": 3.0},
        ])
        models_map = {"XR150": "XR150", "CB190": "CB190"}
        parsed = parse_packing_list_workbook(file_bytes, "E0000573-SP", models_map)
        assert parsed.items[("ABC-001", "XR150")] == 5
        assert parsed.items[("ABC-001", "CB190")] == 3

    def test_repeated_part_model_pair_accumulates_amount_and_keeps_first_unit_price(self):
        """
        Mirrors the accumulation rule in the original inline loop: repeated
        (part, model) rows sum `amount`, but `unit_price`/description fields
        keep the FIRST non-null value seen (`prev[0] or unit_price`).
        """
        file_bytes = build_invoice_xlsx([
            {"part_number": "ABC-001", "model": "XR150", "description": "First", "qty": 5, "unit_price": 4.0, "amount": 20.0},
            {"part_number": "ABC-001", "model": "XR150", "description": "Second", "qty": 3, "unit_price": 9.0, "amount": 27.0},
        ])
        models_map = {"XR150": "XR150"}
        parsed = parse_packing_list_workbook(file_bytes, "E0000573-SP", models_map)

        assert parsed.items[("ABC-001", "XR150")] == 8
        unit_price, amount, desc_en, desc_es, model_val = parsed.prices[("ABC-001", "XR150")]
        assert unit_price == 4.0  # keeps first, not overwritten by second row
        assert amount == 47.0     # 20 + 27


class TestNoValidHeaders:

    def test_missing_headers_returns_error_and_empty_defaults(self):
        parsed = parse_packing_list_workbook(build_malformed_xlsx(), "E0000573-SP", models_map={})
        assert parsed.error is not None
        assert "cabeceras" in parsed.error.lower()
        assert parsed.is_invoice is False
        assert parsed.rows == []
        assert parsed.items == {}
        assert parsed.prices == {}


class TestLocatePackingListSheet:
    """Direct tests of the sheet/header-location step in isolation."""

    def test_prefers_sheet_matching_lot_identifier(self):
        # CBM column required so _detect_sheet_type recognizes "sp_packing_list"
        # (see build_packing_list_xlsx docstring) — otherwise the multi-sheet
        # preference loop never activates.
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "OTHER-SP"
        ws1.append(["Part #", "Complete Description", "Qty(PCS)", "N.W", "G.W", "CBM"])
        ws1.append(["ABC-999", "wrong sheet", 1, 1.0, 1.0, 0.01])

        ws2 = wb.create_sheet("E0000573-SP")
        ws2.append(["Part #", "Complete Description", "Qty(PCS)", "N.W", "G.W", "CBM"])
        ws2.append(["ABC-001", "right sheet", 7, 1.0, 1.0, 0.01])

        import io as _io
        buf = _io.BytesIO()
        wb.save(buf)

        location = _locate_packing_list_sheet(buf.getvalue(), "E0000573-SP")
        assert location.error is None
        assert location.sheet.title == "E0000573-SP"

    def test_no_matching_sheet_falls_back_to_active(self):
        file_bytes = build_packing_list_xlsx([{"part_number": "ABC-001", "qty": 1}])
        location = _locate_packing_list_sheet(file_bytes, "UNRELATED-PI")
        assert location.error is None
        assert location.sheet is not None
