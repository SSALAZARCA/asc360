"""
Phase 6 "Demanda perdida — bot write path" (sdd/motored-ventas-perdidas-bot,
tasks 6.5-6.13; design D3/D4) — HTTP-layer coverage for the ASESOR_MOSTRADOR
surface of `/api/motored/bot/*`:

- `POST /referencias/resolver`
- `POST /demanda-perdida` (register, with `Idempotency-Key`)
- `GET /demanda-perdida/hoy`
- `PATCH /demanda-perdida/lineas/{linea_id}`
- `POST /demanda-perdida/{carga_id}/anular`

Same `FakeAsyncSession`/`override_motored_db`/`_headers` convention as
`test_bot_api.py` (Phase 5).
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.main import app
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal
from app.motored.services.reloj import hoy_bogota
from tests.motored.conftest import (
    AdditiveDemandaPerdidaFakeSession,
    FakeAsyncSession,
    override_motored_db,
)

BOT_URL = "/api/motored/bot"
LORE_SECRET = "bot-test-lore-secret-6"


@pytest.fixture(autouse=True)
def _lore_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "bot-test-motored-secret-6")
    monkeypatch.setattr(settings, "SECRET_KEY", "bot-test-asc360-secret-6")
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "bot-test-sonia-secret-6")
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", LORE_SECRET)
    yield
    app.dependency_overrides.clear()


def _headers(telegram_id, secret=LORE_SECRET, idempotency_key=None) -> dict:
    headers = {"X-Lore-Secret": secret, "X-Lore-Telegram-Id": str(telegram_id)}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = str(idempotency_key)
    return headers


def _client_with_queue(
    execute_queue, raise_integrity_error=None, session_cls=FakeAsyncSession, **session_kwargs
) -> "tuple[TestClient, FakeAsyncSession]":
    """`session_cls`/`session_kwargs` (fix-up finding #2): un test que
    necesita PROBAR de verdad la aritmética aditiva de `demanda_perdida`
    (en vez de solo la forma del statement) pasa `session_cls=
    AdditiveDemandaPerdidaFakeSession` + `filas_iniciales=...`; todo el
    resto de los tests sigue usando el `FakeAsyncSession` liso, sin
    cambios."""
    session = session_cls(
        execute_queue=[[]] + list(execute_queue),
        raise_integrity_error=raise_integrity_error,
        **session_kwargs,
    )
    override_motored_db(session)
    return TestClient(app), session


def _asesor(*, telegram_id, sucursal_ids=None, **overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Juan Asesor", email=None, hashed_password=None,
        role="ASESOR_MOSTRADOR", activo=True, status="approved", telegram_id=telegram_id,
        phone="3001234567",
    )
    base.update(overrides)
    usuario = Usuario(**base)
    usuario.sucursales = [
        UsuarioSucursal(id=uuid.uuid4(), usuario_id=usuario.id, sucursal_id=sid)
        for sid in (sucursal_ids or [])
    ]
    return usuario


def _carga_bot(**overrides) -> CargaArchivo:
    base = dict(
        id=uuid.uuid4(), tipo="DEMANDA_PERDIDA", origen="BOT", estado="APLICADO",
        nombre_archivo=None, hash_sha256=None, ruta_objeto=None, bytes=None,
        filas_leidas=0, filas_validas=0, filas_rechazadas=0,
        lotes_staged=0, ultimo_lote_aplicado=0, log=None,
    )
    base.update(overrides)
    return CargaArchivo(**base)


def _linea_bot(**overrides) -> DemandaPerdidaBotLinea:
    base = dict(
        id=uuid.uuid4(), carga_id=uuid.uuid4(), usuario_id=uuid.uuid4(),
        fecha=hoy_bogota(), sucursal_id=uuid.uuid4(), referencia_id=uuid.uuid4(),
        cantidad=Decimal("2"), estado="ACTIVA",
    )
    base.update(overrides)
    return DemandaPerdidaBotLinea(**base)


# ---------------------------------------------------------------------------
# POST /referencias/resolver (task 6.5)
# ---------------------------------------------------------------------------


def test_resolver_referencias_exact_match_resolves():
    proveedor_id = uuid.uuid4()
    referencia_id = uuid.uuid4()
    asesor = _asesor(telegram_id=1)
    client, _session = _client_with_queue(
        [
            [asesor],  # actor lookup
            [proveedor_id],  # resolver_proveedor_principal
            [(referencia_id, "ABC123", "Filtro de aceite")],  # match query
        ]
    )

    response = client.post(
        f"{BOT_URL}/referencias/resolver", json={"codigos": [" abc123 "]}, headers=_headers(1)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["no_resueltas"] == []
    assert body["resueltas"] == [
        {"entrada": " abc123 ", "referencia_id": str(referencia_id), "codigo": "ABC123", "nombre": "Filtro de aceite"}
    ]


def test_resolver_referencias_no_match_is_unresolved():
    proveedor_id = uuid.uuid4()
    asesor = _asesor(telegram_id=1)
    client, _session = _client_with_queue([[asesor], [proveedor_id], []])

    response = client.post(
        f"{BOT_URL}/referencias/resolver", json={"codigos": ["ZZZ999"]}, headers=_headers(1)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resueltas"] == []
    assert body["no_resueltas"] == ["ZZZ999"]


def test_resolver_referencias_multiple_hits_is_unresolved_no_fuzzy_matching():
    """Design D3: "More than one hit counts as unresolved. There is no
    fuzzy matching." -- two DIFFERENT `Referencia` rows whose codigo
    normalizes to the SAME value (e.g. differing only by case, which the
    real UNIQUE(codigo, proveedor_id) constraint does not catch) must NOT
    be silently picked -- the whole entry is unresolved."""
    proveedor_id = uuid.uuid4()
    id_a, id_b = uuid.uuid4(), uuid.uuid4()
    asesor = _asesor(telegram_id=1)
    client, _session = _client_with_queue(
        [[asesor], [proveedor_id], [(id_a, "abc123", "Uno"), (id_b, "ABC123", "Otro")]]
    )

    response = client.post(
        f"{BOT_URL}/referencias/resolver", json={"codigos": ["ABC123"]}, headers=_headers(1)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resueltas"] == []
    assert body["no_resueltas"] == ["ABC123"]


def test_resolver_referencias_more_than_30_codigos_is_422():
    client, _session = _client_with_queue([[_asesor(telegram_id=1)]])
    response = client.post(
        f"{BOT_URL}/referencias/resolver",
        json={"codigos": [f"C{i}" for i in range(31)]},
        headers=_headers(1),
    )
    assert response.status_code == 422


def test_resolver_referencias_wrong_secret_returns_401():
    client, _session = _client_with_queue([])
    response = client.post(
        f"{BOT_URL}/referencias/resolver", json={"codigos": ["ABC123"]}, headers=_headers(1, secret="wrong")
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /demanda-perdida (tasks 6.6/6.7) — register + idempotency
# ---------------------------------------------------------------------------


def test_registrar_demanda_perdida_success_writes_header_lineas_and_delta():
    sucursal_id = uuid.uuid4()
    referencia_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[sucursal_id])
    linea_esperada = _linea_bot(
        carga_id=idempotency_key, usuario_id=asesor.id, sucursal_id=sucursal_id,
        referencia_id=referencia_id, cantidad=Decimal("3"),
    )
    client, session = _client_with_queue(
        [
            [asesor],  # actor lookup
            [],  # idempotency pre-check: no existing carga
            [],  # aplicar_delta_demanda_perdida -> upsert execute
            [linea_esperada],  # _serializar_registro re-select
        ]
    )

    payload = {
        "sucursal_id": str(sucursal_id),
        "metodo": "MANUAL",
        "lineas": [{"referencia_id": str(referencia_id), "cantidad": 3}],
    }
    response = client.post(
        f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=idempotency_key)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["carga_id"] == str(idempotency_key)
    assert body["lineas"] == [
        {
            "linea_id": str(linea_esperada.id), "referencia_id": str(referencia_id),
            "cantidad": 3.0, "estado": "ACTIVA",
        }
    ]

    creadas = session.added_of_type(CargaArchivo)
    assert len(creadas) == 1
    assert creadas[0].id == idempotency_key
    assert creadas[0].origen == "BOT"
    assert creadas[0].tipo == "DEMANDA_PERDIDA"
    assert creadas[0].estado == "APLICADO"
    assert creadas[0].subido_por == asesor.id

    lineas_creadas = session.added_of_type(DemandaPerdidaBotLinea)
    assert len(lineas_creadas) == 1
    assert lineas_creadas[0].cantidad == Decimal("3")
    assert lineas_creadas[0].fecha == hoy_bogota()
    assert session.committed is True

    # The additive-upsert statement carries 'BOT' origin and the exact delta.
    # executed_statements: [0]=readiness probe, [1]=actor lookup,
    # [2]=idempotency pre-check, [3]=upsert.
    upsert_stmt = session.executed_statements[3]
    valores = upsert_stmt.compile().construct_params()
    assert "BOT" in valores.values()
    assert Decimal("3") in valores.values()


def test_registrar_demanda_perdida_sucursal_no_autorizada_returns_403():
    asesor = _asesor(telegram_id=1, sucursal_ids=[])
    client, _session = _client_with_queue([[asesor]])

    payload = {
        "sucursal_id": str(uuid.uuid4()), "metodo": "MANUAL",
        "lineas": [{"referencia_id": str(uuid.uuid4()), "cantidad": 1}],
    }
    response = client.post(
        f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=uuid.uuid4())
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "SUCURSAL_NO_AUTORIZADA"


def test_registrar_demanda_perdida_duplicate_referencia_in_lineas_is_422():
    referencia_id = uuid.uuid4()
    client, _session = _client_with_queue([[_asesor(telegram_id=1)]])

    payload = {
        "sucursal_id": str(uuid.uuid4()), "metodo": "MANUAL",
        "lineas": [
            {"referencia_id": str(referencia_id), "cantidad": 1},
            {"referencia_id": str(referencia_id), "cantidad": 2},
        ],
    }
    response = client.post(
        f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=uuid.uuid4())
    )

    assert response.status_code == 422


@pytest.mark.parametrize("cantidad", [0, -1, 10000])
def test_registrar_demanda_perdida_cantidad_fuera_de_rango_is_422(cantidad):
    client, _session = _client_with_queue([[_asesor(telegram_id=1)]])
    payload = {
        "sucursal_id": str(uuid.uuid4()), "metodo": "MANUAL",
        "lineas": [{"referencia_id": str(uuid.uuid4()), "cantidad": cantidad}],
    }
    response = client.post(
        f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=uuid.uuid4())
    )
    assert response.status_code == 422


def test_registrar_demanda_perdida_idempotent_replay_same_actor_returns_200():
    sucursal_id = uuid.uuid4()
    referencia_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[sucursal_id])
    carga_existente = _carga_bot(id=idempotency_key, subido_por=asesor.id)
    linea_existente = _linea_bot(
        carga_id=idempotency_key, usuario_id=asesor.id, sucursal_id=sucursal_id,
        referencia_id=referencia_id, cantidad=Decimal("2"),
    )
    client, session = _client_with_queue(
        [[asesor], [carga_existente], [linea_existente]]
    )

    payload = {
        "sucursal_id": str(sucursal_id), "metodo": "MANUAL",
        "lineas": [{"referencia_id": str(referencia_id), "cantidad": 2}],
    }
    response = client.post(
        f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=idempotency_key)
    )

    assert response.status_code == 200, response.text
    assert response.json()["carga_id"] == str(idempotency_key)
    assert session.added == []  # no new rows were ever added
    assert session.committed is False


def test_registrar_demanda_perdida_idempotency_key_owned_by_other_actor_returns_409():
    idempotency_key = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[uuid.uuid4()])
    carga_de_otro = _carga_bot(id=idempotency_key, subido_por=uuid.uuid4())
    client, _session = _client_with_queue([[asesor], [carga_de_otro]])

    payload = {
        "sucursal_id": str(uuid.uuid4()), "metodo": "MANUAL",
        "lineas": [{"referencia_id": str(uuid.uuid4()), "cantidad": 1}],
    }
    # sucursal check happens before the idempotency lookup, so make the
    # payload's sucursal one the actor legitimately owns.
    payload["sucursal_id"] = str(asesor.sucursales[0].sucursal_id)

    response = client.post(
        f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=idempotency_key)
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_EN_USO"


def test_registrar_demanda_perdida_concurrent_same_key_race_returns_200_not_500():
    """Two near-simultaneous registrations with the SAME Idempotency-Key
    both pass the pre-check `SELECT` before either commits -- the second
    `db.commit()` then violates `carga_archivo`'s PK for real. Must become
    the SAME clean 200 idempotent-replay the sequential check already
    returns, never an unhandled `IntegrityError` -> 500."""
    sucursal_id = uuid.uuid4()
    referencia_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[sucursal_id])
    carga_repetida = _carga_bot(id=idempotency_key, subido_por=asesor.id)
    linea_repetida = _linea_bot(
        carga_id=idempotency_key, usuario_id=asesor.id, sucursal_id=sucursal_id,
        referencia_id=referencia_id, cantidad=Decimal("2"),
    )
    client, session = _client_with_queue(
        [
            [asesor],  # actor lookup
            [],  # idempotency pre-check: no existing carga (both racers see this)
            [],  # aplicar_delta_demanda_perdida -> upsert execute
            [carga_repetida],  # post-IntegrityError re-select
            [linea_repetida],  # _serializar_registro re-select
        ],
        raise_integrity_error=IntegrityError(
            "INSERT carga_archivo", {},
            Exception('duplicate key value violates unique constraint "carga_archivo_pkey"'),
        ),
    )

    payload = {
        "sucursal_id": str(sucursal_id), "metodo": "MANUAL",
        "lineas": [{"referencia_id": str(referencia_id), "cantidad": 2}],
    }
    response = client.post(
        f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=idempotency_key)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["carga_id"] == str(idempotency_key)
    # Fix-up finding #3 (CRITICAL): the replayed body must reflect the REAL
    # submitted content, not just a matching status code/id -- a replay that
    # silently returned someone else's lineas (or none at all) would still
    # have passed the old, weaker assertion.
    assert body["lineas"] == [
        {
            "linea_id": str(linea_repetida.id), "referencia_id": str(referencia_id),
            "cantidad": 2.0, "estado": "ACTIVA",
        }
    ]
    assert session.rolled_back is True


def test_registrar_demanda_perdida_nonexistent_referencia_returns_404_not_500():
    sucursal_id = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[sucursal_id])
    client, session = _client_with_queue(
        [[asesor], [], []],
        raise_integrity_error=IntegrityError(
            "INSERT demanda_perdida_bot_linea", {},
            Exception(
                'insert or update on table "demanda_perdida_bot_linea" violates foreign key '
                'constraint "demanda_perdida_bot_linea_referencia_id_fkey"'
            ),
        ),
    )
    payload = {
        "sucursal_id": str(sucursal_id), "metodo": "MANUAL",
        "lineas": [{"referencia_id": str(uuid.uuid4()), "cantidad": 1}],
    }
    response = client.post(
        f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=uuid.uuid4())
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "REFERENCIA_NO_ENCONTRADA"
    assert session.rolled_back is True


def test_registrar_demanda_perdida_sucursal_fk_violation_returns_404_not_500():
    """Fix-up finding #7: a concurrent sucursal deactivation/deletion
    between `GET /sucursales` and this call violates the sucursal FK for
    real -- must map to `SUCURSAL_NO_ENCONTRADA`, not the referencia code
    the old blanket `except IntegrityError` defaulted everything to."""
    sucursal_id = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[sucursal_id])
    client, session = _client_with_queue(
        [[asesor], [], []],
        raise_integrity_error=IntegrityError(
            "INSERT demanda_perdida_bot_linea", {},
            Exception(
                'insert or update on table "demanda_perdida_bot_linea" violates foreign key '
                'constraint "demanda_perdida_bot_linea_sucursal_id_fkey"'
            ),
        ),
    )
    payload = {
        "sucursal_id": str(sucursal_id), "metodo": "MANUAL",
        "lineas": [{"referencia_id": str(uuid.uuid4()), "cantidad": 1}],
    }
    response = client.post(
        f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=uuid.uuid4())
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "SUCURSAL_NO_ENCONTRADA"
    assert session.rolled_back is True


def test_registrar_demanda_perdida_unexpected_integrity_error_is_logged_and_returns_clean_error(
    caplog,
):
    """Fix-up finding #7 (WARNING, converges risk/resilience/reliability):
    an IntegrityError that matches NEITHER the idempotency-key PK nor a
    known referencia/sucursal FK must never be silently relabeled as
    `REFERENCIA_NO_ENCONTRADA` -- it must be logged (with the real
    `exc.orig`, for a real ops trail) and returned as its own distinct,
    clean 4xx, never an unhandled 500."""
    sucursal_id = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[sucursal_id])
    detalle_inesperado = (
        'insert or update on table "demanda_perdida_bot_linea" violates foreign key '
        'constraint "demanda_perdida_bot_linea_usuario_id_fkey"'
    )
    client, session = _client_with_queue(
        [[asesor], [], []],
        raise_integrity_error=IntegrityError(
            "INSERT demanda_perdida_bot_linea", {}, Exception(detalle_inesperado)
        ),
    )
    payload = {
        "sucursal_id": str(sucursal_id), "metodo": "MANUAL",
        "lineas": [{"referencia_id": str(uuid.uuid4()), "cantidad": 1}],
    }

    with caplog.at_level("ERROR", logger="motored.bot_demanda_perdida"):
        response = client.post(
            f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=uuid.uuid4())
        )

    assert response.status_code not in (200, 201, 500), response.text
    assert response.json()["detail"]["code"] not in (
        "REFERENCIA_NO_ENCONTRADA", "SUCURSAL_NO_ENCONTRADA", "IDEMPOTENCY_KEY_EN_USO",
    )
    assert session.rolled_back is True
    assert any(
        record.levelname == "ERROR" and "usuario_id_fkey" in record.getMessage()
        for record in caplog.records
    )


def test_registrar_demanda_perdida_multiple_lineas_each_gets_own_additive_delta():
    """Fix-up finding #10: `POST /demanda-perdida`'s documented "1+ lines
    in one transaction" contract was only ever tested with exactly ONE
    line. 2 distinct lines here, each proven (via `AdditiveDemandaPerdida
    FakeSession`'s real arithmetic, not statement-shape introspection) to
    receive its OWN additive delta, both reflected in the response."""
    sucursal_id = uuid.uuid4()
    referencia_a = uuid.uuid4()
    referencia_b = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[sucursal_id])
    linea_a = _linea_bot(
        carga_id=idempotency_key, usuario_id=asesor.id, sucursal_id=sucursal_id,
        referencia_id=referencia_a, cantidad=Decimal("3"),
    )
    linea_b = _linea_bot(
        carga_id=idempotency_key, usuario_id=asesor.id, sucursal_id=sucursal_id,
        referencia_id=referencia_b, cantidad=Decimal("5"),
    )
    client, session = _client_with_queue(
        [
            [asesor],  # actor lookup
            [],  # idempotency pre-check: no existing carga
            [linea_a, linea_b],  # _serializar_registro re-select
        ],
        session_cls=AdditiveDemandaPerdidaFakeSession,
    )

    payload = {
        "sucursal_id": str(sucursal_id),
        "metodo": "MANUAL",
        "lineas": [
            {"referencia_id": str(referencia_a), "cantidad": 3},
            {"referencia_id": str(referencia_b), "cantidad": 5},
        ],
    }
    response = client.post(
        f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1, idempotency_key=idempotency_key)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert {(linea["referencia_id"], linea["cantidad"]) for linea in body["lineas"]} == {
        (str(referencia_a), 3.0), (str(referencia_b), 5.0),
    }
    # Each referencia got its OWN real additive delta -- never a single
    # shared statement, never one line's amount leaking into the other's.
    assert session.cantidad_actual(
        fecha=hoy_bogota(), sucursal_id=sucursal_id, referencia_id=referencia_a
    ) == Decimal("3")
    assert session.cantidad_actual(
        fecha=hoy_bogota(), sucursal_id=sucursal_id, referencia_id=referencia_b
    ) == Decimal("5")


def test_registrar_demanda_perdida_missing_idempotency_key_header_is_422():
    client, _session = _client_with_queue([[_asesor(telegram_id=1)]])
    payload = {
        "sucursal_id": str(uuid.uuid4()), "metodo": "MANUAL",
        "lineas": [{"referencia_id": str(uuid.uuid4()), "cantidad": 1}],
    }
    response = client.post(f"{BOT_URL}/demanda-perdida", json=payload, headers=_headers(1))
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /demanda-perdida/hoy (tasks 6.8/6.9)
# ---------------------------------------------------------------------------


def test_listar_hoy_returns_empty_list_when_no_lineas():
    asesor = _asesor(telegram_id=1)
    client, _session = _client_with_queue([[asesor], []])

    response = client.get(f"{BOT_URL}/demanda-perdida/hoy", headers=_headers(1))

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_listar_hoy_returns_own_active_registrations_with_referencia_and_sucursal():
    asesor = _asesor(telegram_id=1)
    sucursal = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE", activa=True)
    referencia = Referencia(id=uuid.uuid4(), codigo="ABC123", proveedor_id=uuid.uuid4(), nombre="Filtro")
    carga = _carga_bot(subido_por=asesor.id)
    linea = _linea_bot(
        carga_id=carga.id, usuario_id=asesor.id, sucursal_id=sucursal.id,
        referencia_id=referencia.id, cantidad=Decimal("4"),
    )
    client, _session = _client_with_queue(
        [[asesor], [linea], [carga], [referencia], [sucursal]]
    )

    response = client.get(f"{BOT_URL}/demanda-perdida/hoy", headers=_headers(1))

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["carga_id"] == str(carga.id)
    assert body[0]["sucursal"] == {"id": str(sucursal.id), "nombre": "CALI NORTE"}
    assert body[0]["lineas"] == [
        {
            "linea_id": str(linea.id),
            "referencia": {"codigo": "ABC123", "nombre": "Filtro"},
            "cantidad": 4.0,
        }
    ]


def test_listar_hoy_multiple_cargas_no_cross_contamination():
    """Fix-up finding #9: 2 different cargas from the SAME actor (different
    registrations), each with their own line -- proves no cross-
    contamination between them in the grouped response."""
    asesor = _asesor(telegram_id=1)
    sucursal_a = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE", activa=True)
    sucursal_b = Sucursal(id=uuid.uuid4(), nombre="BOGOTA CENTRO", activa=True)
    referencia_a = Referencia(id=uuid.uuid4(), codigo="AAA111", proveedor_id=uuid.uuid4(), nombre="Filtro A")
    referencia_b = Referencia(id=uuid.uuid4(), codigo="BBB222", proveedor_id=uuid.uuid4(), nombre="Filtro B")
    carga_a = _carga_bot(subido_por=asesor.id)
    carga_b = _carga_bot(subido_por=asesor.id)
    linea_a = _linea_bot(
        carga_id=carga_a.id, usuario_id=asesor.id, sucursal_id=sucursal_a.id,
        referencia_id=referencia_a.id, cantidad=Decimal("2"),
    )
    linea_b = _linea_bot(
        carga_id=carga_b.id, usuario_id=asesor.id, sucursal_id=sucursal_b.id,
        referencia_id=referencia_b.id, cantidad=Decimal("5"),
    )
    client, _session = _client_with_queue(
        [
            [asesor],
            [linea_a, linea_b],
            [carga_a, carga_b],
            [referencia_a, referencia_b],
            [sucursal_a, sucursal_b],
        ]
    )

    response = client.get(f"{BOT_URL}/demanda-perdida/hoy", headers=_headers(1))

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 2
    por_carga = {registro["carga_id"]: registro for registro in body}
    assert por_carga[str(carga_a.id)]["sucursal"]["nombre"] == "CALI NORTE"
    assert por_carga[str(carga_a.id)]["lineas"] == [
        {
            "linea_id": str(linea_a.id),
            "referencia": {"codigo": "AAA111", "nombre": "Filtro A"},
            "cantidad": 2.0,
        }
    ]
    assert por_carga[str(carga_b.id)]["sucursal"]["nombre"] == "BOGOTA CENTRO"
    assert por_carga[str(carga_b.id)]["lineas"] == [
        {
            "linea_id": str(linea_b.id),
            "referencia": {"codigo": "BBB222", "nombre": "Filtro B"},
            "cantidad": 5.0,
        }
    ]


def test_listar_hoy_excludes_line_whose_carga_was_concurrently_anulada():
    """Fix-up finding #9: a line whose parent carga was concurrently
    `ANULADO` (the DB's `estado != 'ANULADO'` filter excludes it from the
    cargas query) must be excluded from the response entirely -- per the
    `if linea.carga_id in cargas_por_id` guard -- never a "ghost" registro
    with no header."""
    asesor = _asesor(telegram_id=1)
    carga_activa = _carga_bot(subido_por=asesor.id)
    linea_activa = _linea_bot(carga_id=carga_activa.id, usuario_id=asesor.id)
    linea_huerfana = _linea_bot(carga_id=uuid.uuid4(), usuario_id=asesor.id)
    client, _session = _client_with_queue(
        [
            [asesor],
            [linea_activa, linea_huerfana],
            [carga_activa],  # the concurrently-ANULADO carga was filtered out at the DB level
            [],
            [],
        ]
    )

    response = client.get(f"{BOT_URL}/demanda-perdida/hoy", headers=_headers(1))

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["carga_id"] == str(carga_activa.id)


# ---------------------------------------------------------------------------
# PATCH /demanda-perdida/lineas/{linea_id} (tasks 6.10/6.11)
# ---------------------------------------------------------------------------


def test_editar_linea_positive_delta_applies_upsert_and_updates_cantidad():
    asesor = _asesor(telegram_id=1)
    linea = _linea_bot(usuario_id=asesor.id, cantidad=Decimal("2"))
    client, session = _client_with_queue([[asesor], [linea], []])

    response = client.patch(
        f"{BOT_URL}/demanda-perdida/lineas/{linea.id}", json={"cantidad": 5}, headers=_headers(1)
    )

    assert response.status_code == 200, response.text
    assert linea.cantidad == Decimal("5")
    assert session.committed is True


def test_editar_linea_negative_delta_uses_update_then_delete_never_upsert():
    asesor = _asesor(telegram_id=1)
    linea = _linea_bot(usuario_id=asesor.id, cantidad=Decimal("5"))
    client, session = _client_with_queue([[asesor], [linea], [], []])

    response = client.patch(
        f"{BOT_URL}/demanda-perdida/lineas/{linea.id}", json={"cantidad": 2}, headers=_headers(1)
    )

    assert response.status_code == 200, response.text
    assert linea.cantidad == Decimal("2")
    # 2 statements after the linea lookup: UPDATE then DELETE (never an
    # ON CONFLICT upsert for a negative delta).
    delta_statements = session.executed_statements[2:4]
    assert not any(hasattr(stmt, "excluded") for stmt in delta_statements)


def test_editar_linea_not_own_returns_404():
    asesor = _asesor(telegram_id=1)
    linea_de_otro = _linea_bot(usuario_id=uuid.uuid4())
    client, _session = _client_with_queue([[asesor], [linea_de_otro]])

    response = client.patch(
        f"{BOT_URL}/demanda-perdida/lineas/{linea_de_otro.id}", json={"cantidad": 5}, headers=_headers(1)
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "LINEA_NO_ENCONTRADA"


def test_editar_linea_not_found_returns_404():
    asesor = _asesor(telegram_id=1)
    client, _session = _client_with_queue([[asesor], []])

    response = client.patch(
        f"{BOT_URL}/demanda-perdida/lineas/{uuid.uuid4()}", json={"cantidad": 5}, headers=_headers(1)
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "LINEA_NO_ENCONTRADA"


def test_editar_linea_stale_date_returns_409_fuera_de_ventana():
    asesor = _asesor(telegram_id=1)
    linea = _linea_bot(usuario_id=asesor.id, fecha=datetime.date(2020, 1, 1))
    client, _session = _client_with_queue([[asesor], [linea]])

    response = client.patch(
        f"{BOT_URL}/demanda-perdida/lineas/{linea.id}", json={"cantidad": 5}, headers=_headers(1)
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "FUERA_DE_VENTANA"


def test_editar_linea_anulada_returns_409():
    asesor = _asesor(telegram_id=1)
    linea = _linea_bot(usuario_id=asesor.id, estado="ANULADA")
    client, _session = _client_with_queue([[asesor], [linea]])

    response = client.patch(
        f"{BOT_URL}/demanda-perdida/lineas/{linea.id}", json={"cantidad": 5}, headers=_headers(1)
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LINEA_ANULADA"


@pytest.mark.parametrize("cantidad", [0, -1, 10000])
def test_editar_linea_cantidad_fuera_de_rango_is_422(cantidad):
    client, _session = _client_with_queue([[_asesor(telegram_id=1)]])
    response = client.patch(
        f"{BOT_URL}/demanda-perdida/lineas/{uuid.uuid4()}", json={"cantidad": cantidad}, headers=_headers(1)
    )
    assert response.status_code == 422


def test_editar_linea_delta_cero_no_toca_demanda_perdida_and_returns_200():
    """Fix-up finding #11: editing a line to its OWN current value (`delta
    == 0`) must leave `demanda_perdida` completely untouched -- no upsert/
    update/delete statement issued at all -- and the endpoint still
    returns 200. Only the readiness probe + actor lookup + linea lookup
    are ever executed."""
    asesor = _asesor(telegram_id=1)
    linea = _linea_bot(usuario_id=asesor.id, cantidad=Decimal("5"))
    client, session = _client_with_queue([[asesor], [linea]])

    response = client.patch(
        f"{BOT_URL}/demanda-perdida/lineas/{linea.id}", json={"cantidad": 5}, headers=_headers(1)
    )

    assert response.status_code == 200, response.text
    assert linea.cantidad == Decimal("5")
    assert len(session.executed_statements) == 3
    assert session.committed is True


# ---------------------------------------------------------------------------
# POST /demanda-perdida/{carga_id}/anular (tasks 6.12/6.13) — router wiring
# ---------------------------------------------------------------------------


def test_anular_propio_success():
    asesor = _asesor(telegram_id=1)
    carga = _carga_bot(subido_por=asesor.id)
    linea = _linea_bot(carga_id=carga.id, usuario_id=asesor.id, cantidad=Decimal("3"))
    client, session = _client_with_queue(
        [
            [asesor],  # actor lookup
            [carga],  # carga lookup
            [linea.fecha],  # _validar_ventana_propia ledger-fecha lookup
            [carga.id],  # claim atomico
            [linea],  # select ACTIVA lines
        ],
        session_cls=AdditiveDemandaPerdidaFakeSession,
        filas_iniciales={
            (linea.fecha, linea.sucursal_id, linea.referencia_id, "BOT"): Decimal("10"),
        },
    )

    response = client.post(f"{BOT_URL}/demanda-perdida/{carga.id}/anular", headers=_headers(1))

    assert response.status_code == 200, response.text
    assert response.json()["estado"] == "ANULADO"
    assert linea.estado == "ANULADA"
    assert session.committed is True
    # Real reversal (fix-up finding #1): 10 - 3 = 7, applied via the atomic
    # UPDATE, never a SELECT-then-mutate.
    assert session.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id
    ) == Decimal("7")


def test_anular_propio_carga_not_found_returns_404():
    asesor = _asesor(telegram_id=1)
    client, _session = _client_with_queue([[asesor], []])

    response = client.post(f"{BOT_URL}/demanda-perdida/{uuid.uuid4()}/anular", headers=_headers(1))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CARGA_NO_ENCONTRADA"


def test_anular_propio_not_owner_returns_404():
    asesor = _asesor(telegram_id=1)
    carga_de_otro = _carga_bot(subido_por=uuid.uuid4())
    client, _session = _client_with_queue([[asesor], [carga_de_otro]])

    response = client.post(f"{BOT_URL}/demanda-perdida/{carga_de_otro.id}/anular", headers=_headers(1))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CARGA_NO_ENCONTRADA"


def test_anular_propio_stale_date_returns_409_fuera_de_ventana():
    asesor = _asesor(telegram_id=1)
    carga = _carga_bot(subido_por=asesor.id)
    client, _session = _client_with_queue([[asesor], [carga], [datetime.date(2020, 1, 1)]])

    response = client.post(f"{BOT_URL}/demanda-perdida/{carga.id}/anular", headers=_headers(1))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "FUERA_DE_VENTANA"


def test_anular_propio_already_anulada_returns_409():
    asesor = _asesor(telegram_id=1)
    carga = _carga_bot(subido_por=asesor.id, estado="ANULADO")
    client, _session = _client_with_queue(
        [[asesor], [carga], [hoy_bogota()], []]  # claim finds 0 rows
    )

    response = client.post(f"{BOT_URL}/demanda-perdida/{carga.id}/anular", headers=_headers(1))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "YA_ANULADA"


# ---------------------------------------------------------------------------
# Integration test (task 6.15): edit-then-cancel the SAME registration --
# the reversal must equal the CURRENT (post-edit) quantity, never the
# original one.
# ---------------------------------------------------------------------------


def test_edit_then_cancel_reverses_current_amount_not_original():
    """Fix-up finding #2 (CRITICAL, previously hollow): the PATCH and the
    anular call both go through the REAL `aplicar_delta_demanda_perdida`/
    `_ejecutar_delta_negativo` code path against `AdditiveDemandaPerdidaFake
    Session`'s in-memory row -- the PATCH's own `delta = 7 - 3 = +4` is
    genuinely applied to the seeded baseline of 20 BEFORE the anular call
    ever runs, proving the reversal really does read the POST-edit state,
    never a hand-built expectation."""
    asesor = _asesor(telegram_id=1)
    carga = _carga_bot(subido_por=asesor.id)
    linea = _linea_bot(carga_id=carga.id, usuario_id=asesor.id, cantidad=Decimal("3"))
    clave = (linea.fecha, linea.sucursal_id, linea.referencia_id, "BOT")

    session = AdditiveDemandaPerdidaFakeSession(
        execute_queue=[
            [],  # readiness probe (PATCH)
            [asesor],  # actor lookup (PATCH)
            [linea],  # linea lookup (PATCH)
            [],  # readiness probe (anular)
            [asesor],  # actor lookup (anular)
            [carga],  # carga lookup (anular)
            [linea.fecha],  # _validar_ventana_propia ledger-fecha lookup
            [carga.id],  # claim atomico
            [linea],  # select ACTIVA lines
        ],
        filas_iniciales={clave: Decimal("20")},
    )
    override_motored_db(session)
    client = TestClient(app)

    patch_response = client.patch(
        f"{BOT_URL}/demanda-perdida/lineas/{linea.id}", json={"cantidad": 7}, headers=_headers(1)
    )
    assert patch_response.status_code == 200, patch_response.text
    assert linea.cantidad == Decimal("7")
    # The PATCH's own delta (7 - 3 = +4) was genuinely applied: 20 + 4 = 24.
    assert session.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id
    ) == Decimal("24")

    anular_response = client.post(f"{BOT_URL}/demanda-perdida/{carga.id}/anular", headers=_headers(1))

    assert anular_response.status_code == 200, anular_response.text
    assert linea.estado == "ANULADA"
    # 24 - 7 (CURRENT, post-edit) = 17. A buggy implementation reversing the
    # ORIGINAL quantity (3) would leave this at 21 instead.
    assert session.cantidad_actual(
        fecha=linea.fecha, sucursal_id=linea.sucursal_id, referencia_id=linea.referencia_id
    ) == Decimal("17")
