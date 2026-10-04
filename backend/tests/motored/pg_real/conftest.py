"""Shared plumbing for the `pg_real` suite.

The corridas/inventory purges read their switch from
`parametro_metodologia` and keep the last value read in a module-level
memo (`_memoria_config`). Both survive across tests of one process, so a
test that stores or reads a retention setting must not decide the next
one: the memos are cleared around every test.
"""
import pytest

from app.motored.services import retencion
from app.motored.services.corridas import retencion_corridas


def _olvidar_ajustes_leidos():
    retencion._memoria_config.clear()
    retencion_corridas._memoria_config.clear()


@pytest.fixture(autouse=True)
def _retencion_sin_memoria():
    _olvidar_ajustes_leidos()
    yield
    _olvidar_ajustes_leidos()
