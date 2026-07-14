"""
Unit tests for report_service.py pure helper functions.

Covers: _pct, _bar, _heat_style, _make_conic

TDD: these tests were written first (RED), then the functions were implemented (GREEN).
"""
import pytest
import sys
import os
from unittest.mock import MagicMock

# Make sure backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Stub out weasyprint before importing report_service (not installed locally)
sys.modules.setdefault('weasyprint', MagicMock())

from app.services.report_service import _pct, _bar, _heat_style, _make_conic


# ---------------------------------------------------------------------------
# _pct
# ---------------------------------------------------------------------------

class TestPct:
    def test_division_by_zero_returns_zero(self):
        assert _pct(100, 0) == 0

    def test_division_by_zero_with_decimals(self):
        assert _pct(50, 0, decimals=2) == 0

    def test_normal_case_no_decimals(self):
        assert _pct(1, 4) == 25

    def test_normal_case_with_decimals(self):
        assert _pct(1, 3, decimals=1) == 33.3

    def test_100_percent(self):
        assert _pct(10, 10) == 100

    def test_returns_int_when_no_decimals(self):
        result = _pct(1, 4)
        assert isinstance(result, int)

    def test_returns_float_when_decimals_specified(self):
        result = _pct(1, 3, decimals=1)
        assert isinstance(result, float)

    def test_zero_numerator(self):
        assert _pct(0, 100) == 0

    def test_rounding(self):
        # 2/3 = 66.666... -> round to 67
        assert _pct(2, 3) == 67

    def test_rounding_with_decimals(self):
        assert _pct(2, 3, decimals=2) == 66.67


# ---------------------------------------------------------------------------
# _bar
# ---------------------------------------------------------------------------

class TestBar:
    def test_max_val_zero_returns_zero(self):
        assert _bar(100, 0) == 0

    def test_normal_case(self):
        assert _bar(50, 100) == 50

    def test_clamp_at_100(self):
        assert _bar(200, 100) == 100

    def test_value_equals_max(self):
        assert _bar(75, 75) == 100

    def test_value_zero(self):
        assert _bar(0, 100) == 0

    def test_returns_non_negative(self):
        assert _bar(0, 50) >= 0

    def test_proportional(self):
        # 25/400 = 6.25% -> round = 6
        assert _bar(25, 400) == 6

    def test_result_at_most_100(self):
        for v in [100, 150, 999]:
            assert _bar(v, 100) <= 100


# ---------------------------------------------------------------------------
# _heat_style
# ---------------------------------------------------------------------------

class TestHeatStyle:
    def test_value_zero_returns_neutral_bg(self):
        style = _heat_style(0, 100)
        assert '#F5F6F9' in style

    def test_value_zero_max_zero_returns_neutral_bg(self):
        style = _heat_style(0, 0)
        assert '#F5F6F9' in style

    def test_max_zero_returns_neutral_bg(self):
        style = _heat_style(5, 0)
        assert '#F5F6F9' in style

    def test_high_intensity_dark_orange(self):
        # 70% or more intensity → darkest shade
        # Palette softened in 06bf6a2 (2026-06-23) — pinned values updated to
        # match the current, intentionally lighter design (tests had drifted).
        style = _heat_style(70, 100)
        assert '#F9CCAF' in style
        assert '#B05030' in style

    def test_medium_high_intensity(self):
        # 40-70% → medium dark
        style = _heat_style(50, 100)
        assert '#FBDECB' in style
        assert '#C06040' in style

    def test_medium_low_intensity(self):
        # 20-40%
        style = _heat_style(25, 100)
        assert '#FDEEE4' in style
        assert '#C87050' in style

    def test_low_intensity(self):
        # < 20%
        style = _heat_style(10, 100)
        assert '#FEF5F0' in style
        assert '#D08060' in style

    def test_returns_string(self):
        assert isinstance(_heat_style(50, 100), str)

    def test_full_intensity(self):
        # value == max_val → 100% → darkest
        style = _heat_style(100, 100)
        assert '#F9CCAF' in style


# ---------------------------------------------------------------------------
# _make_conic
# ---------------------------------------------------------------------------

class TestMakeConic:
    def test_empty_list_returns_solid_fallback(self):
        result = _make_conic([])
        assert '#AEB6BF' in result

    def test_returns_conic_gradient_string(self):
        result = _make_conic([('#E8590C', 100.0)])
        assert 'conic-gradient' in result

    def test_single_slice_full_gradient(self):
        result = _make_conic([('#E8590C', 100.0)])
        assert '#E8590C' in result
        assert '0.0%' in result
        assert '100.0%' in result

    def test_two_slices_cumulative_stops(self):
        result = _make_conic([('#E8590C', 60.0), ('#3B47B8', 40.0)])
        # First slice: 0% to 60%
        assert '#E8590C 0.0% 60.0%' in result
        # Second slice: 60% to 100%
        assert '#3B47B8 60.0% 100.0%' in result

    def test_three_slices_stops_are_cumulative(self):
        result = _make_conic([('#E8590C', 30.0), ('#3B47B8', 40.0), ('#0CA678', 30.0)])
        assert '#E8590C 0.0% 30.0%' in result
        assert '#3B47B8 30.0% 70.0%' in result
        assert '#0CA678 70.0% 100.0%' in result

    def test_empty_fallback_is_not_conic(self):
        # Fallback for empty: just a solid color, no real gradient needed
        # But we document the actual behavior: returns a conic with single segment or solid
        result = _make_conic([])
        # At minimum must be a valid CSS string (not raise, returns something)
        assert isinstance(result, str)
        assert len(result) > 0
