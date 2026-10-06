"""Timestamps leave the API as UTC with an explicit offset.

The Motored models store naive UTC (`datetime.utcnow`), which pydantic and
FastAPI serialize without an offset; browsers then read it as local time and
show the wrong hour. Every displayed instant goes through `a_utc_iso` (hand
built dicts) or the `UtcDatetime` annotated type (pydantic schemas).
"""
from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import PlainSerializer


def a_utc_iso(valor: Optional[datetime]) -> Optional[str]:
    """Naive values are taken as UTC; aware ones are converted to UTC."""
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc).isoformat()


UtcDatetime = Annotated[
    datetime,
    PlainSerializer(a_utc_iso, return_type=Optional[str], when_used="json"),
]
