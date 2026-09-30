"""Production runs Python 3.11 (backend/Dockerfile), where a dataclass field
default must be hashable. `types.MappingProxyType` only became hashable in
Python 3.12, so `field(default=<mappingproxy>)` imports fine on a newer local
interpreter but crashes the whole backend on start in production (outage
2026-09-30). Guard every motor dataclass against that default shape.
"""
from dataclasses import MISSING, fields
from types import MappingProxyType

from app.motored.services.motor.tipos import K_FMS_LEGACY, ParametrosMotor


def test_no_field_uses_a_mappingproxy_as_plain_default():
    offenders = [
        f.name for f in fields(ParametrosMotor)
        if f.default is not MISSING and isinstance(f.default, MappingProxyType)
    ]
    assert offenders == []


def test_k_fms_still_defaults_to_the_legacy_preset():
    assert ParametrosMotor().k_fms == K_FMS_LEGACY
