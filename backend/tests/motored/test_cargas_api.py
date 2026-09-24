"""
Fase 2 "Ingesta", Phase 9 "Adapter + API" (PR9), tasks 9.3/9.4/9.5
(sdd/motored-pedidos-ingesta) — `/api/motored/cargas`. Narrowed by Fase 3
"Cargas: Tipo Declarado" (sdd/motored-cargas-tipo-declarado, Phase 2, task
2.3): `tipo` is now a REQUIRED, caller-declared `Form` field on `POST
/cargas` -- every RBAC/PATCH-state-machine test below that used to upload
without a `tipo` now declares one explicitly (a matching one, so the
non-`tipo` assertion under test is not accidentally masked by a 400/422
from the type gate). The old detection-era tests (task 9.4, "detección de
tipo por firma de encabezado") are replaced by the declared-type contract
tests at the bottom of this file.

RBAC matrix (task 9.3, RED-before-route per this project's strict-TDD
discipline) across EVERY endpoint of the new router: `ADMIN`/`COMPRAS` can
upload/complete/resolve/aplicar/anular; `SUCURSAL`/`CONSULTA` are
read-only. Branch scoping (task 9.5, T19 — the known hot spot: Fase 1's own
verification already caught a real branch-scoping defect there) is proven
separately for `errores`/`errores.csv`. Anulación-guard tests (task 9.5)
prove the empty-corrida-set scenario succeeds unconditionally, and that an
already-`ANULADO` load is a 409, never a silent no-op.

Same `FakeAsyncSession`/`override_motored_db`/`override_motored_user`
convention as `test_rbac_matrix.py`/`test_sucursal_scoping.py` — no live
database, no live MinIO (`storage.subir_archivo`/`storage.descargar_
archivo` are monkeypatched at the module level, mirroring `test_storage.py`'s
own stated precedent of mocking the invoking service's higher-level
function). `get_job_runner` is overridden to a no-op `JobRunner` so an RBAC
test never accidentally exercises the real dry-run pipeline (a different,
separately-tested concern — see `test_ingesta_orquestador.py`).
"""
import io
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import cargas as cargas_api
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.auth import MotoredUser
from app.motored.services.storage import ResultadoSubida
from app.motored.services.trabajos.runner import JobRunner
from tests.motored.conftest import (
    FakeAsyncSession,
    _ExecuteResult,
    override_motored_db,
    override_motored_user,
)

ALL_ROLES = ["ADMIN", "COMPRAS", "SUCURSAL", "CONSULTA"]
WRITE_ROLES = {"ADMIN", "COMPRAS"}

CARGAS_URL = "/api/motored/cargas"


class _NoOpJobRunner(JobRunner):
    """Nunca despacha de verdad -- ver docstring del módulo. Un RBAC test
    solo debe probar el gate de rol, no la ejecución del job real."""

    async def enqueue(self, carga_id, tipo) -> None:
        return None


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "cargas-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "cargas-test-asc360-secret")
    app.dependency_overrides[cargas_api.get_job_runner] = lambda: _NoOpJobRunner()
    yield
    app.dependency_overrides.clear()


def _client_as(role: str, execute_queue) -> TestClient:
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(FakeAsyncSession(execute_queue=execute_queue))
    return TestClient(app)


def _client_scoped_to(*branch_ids, execute_queue) -> TestClient:
    user = MotoredUser(
        user_id=str(uuid.uuid4()), role="SUCURSAL", sucursal_ids=[str(b) for b in branch_ids]
    )
    override_motored_user(user)
    override_motored_db(FakeAsyncSession(execute_queue=execute_queue))
    return TestClient(app)


def _carga(estado="VALIDADO", tipo="INVENTARIO", **overrides) -> CargaArchivo:
    """Filas de `CargaArchivo` construidas a mano NUNCA pasan por
    `db.add()` (nunca se les aplican los `default=` de columna) -- todo
    campo no-Optional del schema `CargaArchivoRead` se fija explícitamente
    acá para que `model_validate` no falle por un `None` inesperado."""
    base = dict(
        id=uuid.uuid4(),
        tipo=tipo,
        origen="EXCEL",
        nombre_archivo="archivo.xlsx",
        hash_sha256="a" * 64,
        ruta_objeto=f"{tipo or 'SIN_TIPO'}/2026/09/x.xlsx",
        bytes=100,
        estado=estado,
        filas_leidas=0,
        filas_validas=0,
        filas_rechazadas=0,
        periodo_desde=None,
        periodo_hasta=None,
        lotes_staged=0,
        ultimo_lote_aplicado=0,
        latido_en=None,
        log=None,
        subido_por=uuid.uuid4(),
        aplicado_en=None,
        created_at=datetime.utcnow(),
    )
    base.update(overrides)
    return CargaArchivo(**base)


def _build_xlsx_bytes(filas: list) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for fila in filas:
        sheet.append(fila)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


_ARCHIVO_SIN_TIPO_RECONOCIBLE = _build_xlsx_bytes([["Columna A", "Columna B"], [1, 2]])
_ARCHIVO_INVENTARIO = _build_xlsx_bytes(
    [["Referencia", "Bodega", "Desc.bodega", "Existencia"], ["REF1", "BA061", "CALI NORTE", 10]]
)


def _mock_subida(monkeypatch):
    monkeypatch.setattr(
        cargas_api.storage, "subir_archivo",
        lambda *a, **k: ResultadoSubida(
            ruta_objeto="X/2026/09/id.xlsx", hash_sha256="deadbeef" * 8
        ),
    )


# ---------------------------------------------------------------------------
# Task 9.3 — RBAC matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ALL_ROLES)
def test_post_cargas_restricted_to_admin_and_compras(role, monkeypatch):
    _mock_subida(monkeypatch)
    client = _client_as(role, execute_queue=[[], []])
    response = client.post(
        CARGAS_URL,
        files={"file": ("inventario.xlsx", _ARCHIVO_INVENTARIO, "application/octet-stream")},
        data={"tipo": "INVENTARIO"},
    )
    if role in WRITE_ROLES:
        assert response.status_code == 202, response.text
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_patch_cargas_restricted_to_admin_and_compras(role):
    carga = _carga(estado="PENDIENTE", tipo="INVENTARIO")
    client = _client_as(role, execute_queue=[[], [carga]])
    response = client.patch(f"{CARGAS_URL}/{carga.id}", json={"periodo_desde": "2026-09-01"})
    if role in WRITE_ROLES:
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_get_cargas_list_allowed_for_every_role(role):
    client = _client_as(role, execute_queue=[[], [_carga()]])
    response = client.get(CARGAS_URL)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("role", ALL_ROLES)
def test_get_carga_by_id_allowed_for_every_role(role):
    carga = _carga()
    client = _client_as(role, execute_queue=[[], [carga]])
    response = client.get(f"{CARGAS_URL}/{carga.id}")
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("role", ALL_ROLES)
def test_get_informe_allowed_for_every_role(role):
    carga = _carga()
    client = _client_as(role, execute_queue=[[], [carga], []])
    response = client.get(f"{CARGAS_URL}/{carga.id}/informe")
    assert response.status_code == 200, response.text


def test_get_informe_computa_variacion_exacta_vs_carga_aplicada_anterior_del_mismo_tipo():
    """Verify-report WARNING #1: the ±40% variance number itself, not just
    HTTP 200. `_carga_or_404`'s query returns the FULL `CargaArchivo` row
    for the carga under inspection; the "anterior" query in `obtener_
    informe` (cargas.py:389-403) is a narrower `select(CargaArchivo.filas_
    validas)`, so its queued row is the bare `int`, not a model instance
    (`FakeAsyncSession.execute` -> `.scalars().first()` just returns
    whatever was queued)."""
    filas_validas_carga_anterior = 80
    filas_validas_carga_nueva = 50
    carga_nueva = _carga(
        estado="VALIDADO", tipo="INVENTARIO", filas_validas=filas_validas_carga_nueva
    )
    client = _client_as(
        "ADMIN",
        execute_queue=[[], [carga_nueva], [filas_validas_carga_anterior]],
    )

    response = client.get(f"{CARGAS_URL}/{carga_nueva.id}/informe")

    assert response.status_code == 200, response.text
    # Hand-computed: (50 - 80) / 80 * 100 = -37.5 -- a real drop, well past
    # the frontend's -40% red-flag threshold's neighborhood (deliberately
    # NOT exactly -40, so this test proves the raw arithmetic, independent
    # of the separately-tested UI threshold).
    variacion_esperada = -37.5
    assert (
        (filas_validas_carga_nueva - filas_validas_carga_anterior)
        / filas_validas_carga_anterior
        * 100
    ) == variacion_esperada
    assert response.json()["variacion_pct_vs_carga_anterior"] == pytest.approx(variacion_esperada)


def test_get_informe_sin_variacion_cuando_no_hay_carga_aplicada_anterior_del_mismo_tipo():
    """Base case: no prior `APLICADO` load of the same `tipo` exists ->
    `anterior_result.scalars().first()` is `None` -> `variacion` stays
    `None` (cargas.py:401-403), never a computed number."""
    carga = _carga(estado="VALIDADO", tipo="INVENTARIO", filas_validas=50)
    client = _client_as("ADMIN", execute_queue=[[], [carga], []])

    response = client.get(f"{CARGAS_URL}/{carga.id}/informe")

    assert response.status_code == 200, response.text
    assert response.json()["variacion_pct_vs_carga_anterior"] is None


@pytest.mark.parametrize("role", ALL_ROLES)
def test_get_errores_allowed_for_every_role(role):
    carga = _carga()
    client = _client_as(role, execute_queue=[[], [carga], [], []])
    response = client.get(f"{CARGAS_URL}/{carga.id}/errores")
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("role", ALL_ROLES)
def test_get_errores_csv_allowed_for_every_role(role):
    carga = _carga()
    client = _client_as(role, execute_queue=[[], [carga], [], []])
    response = client.get(f"{CARGAS_URL}/{carga.id}/errores.csv")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")


@pytest.mark.parametrize("role", ALL_ROLES)
def test_get_preview_allowed_for_every_role(role):
    carga = _carga()
    client = _client_as(role, execute_queue=[[], [carga], []])
    response = client.get(f"{CARGAS_URL}/{carga.id}/preview")
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("role", ALL_ROLES)
def test_post_resolver_restricted_to_admin_and_compras(role):
    carga = _carga()
    client = _client_as(role, execute_queue=[[], [carga]])
    response = client.post(
        f"{CARGAS_URL}/{carga.id}/resolver",
        json={"acciones": [{"codigo_error": "SUCURSAL_NO_ENCONTRADA", "accion": "ignorar"}]},
    )
    if role in WRITE_ROLES:
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_post_aplicar_restricted_to_admin_and_compras(role):
    carga = _carga(estado="VALIDADO", tipo="INVENTARIO")
    client = _client_as(role, execute_queue=[[], [carga], [], []])
    response = client.post(f"{CARGAS_URL}/{carga.id}/aplicar")
    if role in WRITE_ROLES:
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_post_anular_restricted_to_admin_and_compras(role):
    carga = _carga(estado="APLICADO")
    client = _client_as(role, execute_queue=[[], [carga], []])
    response = client.post(f"{CARGAS_URL}/{carga.id}/anular")
    if role in WRITE_ROLES:
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Task 9.5 — SUCURSAL branch scoping on `errores`/`errores.csv` (T19, hot
# spot histórico)
# ---------------------------------------------------------------------------

B1_ID = uuid.uuid4()
B2_ID = uuid.uuid4()


def _error(fila: int, codigo="REFERENCIA_NO_ENCONTRADA") -> CargaError:
    return CargaError(
        id=uuid.uuid4(), carga_id=uuid.uuid4(), fila=fila, columna="X", valor="v",
        codigo_error=codigo, mensaje="m", created_at=datetime.utcnow(),
    )


def test_sucursal_role_sees_only_errores_of_its_own_branch():
    carga = _carga()
    error_b1 = _error(fila=1)
    error_b2 = _error(fila=2)
    staging_map = [(1, B1_ID), (2, B2_ID)]
    client = _client_scoped_to(
        B1_ID, execute_queue=[[], [carga], [error_b1, error_b2], staging_map]
    )

    response = client.get(f"{CARGAS_URL}/{carga.id}/errores")

    assert response.status_code == 200
    filas = {row["fila"] for row in response.json()}
    assert filas == {1}


def test_sucursal_role_never_sees_errores_with_unresolved_sucursal_fail_closed():
    """Un error `SUCURSAL_NO_ENCONTRADA` NO tiene, por definición, una
    `sucursal_id` resuelta en staging -- fail-closed: SUCURSAL nunca lo ve,
    en vez de arriesgar mostrar el de otra sucursal (ver docstring de
    `api/cargas.py`)."""
    carga = _carga()
    error_sin_sucursal = _error(fila=5, codigo="SUCURSAL_NO_ENCONTRADA")
    staging_map = [(5, None)]
    client = _client_scoped_to(
        B1_ID, execute_queue=[[], [carga], [error_sin_sucursal], staging_map]
    )

    response = client.get(f"{CARGAS_URL}/{carga.id}/errores")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("role", ["ADMIN", "COMPRAS", "CONSULTA"])
def test_non_sucursal_roles_see_every_error_unfiltered(role):
    carga = _carga()
    error_b1 = _error(fila=1)
    error_b2 = _error(fila=2)
    client = _client_as(role, execute_queue=[[], [carga], [error_b1, error_b2], []])

    response = client.get(f"{CARGAS_URL}/{carga.id}/errores")

    assert response.status_code == 200
    filas = {row["fila"] for row in response.json()}
    assert filas == {1, 2}


def test_errores_csv_is_also_branch_scoped_for_sucursal():
    carga = _carga()
    error_b1 = _error(fila=1)
    error_b2 = _error(fila=2)
    staging_map = [(1, B1_ID), (2, B2_ID)]
    client = _client_scoped_to(
        B1_ID, execute_queue=[[], [carga], [error_b1, error_b2], staging_map]
    )

    response = client.get(f"{CARGAS_URL}/{carga.id}/errores.csv")

    assert response.status_code == 200
    assert "1" in response.text.splitlines()[1]
    assert len(response.text.splitlines()) == 2  # encabezado + 1 fila (B2 excluida)


# ---------------------------------------------------------------------------
# Task 9.5 — SUCURSAL branch scoping on `preview` (T19): `carga_fila_
# staging` resuelve una sucursal POR FILA, exactamente igual que
# `carga_error` -- el mismo motivo que justifica el filtro de errores
# aplica acá; sin él, un SUCURSAL podía leer el payload crudo (cantidades,
# valores) de OTRA sucursal a través de este endpoint.
# ---------------------------------------------------------------------------


def _fila_staging(fila: int, sucursal_id) -> CargaFilaStaging:
    return CargaFilaStaging(
        id=uuid.uuid4(), carga_id=uuid.uuid4(), fila=fila, lote=1,
        payload={"cantidad": "10"}, sucursal_id=sucursal_id, referencia_id=uuid.uuid4(),
    )


def test_sucursal_role_sees_only_preview_rows_of_its_own_branch():
    carga = _carga()
    fila_b1 = _fila_staging(fila=1, sucursal_id=B1_ID)
    fila_b2 = _fila_staging(fila=2, sucursal_id=B2_ID)
    client = _client_scoped_to(B1_ID, execute_queue=[[], [carga], [fila_b1, fila_b2]])

    response = client.get(f"{CARGAS_URL}/{carga.id}/preview")

    assert response.status_code == 200
    filas = {row["fila"] for row in response.json()}
    assert filas == {1}


def test_sucursal_role_never_sees_preview_rows_with_unresolved_sucursal_fail_closed():
    carga = _carga()
    fila_sin_sucursal = _fila_staging(fila=3, sucursal_id=None)
    client = _client_scoped_to(B1_ID, execute_queue=[[], [carga], [fila_sin_sucursal]])

    response = client.get(f"{CARGAS_URL}/{carga.id}/preview")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("role", ["ADMIN", "COMPRAS", "CONSULTA"])
def test_non_sucursal_roles_see_every_preview_row_unfiltered(role):
    carga = _carga()
    fila_b1 = _fila_staging(fila=1, sucursal_id=B1_ID)
    fila_b2 = _fila_staging(fila=2, sucursal_id=B2_ID)
    client = _client_as(role, execute_queue=[[], [carga], [fila_b1, fila_b2]])

    response = client.get(f"{CARGAS_URL}/{carga.id}/preview")

    assert response.status_code == 200
    filas = {row["fila"] for row in response.json()}
    assert filas == {1, 2}


# ---------------------------------------------------------------------------
# Task 9.5 — anulación guard (empty corrida set)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["PENDIENTE", "VALIDADO", "CON_ERRORES", "APLICADO"])
def test_anular_succeeds_unconditionally_against_empty_corrida_set(estado):
    carga = _carga(estado=estado)
    client = _client_as("ADMIN", execute_queue=[[], [carga], []])

    response = client.post(f"{CARGAS_URL}/{carga.id}/anular")

    assert response.status_code == 200, response.text
    assert response.json()["estado"] == "ANULADO"


def test_anular_ya_anulada_is_409_not_a_silent_noop():
    carga = _carga(estado="ANULADO")
    client = _client_as("ADMIN", execute_queue=[[], [carga]])

    response = client.post(f"{CARGAS_URL}/{carga.id}/anular")

    assert response.status_code == 409


def test_anular_not_found_is_404():
    client = _client_as("ADMIN", execute_queue=[[], []])

    response = client.post(f"{CARGAS_URL}/{uuid.uuid4()}/anular")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Task 9.4/9.5 — PATCH state machine (ADR-9, E10) + período futuro (E7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["VALIDADO", "CON_ERRORES", "APLICADO", "ANULADO"])
def test_patch_outside_pendiente_is_409(estado):
    carga = _carga(estado=estado, tipo="INVENTARIO")
    client = _client_as("ADMIN", execute_queue=[[], [carga]])

    response = client.patch(f"{CARGAS_URL}/{carga.id}", json={"periodo_desde": "2026-09-01"})

    assert response.status_code == 409


def test_patch_future_periodo_is_422():
    carga = _carga(estado="PENDIENTE", tipo="INVENTARIO")
    client = _client_as("ADMIN", execute_queue=[[], [carga]])
    futuro = (date.today() + timedelta(days=5)).isoformat()

    response = client.patch(f"{CARGAS_URL}/{carga.id}", json={"periodo_desde": futuro})

    assert response.status_code == 422


def test_post_cargas_future_periodo_is_422_before_any_write(monkeypatch):
    _mock_subida(monkeypatch)
    called = {"subida": False}
    monkeypatch.setattr(
        cargas_api.storage, "subir_archivo",
        lambda *a, **k: called.__setitem__("subida", True) or ResultadoSubida("x", "y"),
    )
    futuro = (date.today() + timedelta(days=5)).isoformat()
    client = _client_as("ADMIN", execute_queue=[[]])

    response = client.post(
        CARGAS_URL,
        files={"file": ("inventario.xlsx", _ARCHIVO_INVENTARIO, "application/octet-stream")},
        data={"tipo": "INVENTARIO", "periodo_desde": futuro},
    )

    assert response.status_code == 422
    assert called["subida"] is False


def test_patch_no_longer_accepts_tipo_ignores_unknown_field_and_never_dispatches_maestro(monkeypatch):
    """`sdd/motored-cargas-tipo-declarado/design`, D1: `CargaArchivoPatch`
    dropped `tipo` -- an unknown JSON field is silently ignored by pydantic
    (never a 422), `carga.tipo` stays whatever it was declared as at
    upload, and `orquestador.ejecutar_maestro` -- the branch this used to
    dispatch to -- is now structurally unreachable from this endpoint."""
    carga = _carga(estado="PENDIENTE", tipo="INVENTARIO")
    llamado = {"called": False}

    async def _fake_ejecutar_maestro(*args, **kwargs):
        llamado["called"] = True

    monkeypatch.setattr(cargas_api.orquestador, "ejecutar_maestro", _fake_ejecutar_maestro)
    client = _client_as("ADMIN", execute_queue=[[], [carga]])

    response = client.patch(f"{CARGAS_URL}/{carga.id}", json={"tipo": "MAESTRO_BODEGAS"})

    assert response.status_code == 200, response.text
    assert response.json()["tipo"] == "INVENTARIO"
    assert llamado["called"] is False


# ---------------------------------------------------------------------------
# Fase 3 "Cargas: Tipo Declarado" (sdd/motored-cargas-tipo-declarado, Phase
# 2, task 2.3) — `tipo` DECLARADO en `POST /cargas`, reemplaza la vieja
# "detección de tipo por firma de encabezado".
# ---------------------------------------------------------------------------


def test_post_cargas_missing_tipo_is_422_before_any_write(monkeypatch):
    _mock_subida(monkeypatch)
    called = {"subida": False}
    monkeypatch.setattr(
        cargas_api.storage, "subir_archivo",
        lambda *a, **k: called.__setitem__("subida", True) or ResultadoSubida("x", "y"),
    )
    client = _client_as("ADMIN", execute_queue=[[]])

    response = client.post(
        CARGAS_URL,
        files={"file": ("inventario.xlsx", _ARCHIVO_INVENTARIO, "application/octet-stream")},
    )

    assert response.status_code == 422
    assert called["subida"] is False


@pytest.mark.parametrize("tipo_maestro", ["MAESTRO_REFERENCIAS", "MAESTRO_BODEGAS"])
def test_post_cargas_maestro_tipo_is_400_before_any_write(tipo_maestro, monkeypatch):
    called = {"subida": False}
    monkeypatch.setattr(
        cargas_api.storage, "subir_archivo",
        lambda *a, **k: called.__setitem__("subida", True) or ResultadoSubida("x", "y"),
    )
    client = _client_as("ADMIN", execute_queue=[[]])

    response = client.post(
        CARGAS_URL,
        files={"file": ("inventario.xlsx", _ARCHIVO_INVENTARIO, "application/octet-stream")},
        data={"tipo": tipo_maestro},
    )

    assert response.status_code == 400, response.text
    assert called["subida"] is False


def test_post_cargas_tipo_mismatch_is_400_naming_missing_columns(monkeypatch):
    """Declara VENTAS, sube un archivo de INVENTARIO -- coincidencia
    parcial (ratio 3/8, ver `test_ingesta_deteccion.py`), rechazado
    nombrando el tipo declarado y las columnas de VENTAS que faltaron; sin
    escribir nada."""
    called = {"subida": False}
    monkeypatch.setattr(
        cargas_api.storage, "subir_archivo",
        lambda *a, **k: called.__setitem__("subida", True) or ResultadoSubida("x", "y"),
    )
    client = _client_as("ADMIN", execute_queue=[[]])

    response = client.post(
        CARGAS_URL,
        files={"file": ("inventario.xlsx", _ARCHIVO_INVENTARIO, "application/octet-stream")},
        data={"tipo": "VENTAS"},
    )

    assert response.status_code == 400, response.text
    body = response.json()["detail"]
    assert body["tipo_declarado"] == "VENTAS"
    assert body["sin_coincidencia"] is False
    assert len(body["columnas_faltantes"]) > 0
    assert called["subida"] is False


def test_post_cargas_sin_ninguna_coincidencia_is_400_distinguishable_from_mismatch(monkeypatch):
    client = _client_as("ADMIN", execute_queue=[[]])

    response = client.post(
        CARGAS_URL,
        files={"file": ("archivo.xlsx", _ARCHIVO_SIN_TIPO_RECONOCIBLE, "application/octet-stream")},
        data={"tipo": "INVENTARIO"},
    )

    assert response.status_code == 400, response.text
    body = response.json()["detail"]
    assert body["tipo_declarado"] == "INVENTARIO"
    assert body["sin_coincidencia"] is True
    assert body["columnas_faltantes"] == []


def test_post_cargas_success_matches_declared_type_response_shape(monkeypatch):
    """Design D3: la respuesta se angosta a `{carga_id, duplicado_de}` --
    ya no expone `tipo_detectado`/`requiere_tipo`/`requiere_periodo`."""
    _mock_subida(monkeypatch)
    client = _client_as("ADMIN", execute_queue=[[], []])

    response = client.post(
        CARGAS_URL,
        files={"file": ("inventario.xlsx", _ARCHIVO_INVENTARIO, "application/octet-stream")},
        data={"tipo": "INVENTARIO"},
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert set(body.keys()) == {"carga_id", "duplicado_de"}
    assert body["duplicado_de"] is None


def test_post_cargas_duplicate_hash_is_flagged_never_blocked(monkeypatch):
    _mock_subida(monkeypatch)
    carga_previa_id = uuid.uuid4()
    client = _client_as("ADMIN", execute_queue=[[], [carga_previa_id]])

    response = client.post(
        CARGAS_URL,
        files={"file": ("inventario.xlsx", _ARCHIVO_INVENTARIO, "application/octet-stream")},
        data={"tipo": "INVENTARIO"},
    )

    assert response.status_code == 202, response.text
    assert response.json()["duplicado_de"] == str(carga_previa_id)


# ---------------------------------------------------------------------------
# Phase 3 (sdd/motored-ventas-perdidas-bot, design D1/D4) — 4 pre-existing
# bugfixes surfaced by the bot's `origen='BOT'` rows, plus the PATCH/anular
# BOT guards.
# ---------------------------------------------------------------------------


def _client_with_session(role: str, session: "FakeAsyncSession") -> TestClient:
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(session)
    return TestClient(app)


def _extraer_predicados(stmt) -> list:
    """Post-Phase-3 review, finding #3: camina el WHERE compilado (nivel
    superior, unido por AND) de `stmt` y devuelve `(nombre_columna,
    operador, valor)` por cada comparación DIRECTA columna-vs-literal.
    Usado por `_FilteringFakeSession` para probar que un filtro (origen,
    ventana de fechas) REALMENTE determina qué filas sobreviven, en vez de
    solo verificar que un string aparece en algún bind param del statement
    compilado -- esa aserción vieja (`"EXCEL" in stmt.compile().params.
    values()`) pasaba igual con un filtro atado a la columna equivocada, o
    directamente ausente (un no-op). Los nodos OR (p.ej. las cláusulas de
    período `periodo_hasta IS NULL OR periodo_hasta >= desde`) no tienen
    `.left`/`.right` de nivel superior -- se saltean sin error, esos casos
    ya están cubiertos por otros tests (los `422` de rango)."""
    whereclause = getattr(stmt, "whereclause", None)
    if whereclause is None:
        return []
    clausulas = getattr(whereclause, "clauses", [whereclause])
    predicados = []
    for clausula in clausulas:
        left = getattr(clausula, "left", None)
        right = getattr(clausula, "right", None)
        operador = getattr(clausula, "operator", None)
        nombre_columna = getattr(left, "key", None)
        if nombre_columna is None or operador is None or not hasattr(right, "value"):
            continue
        predicados.append((nombre_columna, operador, right.value))
    return predicados


class _FilteringFakeSession(FakeAsyncSession):
    """Como `FakeAsyncSession`, pero filtra la página encolada por los
    predicados REALES extraídos del `select` compilado antes de
    devolverla -- ver `_extraer_predicados`. Una fila candidata sin el
    atributo que un predicado necesita se excluye (fail-closed), no se deja
    pasar por descuido."""

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        if not self._execute_queue:
            raise AssertionError(
                "FakeAsyncSession.execute() called more times than expected "
                "— update the test's execute_queue."
            )
        rows = self._execute_queue.pop(0)
        predicados = _extraer_predicados(stmt)
        if predicados:
            rows = [
                row for row in rows
                if all(
                    hasattr(row, nombre) and operador(getattr(row, nombre), valor)
                    for nombre, operador, valor in predicados
                )
            ]
        # `_CandidataAnterior` (más abajo) simula una fila de un `select`
        # PROYECTADO (una sola columna, no la entidad completa) -- una vez
        # filtrada, la consulta real solo devuelve el escalar, nunca el
        # wrapper que carga los campos extra necesarios para filtrar.
        rows = [row.valor if hasattr(row, "valor") else row for row in rows]
        return _ExecuteResult(rows)


def test_get_cargas_default_origen_filters_to_excel_only():
    """Task 3.1/3.2 + review finding #3: no `origen` param -> defaults to
    `EXCEL`. Queues BOTH an EXCEL and a BOT row as available candidates and
    proves the response only contains the EXCEL one -- a filter bound to
    the wrong column, or no filter at all, would leak the BOT row into this
    response and fail this assertion."""
    carga_excel = _carga(origen="EXCEL")
    carga_bot = _carga(
        origen="BOT", tipo="DEMANDA_PERDIDA", estado="APLICADO",
        nombre_archivo=None, hash_sha256=None, ruta_objeto=None, bytes=None,
    )
    session = _FilteringFakeSession(execute_queue=[[], [carga_excel, carga_bot]])
    client = _client_with_session("ADMIN", session)

    response = client.get(CARGAS_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body] == [str(carga_excel.id)]
    assert all(row["origen"] == "EXCEL" for row in body)


def test_get_cargas_origen_bot_sin_desde_hasta_is_422():
    """Task 3.1/3.2: `origen=BOT` without both `desde` and `hasta` is
    rejected before touching the DB -- an unbounded BOT scan is exactly the
    volume problem design D1 exists to prevent."""
    session = FakeAsyncSession(execute_queue=[[]])
    client = _client_with_session("ADMIN", session)

    response = client.get(CARGAS_URL, params={"origen": "BOT"})

    assert response.status_code == 422


def test_get_cargas_origen_bot_con_rango_mayor_a_31_dias_is_422():
    session = FakeAsyncSession(execute_queue=[[]])
    client = _client_with_session("ADMIN", session)

    response = client.get(
        CARGAS_URL,
        params={"origen": "BOT", "desde": "2026-01-01", "hasta": "2026-03-01"},
    )

    assert response.status_code == 422


def test_get_cargas_origen_bot_hasta_anterior_a_desde_is_422():
    """Review finding #1 (post-Phase-3): an inverted range (`hasta` before
    `desde`) yields a NEGATIVE `(hasta - desde).days`, which silently
    passes the `> 31` check -- must be rejected explicitly instead of
    leaking through as a seemingly-valid, unbounded-in-practice request."""
    session = FakeAsyncSession(execute_queue=[[]])
    client = _client_with_session("ADMIN", session)

    response = client.get(
        CARGAS_URL,
        params={"origen": "BOT", "desde": "2026-09-24", "hasta": "2026-09-01"},
    )

    assert response.status_code == 422


def test_get_cargas_origen_bot_con_rango_valido_filtra_por_origen_bot():
    """Task 3.1/3.2 + review finding #1/#3: proves BOTH that only
    BOT-origin rows survive AND that the date window is actually bound
    against `created_at` (the column that has a real value on every BOT
    row) -- `periodo_desde`/`periodo_hasta` are always NULL for BOT rows
    (design D1: a bot header never declares a period), so filtering on
    those columns would be a no-op that bounds nothing. A BOT row created
    OUTSIDE the requested window must be excluded."""
    carga_excel = _carga(origen="EXCEL", created_at=datetime(2026, 9, 10))
    carga_bot_en_rango = _carga(
        origen="BOT", tipo="DEMANDA_PERDIDA", estado="APLICADO",
        nombre_archivo=None, hash_sha256=None, ruta_objeto=None, bytes=None,
        created_at=datetime(2026, 9, 10),
    )
    carga_bot_fuera_de_rango = _carga(
        origen="BOT", tipo="DEMANDA_PERDIDA", estado="APLICADO",
        nombre_archivo=None, hash_sha256=None, ruta_objeto=None, bytes=None,
        created_at=datetime(2026, 8, 1),
    )
    session = _FilteringFakeSession(
        execute_queue=[[], [carga_excel, carga_bot_en_rango, carga_bot_fuera_de_rango]]
    )
    client = _client_with_session("ADMIN", session)

    response = client.get(
        CARGAS_URL, params={"origen": "BOT", "desde": "2026-09-01", "hasta": "2026-09-24"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body] == [str(carga_bot_en_rango.id)]


@dataclass
class _CandidataAnterior:
    """Envoltorio mínimo para simular una fila candidata de un `select`
    PROYECTADO (`select(CargaArchivo.filas_validas)`, no la entidad
    completa) que además expone los campos que la query realmente filtra
    (`origen`, `tipo`, `estado`, `id`) -- necesarios para que
    `_FilteringFakeSession` evalúe los predicados reales. Una consulta real
    jamás ve este wrapper: el filtrado ya pasó server-side y solo llega el
    escalar `valor`."""

    origen: str
    tipo: str
    estado: str
    id: uuid.UUID
    valor: int


def test_get_informe_variacion_query_filtra_por_origen_excel():
    """Task 3.3/3.4 + review finding #3: queues BOTH an EXCEL and a BOT
    candidate for the 'previous APLICADO carga' query and proves the BOT
    one is never picked as the variance baseline -- the old test only
    checked that 'EXCEL' appeared somewhere among the compiled bind params,
    which would pass even if the filter were bound to `tipo`/`estado`
    instead of `origen`."""
    carga = _carga(estado="VALIDADO", tipo="INVENTARIO", filas_validas=50)
    candidata_excel = _CandidataAnterior(
        origen="EXCEL", tipo="INVENTARIO", estado="APLICADO", id=uuid.uuid4(), valor=80,
    )
    candidata_bot = _CandidataAnterior(
        origen="BOT", tipo="INVENTARIO", estado="APLICADO", id=uuid.uuid4(), valor=999,
    )
    session = _FilteringFakeSession(
        execute_queue=[[], [carga], [candidata_excel, candidata_bot]]
    )
    client = _client_with_session("ADMIN", session)

    response = client.get(f"{CARGAS_URL}/{carga.id}/informe")

    assert response.status_code == 200, response.text
    # 999 (the BOT candidate) would have produced a wildly different
    # number -- proves the EXCEL candidate (80) is the one actually used.
    variacion_esperada = ((50 - 80) / 80) * 100
    assert response.json()["variacion_pct_vs_carga_anterior"] == pytest.approx(variacion_esperada)


def test_get_carga_by_id_bot_row_with_null_nombre_archivo_does_not_500():
    """Task 3.5/3.6: Phase 1 made `nombre_archivo`/`hash_sha256`/
    `ruta_objeto`/`bytes` nullable at the DB level for BOT rows;
    `CargaArchivoRead.nombre_archivo` was still a required `str`, which
    500s the instant a BOT row is read."""
    carga_bot = _carga(
        origen="BOT", tipo="DEMANDA_PERDIDA", estado="APLICADO",
        nombre_archivo=None, hash_sha256=None, ruta_objeto=None, bytes=None,
    )
    client = _client_as("ADMIN", execute_queue=[[], [carga_bot]])

    response = client.get(f"{CARGAS_URL}/{carga_bot.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["nombre_archivo"] is None
    assert body["origen"] == "BOT"


def test_patch_carga_bot_origin_is_409():
    """Task 3.7/3.8 (design D1): a BOT-origin carga_archivo never declares
    a period upfront -- PATCH must reject it explicitly, independent of
    `estado`. Deliberately uses `estado='PENDIENTE'` (never true in
    practice for a BOT row, born APLICADO -- design D1) so this test proves
    a dedicated `origen` guard exists, instead of accidentally passing
    because the pre-existing `estado != PENDIENTE` check happens to also
    catch every real BOT row."""
    carga_bot = _carga(
        origen="BOT", tipo="DEMANDA_PERDIDA", estado="PENDIENTE",
        nombre_archivo=None, hash_sha256=None, ruta_objeto=None, bytes=None,
    )
    client = _client_as("ADMIN", execute_queue=[[], [carga_bot]])

    response = client.patch(f"{CARGAS_URL}/{carga_bot.id}", json={"periodo_desde": "2026-09-01"})

    assert response.status_code == 409


def test_anular_carga_bot_origin_delegates_to_anular_registro_bot(monkeypatch):
    """Task 3.7/3.8 (design D4): an ADMIN web anular on a BOT row must NOT
    run the EXCEL staging-delete flow -- it delegates to
    `services.demanda_perdida_bot.anular_registro_bot(db, carga, actor,
    validar_ventana=False)`."""
    carga_bot = _carga(
        origen="BOT", tipo="DEMANDA_PERDIDA", estado="APLICADO",
        nombre_archivo=None, hash_sha256=None, ruta_objeto=None, bytes=None,
    )
    llamadas = []

    async def _fake_anular_registro_bot(db, carga, actor, validar_ventana=False):
        llamadas.append((carga.id, actor, validar_ventana))
        carga.estado = "ANULADO"

    monkeypatch.setattr(
        cargas_api.demanda_perdida_bot_mod, "anular_registro_bot", _fake_anular_registro_bot
    )
    client = _client_as("ADMIN", execute_queue=[[], [carga_bot]])

    response = client.post(f"{CARGAS_URL}/{carga_bot.id}/anular")

    assert response.status_code == 200, response.text
    assert response.json()["estado"] == "ANULADO"
    assert len(llamadas) == 1
    assert llamadas[0][0] == carga_bot.id
    assert llamadas[0][2] is False
