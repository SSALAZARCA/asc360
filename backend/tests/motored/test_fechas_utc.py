"""Every timestamp leaves the API as UTC with an explicit offset."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel

from app.motored.services.fechas_utc import UtcDatetime, a_utc_iso

BOGOTA = timezone(timedelta(hours=-5))


def test_naive_is_taken_as_utc():
    assert a_utc_iso(datetime(2026, 10, 5, 12, 43)) == "2026-10-05T12:43:00+00:00"


def test_aware_bogota_is_converted_to_utc():
    assert a_utc_iso(datetime(2026, 10, 5, 7, 43, tzinfo=BOGOTA)) == "2026-10-05T12:43:00+00:00"


def test_none_stays_none():
    assert a_utc_iso(None) is None


class _Esquema(BaseModel):
    a: UtcDatetime
    b: Optional[UtcDatetime] = None


def test_schema_json_round_trip_carries_the_offset():
    modelo = _Esquema(a=datetime(2026, 10, 5, 12, 43))
    assert modelo.model_dump(mode="json") == {"a": "2026-10-05T12:43:00+00:00", "b": None}
    assert "+00:00" in modelo.model_dump_json()
    # Python-mode dumps keep the datetime so internal callers are unaffected.
    assert modelo.model_dump()["a"] == datetime(2026, 10, 5, 12, 43)


def test_corrida_and_pedido_schemas_emit_utc_offsets():
    from app.motored.schemas.corrida import EnvioInfo, UltimoEvento

    evento = UltimoEvento(evento="ENVIADO", creado_en=datetime(2026, 10, 6, 0, 30))
    assert evento.model_dump(mode="json")["creado_en"] == "2026-10-06T00:30:00+00:00"
    envio = EnvioInfo.model_validate({
        "numero_orden": "1", "fecha_envio": "2026-10-05",
        "enviado_en": datetime(2026, 10, 5, 7, 43, tzinfo=BOGOTA),
    })
    dumped = envio.model_dump(mode="json")
    assert dumped["enviado_en"] == "2026-10-05T12:43:00+00:00"
    assert dumped["fecha_envio"] == "2026-10-05"  # pure dates are untouched
