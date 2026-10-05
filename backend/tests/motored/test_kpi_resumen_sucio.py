"""R7a: the summaries are marked dirty when one of their inputs changes (unit; SQL in `pg_real/test_kpi_resumen_sucio_pg.py`)."""
import datetime
import uuid

import pytest

from app.motored.models.referencia import Referencia
from app.motored.schemas.referencia import ReferenciaUpdate
from app.motored.services import kpi_resumen as k
from app.motored.services import maestros, parametros
from tests.motored.conftest import FakeAsyncSession


def _estado(**cambios):
    base = dict(sucio=False, reconstruyendo=False, actualizado_en=None,
                ultima_reconstruccion_total=datetime.datetime(2026, 10, 1), version=1)
    return k.Estado(**{**base, **cambios})


class _Sesion:
    def __init__(self, estado):
        self.eventos = []
        self._estado = estado


@pytest.fixture
def espiado(monkeypatch):
    def preparar(estado):
        sesion = _Sesion(estado)

        async def bloquear(db):
            db.eventos.append("bloquear")

        async def leer(db):
            db.eventos.append("estado")
            return db._estado

        async def sucio(db):
            db.eventos.append("sucio")

        monkeypatch.setattr(k, "_bloquear", bloquear)
        monkeypatch.setattr(k, "estado", leer)
        monkeypatch.setattr(k, "marcar_sucio", sucio)
        return sesion

    return preparar


async def test_marks_dirty_after_taking_the_lock_and_reading_the_state(espiado):
    sesion = espiado(_estado())

    assert await k.marcar_sucio_si_construido(sesion) is True

    assert sesion.eventos == ["bloquear", "estado", "sucio"]


@pytest.mark.parametrize("estado", [None, _estado(ultima_reconstruccion_total=None, sucio=True)],
                         ids=["no-state-row", "never-built"])
async def test_does_nothing_until_the_summaries_were_built_once(espiado, estado):
    sesion = espiado(estado)

    assert await k.marcar_sucio_si_construido(sesion) is False

    assert "sucio" not in sesion.eventos


@pytest.fixture
def marcas(monkeypatch):
    llamadas = []

    async def marcar(db):
        llamadas.append(db)
        return True

    monkeypatch.setattr(k, "marcar_sucio_si_construido", marcar)
    return llamadas


async def _actualizar_referencia(**cambios):
    referencia = Referencia(id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(), nombre="N",
                            linea_comercial="MOTOS", unidad_empaque=1)
    db = FakeAsyncSession()
    await maestros.update_referencia(db, referencia, ReferenciaUpdate(**cambios), verificar_sustituta=False)
    return db


async def test_changing_the_linea_comercial_of_a_referencia_marks_dirty(marcas):
    db = await _actualizar_referencia(linea_comercial="REPUESTOS")

    assert marcas == [db]


@pytest.mark.parametrize("cambios", [{"linea_comercial": "MOTOS"}, {"nombre": "Otro"}],
                         ids=["same-linea", "other-field"])
async def test_an_unchanged_linea_comercial_does_not_mark_dirty(marcas, cambios):
    await _actualizar_referencia(**cambios)

    assert marcas == []


@pytest.mark.parametrize("clave,marca", [("hmcl_nits", True), ("lineas_comerciales", True),
                                         ("dias_ventana_ingresos", False)])
async def test_only_the_configuration_keys_the_summaries_depend_on_mark_dirty(marcas, clave, marca):
    db = FakeAsyncSession()

    await parametros.registrar_cambio(db, clave, ["X"], datetime.date(2026, 10, 1))

    assert (marcas == [db]) is marca
