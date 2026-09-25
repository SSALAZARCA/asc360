"""
Phase 3 "Models/Schemas/Services" — shared test plumbing
(sdd/motored-pedidos-cimientos). Phase 4 "API + Integration" adds the HTTP
layer helpers at the bottom (`motored_client`, `override_motored_db`,
`override_motored_user`).

Fase 2 "Ingesta", Phase 2 "JobRunner + Supervisor" adds an autouse fixture
(`_reset_motored_supervisor`, bottom of file): `deps.require_motored_ready`
now calls `supervisor.ensure_started()` on every Motored request, so ANY
test in this suite that exercises that dependency (e.g.
`test_availability.py`'s `MOTORED_ENABLED=True` cases) can start the
real in-process poll loop. Without a suite-wide cleanup, that task would
leak into the next test's event loop teardown ("Task was destroyed but it
is pending!") regardless of which test file triggered it -- this fixture
protects the whole `tests/motored/` suite, not just the supervisor's own
tests.

Mirrors the project's established fake-session convention
(`tests/imports/conftest.py`'s `FakeAsyncSession`/`_ExecuteResult`): no live
database anywhere in this suite, matching `tests/conftest.py`'s own stated
approach ("pure unit tests using MagicMock/AsyncMock — no live database
required"). This is a Motored-local copy, deliberately not importing the
`tests/imports` version, since the two domains have nothing in common and
this module must stay independently readable.
"""
import operator as _operator
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


class _ScalarsResult:
    def __init__(self, items: list):
        self._items = items

    def all(self) -> list:
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None

    def one_or_none(self):
        if len(self._items) > 1:
            raise AssertionError("one_or_none() expects 0 or 1 queued rows")
        return self._items[0] if self._items else None


class _ExecuteResult:
    def __init__(self, items: list):
        self._items = items

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._items)

    def all(self) -> list:
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None

    @property
    def rowcount(self) -> int:
        """Fase 6 fix-up (finding #1, BLOCKER): un `UPDATE`/`DELETE` real sin
        `.returning()` no devuelve filas -- devuelve un CONTEO de filas
        afectadas (`CursorResult.rowcount`). `FakeAsyncSession` no distingue
        un SELECT de un UPDATE/DELETE en su cola (ambos encolan una lista),
        así que acá se interpreta el largo de esa lista encolada como el
        rowcount para el caller que solo necesita saber CUÁNTAS filas fueron
        tocadas, nunca su contenido -- p.ej. `_ejecutar_delta_negativo`
        (services/demanda_perdida_bot.py), que nunca hace `.returning()` y
        usa el rowcount de su propio `UPDATE` para decidir si existía o no
        una fila `demanda_perdida` para esa clave."""
        return len(self._items)


class FakeAsyncSession:
    """Minimal stand-in for `AsyncSession`. `execute_queue` is a list of
    lists: each `await db.execute(stmt)` call pops the next queued list of
    rows, in the exact order the service under test issues its queries.

    Post-Phase-5-review addition (fix #1/#2): two opt-in ways to simulate a
    real Postgres `IntegrityError` surfacing where it actually would in
    production, mirroring the established convention already used by
    `tests/historical_orders/conftest.py`/`tests/orders/conftest.py` (a
    one-shot `raise_integrity_error` flag consumed by `commit()`), extended
    here to also accept a specific exception instance (not just `True`) so
    a test can control the exact `str(exc.orig)` message the production
    code branches on (e.g. `uq_usuario_telegram_id` vs a FK constraint
    name) -- and a matching one-shot mechanism on `execute()` itself, for
    races that surface at the statement level (a raw `UPDATE ... RETURNING`
    claim, like `consumir_codigo_vinculacion`'s), not at `commit()` time.
    """

    def __init__(
        self,
        execute_queue: Optional[List[list]] = None,
        get_queue: Optional[list] = None,
        raise_integrity_error: "Optional[Any]" = None,
    ):
        self._execute_queue = list(execute_queue or [])
        self._get_queue = list(get_queue) if get_queue is not None else None
        self._raise_integrity_error = raise_integrity_error
        self.added: List[Any] = []
        self.committed = False
        self.rolled_back = False
        self.executed_statements: List[Any] = []

    async def get(self, model, ident):
        """Stand-in for `session.get(Model, id)` -- used by the crash-safety
        re-fetch pattern in `orquestador.py` (`ejecutar_dry_run`/`ejecutar_
        maestro`) after a `rollback()`. `get_queue` is a plain list (one
        item per call, not a list-of-lists like `execute_queue`, since
        `session.get` returns a single row/`None`, never a result set).
        Defaults to `None` (nothing configured) so a test that never
        exercises this path doesn't need to know about it."""
        if self._get_queue is None:
            return None
        if not self._get_queue:
            raise AssertionError(
                "FakeAsyncSession.get() called more times than expected "
                "— update the test's get_queue."
            )
        return self._get_queue.pop(0)

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        if not self._execute_queue:
            raise AssertionError(
                "FakeAsyncSession.execute() called more times than expected "
                "— update the test's execute_queue."
            )
        proximo = self._execute_queue.pop(0)
        if isinstance(proximo, BaseException):
            # Fix #2: a race that a real Postgres unique/FK constraint
            # catches at STATEMENT-execution time (e.g. the atomic claim
            # `UPDATE ... RETURNING` inside `consumir_codigo_vinculacion`),
            # not at `commit()` time — queue the exception itself instead
            # of a row list to simulate exactly that.
            raise proximo
        return _ExecuteResult(proximo)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self._apply_column_defaults(obj)
        self.added.append(obj)

    @staticmethod
    def _apply_column_defaults(obj) -> None:
        """Phase 4 addition: a real `AsyncSession` applies SQLAlchemy
        client-side column `default=` values (scalar or callable) at flush
        time, and — because Motored's session is built with
        `expire_on_commit=False` — the in-memory object keeps that value
        after `commit()`. `FakeAsyncSession` never flushes, so without this
        an HTTP-layer test that builds a Pydantic `*Read` response straight
        from a freshly-`add()`ed row (e.g. `sucursal.activa`) would see
        `None` instead of the real default — a test-fake gap, not a
        production bug. Mirrors the real flush behavior closely enough for
        every default used in this module (booleans, `datetime.utcnow`,
        numeric defaults)."""
        table = getattr(obj, "__table__", None)
        if table is None:
            return
        for column in table.columns:
            if getattr(obj, column.name, None) is not None:
                continue
            default = column.default
            if default is None:
                continue
            if getattr(default, "is_scalar", False):
                setattr(obj, column.name, default.arg)
            elif getattr(default, "is_callable", False):
                setattr(obj, column.name, default.arg(None))

    async def commit(self):
        if self._raise_integrity_error:
            # Fix #1: a race that only a real Postgres unique/FK constraint
            # would catch at flush/COMMIT time (the ORM `INSERT`s from
            # `db.add(...)`, unlike the raw `UPDATE` above). One-shot, same
            # convention as `tests/historical_orders/conftest.py`.
            error, self._raise_integrity_error = self._raise_integrity_error, None
            if error is True:
                from sqlalchemy.exc import IntegrityError

                error = IntegrityError("COMMIT", {}, Exception("duplicate key value"))
            raise error
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def flush(self):
        pass

    async def refresh(self, obj, attribute_names=None):
        pass

    def added_of_type(self, cls) -> list:
        return [obj for obj in self.added if isinstance(obj, cls)]


# ---------------------------------------------------------------------------
# Fase 6 fix-up (sdd/motored-ventas-perdidas-bot, review finding #2,
# CRITICAL) -- `AdditiveDemandaPerdidaFakeSession`.
#
# Motivo: hasta acá, todo test de `services/demanda_perdida_bot.py` probaba
# el UPSERT/UPDATE/DELETE aditivo SOLO por introspección del statement
# compilado ("¿tiene la forma correcta?"), nunca ejecutándolo de verdad --
# `FakeAsyncSession.execute()` simplemente devuelve la próxima página
# encolada, sin aplicar ninguna semántica. Eso dejó pasar 3 rondas de
# "hollow test" en este mismo feature (el upsert aditivo, el test de
# integración edición+cancelación, el test de carrera de idempotencia).
#
# Esta clase SÍ aplica de verdad, contra un diccionario en memoria
# `{(fecha, sucursal_id, referencia_id, origen): Decimal}`, los 2 shapes de
# statement concretos que ese módulo usa para escritura ADITIVA de
# `demanda_perdida`:
#   - `pg_insert(...).on_conflict_do_update(...)` (el upsert, delta > 0)
#   - `UPDATE demanda_perdida SET cantidad_solicitada = cantidad_solicitada
#     + :delta WHERE (clave)` seguido de `DELETE ... WHERE (clave) AND
#     cantidad_solicitada <= 0` (delta < 0, incluida la reversa de
#     `_revertir_linea` post-BLOCKER-fix)
#
# Deliberadamente NO se centralizó como una convención general de
# `FakeAsyncSession` (a diferencia de, p.ej., `_FilteringFakeSession`, que
# cada archivo de test define localmente porque cada uno filtra columnas/
# tablas distintas): acá los 3 archivos consumidores (`test_demanda_perdida
# _bot_anular.py`, `test_demanda_perdida_bot_upsert.py`,
# `test_bot_demanda_perdida_api.py`) necesitan la MISMA lógica de aritmética
# bit-a-bit para la MISMA tabla -- triplicarla localmente solo crearía 3
# copias que divergirían con el tiempo.
#
# Cualquier otro statement (SELECTs de negocio, el `UPDATE ... RETURNING`
# del claim atómico sobre `carga_archivo`, etc.) cae al comportamiento
# heredado de `FakeAsyncSession` (`execute_queue`), así que un test puede
# mezclar libremente filas encoladas para sus SELECTs con aserciones reales
# sobre `demanda_perdida`.
# ---------------------------------------------------------------------------

_CLAVE_DEMANDA_PERDIDA_BOT: Tuple[str, str, str, str] = (
    "fecha", "sucursal_id", "referencia_id", "origen",
)


class _ResultadoConRowcount:
    """Standin mínimo para el `CursorResult` que un `UPDATE`/`DELETE` real
    sin `.returning()` devuelve -- solo expone `.rowcount`, que es lo único
    que `_ejecutar_delta_negativo` lee del resultado del `UPDATE` para saber
    si encontró o no una fila `demanda_perdida` existente para esa clave."""

    def __init__(self, rowcount: int):
        self.rowcount = rowcount


def _extraer_igualdades_where(stmt) -> Dict[str, Any]:
    """Como `_extraer_predicados` en `test_cargas_api.py`, pero devuelve un
    dict `{nombre_columna: valor}` en vez de una lista de tuplas -- más
    cómodo acá porque se arma una clave compuesta de 4 columnas a partir del
    WHERE. Solo mira cláusulas de IGUALDAD de nivel superior (`==`); una
    cláusula `cantidad_solicitada <= 0` (el DELETE condicional) queda afuera
    a propósito -- ese umbral se evalúa aparte, contra el valor YA
    actualizado en el diccionario en memoria, nunca releído del statement."""
    whereclause = getattr(stmt, "whereclause", None)
    if whereclause is None:
        return {}
    igualdades: Dict[str, Any] = {}
    for clausula in getattr(whereclause, "clauses", [whereclause]):
        if getattr(clausula, "operator", None) is not _operator.eq:
            continue
        columna = getattr(getattr(clausula, "left", None), "key", None)
        valor_bind = getattr(clausula, "right", None)
        if columna is not None and hasattr(valor_bind, "value"):
            igualdades[columna] = valor_bind.value
    return igualdades


def _clave_demanda_perdida(igualdades: Dict[str, Any]) -> tuple:
    faltantes = [c for c in _CLAVE_DEMANDA_PERDIDA_BOT if c not in igualdades]
    if faltantes:
        raise AssertionError(
            f"AdditiveDemandaPerdidaFakeSession: statement sin columnas {faltantes} "
            "en su WHERE -- forma inesperada para este fake (actualizar el fake si "
            "el shape real del UPDATE/DELETE cambió)."
        )
    return tuple(igualdades[c] for c in _CLAVE_DEMANDA_PERDIDA_BOT)


class AdditiveDemandaPerdidaFakeSession(FakeAsyncSession):
    """Ver el comentario de sección de arriba. `filas_iniciales` siembra el
    estado "ya existente en la base" antes de que el código bajo test emita
    su primer statement -- `{(fecha, sucursal_id, referencia_id, origen):
    Decimal}`. `cantidad_actual(...)` es el punto de lectura para
    aserciones (`None` si la clave nunca existió o fue borrada por un
    `DELETE ... WHERE cantidad_solicitada <= 0`)."""

    def __init__(self, *, filas_iniciales: Optional[Dict[tuple, Decimal]] = None, **kwargs):
        super().__init__(**kwargs)
        self.filas_demanda_perdida: Dict[tuple, Decimal] = dict(filas_iniciales or {})

    def cantidad_actual(
        self, *, fecha, sucursal_id, referencia_id, origen: str = "BOT"
    ) -> Optional[Decimal]:
        return self.filas_demanda_perdida.get((fecha, sucursal_id, referencia_id, origen))

    async def execute(self, stmt):
        resultado = self._aplicar_semantica_real(stmt)
        if resultado is not None:
            self.executed_statements.append(stmt)
            return resultado
        return await super().execute(stmt)

    def _aplicar_semantica_real(self, stmt):
        tipo = type(stmt).__name__
        tabla = getattr(getattr(stmt, "table", None), "name", None)
        if tipo == "Insert" and getattr(stmt, "_post_values_clause", None) is not None:
            if tabla is not None and tabla != "demanda_perdida":
                return None
            return self._aplicar_upsert_aditivo(stmt)
        if tabla == "demanda_perdida" and tipo == "Update":
            return self._aplicar_update_delta(stmt)
        if tabla == "demanda_perdida" and tipo == "Delete":
            return self._aplicar_delete_condicional(stmt)
        return None

    def _aplicar_upsert_aditivo(self, stmt):
        """`pg_insert(...).on_conflict_do_update(...)`, delta > 0 -- suma
        contra el valor existente (o lo crea, si la clave es nueva),
        exactamente la semántica que Postgres aplicaría con el `ON CONFLICT
        DO UPDATE SET cantidad_solicitada = demanda_perdida.
        cantidad_solicitada + excluded.cantidad_solicitada` real."""
        valores = stmt.compile().construct_params()
        clave = tuple(valores[columna] for columna in _CLAVE_DEMANDA_PERDIDA_BOT)
        delta = valores["cantidad_solicitada"]
        actual = self.filas_demanda_perdida.get(clave, Decimal("0"))
        self.filas_demanda_perdida[clave] = actual + delta
        return _ExecuteResult([])

    def _aplicar_update_delta(self, stmt):
        """`UPDATE demanda_perdida SET cantidad_solicitada =
        cantidad_solicitada + :delta WHERE (clave)` -- 0 filas afectadas
        (rowcount) si la clave no existe todavía, nunca crea una fila (a
        diferencia del upsert; ver `_ejecutar_delta_negativo`'s propio
        docstring sobre por qué un delta negativo NUNCA pasa por el
        upsert)."""
        clave = _clave_demanda_perdida(_extraer_igualdades_where(stmt))
        delta = None
        for columna, expresion in stmt._values.items():
            if columna.name == "cantidad_solicitada":
                delta = getattr(getattr(expresion, "right", expresion), "value", expresion)
        if delta is None:
            raise AssertionError(
                "AdditiveDemandaPerdidaFakeSession: UPDATE sin SET "
                "cantidad_solicitada -- forma inesperada para este fake."
            )
        if clave not in self.filas_demanda_perdida:
            return _ResultadoConRowcount(rowcount=0)
        self.filas_demanda_perdida[clave] = self.filas_demanda_perdida[clave] + delta
        return _ResultadoConRowcount(rowcount=1)

    def _aplicar_delete_condicional(self, stmt):
        """`DELETE ... WHERE (clave) AND cantidad_solicitada <= 0` -- el
        umbral `<= 0` se evalúa acá contra el valor YA actualizado por el
        `UPDATE` anterior (nunca releído del statement compilado, ver
        `_extraer_igualdades_where`), igual que lo haría Postgres evaluando
        el predicado contra la fila real."""
        clave = _clave_demanda_perdida(_extraer_igualdades_where(stmt))
        actual = self.filas_demanda_perdida.get(clave)
        if actual is not None and actual <= 0:
            del self.filas_demanda_perdida[clave]
        return _ExecuteResult([])


# ---------------------------------------------------------------------------
# Phase 4 "API + Integration" — HTTP-layer helpers.
#
# Mirrors the design doc's own Testing Strategy line ("`tests/motored/
# conftest.py` `make_motored_client` overriding `get_motored_db`/
# `get_current_motored_user`"): API-layer tests use the REAL `TestClient
# (app)` around the real mounted Motored router (Phase 4), and swap only the
# two dependency seams that Phase 2/3 already designed to be swappable --
# never a throwaway app object, never a monkeypatched service function.
# ---------------------------------------------------------------------------
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.motored.database import get_motored_db
from app.motored.deps import get_current_motored_user


@pytest.fixture
def motored_client():
    """Real `TestClient(app)` around the real, already-mounted Motored
    router. Cleans up both dependency-override seams after the test so one
    test's fake session/user never leaks into the next."""
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_motored_db, None)
    app.dependency_overrides.pop(get_current_motored_user, None)


def override_motored_db(session: "FakeAsyncSession") -> None:
    """Swaps the innermost DB seam. `get_motored_db_or_503` (which every
    Motored router actually depends on) itself depends on `get_motored_db`,
    so overriding this one leaf makes every layer above it (readiness probe,
    user lookup, business queries) transparently use `session`."""
    app.dependency_overrides[get_motored_db] = lambda: session


@pytest.fixture(autouse=True)
async def _reset_motored_supervisor():
    """Suite-wide safety net (Fase 2 "Ingesta", ADR-1): whatever a test
    did, never leave the supervisor's poll-loop task running into the
    next test's event loop."""
    yield
    from app.motored.services.trabajos import supervisor

    await supervisor.reset_for_tests()


def override_motored_user(user) -> None:
    """Swaps the resolved-user seam directly, bypassing the real DB-backed
    lookup entirely (its own correctness is Phase 3's concern, already
    covered by `test_usuario_lookup.py`) — this is what lets RBAC-matrix
    tests fix a role per request without staging a matching `usuario` row
    in `execute_queue` for every single case."""

    async def _fake_current_user():
        return user

    app.dependency_overrides[get_current_motored_user] = _fake_current_user
