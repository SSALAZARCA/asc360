"""Colombian public holidays (Ley 51 de 1983, "ley Emiliani") and the Mon-Sat working-day count."""
import datetime

import pytest

from app.motored.services import festivos_colombia as f

D = datetime.date


def _fechas(*pares):
    return {D(anio, mes, dia) for anio, mes, dia in pares}


FESTIVOS_2026 = _fechas(
    (2026, 1, 1), (2026, 1, 12), (2026, 3, 23), (2026, 4, 2), (2026, 4, 3), (2026, 5, 1), (2026, 5, 18),
    (2026, 6, 8), (2026, 6, 15), (2026, 6, 29), (2026, 7, 20), (2026, 8, 7), (2026, 8, 17), (2026, 10, 12),
    (2026, 11, 2), (2026, 11, 16), (2026, 12, 8), (2026, 12, 25))
FESTIVOS_2027 = _fechas(
    (2027, 1, 1), (2027, 1, 11), (2027, 3, 22), (2027, 3, 25), (2027, 3, 26), (2027, 5, 1), (2027, 5, 10),
    (2027, 5, 31), (2027, 6, 7), (2027, 7, 5), (2027, 7, 20), (2027, 8, 7), (2027, 8, 16), (2027, 10, 18),
    (2027, 11, 1), (2027, 11, 15), (2027, 12, 8), (2027, 12, 25))


@pytest.mark.parametrize("anio,esperados", [(2026, FESTIVOS_2026), (2027, FESTIVOS_2027)])
def test_the_year_has_the_eighteen_known_holidays(anio, esperados):
    assert f.festivos(anio) == esperados


def test_a_holiday_that_falls_on_monday_is_not_moved():
    assert D(2026, 6, 29) in f.festivos(2026) and D(2026, 10, 12) in f.festivos(2026)
    assert D(2026, 6, 30) not in f.festivos(2026)


def test_good_friday_and_holy_thursday_are_never_moved():
    assert {D(2026, 4, 2), D(2026, 4, 3)} <= f.festivos(2026)


def test_working_days_count_monday_to_saturday_without_holidays():
    # Thu Oct 8 .. Sat Oct 31 2026: 3 + 5 (Mon Oct 12 is a holiday) + 6 + 6
    assert f.dias_habiles(D(2026, 10, 8), D(2026, 10, 31)) == 20


def test_sundays_never_count_and_the_range_is_inclusive():
    assert f.dias_habiles(D(2026, 10, 4), D(2026, 10, 4)) == 0  # a Sunday
    assert f.dias_habiles(D(2026, 10, 3), D(2026, 10, 3)) == 1  # a Saturday


def test_an_empty_range_has_no_working_days():
    assert f.dias_habiles(D(2026, 10, 9), D(2026, 10, 8)) == 0


def test_a_range_crossing_years_uses_each_years_holidays():
    # Wed Dec 23 2026 .. Sat Jan 2 2027: all but Sun 27 and the holidays Dec 25 and Jan 1
    assert f.dias_habiles(D(2026, 12, 23), D(2027, 1, 2)) == 8
