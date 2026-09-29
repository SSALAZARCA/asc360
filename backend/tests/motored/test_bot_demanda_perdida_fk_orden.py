"""
Regression: `POST /api/motored/bot/demanda-perdida` returned 500 in production
(2026-09-29) with `ForeignKeyViolationError ... demanda_perdida_carga_id_fkey
... Key (carga_id) is not present in table "carga_archivo"`.

Cause: the Motored session is built with `autoflush=False`
(`app/motored/database.py`). `_agregar_registro` did `db.add(CargaArchivo)`
and then executed the Core `INSERT INTO demanda_perdida ... ON CONFLICT`
right away. That statement goes straight to Postgres, while the
`carga_archivo` row was still only pending in the unit of work, so the FK
check failed. The plain `FakeAsyncSession` never enforced FKs, so no test
ever saw it.

`_FkEnforcingSession` adds exactly the Postgres rules this path depends on,
with the same `autoflush=False` semantics as production:
- `execute()` does NOT flush pending ORM objects.
- A Core insert into `demanda_perdida` needs its `carga_id` to be a
  `carga_archivo` row that is already flushed (or already in the DB).
- Flushing a `demanda_perdida_bot_linea` needs its `carga_id` flushed too.
- Flushing a `carga_archivo` whose id already exists raises the real
  `carga_archivo_pkey` violation (the idempotency-key race), now possibly at
  `flush()` time instead of `commit()` time.
Pending objects are flushed in `add()` order (no ORM relationship is
declared between these models).
"""
import uuid
from decimal import Decimal
from typing import Iterable, Optional, Set

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.main import app
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.services.reloj import hoy_bogota
from tests.motored.conftest import AdditiveDemandaPerdidaFakeSession, override_motored_db
from tests.motored.test_bot_demanda_perdida_api import (
    BOT_URL,
    _asesor,
    _carga_bot,
    _headers,
    _linea_bot,
    _sucursal,
)

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


def _fk_error(tabla: str, constraint: str) -> IntegrityError:
    return IntegrityError(
        f"INSERT {tabla}", {},
        Exception(
            f'insert or update on table "{tabla}" violates foreign key constraint "{constraint}"'
        ),
    )


class _FkEnforcingSession(AdditiveDemandaPerdidaFakeSession):
    def __init__(
        self,
        *,
        carga_ids_en_db: Optional[Iterable[uuid.UUID]] = None,
        referencia_ids_en_db: Optional[Iterable[uuid.UUID]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._carga_ids_en_db: Set[uuid.UUID] = set(carga_ids_en_db or [])
        self._referencia_ids_en_db = (
            None if referencia_ids_en_db is None else set(referencia_ids_en_db)
        )
        self._carga_ids_flusheadas: Set[uuid.UUID] = set()
        self._flusheados = 0
        self.flush_count = 0

    def _carga_existe(self, carga_id) -> bool:
        return carga_id in self._carga_ids_en_db or carga_id in self._carga_ids_flusheadas

    def _simular_flush(self) -> None:
        pendientes = self.added[self._flusheados:]
        for obj in pendientes:
            if isinstance(obj, CargaArchivo):
                if obj.id in self._carga_ids_en_db:
                    raise IntegrityError(
                        "INSERT carga_archivo", {},
                        Exception(
                            'duplicate key value violates unique constraint "carga_archivo_pkey"'
                        ),
                    )
                self._carga_ids_flusheadas.add(obj.id)
            elif isinstance(obj, DemandaPerdidaBotLinea) and not self._carga_existe(obj.carga_id):
                raise _fk_error("demanda_perdida_bot_linea", "demanda_perdida_bot_linea_carga_id_fkey")
            self._flusheados += 1

    async def execute(self, stmt):
        tabla = getattr(getattr(stmt, "table", None), "name", None)
        if type(stmt).__name__ == "Insert" and tabla == "demanda_perdida":
            valores = stmt.compile().construct_params()
            if not self._carga_existe(valores["carga_id"]):
                raise _fk_error("demanda_perdida", "demanda_perdida_carga_id_fkey")
            if (
                self._referencia_ids_en_db is not None
                and valores["referencia_id"] not in self._referencia_ids_en_db
            ):
                raise _fk_error("demanda_perdida", "demanda_perdida_referencia_id_fkey")
        return await super().execute(stmt)

    async def flush(self):
        self._simular_flush()
        self.flush_count += 1

    async def commit(self):
        self._simular_flush()
        await super().commit()


def _client(execute_queue, **session_kwargs):
    # [[]] = readiness probe, same convention as `_client_with_queue`.
    session = _FkEnforcingSession(execute_queue=[[]] + list(execute_queue), **session_kwargs)
    override_motored_db(session)
    return TestClient(app), session


def _payload(sucursal_id, *referencia_cantidades) -> dict:
    return {
        "sucursal_id": str(sucursal_id),
        "metodo": "MANUAL",
        "lineas": [
            {"referencia_id": str(referencia_id), "cantidad": cantidad}
            for referencia_id, cantidad in referencia_cantidades
        ],
    }


def test_registrar_flushes_carga_before_the_demanda_perdida_upsert_references_it():
    """The production 500: the Core upsert ran while `carga_archivo` was
    still pending. Must succeed, with both deltas applied, in one commit."""
    sucursal_id = uuid.uuid4()
    referencia_a = uuid.uuid4()
    referencia_b = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[sucursal_id])
    lineas = [
        _linea_bot(carga_id=idempotency_key, usuario_id=asesor.id, sucursal_id=sucursal_id,
                   referencia_id=referencia_a, cantidad=Decimal("3")),
        _linea_bot(carga_id=idempotency_key, usuario_id=asesor.id, sucursal_id=sucursal_id,
                   referencia_id=referencia_b, cantidad=Decimal("5")),
    ]
    client, session = _client(
        [
            [asesor],  # actor lookup
            [_sucursal(id=sucursal_id)],  # sucursal exists+activa
            [],  # idempotency pre-check: no existing carga
            lineas,  # _serializar_registro re-select
        ]
    )

    response = client.post(
        f"{BOT_URL}/demanda-perdida",
        json=_payload(sucursal_id, (referencia_a, 3), (referencia_b, 5)),
        headers=_headers(1, idempotency_key=idempotency_key),
    )

    assert response.status_code == 201, response.text
    assert session.committed is True
    assert session.rolled_back is False
    assert session.cantidad_actual(
        fecha=hoy_bogota(), sucursal_id=sucursal_id, referencia_id=referencia_a
    ) == Decimal("3")
    assert session.cantidad_actual(
        fecha=hoy_bogota(), sucursal_id=sucursal_id, referencia_id=referencia_b
    ) == Decimal("5")
    assert len(session.added_of_type(DemandaPerdidaBotLinea)) == 2


def test_idempotency_key_race_surfacing_at_flush_is_still_an_idempotent_replay():
    """With the early flush, the `carga_archivo_pkey` violation of two
    concurrent requests with the SAME Idempotency-Key can surface at
    `flush()` instead of `commit()`. It must still become the same 200
    replay, never a 500."""
    sucursal_id = uuid.uuid4()
    referencia_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[sucursal_id])
    carga_repetida = _carga_bot(id=idempotency_key, subido_por=asesor.id)
    linea_repetida = _linea_bot(
        carga_id=idempotency_key, usuario_id=asesor.id, sucursal_id=sucursal_id,
        referencia_id=referencia_id, cantidad=Decimal("2"),
    )
    client, session = _client(
        [
            [asesor],  # actor lookup
            [_sucursal(id=sucursal_id)],  # sucursal exists+activa
            [],  # idempotency pre-check: the other racer has not committed yet
            [carga_repetida],  # post-IntegrityError re-select
            [linea_repetida],  # _serializar_registro re-select
        ],
        # The other racer's row lands between the pre-check and our flush.
        carga_ids_en_db=[idempotency_key],
    )

    response = client.post(
        f"{BOT_URL}/demanda-perdida",
        json=_payload(sucursal_id, (referencia_id, 2)),
        headers=_headers(1, idempotency_key=idempotency_key),
    )

    assert response.status_code == 200, response.text
    assert response.json()["carga_id"] == str(idempotency_key)
    assert session.rolled_back is True
    assert session.committed is False
    # The header is flushed BEFORE any delta: the PK failure stops the
    # request before it ever touches `demanda_perdida`.
    assert not any(
        getattr(getattr(stmt, "table", None), "name", None) == "demanda_perdida"
        for stmt in session.executed_statements
    )


def test_nonexistent_referencia_rejected_by_the_upsert_itself_returns_404_not_500():
    """A referencia deleted between resolving it and registering violates
    `demanda_perdida_referencia_id_fkey` at the upsert statement, before
    `commit()`. It must reach the same `except IntegrityError` translation
    as a commit-time violation, not escape as a 500."""
    sucursal_id = uuid.uuid4()
    asesor = _asesor(telegram_id=1, sucursal_ids=[sucursal_id])
    client, session = _client(
        [[asesor], [_sucursal(id=sucursal_id)], []],
        referencia_ids_en_db=[],
    )

    response = client.post(
        f"{BOT_URL}/demanda-perdida",
        json=_payload(sucursal_id, (uuid.uuid4(), 1)),
        headers=_headers(1, idempotency_key=uuid.uuid4()),
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "REFERENCIA_NO_ENCONTRADA"
    assert session.rolled_back is True
    assert session.committed is False
