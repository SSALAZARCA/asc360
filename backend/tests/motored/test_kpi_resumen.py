"""KPI summary service (R2): pure helpers. The SQL is covered in `pg_real/test_kpi_resumen_pg.py`."""
import datetime

import pytest

from app.motored.services import kpi_resumen as k


def test_union_lineas_keeps_the_default_and_every_historical_value_normalized():
    result = k.union_lineas([["Motos", " baterías "], "not a list", [], ["REPUESTOS", 7]])

    assert result == tuple(sorted({*k.t.LINEAS, "MOTOS", "BATERIAS"}))


def test_union_lineas_without_history_is_the_registry_default():
    assert k.union_lineas([]) == tuple(sorted(k.t.LINEAS))


def test_union_nits_keeps_the_default_and_strips_and_ignores_blanks():
    result = k.union_nits([[" 811000111 ", "  "], None, ["900723988"], "x"])

    assert result == tuple(sorted({*k.t.HMCL_NITS, "811000111"}))


class _Sesion:
    """Records the order of the lock, the state read and the refresh."""

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

        async def refrescar(db, claves):
            db.eventos.append(("refrescar", claves))

        monkeypatch.setattr(k, "_bloquear", bloquear)
        monkeypatch.setattr(k, "estado", leer)
        monkeypatch.setattr(k, "refrescar_periodos", refrescar)
        return sesion

    return preparar


def _construido(**cambios):
    base = dict(sucio=False, reconstruyendo=False, actualizado_en=None,
                ultima_reconstruccion_total=datetime.datetime(2026, 10, 1), version=1)
    return k.Estado(**{**base, **cambios})


CLAVES = {("s1", 2026, 9), ("s1", 2026, 10)}


async def test_refrescar_si_construido_refresca_despues_de_bloquear_y_mirar_el_estado(espiado):
    sesion = espiado(_construido())

    assert await k.refrescar_si_construido(sesion, CLAVES) is True

    assert sesion.eventos == ["bloquear", "estado", ("refrescar", CLAVES)]


async def test_refrescar_si_construido_refresca_aunque_el_resumen_este_sucio(espiado):
    sesion = espiado(_construido(sucio=True))

    assert await k.refrescar_si_construido(sesion, CLAVES) is True


@pytest.mark.parametrize("estado", [None, _construido(ultima_reconstruccion_total=None, sucio=True)],
                         ids=["no-state-row", "never-built"])
async def test_refrescar_si_construido_no_hace_nada_si_nunca_se_construyo(espiado, estado):
    sesion = espiado(estado)

    assert await k.refrescar_si_construido(sesion, CLAVES) is False

    assert sesion.eventos == ["bloquear", "estado"]  # the lock is held until the caller commits


async def test_refrescar_si_construido_sin_claves_no_toca_la_base(espiado):
    sesion = espiado(_construido())

    assert await k.refrescar_si_construido(sesion, set()) is False

    assert sesion.eventos == []
