"""
Fase 2 "Ingesta", Phase 2 "JobRunner + Supervisor" (sdd/motored-pedidos-
ingesta, ADR-1) — el puerto `JobRunner` y sus dos adaptadores.

`InlineRunner` es el que usa TODA la suite de tests funcionales: debe
ejecutar el handler registrado para `tipo` de forma síncrona, en el mismo
contexto async del caller, sin tocar el supervisor en absoluto.
`SupervisorRunner` es el adaptador de producción: no ejecuta nada él
mismo, solo garantiza que el supervisor esté corriendo.
"""
import uuid

import pytest

from app.motored.services.trabajos import jobs
from app.motored.services.trabajos.runner import InlineRunner, JobRunner, SupervisorRunner


@pytest.fixture(autouse=True)
def _clean_job_registry():
    """Ningún test debe dejar un handler registrado para el siguiente."""
    original = dict(jobs.JOB_HANDLERS)
    yield
    jobs.JOB_HANDLERS.clear()
    jobs.JOB_HANDLERS.update(original)


async def test_inline_runner_executes_the_registered_handler_synchronously():
    calls = []

    async def _handler(carga_id):
        calls.append(carga_id)

    jobs.register_job("TEST_TIPO", _handler)
    carga_id = uuid.uuid4()

    await InlineRunner().enqueue(carga_id, "TEST_TIPO")

    assert calls == [carga_id]


async def test_inline_runner_is_a_noop_when_no_handler_is_registered():
    """Ningún tipo real está registrado todavía (Fase 3+) -- esto NUNCA
    debe lanzar, es un no-op documentado."""
    jobs.JOB_HANDLERS.pop("SIN_HANDLER", None)

    # No debe lanzar.
    await InlineRunner().enqueue(uuid.uuid4(), "SIN_HANDLER")


async def test_inline_runner_never_touches_the_supervisor(monkeypatch):
    from app.motored.services.trabajos import supervisor

    def _fail_if_called():
        raise AssertionError("InlineRunner no debe tocar el supervisor")

    monkeypatch.setattr(supervisor, "ensure_started", _fail_if_called)

    async def _handler(carga_id):
        return None

    jobs.register_job("TEST_TIPO", _handler)

    # No debe lanzar -- si tocara ensure_started, el monkeypatch de arriba
    # haría fallar el test.
    await InlineRunner().enqueue(uuid.uuid4(), "TEST_TIPO")


async def test_supervisor_runner_enqueue_only_ensures_the_supervisor_is_started(monkeypatch):
    from app.motored.services.trabajos import supervisor

    calls = []
    monkeypatch.setattr(supervisor, "ensure_started", lambda: calls.append(True))

    handler_called = []

    async def _handler(carga_id):
        handler_called.append(carga_id)

    jobs.register_job("TEST_TIPO", _handler)

    await SupervisorRunner().enqueue(uuid.uuid4(), "TEST_TIPO")

    assert calls == [True]
    # SupervisorRunner nunca ejecuta el handler él mismo -- eso es trabajo
    # del poll loop del supervisor, no de `enqueue()`.
    assert handler_called == []


def test_both_adapters_implement_the_job_runner_port():
    assert issubclass(InlineRunner, JobRunner)
    assert issubclass(SupervisorRunner, JobRunner)


async def test_job_runner_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        JobRunner()
