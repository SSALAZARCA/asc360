"""
Phase 4 "Approval service + Usuarios UI" (sdd/motored-ventas-perdidas-bot,
tasks 4.1/4.2; design D5) — unit coverage for `services/solicitudes.py::
resolver_solicitud`, the SINGLE function both the web Usuarios screen
(`POST /api/motored/usuarios/{id}/aprobar|rechazar`, this Phase) and the
bot's own Telegram admin-approval buttons (`POST /admin/solicitudes/{id}/
aprobar|rechazar`, Fase 5) must call — never duplicated logic (design D5).

Same `FakeAsyncSession` convention as `test_demanda_perdida_bot_anular.py`,
and the same atomic-claim race-simulation shape (two separate
`FakeAsyncSession`s, one per "transaction").
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.motored.models.usuario import Usuario
from app.motored.services.solicitudes import (
    SolicitudYaResuelta,
    UsuarioNoEncontradoTrasClaim,
    resolver_solicitud,
)
from tests.motored.conftest import FakeAsyncSession


def _predicados_where(stmt) -> list:
    """Local, UPDATE-statement-specific twin of `test_usuarios_api.py`'s
    `_extraer_predicados` (post-Phase-4 review, finding #1): walks the
    compiled top-level AND WHERE clauses of `resolver_solicitud`'s REAL
    `update(Usuario)` statement and returns `(column_name, value_or_sql)`
    per clause -- proves the ACTUAL claim predicate, not just that SOME
    query ran. `.is_(True)` clauses (e.g. `Usuario.activo.is_(True)`) have
    no bound-param `.value` (they compile to a literal `IS true`), so those
    fall back to the clause's rendered SQL text instead of a bound value."""
    whereclause = getattr(stmt, "whereclause", None)
    if whereclause is None:
        return []
    clausulas = getattr(whereclause, "clauses", [whereclause])
    predicados = []
    for clausula in clausulas:
        left = getattr(clausula, "left", None)
        right = getattr(clausula, "right", None)
        nombre_columna = getattr(left, "key", None)
        if nombre_columna is None:
            continue
        if hasattr(right, "value"):
            predicados.append((nombre_columna, right.value))
        else:
            predicados.append((nombre_columna, str(clausula)))
    return predicados


def _usuario_pending(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Juan Asesor", email=None, hashed_password=None,
        role="ASESOR_MOSTRADOR", activo=True, status="pending",
        telegram_id=111, phone="3001234567",
    )
    base.update(overrides)
    return Usuario(**base)


async def test_resolver_solicitud_approve_updates_status_and_resuelto_fields():
    usuario = _usuario_pending()
    actor_id = uuid.uuid4()
    db = FakeAsyncSession(
        execute_queue=[
            [usuario.id],  # UPDATE ... WHERE status='pending' RETURNING id -- claim succeeds
            [usuario],  # select(Usuario) re-fetch after claim
        ]
    )

    resultado = await resolver_solicitud(db, usuario.id, "approved", actor_id)

    assert resultado is usuario
    assert usuario.status == "approved"
    assert usuario.resuelto_por == actor_id
    assert usuario.resuelto_en is not None


async def test_resolver_solicitud_reject_updates_status():
    usuario = _usuario_pending()
    actor_id = uuid.uuid4()
    db = FakeAsyncSession(execute_queue=[[usuario.id], [usuario]])

    await resolver_solicitud(db, usuario.id, "rejected", actor_id)

    assert usuario.status == "rejected"


async def test_resolver_solicitud_race_second_call_raises_solicitud_ya_resuelta():
    """Review-established pattern (mirrors `anular_registro_bot`'s
    concurrent-anulación test): two concurrent resolutions of the SAME
    pending request (a double-click, or a web click racing a Telegram tap)
    -- only the first transaction's atomic claim wins; the second sees 0
    rows affected and must raise `SolicitudYaResuelta` BEFORE touching
    anything else, and must NEVER re-apply a decision on top of the first."""
    usuario = _usuario_pending()
    actor_1 = uuid.uuid4()
    actor_2 = uuid.uuid4()

    db1 = FakeAsyncSession(execute_queue=[[usuario.id], [usuario]])
    await resolver_solicitud(db1, usuario.id, "approved", actor_1)
    assert usuario.status == "approved"
    assert usuario.resuelto_por == actor_1

    # Second transaction's own claim query finds 0 rows (status is no
    # longer 'pending' by the time its UPDATE runs).
    db2 = FakeAsyncSession(execute_queue=[[]])

    with pytest.raises(SolicitudYaResuelta):
        await resolver_solicitud(db2, usuario.id, "rejected", actor_2)

    # No second query was ever issued -- the race is closed BEFORE any
    # further read, and the decision was never overwritten.
    assert len(db2.executed_statements) == 1
    assert usuario.status == "approved"
    assert usuario.resuelto_por == actor_1


async def test_resolver_solicitud_nonexistent_or_already_resolved_id_raises_same_error():
    """A bogus/unknown `usuario_id` and an already-resolved one both fail
    the SAME atomic `WHERE status='pending'` claim -- both surface as
    `SolicitudYaResuelta`, mirroring `CargaYaAnuladaError`'s own
    no-distinction precedent (see `services/demanda_perdida_bot.py`)."""
    db = FakeAsyncSession(execute_queue=[[]])

    with pytest.raises(SolicitudYaResuelta):
        await resolver_solicitud(db, uuid.uuid4(), "approved", uuid.uuid4())


async def test_resolver_solicitud_update_statement_has_correct_values_and_full_where_predicate():
    """CRITICAL (post-Phase-4 review, finding #1): every prior test in this
    file only checked the OUTCOME of `resolver_solicitud`'s manual
    in-memory field sync -- a workaround because `FakeAsyncSession` never
    actually applies a real `UPDATE` -- never the actual `.values()`/
    `.where()` content of the `update(Usuario)...` statement it builds. A
    wrong column in `.values()`, a swapped `actor_id`/`resuelto_por`, or a
    dropped `Usuario.activo.is_(True)` predicate would have passed every
    one of the other tests here. This inspects `db.executed_statements[0]`
    directly, the same pattern `test_usuarios_api.py`'s `_extraer_
    predicados` helper already established for `GET /usuarios?status=
    pending`'s SELECT."""
    usuario = _usuario_pending()
    actor_id = uuid.uuid4()
    db = FakeAsyncSession(execute_queue=[[usuario.id], [usuario]])

    await resolver_solicitud(db, usuario.id, "approved", actor_id)

    stmt = db.executed_statements[0]

    # Bound SET values -- the real UPDATE's `.values()`, not the in-memory
    # sync that runs afterwards.
    valores = {col.key: bind.value for col, bind in stmt._values.items()}
    assert valores["status"] == "approved"
    assert valores["resuelto_por"] == actor_id
    assert isinstance(valores["resuelto_en"], datetime)

    # WHERE predicate -- must include status=='pending' AND activo==True,
    # not just id==usuario_id.
    predicados = dict(_predicados_where(stmt))
    assert predicados["id"] == usuario.id
    assert predicados["status"] == "pending"
    assert "activo" in predicados
    assert "IS true" in predicados["activo"] or "IS 1" in predicados["activo"]


async def test_resolver_solicitud_missing_row_after_claim_raises_loud_error_before_commit():
    """WARNING (post-Phase-4 review, finding #3): if the atomic claim
    affects a row but the follow-up `SELECT` finds no matching `Usuario`
    (today effectively unreachable -- no hard-delete path exists for
    `Usuario` -- but shared code Fase 5 will also call), `resolver_
    solicitud` must fail LOUDLY here, BEFORE any caller commits, instead of
    returning `None` silently and letting `_resolver_solicitud_endpoint`
    commit the state transition and only then crash with an opaque
    `pydantic.ValidationError` while building `_to_read(None)`."""
    usuario_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    db = FakeAsyncSession(execute_queue=[[usuario_id], []])

    with pytest.raises(UsuarioNoEncontradoTrasClaim):
        await resolver_solicitud(db, usuario_id, "approved", actor_id)

    assert db.committed is False
