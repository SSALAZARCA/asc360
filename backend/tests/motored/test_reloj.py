"""
Motored Ventas Perdidas — Bot "Lore", Phase 2 (sdd/motored-ventas-perdidas-bot,
task 2.3/2.4; design D4) — `services/reloj.py::hoy_bogota`.

"Today" for the bot's own logic (today-only edit/cancel window) is computed
with a FIXED UTC-5 offset, never `tzdata`: Colombia has had no DST since
1993, so a fixed offset is correct and needs no timezone database in the
slim container image (design D4, explicit rationale).

`ahora` is an optional injectable parameter (defaults to
`datetime.now(timezone.utc)`), same convention as
`services/storage.py::subir_archivo`'s `ahora` param — parametrizable so
tests are deterministic without mocking the global clock.
"""
from datetime import date, datetime, timezone

from app.motored.services import reloj


def test_hoy_bogota_usa_fecha_bogota_no_la_fecha_utc_cerca_de_medianoche():
    # 2026-09-25 03:30:00 UTC == 2026-09-24 22:30:00 Bogota (UTC-5): la
    # fecha UTC ya cruzó al día siguiente, pero Bogota sigue en el día
    # anterior -- exactamente el caso que un `date.today()` ingenuo en UTC
    # calcularía mal (design D4's flagged pending inconsistency).
    ahora_utc = datetime(2026, 9, 25, 3, 30, 0, tzinfo=timezone.utc)

    assert reloj.hoy_bogota(ahora_utc) == date(2026, 9, 24)
    assert ahora_utc.date() == date(2026, 9, 25)  # confirma que difieren


def test_hoy_bogota_sin_argumento_usa_el_reloj_real():
    resultado = reloj.hoy_bogota()

    assert isinstance(resultado, date)
