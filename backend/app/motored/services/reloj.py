"""
Motored Ventas Perdidas — Bot "Lore", Phase 2 (sdd/motored-ventas-perdidas-bot,
task 2.3; design D4) — `hoy_bogota`.

"Today" for the bot's own logic (the today-only edit/cancel window on
`demanda_perdida_bot_linea`, Phase 6) is computed with a FIXED UTC-5 offset,
never `tzdata`: Colombia has had no DST since 1993, so a fixed offset is
correct and needs no timezone database in the slim container image.

Existing `date.today()` call sites elsewhere in Motored (`cargas.py:153`,
`orquestador.py:479/581`, `parametros.py:49`) are UTC in the container and
are DELIBERATELY NOT touched here -- design D4 logs that as a pending
inconsistency, out of scope for this phase.

`ahora` is optional (default `datetime.now(timezone.utc)`) so tests can be
deterministic without mocking the global clock -- same convention as
`services/storage.py::subir_archivo`'s `ahora` parameter.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

BOGOTA_OFFSET = timezone(timedelta(hours=-5))


def hoy_bogota(ahora: Optional[datetime] = None) -> date:
    momento = ahora if ahora is not None else datetime.now(timezone.utc)
    return momento.astimezone(BOGOTA_OFFSET).date()
