"""Colombian public holidays and working-day counting (pure, no database).

Three families (Ley 51 de 1983, "ley Emiliani"):
- fixed dates that never move: Jan 1, May 1, Jul 20, Aug 7, Dec 8, Dec 25;
- dates moved to the next Monday (a Monday stays): Jan 6, Mar 19, Jun 29, Aug 15, Oct 12, Nov 1, Nov 11;
- Easter-based: Holy Thursday (-3) and Good Friday (-2) stay; Ascension (+39), Corpus Christi (+60)
  and Sacred Heart (+68) move to the following Monday (+43, +64, +71 from Easter Sunday).
"""
import datetime
from functools import lru_cache
from typing import FrozenSet

_FIJOS = ((1, 1), (5, 1), (7, 20), (8, 7), (12, 8), (12, 25))
_TRASLADABLES = ((1, 6), (3, 19), (6, 29), (8, 15), (10, 12), (11, 1), (11, 11))
_DESDE_PASCUA_MOVIDOS = (39, 60, 68)
_DESDE_PASCUA_FIJOS = (-3, -2)


def _pascua(anio: int) -> datetime.date:
    """Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * ell) // 433
    mes = (h + ell - 7 * m + 90) // 25
    dia = (h + ell - 7 * m + 33 * mes + 19) % 32
    return datetime.date(anio, mes, dia)


def _al_lunes(dia: datetime.date) -> datetime.date:
    """The same day when it is a Monday, else the next Monday."""
    return dia + datetime.timedelta(days=(7 - dia.weekday()) % 7)


@lru_cache(maxsize=None)
def _festivos(anio: int) -> FrozenSet[datetime.date]:
    pascua = _pascua(anio)
    dias = {datetime.date(anio, m, d) for m, d in _FIJOS}
    dias |= {_al_lunes(datetime.date(anio, m, d)) for m, d in _TRASLADABLES}
    dias |= {pascua + datetime.timedelta(days=n) for n in _DESDE_PASCUA_FIJOS}
    dias |= {_al_lunes(pascua + datetime.timedelta(days=n)) for n in _DESDE_PASCUA_MOVIDOS}
    return frozenset(dias)


def festivos(anio: int) -> set:
    """The public holidays of `anio` as a set of dates."""
    return set(_festivos(anio))


def dias_habiles(desde: datetime.date, hasta: datetime.date) -> int:
    """Working days between `desde` and `hasta`, both included: Monday to Saturday minus holidays.
    0 when the range is empty."""
    cuenta, dia = 0, desde
    while dia <= hasta:
        if dia.weekday() != 6 and dia not in _festivos(dia.year):
            cuenta += 1
        dia += datetime.timedelta(days=1)
    return cuenta
