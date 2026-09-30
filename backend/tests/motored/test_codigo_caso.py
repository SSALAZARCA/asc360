"""Business-style detractor case code: DET-<year opened>-<numero, 6 digits>."""
from datetime import datetime

import pytest

from app.motored.services.caso_detractor import codigo_caso, parse_codigo_caso


def test_code_uses_opening_year_and_six_digit_padding():
    assert codigo_caso(3, datetime(2026, 9, 30, 10)) == "DET-2026-000003"


def test_code_keeps_numbers_wider_than_padding():
    assert codigo_caso(1234567, datetime(2027, 1, 1)) == "DET-2027-1234567"


@pytest.mark.parametrize("text", ["DET-2026-000003", "det-2026-000003", "  Det-2026-3  ", "DET - 2026 - 000003"])
def test_parse_accepts_case_insensitive_code_with_spaces(text):
    assert parse_codigo_caso(text) == (2026, 3)


@pytest.mark.parametrize("text", ["123", "DET-26-000003", "DET-2026-", "ABC-2026-000003", "Ana Perez", "", None])
def test_parse_rejects_everything_else(text):
    assert parse_codigo_caso(text) is None
