"""
Motored satisfaction survey, slice T4: PUBLIC (unauthenticated) survey API
under `/api/motored/encuesta/publico`. No user override on purpose: these
routes must work without a token.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.core.limiter import limiter
from app.main import app
from app.motored.models.caso_detractor import CasoDetractor
from app.motored.models.caso_detractor_accion import CasoDetractorAccion
from app.motored.models.encuesta_respuesta import EncuestaRespuesta
from app.motored.services import encuesta_intentos
from tests.motored.conftest import FakeAsyncSession, override_motored_db

BASE = "/api/motored/encuesta/publico"
IDENTIFICAR = f"{BASE}/identificar"
RESPUESTAS = f"{BASE}/respuestas"
NOT_FOUND_MESSAGE = (
    "No encontramos tus datos. Revisa la cédula de la persona a cuyo nombre está registrada "
    "la motocicleta y los últimos 4 dígitos del celular donde te llegó el mensaje."
)
CELULAR = "3001112233"
LAST4 = "2233"
MATRIX_KEYS = [
    "p_explicacion_tecnica", "p_confianza_reparacion", "p_servicio_taller",
    "p_calidad_mecanicos", "p_claridad_cobros", "p_originalidad_repuestos",
]
FORBIDDEN_KEYS = {"cedula", "celular", "sic", "nombre", "centro_servicio", "tipo"}


class _CaseFakeSession(FakeAsyncSession):
    """Emulates the Identity column: `numero` is assigned on refresh."""

    async def refresh(self, obj, attribute_names=None):
        if isinstance(obj, CasoDetractor) and obj.numero is None:
            obj.numero = 4321
            obj.created_at = datetime(2026, 9, 30, 12)  # Python-side default, applied on INSERT


def _reg(placa="ABC12D", linea="Xtreet 401", nombre="ANA MARIA perez", carga=datetime(2026, 9, 1),
         respondida=None, reg_id=None, celular=CELULAR):
    return SimpleNamespace(
        id=reg_id or uuid.uuid4(), placa=placa, linea=linea, nombre=nombre, celular=celular,
        carga_created_at=carga, respuesta_created_at=respondida,
    )


def _session(*result_sets, cls=FakeAsyncSession, **kwargs):
    # first queued list = readiness probe (`SELECT 1`)
    session = cls(execute_queue=[[], *result_sets], **kwargs)
    override_motored_db(session)
    return session


def _identificar(cedula="1.234.567-8", last4=LAST4):
    with TestClient(app) as client:
        return client.post(IDENTIFICAR, json={"cedula": cedula, "celular_ultimos4": last4})


def _payload(_registro_id, **overrides):
    body = {
        "cedula": "12345678", "celular_ultimos4": LAST4,
        "registro_id": str(_registro_id), "satisfaccion_general": 5,
        **{key: 4 for key in MATRIX_KEYS}, "observaciones": None, "autoriza_datos": True,
    }
    body.update(overrides)
    return body


def _submit(body):
    with TestClient(app) as client:
        return client.post(RESPUESTAS, json=body)


def _target(cedula="12345678", tipo="SERVICIO_TALLER", respondida=False, nombre="Ana maria PEREZ",
            celular=CELULAR):
    reg_id = uuid.uuid4()
    return reg_id, SimpleNamespace(
        id=reg_id, cedula=cedula, tipo=tipo, nombre=nombre, celular=celular,
        respuesta_id=uuid.uuid4() if respondida else None,
    )


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "encuesta-publica-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "encuesta-publica-test-asc360-secret")
    limiter.reset()  # in-memory per-IP counters must not leak between tests
    encuesta_intentos.reset()  # ...nor the per-cedula failure counters
    yield
    limiter.reset()
    encuesta_intentos.reset()
    app.dependency_overrides.clear()


# --- identificar -------------------------------------------------------------

def test_identificar_unknown_cedula_returns_not_found_message():
    session = _session([])
    response = _identificar()
    assert response.status_code == 200
    assert response.json() == {"estado": "NO_ENCONTRADA", "mensaje": NOT_FOUND_MESSAGE}
    assert session.committed is False


def test_identificar_non_numeric_cedula_is_not_found_without_querying():
    session = _session()  # only the readiness probe is queued
    response = _identificar("abc")
    assert response.json()["estado"] == "NO_ENCONTRADA"
    assert len(session.executed_statements) == 1


def test_identificar_all_answered_returns_latest_response_date():
    older, newer = datetime(2026, 9, 2, 10, 0), datetime(2026, 9, 5, 15, 30)
    _session([_reg(respondida=older), _reg(placa="XYZ99A", respondida=newer)])
    body = _identificar().json()
    assert body["estado"] == "YA_RESPONDIDA"
    assert body["respondida_at"].startswith("2026-09-05T15:30")


def test_identificar_pending_returns_minimal_payload_and_title_cased_first_name():
    rid = uuid.uuid4()
    _session([_reg(reg_id=rid, nombre="ANA MARIA perez")])
    body = _identificar().json()
    assert body == {
        "estado": "PENDIENTE",
        "primer_nombre": "Ana",
        "registros": [{"registro_id": str(rid), "placa": "ABC12D", "linea": "Xtreet 401"}],
    }
    flat = str(body).lower()
    assert not FORBIDDEN_KEYS & set(body) and not FORBIDDEN_KEYS & set(body["registros"][0])
    assert "12345678" not in flat and "perez" not in flat


def test_identificar_dedupes_pending_by_placa_newest_carga_wins():
    new_id, old_id = uuid.uuid4(), uuid.uuid4()
    _session([
        _reg(reg_id=old_id, carga=datetime(2026, 8, 1)),
        _reg(reg_id=new_id, carga=datetime(2026, 9, 1)),
        _reg(placa="ZZZ11Z", carga=datetime(2026, 8, 15)),
    ])
    ids = [r["registro_id"] for r in _identificar().json()["registros"]]
    assert str(new_id) in ids and str(old_id) not in ids and len(ids) == 2


def test_identificar_placa_answered_in_newest_batch_is_not_asked_again():
    _session([
        _reg(carga=datetime(2026, 9, 1), respondida=datetime(2026, 9, 3)),
        _reg(carga=datetime(2026, 8, 1)),  # stale pending row for the same placa
        _reg(placa="ZZZ11Z", carga=datetime(2026, 8, 15)),
    ])
    placas = [r["placa"] for r in _identificar().json()["registros"]]
    assert placas == ["ZZZ11Z"]


def test_identificar_query_is_scoped_to_normalized_cedula_and_servicio_taller():
    session = _session([])
    _identificar("1.234.567-8")
    compiled = session.executed_statements[1].compile()
    assert "12345678" in compiled.params.values()
    assert "SERVICIO_TALLER" in compiled.params.values()  # VENTA rows never surface


def test_identificar_wrong_digits_is_identical_to_unknown_cedula():
    _session([])
    unknown = _identificar()
    _session([_reg()])
    wrong = _identificar(last4="9999")
    assert unknown.status_code == wrong.status_code == 200
    assert wrong.json() == unknown.json() == {"estado": "NO_ENCONTRADA", "mensaje": NOT_FOUND_MESSAGE}


def test_identificar_registro_without_celular_never_matches():
    _session([_reg(celular=None), _reg(placa="XYZ99A", celular="")])
    assert _identificar().json() == {"estado": "NO_ENCONTRADA", "mensaje": NOT_FOUND_MESSAGE}


def test_identificar_state_is_computed_only_over_registros_matching_both_factors():
    mine, other = uuid.uuid4(), uuid.uuid4()
    _session([
        _reg(reg_id=mine, respondida=datetime(2026, 9, 3)),
        _reg(reg_id=other, placa="ZZZ11Z", celular="3009998877"),  # same cedula, other celular
    ])
    assert _identificar().json()["estado"] == "YA_RESPONDIDA"
    _session([_reg(reg_id=mine), _reg(reg_id=other, placa="ZZZ11Z", celular="3009998877")])
    registros = _identificar().json()["registros"]
    assert [r["registro_id"] for r in registros] == [str(mine)]


@pytest.mark.parametrize("last4", ["123", "12345", "abcd", "", "12 3"])
def test_identificar_invalid_celular_ultimos4_is_422(last4):
    session = _session()
    assert _identificar(last4=last4).status_code == 422
    assert len(session.executed_statements) <= 1


def test_identificar_missing_celular_ultimos4_is_422():
    _session()
    with TestClient(app) as client:
        assert client.post(IDENTIFICAR, json={"cedula": "1"}).status_code == 422


def test_identificar_strips_non_digits_around_the_four_digits():
    _session([_reg()])
    assert _identificar(last4=" 2233 ").json()["estado"] == "PENDIENTE"


def test_identificar_needs_no_authentication():
    _session([])
    with TestClient(app) as client:
        body = {"cedula": "1", "celular_ultimos4": LAST4}
        assert client.post(IDENTIFICAR, json=body).status_code == 200


def test_identificar_is_rate_limited_per_ip():
    # distinct cedulas: the per-cedula failure lock must not be what trips here
    for n in range(10):
        _session([])
        assert _identificar(cedula=str(1000 + n)).status_code == 200
    _session([])
    assert _identificar(cedula="2000").status_code == 429


# --- respuestas ----------------------------------------------------------------

def test_submit_satisfied_creates_response_without_case():
    rid, row = _target()
    session = _session([row], cls=_CaseFakeSession)
    response = _submit(_payload(rid, observaciones="  Todo bien  "))
    assert response.status_code == 200
    assert response.json() == {"clasificacion": "SATISFECHO", "caso_numero": None, "caso_codigo": None, "primer_nombre": "Ana"}
    (respuesta,) = session.added_of_type(EncuestaRespuesta)
    assert respuesta.registro_id == rid and respuesta.satisfaccion_general == 5
    assert respuesta.observaciones == "Todo bien" and respuesta.autoriza_datos is True
    assert session.added_of_type(CasoDetractor) == []
    assert session.committed is True


def test_submit_blank_observaciones_become_null_and_ns_nr_kept():
    rid, row = _target()
    session = _session([row], cls=_CaseFakeSession)
    body = _payload(rid, observaciones="   ", p_claridad_cobros=None)
    assert _submit(body).status_code == 200
    (respuesta,) = session.added_of_type(EncuestaRespuesta)
    assert respuesta.observaciones is None and respuesta.p_claridad_cobros is None


@pytest.mark.parametrize("score", [1, 2, 3])
def test_submit_detractor_opens_case_and_system_apertura_action(score):
    rid, row = _target()
    session = _session([row], cls=_CaseFakeSession)
    response = _submit(_payload(rid, satisfaccion_general=score))
    assert response.status_code == 200
    assert response.json() == {
        "clasificacion": "DETRACTOR", "caso_numero": 4321, "caso_codigo": "DET-2026-004321",
        "primer_nombre": "Ana",
    }
    (respuesta,) = session.added_of_type(EncuestaRespuesta)
    (caso,) = session.added_of_type(CasoDetractor)
    (accion,) = session.added_of_type(CasoDetractorAccion)
    assert caso.respuesta_id == respuesta.id and caso.estado == "ABIERTO"
    assert accion.caso_id == caso.id and accion.tipo == "APERTURA" and accion.usuario_id is None
    assert accion.descripcion == f"Caso abierto automáticamente: satisfacción general {score}/5"
    assert session.committed is True


def test_submit_boundary_four_opens_no_case():
    rid, row = _target()
    session = _session([row], cls=_CaseFakeSession)
    response = _submit(_payload(rid, satisfaccion_general=4))
    assert response.json()["clasificacion"] == "SATISFECHO"
    assert session.added_of_type(CasoDetractor) == []


def test_submit_consent_no_still_opens_case_and_says_so():
    rid, row = _target()
    session = _session([row], cls=_CaseFakeSession)
    response = _submit(_payload(rid, satisfaccion_general=2, autoriza_datos=False))
    assert response.json()["clasificacion"] == "DETRACTOR"
    (accion,) = session.added_of_type(CasoDetractorAccion)
    assert accion.descripcion == (
        "Caso abierto automáticamente: satisfacción general 2/5 — "
        "el cliente NO autorizó tratamiento de datos"
    )


@pytest.mark.parametrize("override", [
    {"satisfaccion_general": 0}, {"satisfaccion_general": 6}, {"satisfaccion_general": None},
    {"p_servicio_taller": 7}, {"p_servicio_taller": 0}, {"observaciones": "x" * 2001},
    {"autoriza_datos": None}, {"registro_id": "not-a-uuid"},
])
def test_submit_validation_errors_are_422_and_write_nothing(override):
    rid, row = _target()
    session = _session([row], cls=_CaseFakeSession)
    assert _submit(_payload(rid, **override)).status_code == 422
    assert session.added == [] and session.committed is False


def test_submit_missing_matrix_key_is_422():
    rid, row = _target()
    _session([row])
    body = _payload(rid)
    del body["p_calidad_mecanicos"]
    assert _submit(body).status_code == 422


def test_submit_observaciones_at_limit_is_accepted():
    rid, row = _target()
    _session([row], cls=_CaseFakeSession)
    assert _submit(_payload(rid, observaciones="x" * 2000)).status_code == 200


def test_submit_cedula_mismatch_is_indistinguishable_from_unknown_registro():
    rid, row = _target(cedula="99999999")
    session = _session([row], cls=_CaseFakeSession)
    mismatch = _submit(_payload(rid))
    _session([], cls=_CaseFakeSession)
    unknown = _submit(_payload(uuid.uuid4()))
    assert mismatch.status_code == unknown.status_code == 404
    assert mismatch.json() == unknown.json()
    assert session.added == [] and session.committed is False


@pytest.mark.parametrize("celular,last4", [(None, LAST4), ("3009998877", LAST4), (CELULAR, "0000")])
def test_submit_requires_matching_celular_digits_with_the_same_404(celular, last4):
    rid, row = _target(celular=celular)
    session = _session([row], cls=_CaseFakeSession)
    mismatch = _submit(_payload(rid, celular_ultimos4=last4))
    _session([], cls=_CaseFakeSession)
    unknown = _submit(_payload(uuid.uuid4()))
    assert mismatch.status_code == unknown.status_code == 404
    assert mismatch.json() == unknown.json()
    assert session.added == [] and session.committed is False


def test_submit_invalid_celular_ultimos4_is_422():
    rid, row = _target()
    _session([row], cls=_CaseFakeSession)
    assert _submit(_payload(rid, celular_ultimos4="12")).status_code == 422


def test_submit_venta_registro_is_not_found():
    rid, row = _target(tipo="VENTA")
    session = _session([row], cls=_CaseFakeSession)
    assert _submit(_payload(rid)).status_code == 404
    assert session.added == []


def test_submit_already_answered_is_409():
    rid, row = _target(respondida=True)
    session = _session([row], cls=_CaseFakeSession)
    response = _submit(_payload(rid))
    assert response.status_code == 409
    assert response.json()["detail"] == "YA_RESPONDIDA"
    assert session.added == []


def test_submit_unique_violation_race_rolls_back_and_returns_409():
    rid, row = _target()
    session = _session(
        [row], cls=_CaseFakeSession,
        raise_integrity_error=IntegrityError("COMMIT", {}, Exception("uq_encuesta_respuesta_registro_id")),
    )
    response = _submit(_payload(rid, satisfaccion_general=1))
    assert response.status_code == 409
    assert response.json()["detail"] == "YA_RESPONDIDA"
    assert session.rolled_back is True and session.committed is False


def test_submit_other_integrity_error_is_not_reported_as_already_answered():
    """A foreign-key or check violation is a real bug, never a 409 (2026-09-30)."""
    rid, row = _target()
    session = _session(
        [row], cls=_CaseFakeSession,
        raise_integrity_error=IntegrityError("COMMIT", {}, Exception("caso_detractor_respuesta_id_fkey")),
    )
    with pytest.raises(IntegrityError):
        _submit(_payload(rid, satisfaccion_general=1))
    assert session.rolled_back is True and session.committed is False


def test_submit_is_rate_limited_per_ip():
    for _ in range(20):
        rid, row = _target()
        _session([row], cls=_CaseFakeSession)
        assert _submit(_payload(rid)).status_code == 200
    rid, row = _target()
    _session([row], cls=_CaseFakeSession)
    assert _submit(_payload(rid)).status_code == 429
