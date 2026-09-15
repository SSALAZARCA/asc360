"""
Phase 3 "Models/Schemas/Services" — task 3.6 (sdd/motored-pedidos-cimientos).

`parametro_metodologia` is versioned by INSERTION: a change always inserts
a NEW row keyed by `vigente_desde`; the prior version's row is left
completely unmodified -- never an in-place UPDATE (spec "parametro_
metodologia versioning").
"""
import datetime
import uuid

from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros
from tests.motored.conftest import FakeAsyncSession


class TestInsertOnlyVersioning:
    async def test_registrar_cambio_always_inserts_a_new_row(self):
        db = FakeAsyncSession()

        nueva = await parametros.registrar_cambio(
            db, clave="dias_seguridad_default", valor=3.0,
            vigente_desde=datetime.date(2026, 9, 1),
        )

        assert nueva in db.added
        assert nueva.clave == "dias_seguridad_default"
        assert nueva.vigente_desde == datetime.date(2026, 9, 1)

    async def test_registrar_cambio_never_mutates_the_prior_version_row(self):
        prior = ParametroMetodologia(
            id=uuid.uuid4(), clave="dias_seguridad_default", valor=2.5,
            vigente_desde=datetime.date(2026, 1, 1),
        )
        db = FakeAsyncSession(execute_queue=[[prior]])

        await parametros.registrar_cambio(
            db, clave="dias_seguridad_default", valor=3.0,
            vigente_desde=datetime.date(2026, 9, 1),
        )

        # The prior row's own fields are completely untouched.
        assert prior.valor == 2.5
        assert prior.vigente_desde == datetime.date(2026, 1, 1)

    async def test_parametros_module_never_calls_db_execute_update_or_merge(self):
        """Static guard: no function in `services/parametros.py` may call
        an in-place update/merge on an existing version row -- a "change"
        must always be `db.add(<new row>)`, never `db.merge`/an UPDATE."""
        import ast
        import inspect

        source = inspect.getsource(parametros)
        tree = ast.parse(source)
        forbidden_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("merge",)
        ]
        assert forbidden_calls == []


class TestObtenerVigente:
    async def test_returns_the_latest_version_effective_on_or_before_a_date(self):
        latest = ParametroMetodologia(
            id=uuid.uuid4(), clave="dias_seguridad_default", valor=3.0,
            vigente_desde=datetime.date(2026, 9, 1),
        )
        db = FakeAsyncSession(execute_queue=[[latest]])

        vigente = await parametros.obtener_vigente(db, "dias_seguridad_default", datetime.date(2026, 9, 14))

        assert vigente is latest
