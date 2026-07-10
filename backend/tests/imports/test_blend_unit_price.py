"""
Unit tests for `_blend_unit_price` (`backend/app/services/imports_service.py`)
— Phase 2 of `sdd/backorder-remainder-cost-blending`.

Pure function, no DB: quantity-weighted average of `SparePartItem.unit_price`
against a newly-applied remainder line, rounded to 2 decimals. See
`sdd/backorder-remainder-cost-blending/spec` — "Price Blending on
Confirmation" — for the authoritative formula and scenarios.
"""
from app.services.imports_service import _blend_unit_price


def test_no_prior_price_returns_remainder_price_rounded():
    """Spec: 'No prior price on the item' — direct set, no weighting."""
    assert _blend_unit_price(None, 0, 12.5, 3) == 12.5


def test_prior_qty_zero_returns_remainder_price_rounded_even_if_prior_price_set():
    """`prior_qty_received <= 0` is the same 'nothing to weight against' case
    even if a stray prior_price value exists on the item."""
    assert _blend_unit_price(8.0, 0, 12.5, 3) == 12.5


def test_weighted_average_with_prior_price_and_qty():
    """Spec scenario: prior unit_price=8.00 qty_received=10, remainder
    unit_price=10.00 qty_applied=5 -> (8*10 + 10*5)/15 = 8.666... -> 8.67."""
    assert _blend_unit_price(8.00, 10, 10.00, 5) == 8.67


def test_remainder_price_none_returns_none():
    """Spec: non-invoice / priceless lines never touch unit_price."""
    assert _blend_unit_price(8.0, 10, None, 5) is None


def test_rounding_precision_truncates_to_two_decimals():
    """Spec: 'Rounding precision' — blended value must round to exactly 2
    decimals regardless of how many digits the raw division produces."""
    # (5.0*3 + 7.33*4) / 7 = (15 + 29.32) / 7 = 44.32 / 7 = 6.331428... -> 6.33
    assert _blend_unit_price(5.0, 3, 7.33, 4) == 6.33
