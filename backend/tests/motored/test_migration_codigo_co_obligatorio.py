"""
Migration `c6e1f8a2d953`: `sucursal.codigo_co` becomes NOT NULL. Static
test with a mocked `op` (like `test_migration_referencia_codigo_unico.py`);
the real upgrade and downgrade against Postgres live in
`pg_real/test_codigo_co_obligatorio_pg.py`.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from app.motored.models.sucursal import Sucursal

_RAIZ = Path(__file__).resolve().parents[2]
_ARCHIVO = (
    _RAIZ / "alembic_motored" / "versions"
    / "c6e1f8a2d953_codigo_co_obligatorio.py"
)


def _cargar():
    spec = importlib.util.spec_from_file_location(
        "codigo_co_obligatorio", _ARCHIVO
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _correr(direccion, sin_codigo=()):
    modulo = _cargar()
    with patch.object(modulo, "op") as op_mock:
        resultado = op_mock.get_bind.return_value.execute.return_value
        resultado.scalars.return_value.all.return_value = list(sin_codigo)
        getattr(modulo, direccion)()
    return op_mock


def test_chains_onto_the_codigo_co_migration():
    modulo = _cargar()

    assert modulo.revision == "c6e1f8a2d953"
    assert modulo.down_revision == "b5d9e3a7c418"


def test_upgrade_makes_the_code_required_on_a_clean_table():
    op_mock = _correr("upgrade")

    op_mock.alter_column.assert_called_once()
    args, kwargs = op_mock.alter_column.call_args
    assert args == ("sucursal", "codigo_co")
    assert kwargs["nullable"] is False


def test_upgrade_stops_naming_the_stores_without_a_code():
    with pytest.raises(RuntimeError) as error:
        _correr("upgrade", sin_codigo=["CALI", "PASTO"])

    mensaje = str(error.value)
    assert "Hay 2 sucursales sin Código C.O." in mensaje
    assert "CALI, PASTO" in mensaje
    assert "cárguelo antes de migrar" in mensaje


def test_upgrade_with_null_rows_does_not_alter_the_column():
    modulo = _cargar()
    with patch.object(modulo, "op") as op_mock:
        resultado = op_mock.get_bind.return_value.execute.return_value
        resultado.scalars.return_value.all.return_value = ["CALI"]
        with pytest.raises(RuntimeError):
            modulo.upgrade()

    op_mock.alter_column.assert_not_called()


def test_downgrade_makes_the_code_nullable_again():
    op_mock = _correr("downgrade")

    args, kwargs = op_mock.alter_column.call_args
    assert args == ("sucursal", "codigo_co")
    assert kwargs["nullable"] is True


def test_the_model_requires_the_code():
    assert Sucursal.__table__.c.codigo_co.nullable is False
