"""Unit tests for the shared store-text resolver (C.O. first, then name, then alias)."""
import uuid

import pytest

from app.motored.services.sucursal_texto import sucursal_id_por_texto


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas


class _DbFalsa:
    """Answers each query by the columns it selects."""

    def __init__(self, sucursales, alias=()):
        self.sucursales = sucursales  # (id, nombre, codigo_co)
        self.alias = alias  # (texto_normalizado, sucursal_id)

    async def execute(self, consulta):
        if "sucursal_alias" in str(consulta):
            return _Resultado(list(self.alias))
        if "codigo_co" in str(consulta):
            return _Resultado(list(self.sucursales))
        return _Resultado([(sid, nombre) for sid, nombre, _ in self.sucursales])


ID_A, ID_B = uuid.uuid4(), uuid.uuid4()


@pytest.mark.asyncio
async def test_resolves_by_codigo_co_and_by_name():
    db = _DbFalsa([(ID_A, "Cali Norte", "B08")])

    mapa = await sucursal_id_por_texto(db)

    assert mapa["B08"] == ID_A
    assert mapa["CALI NORTE"] == ID_A


@pytest.mark.asyncio
async def test_codigo_co_wins_over_another_stores_name_that_looks_like_it():
    db = _DbFalsa([(ID_A, "Cali Norte", "B08"), (ID_B, "B08", None)])

    mapa = await sucursal_id_por_texto(db)

    assert mapa["B08"] == ID_A


@pytest.mark.asyncio
async def test_codigo_co_wins_over_an_alias_and_unknown_text_is_missing():
    db = _DbFalsa([(ID_A, "Cali Norte", "B08")], alias=[("B08", ID_B), ("SEDE VIEJA", ID_B)])

    mapa = await sucursal_id_por_texto(db)

    assert mapa["B08"] == ID_A
    assert mapa["SEDE VIEJA"] == ID_B
    assert "Z99" not in mapa


@pytest.mark.asyncio
async def test_a_stored_value_that_breaks_the_c_o_format_is_not_indexed_as_a_code():
    db = _DbFalsa([(ID_A, "Cali Norte", "XX")])

    mapa = await sucursal_id_por_texto(db)

    assert "XX" not in mapa
