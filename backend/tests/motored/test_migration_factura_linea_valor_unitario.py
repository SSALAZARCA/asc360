"""Revision e3a7c1d94b52: nullable `factura_proveedor_linea.valor_unitario`."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"


def _cargar():
    (archivo,) = _VERSIONS.glob("e3a7c1d94b52_*.py")
    spec = importlib.util.spec_from_file_location("valor_unitario_mig", archivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_chains_onto_the_conteo_lecturas_head():
    assert _cargar().down_revision == "d58b2c9e4a17"


def test_upgrade_adds_a_nullable_numeric_column():
    migracion = _cargar()
    with patch.object(migracion, "op") as op_mock:
        migracion.upgrade()

    tabla, columna = op_mock.add_column.call_args.args
    assert tabla == "factura_proveedor_linea"
    assert columna.name == "valor_unitario" and columna.nullable is True
    assert (columna.type.precision, columna.type.scale) == (14, 2)


def test_downgrade_drops_the_column():
    migracion = _cargar()
    with patch.object(migracion, "op") as op_mock:
        migracion.downgrade()

    op_mock.drop_column.assert_called_once_with(
        "factura_proveedor_linea", "valor_unitario")
