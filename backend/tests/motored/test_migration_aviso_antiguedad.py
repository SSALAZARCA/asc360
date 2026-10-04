"""
Motored aviso de antiguedad: la migracion `b5d91e3a7c42` es aditiva (una
tabla nueva con su clave unica) y encadena sobre la cabeza anterior.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

_RAIZ = Path(__file__).resolve().parents[2]
_ARCHIVO = (
    _RAIZ / "alembic_motored" / "versions"
    / "b5d91e3a7c42_aviso_antiguedad_enviado.py")


def _cargar():
    spec = importlib.util.spec_from_file_location("m_aviso", _ARCHIVO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_encadena_sobre_referencia_codigo_unico():
    modulo = _cargar()

    assert modulo.revision == "b5d91e3a7c42"
    assert modulo.down_revision == "f3a8d1c5b704"


def test_upgrade_crea_solo_la_tabla_con_su_clave_unica():
    modulo = _cargar()
    with patch.object(modulo, "op") as op_mock:
        modulo.upgrade()

    op_mock.create_table.assert_called_once()
    args = op_mock.create_table.call_args.args
    assert args[0] == "aviso_antiguedad_enviado"
    nombres = [getattr(a, "name", None) for a in args[1:]]
    assert "uq_aviso_antiguedad_dataset_umbral_vence" in nombres
    op_mock.drop_table.assert_not_called()
    op_mock.add_column.assert_not_called()


def test_downgrade_borra_la_tabla():
    modulo = _cargar()
    with patch.object(modulo, "op") as op_mock:
        modulo.downgrade()

    op_mock.drop_table.assert_called_once_with("aviso_antiguedad_enviado")
