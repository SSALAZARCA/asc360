"""Revision b2f6d9a4c718: transfer lines and confirmations (+ history)."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"


def _cargar():
    (archivo,) = _VERSIONS.glob("b2f6d9a4c718_*.py")
    spec = importlib.util.spec_from_file_location("traslados_mig", archivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_chains_onto_the_invoice_order_type_head():
    assert _cargar().down_revision == "a8d4f1c6b923"


def test_upgrade_creates_the_three_tables_and_their_indexes():
    migracion = _cargar()
    with patch.object(migracion, "op") as op_mock:
        migracion.upgrade()

    tablas = [c.args[0] for c in op_mock.create_table.call_args_list]
    assert tablas == [
        "traslado_linea", "traslado_confirmacion",
        "traslado_confirmacion_historial"]
    indices = {c.args[0] for c in op_mock.create_index.call_args_list}
    assert indices == {
        "ix_traslado_linea_carga_id", "ix_traslado_linea_sucursal_entrada_id",
        "ix_traslado_linea_documento_bodega",
        "ix_traslado_confirmacion_historial_doc"}


def test_downgrade_drops_what_upgrade_creates():
    migracion = _cargar()
    with patch.object(migracion, "op") as op_mock:
        migracion.downgrade()

    borradas = [c.args[0] for c in op_mock.drop_table.call_args_list]
    assert sorted(borradas) == [
        "traslado_confirmacion", "traslado_confirmacion_historial",
        "traslado_linea"]
