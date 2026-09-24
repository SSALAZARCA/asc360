"""
Phase 4 "Approval service + Usuarios UI" (sdd/motored-ventas-perdidas-bot,
task 4.4; design D5 "Telegram linking") — unit coverage for
`services/vinculacion.py`: one-time-code generation (web side, this Phase)
and consumption (a pure service function -- its only caller, the bot's own
`POST /admin/vincular`, is Fase 5's task 5.9, not wired to any endpoint
yet in this Phase).

Same `FakeAsyncSession` convention as the rest of `tests/motored/`.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.motored.models.usuario import Usuario
from app.motored.services.vinculacion import (
    CodigoVinculacionInvalidoError,
    consumir_codigo_vinculacion,
    generar_codigo_vinculacion,
)
from tests.motored.conftest import FakeAsyncSession


def _admin(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Ana Admin", email="ana@motoredcolombia.com.co",
        hashed_password="hash", role="ADMIN", activo=True, status="approved",
        telegram_id=None,
    )
    base.update(overrides)
    return Usuario(**base)


async def test_generar_codigo_vinculacion_stores_only_the_hash_never_the_raw_code():
    usuario = _admin()
    db = FakeAsyncSession(execute_queue=[])

    codigo = await generar_codigo_vinculacion(db, usuario)

    assert len(codigo) == 8
    assert usuario.codigo_vinculacion_hash == hashlib.sha256(codigo.encode("utf-8")).hexdigest()
    assert usuario.codigo_vinculacion_hash != codigo


def test_generar_codigo_vinculacion_alphabet_excludes_ambiguous_characters():
    """0/O/1/I must never appear -- design D5's exact stated alphabet."""
    from app.motored.services.vinculacion import _ALFABETO

    for ambiguo in "0O1I":
        assert ambiguo not in _ALFABETO


async def test_generar_codigo_vinculacion_sets_a_ten_minute_expiry():
    usuario = _admin()
    db = FakeAsyncSession(execute_queue=[])
    antes = datetime.now(timezone.utc)

    await generar_codigo_vinculacion(db, usuario)

    despues = datetime.now(timezone.utc)
    assert antes + timedelta(minutes=9, seconds=55) <= usuario.codigo_vinculacion_expira
    assert usuario.codigo_vinculacion_expira <= despues + timedelta(minutes=10, seconds=5)


async def test_consumir_codigo_vinculacion_links_telegram_id_and_clears_the_code():
    usuario = _admin()
    codigo = "AB23CD45"
    usuario.codigo_vinculacion_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
    usuario.codigo_vinculacion_expira = datetime.now(timezone.utc) + timedelta(minutes=5)
    # [claim UPDATE ... RETURNING id, select(Usuario) re-fetch after claim]
    # -- post-review finding #2, same two-step atomic-claim shape as
    # `services/solicitudes.py::resolver_solicitud`.
    db = FakeAsyncSession(execute_queue=[[usuario.id], [usuario]])

    resultado = await consumir_codigo_vinculacion(db, codigo, telegram_id=987654321)

    assert resultado is usuario
    assert usuario.telegram_id == 987654321
    assert usuario.codigo_vinculacion_hash is None
    assert usuario.codigo_vinculacion_expira is None


async def test_consumir_codigo_vinculacion_wrong_code_raises_invalid():
    db = FakeAsyncSession(execute_queue=[[]])  # claim UPDATE affects 0 rows

    with pytest.raises(CodigoVinculacionInvalidoError):
        await consumir_codigo_vinculacion(db, "WRONGCODE", telegram_id=1)


async def test_consumir_codigo_vinculacion_expired_code_raises_invalid_and_is_not_consumed():
    """Post-review (finding #2): expiry is now enforced INSIDE the atomic
    claim's own WHERE clause (`codigo_vinculacion_expira > :ahora`), so an
    expired code's claim UPDATE affects 0 rows and the row is never
    touched at all -- simpler and strictly more correct than the old
    SELECT-then-check-expiry shape, which read the row before rejecting
    it."""
    usuario = _admin()
    codigo = "ZZ99YY88"
    usuario.codigo_vinculacion_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
    usuario.codigo_vinculacion_expira = datetime.now(timezone.utc) - timedelta(seconds=1)
    db = FakeAsyncSession(execute_queue=[[]])  # claim UPDATE affects 0 rows (expired)

    with pytest.raises(CodigoVinculacionInvalidoError):
        await consumir_codigo_vinculacion(db, codigo, telegram_id=1)

    # An expired code must not still link the account.
    assert usuario.telegram_id is None
    assert usuario.codigo_vinculacion_hash is not None


async def test_consumir_codigo_vinculacion_is_single_use():
    """A second consumption attempt with the SAME raw code must fail --
    the first call already cleared the hash, so the second's own claim
    UPDATE affects 0 rows."""
    usuario = _admin()
    codigo = "QQ11WW22"
    usuario.codigo_vinculacion_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
    usuario.codigo_vinculacion_expira = datetime.now(timezone.utc) + timedelta(minutes=5)
    db1 = FakeAsyncSession(execute_queue=[[usuario.id], [usuario]])

    await consumir_codigo_vinculacion(db1, codigo, telegram_id=42)
    assert usuario.codigo_vinculacion_hash is None

    db2 = FakeAsyncSession(execute_queue=[[]])  # hash no longer matches anything
    with pytest.raises(CodigoVinculacionInvalidoError):
        await consumir_codigo_vinculacion(db2, codigo, telegram_id=42)


async def test_consumir_codigo_vinculacion_race_second_concurrent_attempt_does_not_overwrite_first():
    """WARNING (post-Phase-4 review, finding #2): unlike `resolver_solicitud`
    in this same Phase (and `_reclamar_anulacion` in Phase 3),
    `consumir_codigo_vinculacion` used to do a plain SELECT+mutate, not an
    atomic claim -- two different Telegram accounts presenting the SAME
    still-valid code near-simultaneously could both pass the
    SELECT+expiry check before either committed, and the second write
    could silently overwrite the first's `telegram_id`. Same
    two-separate-`FakeAsyncSession`s race-simulation shape as
    `test_solicitudes.py::test_resolver_solicitud_race_second_call_raises_
    solicitud_ya_resuelta`: the second transaction's own atomic claim
    UPDATE finds 0 rows, because the hash is already NULL by the time its
    claim runs."""
    usuario = _admin()
    codigo = "RC77TT66"
    usuario.codigo_vinculacion_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
    usuario.codigo_vinculacion_expira = datetime.now(timezone.utc) + timedelta(minutes=5)

    db1 = FakeAsyncSession(execute_queue=[[usuario.id], [usuario]])
    await consumir_codigo_vinculacion(db1, codigo, telegram_id=111)
    assert usuario.telegram_id == 111
    assert usuario.codigo_vinculacion_hash is None

    db2 = FakeAsyncSession(execute_queue=[[]])
    with pytest.raises(CodigoVinculacionInvalidoError):
        await consumir_codigo_vinculacion(db2, codigo, telegram_id=222)

    # The second, losing consumer must NEVER overwrite the first's telegram_id.
    assert usuario.telegram_id == 111


async def test_generar_codigo_vinculacion_invalidates_a_previous_unconsumed_code():
    """WARNING (post-Phase-4 review, finding #4): the module's own docstring
    already claimed this ("un código nuevo invalida silenciosamente
    cualquier código anterior") but no test proved it. Generating code B
    overwrites code A's hash before A is ever consumed, so a later attempt
    to consume A finds no matching row (`execute_queue=[[]]`, same
    no-matching-hash convention as `test_consumir_codigo_vinculacion_wrong_
    code_raises_invalid`)."""
    usuario = _admin()
    db = FakeAsyncSession(execute_queue=[])

    codigo_a = await generar_codigo_vinculacion(db, usuario)
    hash_a = usuario.codigo_vinculacion_hash
    await generar_codigo_vinculacion(db, usuario)

    assert usuario.codigo_vinculacion_hash != hash_a

    db2 = FakeAsyncSession(execute_queue=[[]])
    with pytest.raises(CodigoVinculacionInvalidoError):
        await consumir_codigo_vinculacion(db2, codigo_a, telegram_id=1)
