"""
Motored Pedidos — wiring del seam de la Fase 2 con la consulta REAL a
`usuario` (sdd/motored-pedidos-cimientos, "Also required by this slice").

`get_current_motored_user` ahora autentica de verdad contra una fila
`usuario` (vía `services/auth.py::obtener_usuario_motored`), no contra el
lookup en memoria falso que usan los tests de aislamiento de la Fase 2 (esos
siguen siendo válidos y no se tocan -- proveen su PROPIO fake vía
`app.dependency_overrides` para `get_motored_user_lookup`, que sigue siendo
swappable a propósito).
"""
import uuid

import pytest

from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal
from app.motored.services.auth import MotoredUser, crear_lookup_real, obtener_usuario_motored
from tests.motored.conftest import FakeAsyncSession


class TestObtenerUsuarioMotored:
    async def test_found_user_maps_to_motored_user_with_sucursal_ids(self):
        user_id = uuid.uuid4()
        sucursal_id = uuid.uuid4()
        usuario = Usuario(
            id=user_id, nombre="Ana", email="ana@motoredcolombia.com.co",
            hashed_password="hashed", role=MotoredRole.SUCURSAL, activo=True,
        )
        usuario.sucursales = [UsuarioSucursal(id=uuid.uuid4(), usuario_id=user_id, sucursal_id=sucursal_id)]
        db = FakeAsyncSession(execute_queue=[[usuario]])

        result = await obtener_usuario_motored(db, str(user_id))

        assert isinstance(result, MotoredUser)
        assert result.user_id == str(user_id)
        assert result.role == "SUCURSAL"
        assert result.sucursal_ids == [str(sucursal_id)]
        assert result.activo is True

    async def test_unknown_user_id_returns_none(self):
        db = FakeAsyncSession(execute_queue=[[]])

        result = await obtener_usuario_motored(db, str(uuid.uuid4()))

        assert result is None

    async def test_non_uuid_user_id_returns_none_without_querying_db(self):
        db = FakeAsyncSession(execute_queue=[])  # no execute() call expected

        result = await obtener_usuario_motored(db, "not-a-uuid")

        assert result is None
        assert db.executed_statements == []

    async def test_inactive_user_is_still_returned_with_activo_false(self):
        # `get_current_motored_user` is the one that rejects inactive users
        # (401) -- the lookup itself just reports the truth.
        user_id = uuid.uuid4()
        usuario = Usuario(
            id=user_id, nombre="Ana", email="ana@x.com", hashed_password="h",
            role=MotoredRole.CONSULTA, activo=False,
        )
        usuario.sucursales = []
        db = FakeAsyncSession(execute_queue=[[usuario]])

        result = await obtener_usuario_motored(db, str(user_id))

        assert result.activo is False


class TestCrearLookupReal:
    async def test_returned_callable_queries_the_bound_session(self):
        user_id = uuid.uuid4()
        usuario = Usuario(
            id=user_id, nombre="Ana", email="ana@x.com", hashed_password="h",
            role=MotoredRole.ADMIN, activo=True,
        )
        usuario.sucursales = []
        db = FakeAsyncSession(execute_queue=[[usuario]])

        lookup = crear_lookup_real(db)
        result = await lookup(str(user_id))

        assert result.user_id == str(user_id)
        assert result.role == "ADMIN"


class TestDepsWiring:
    def test_get_motored_user_lookup_now_requires_a_db_dependency(self):
        """`get_motored_user_lookup` must now be DB-backed -- it composes
        `get_motored_db_or_503` as its own dependency (mirrors how
        `app/api/deps.py`'s auth composes with `get_db` in asc360: a
        dependency that itself depends on another dependency)."""
        import inspect

        from app.motored.deps import get_motored_user_lookup

        sig = inspect.signature(get_motored_user_lookup)
        assert "db" in sig.parameters

    def test_unwired_placeholder_lookup_no_longer_exists(self):
        """Fase 2's `_unwired_user_lookup` seam placeholder must be removed
        now that the real lookup is wired -- dead code left behind is a
        finding, not a convenience."""
        import app.motored.deps as deps_module

        assert not hasattr(deps_module, "_unwired_user_lookup")

    async def test_get_motored_user_lookup_returns_a_real_db_backed_lookup(self):
        from app.motored.deps import get_motored_user_lookup

        db = FakeAsyncSession(execute_queue=[[]])
        lookup = get_motored_user_lookup(db=db)

        # It must be the real factory's output, not a hardcoded stub.
        result = await lookup(str(uuid.uuid4()))
        assert result is None  # no queued row for this id -- but it genuinely queried
        assert db.executed_statements  # proves it actually hit the (fake) DB
