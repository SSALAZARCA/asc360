"""
Inventory counts, pair access secrets (odd/motored-conteos-inventario,
WU5; design ADR-7, §8.1): the link slug, the 6-digit code and its hash.
"""
import re
import uuid

import pytest

from app.config import settings
from app.motored.services.conteos import acceso

CONTEO = uuid.UUID("11111111-2222-3333-4444-555555555555")


def test_the_slug_is_url_safe_and_fits_the_column():
    slug = acceso.nuevo_slug()
    assert re.fullmatch(r"[A-Za-z0-9_-]{16}", slug)
    assert len(slug) == acceso.LARGO_SLUG


def test_the_slug_carries_96_bits_and_never_repeats():
    assert acceso.BITS_SLUG == 96
    assert len({acceso.nuevo_slug() for _ in range(2000)}) == 2000


def test_the_code_has_six_digits_with_leading_zeros_allowed(monkeypatch):
    assert re.fullmatch(r"[0-9]{6}", acceso.nuevo_codigo())
    monkeypatch.setattr(acceso.secrets, "randbelow", lambda _n: 42)
    assert acceso.nuevo_codigo() == "000042"


def test_the_hash_is_a_keyed_hmac_bound_to_the_conteo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "k1")
    hash_1 = acceso.hash_codigo(CONTEO, "123456")
    otro_conteo = acceso.hash_codigo(uuid.uuid4(), "123456")
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "k2")
    otra_clave = acceso.hash_codigo(CONTEO, "123456")

    assert re.fullmatch(r"[0-9a-f]{64}", hash_1)
    assert "123456" not in hash_1
    assert len({hash_1, otro_conteo, otra_clave}) == 3


def test_verify_accepts_the_right_code_only():
    guardado = acceso.hash_codigo(CONTEO, "012345")

    assert acceso.verificar_codigo(CONTEO, "012345", guardado) is True
    assert acceso.verificar_codigo(CONTEO, " 012345 ", guardado) is True
    assert acceso.verificar_codigo(CONTEO, "012346", guardado) is False
    assert acceso.verificar_codigo(uuid.uuid4(), "012345", guardado) is False


@pytest.mark.parametrize("codigo", ["", "12345", "1234567", "abcdef", None])
def test_verify_refuses_malformed_codes(codigo):
    guardado = acceso.hash_codigo(CONTEO, "123456")
    assert acceso.verificar_codigo(CONTEO, codigo, guardado) is False


def test_verify_refuses_when_no_code_is_stored():
    assert acceso.verificar_codigo(CONTEO, "123456", None) is False


def test_verify_uses_a_constant_time_comparison(monkeypatch):
    llamadas = []

    def espia(a, b):
        llamadas.append((a, b))
        return a == b

    monkeypatch.setattr(acceso.hmac, "compare_digest", espia)
    acceso.verificar_codigo(CONTEO, "123456", "x" * 64)
    assert len(llamadas) == 1
