"""
Bulk upload of referencias: the "Código de referencia sustituta" may point to
a referencia created in the SAME file, not only to one already in the DB
(odd/tasks/motored-sustituta-mismo-archivo.md, T1).

Contract under test:
- A code present in the file under the SAME proveedor is a valid target
  (the same-proveedor rule still holds for in-file targets).
- Persistence is two-pass: every row is upserted WITHOUT the in-file
  sustituta first, then the links are set -- a real Postgres would reject an
  INSERT whose FK points to a row inserted later. `_FkCheckingSession`
  simulates exactly that check at every autoflush/flush/commit point.
- Setting the link keeps the existing side effect: the substituted
  referencia ends up `activa=False`.
- Self-reference and cycles within the file are clear row errors.
- `validar` (dry-run) and `carga` give the same verdict.
"""
import io
import uuid
from typing import Iterable, Optional, Set

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.main import app
from app.motored.api.carga import _resolve_referencia_relaciones
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.services.auth import MotoredUser
from app.motored.services.carga import procesar_carga
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

CARGA_URL = "/api/motored/maestros/referencia/carga"
VALIDAR_URL = "/api/motored/maestros/referencia/carga/validar"
CARGA_EXCEL_URL = "/api/motored/maestros/referencia/carga/excel"
VALIDAR_EXCEL_URL = "/api/motored/maestros/referencia/carga/excel/validar"


class _FkCheckingSession(FakeAsyncSession):
    """`FakeAsyncSession` plus the one Postgres rule this feature depends on:
    `referencia.sustituida_por` must point to a row that is ALREADY inserted
    (or already in the DB) when the pending INSERTs are flushed. Checked at
    every point a real `AsyncSession` would flush: `execute()` (autoflush),
    `flush()` and `commit()`. Pending objects are inserted in `add()` order,
    like SQLAlchemy does for a table with no ORM relationship declared."""

    def __init__(self, db_ids: Optional[Iterable[uuid.UUID]] = None, **kwargs):
        super().__init__(**kwargs)
        self._existing_ids: Set[uuid.UUID] = set(db_ids or [])
        self._loaded: list = []
        self.flush_count = 0

    def _simulate_flush(self) -> None:
        # Loaded (already persisted) rows first: they can only be UPDATEd.
        for obj in [*self._loaded, *self.added_of_type(Referencia)]:
            if obj.sustituida_por is not None and obj.sustituida_por not in self._existing_ids:
                raise IntegrityError(
                    "INSERT/UPDATE referencia", {},
                    Exception("violates foreign key constraint referencia_sustituida_por_fkey"),
                )
            self._existing_ids.add(obj.id)

    async def execute(self, stmt):
        self._simulate_flush()
        result = await super().execute(stmt)
        self._loaded.extend(r for r in result.scalars().all() if isinstance(r, Referencia))
        return result

    async def flush(self):
        self._simulate_flush()
        self.flush_count += 1

    async def commit(self):
        self._simulate_flush()
        await super().commit()


def _proveedor(codigo: str = "HMCL") -> Proveedor:
    return Proveedor(id=uuid.uuid4(), codigo=codigo, nombre=codigo, es_principal=True)


def _by_codigo(session: FakeAsyncSession) -> dict:
    return {r.codigo: r for r in session.added_of_type(Referencia)}


def _xlsx_bytes(headers, rows) -> bytes:
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _upload(name: str, content: bytes) -> dict:
    return {"file": (name, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "sustituta-archivo-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "sustituta-archivo-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    yield
    app.dependency_overrides.clear()


CHAIN_ROWS = [
    {"codigo": "A", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "B"},
    {"codigo": "B", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "C"},
    {"codigo": "C", "proveedor_codigo": "HMCL"},
]


class TestResolverAcceptsTargetsFromTheSameFile:
    async def test_chain_of_new_codes_in_the_same_file_resolves_without_errors(self):
        # proveedor lookup, sustituta lookup (nothing in the DB)
        session = FakeAsyncSession(execute_queue=[[_proveedor()], []])

        resolved, errores = await _resolve_referencia_relaciones(session, "referencia", CHAIN_ROWS)

        assert errores == []
        # In-file targets are never set in the first pass: the id does not
        # exist yet, and the FK would fail on INSERT.
        assert all("sustituida_por" not in fila for fila in resolved)

    async def test_self_reference_is_a_row_error(self):
        session = FakeAsyncSession(execute_queue=[[_proveedor()], []])
        filas = [{"codigo": "A", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "A"}]

        _, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert [e["fila"] for e in errores] == [1]
        assert "Código de referencia sustituta" in errores[0]["motivo"]
        assert "sí misma" in errores[0]["motivo"]

    async def test_self_reference_is_a_row_error_even_when_the_code_exists_in_the_db(self):
        proveedor = _proveedor()
        existente = Referencia(id=uuid.uuid4(), codigo="A", proveedor_id=proveedor.id, unidad_empaque=1)
        session = FakeAsyncSession(execute_queue=[[proveedor], [existente]])
        filas = [{"codigo": "A", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "A"}]

        _, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert [e["fila"] for e in errores] == [1]
        assert "sí misma" in errores[0]["motivo"]

    async def test_cycle_within_the_file_is_a_row_error_on_every_row_of_the_cycle(self):
        session = FakeAsyncSession(execute_queue=[[_proveedor()], []])
        filas = [
            {"codigo": "A", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "B"},
            {"codigo": "B", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "C"},
            {"codigo": "C", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "A"},
            {"codigo": "D", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "A"},
        ]

        _, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        # D only points INTO the cycle; it is not part of it.
        assert sorted(e["fila"] for e in errores) == [1, 2, 3]
        for error in errores:
            assert "Código de referencia sustituta" in error["motivo"]
            assert "ciclo" in error["motivo"]
        # Each row reads the cycle starting from itself.
        motivos = {e["fila"]: e["motivo"] for e in errores}
        assert "A -> B -> C -> A" in motivos[1]
        assert "B -> C -> A -> B" in motivos[2]
        assert "C -> A -> B -> C" in motivos[3]

    async def test_target_in_the_file_under_another_proveedor_is_a_row_error(self):
        hmcl, otro = _proveedor("HMCL"), _proveedor("OTRO")
        session = FakeAsyncSession(execute_queue=[[hmcl, otro], []])
        filas = [
            {"codigo": "A", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "B"},
            {"codigo": "B", "proveedor_codigo": "OTRO"},
        ]

        resolved, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert [e["fila"] for e in errores] == [1]
        assert "Código de referencia sustituta" in errores[0]["motivo"]
        assert "otro proveedor" in errores[0]["motivo"]
        assert "La referencia sustituta debe ser del mismo proveedor." in errores[0]["motivo"]
        assert "Homologados" not in errores[0]["motivo"]
        assert "sustituida_por" not in resolved[0]

    async def test_code_in_neither_db_nor_file_keeps_the_existing_row_error(self):
        session = FakeAsyncSession(execute_queue=[[_proveedor()], []])
        filas = [
            {"codigo": "A", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "GHOST"},
            {"codigo": "B", "proveedor_codigo": "HMCL"},
        ]

        _, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

        assert [e["fila"] for e in errores] == [1]
        assert "GHOST" in errores[0]["motivo"]
        assert "no corresponde" in errores[0]["motivo"]


class TestTwoPassPersistence:
    def test_chain_a_b_c_all_new_in_the_same_file_is_persisted_and_linked(self):
        proveedor = _proveedor()
        # probe, proveedor lookup, sustituta lookup (none in DB),
        # replace plan: all referencias (none), all proveedores
        session = _FkCheckingSession(execute_queue=[[], [proveedor], [], [], [proveedor]])
        override_motored_db(session)

        with TestClient(app) as client:
            response = client.post(CARGA_URL, json={"filas": CHAIN_ROWS, "confirmar_reemplazo": True})

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True, body
        assert body["insertados"] == 3
        refs = _by_codigo(session)
        assert refs["A"].sustituida_por == refs["B"].id
        assert refs["B"].sustituida_por == refs["C"].id
        assert refs["C"].sustituida_por is None
        # Existing side effect: a substituted referencia is inactive.
        assert refs["A"].activa is False
        assert refs["B"].activa is False
        assert refs["C"].activa is True
        assert session.flush_count >= 1
        assert session.committed is True

    def test_target_listed_before_its_source_is_also_linked(self):
        proveedor = _proveedor()
        session = _FkCheckingSession(execute_queue=[[], [proveedor], [], [], [proveedor]])
        override_motored_db(session)
        filas = [
            {"codigo": "NEW", "proveedor_codigo": "HMCL"},
            {"codigo": "OLD", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "NEW"},
        ]

        with TestClient(app) as client:
            body = client.post(CARGA_URL, json={"filas": filas, "confirmar_reemplazo": True}).json()

        assert body["ok"] is True, body
        refs = _by_codigo(session)
        assert refs["OLD"].sustituida_por == refs["NEW"].id
        assert refs["OLD"].activa is False

    async def test_existing_db_referencia_can_point_to_a_new_one_in_the_same_file(self):
        proveedor = _proveedor()
        existente = Referencia(
            id=uuid.uuid4(), codigo="OLD", proveedor_id=proveedor.id, unidad_empaque=1, activa=True, homologados=[]
        )
        # proveedor lookup, sustituta lookup (NEW not in DB), replace plan: all referencias, all proveedores
        session = _FkCheckingSession(
            db_ids=[existente.id], execute_queue=[[proveedor], [], [existente], [proveedor]]
        )
        filas = [
            {"codigo": "OLD", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "NEW"},
            {"codigo": "NEW", "proveedor_codigo": "HMCL"},
        ]

        resolved, errores = await _resolve_referencia_relaciones(session, "referencia", filas)
        resultado = await procesar_carga(
            session, "referencia", resolved, errores_previos=errores, confirmar_reemplazo=True)

        assert resultado.ok is True, resultado
        assert resultado.actualizados == 1 and resultado.insertados == 1
        nueva = _by_codigo(session)["NEW"]
        assert existente.sustituida_por == nueva.id
        assert existente.activa is False

    def test_cycle_blocks_the_whole_file_and_writes_nothing(self):
        proveedor = _proveedor()
        session = _FkCheckingSession(execute_queue=[[], [proveedor], []])
        override_motored_db(session)
        filas = [
            {"codigo": "A", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "B"},
            {"codigo": "B", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "A"},
            {"codigo": "C", "proveedor_codigo": "HMCL"},
        ]

        with TestClient(app) as client:
            body = client.post(CARGA_URL, json={"filas": filas}).json()

        assert body["ok"] is False
        assert sorted(e["fila"] for e in body["errores"]) == [1, 2]
        assert session.added == []
        assert session.committed is False


class TestValidarGivesTheSameVerdictAsCarga:
    @pytest.mark.parametrize(
        "filas, ok_esperado",
        [
            (CHAIN_ROWS, True),
            (
                [
                    {"codigo": "A", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "B"},
                    {"codigo": "B", "proveedor_codigo": "HMCL", "sustituida_por_codigo": "A"},
                ],
                False,
            ),
        ],
    )
    def test_validar_matches_carga(self, filas, ok_esperado):
        proveedor = _proveedor()
        session = FakeAsyncSession(execute_queue=[[], [proveedor], [], [], [proveedor]])
        override_motored_db(session)

        with TestClient(app) as client:
            body = client.post(VALIDAR_URL, json={"filas": filas}).json()

        assert body["ok"] is ok_esperado, body
        assert session.added == []
        assert session.committed is False


class TestExcelEndpoints:
    HEADERS = ["Código", "Código del proveedor", "Código de referencia sustituta"]
    ROWS = [["A", "HMCL", "B"], ["B", "HMCL", "C"], ["C", "HMCL", ""]]

    def test_xlsx_chain_in_the_same_file_uploads_and_links(self):
        proveedor = _proveedor()
        session = _FkCheckingSession(execute_queue=[[], [proveedor], [], [], [proveedor]])
        override_motored_db(session)

        with TestClient(app) as client:
            response = client.post(
                CARGA_EXCEL_URL + "?confirmar_reemplazo=true",
                files=_upload("referencias.xlsx", _xlsx_bytes(self.HEADERS, self.ROWS)),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True, body
        refs = _by_codigo(session)
        assert refs["A"].sustituida_por == refs["B"].id
        assert refs["B"].sustituida_por == refs["C"].id
        assert session.committed is True

    def test_xlsx_validar_accepts_the_same_chain(self):
        proveedor = _proveedor()
        session = FakeAsyncSession(execute_queue=[[], [proveedor], [], [], [proveedor]])
        override_motored_db(session)

        with TestClient(app) as client:
            response = client.post(
                VALIDAR_EXCEL_URL, files=_upload("referencias.xlsx", _xlsx_bytes(self.HEADERS, self.ROWS))
            )

        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert session.committed is False
