"""
Motored `motored-referencia-identidad` (R1): la migracion `f3a8d1c5b704`
cambia la unicidad de `referencia` de (codigo, proveedor_id) a `codigo`.
Prueba ESTATICA con un `op` simulado (al estilo de `test_migration_fase4.py`);
el upgrade/downgrade real contra Postgres vive en
`pg_real/test_referencia_identidad_pg.py`.

Cubre la cadena (una sola cabeza), la guarda de duplicados (aborta con un
mensaje que lista los codigos, nunca fusiona solo), el trim de codigos y el
downgrade que restaura el unico compuesto.
"""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

_RAIZ = Path(__file__).resolve().parents[2]
_ARCHIVO = _RAIZ / "alembic_motored" / "versions" / "f3a8d1c5b704_referencia_codigo_unico.py"


def _cargar():
    spec = importlib.util.spec_from_file_location("referencia_codigo_unico", _ARCHIVO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _correr(direccion, duplicados=()):
    modulo = _cargar()
    with patch.object(modulo, "op") as op_mock:
        op_mock.get_bind.return_value.execute.return_value.all.return_value = list(duplicados)
        getattr(modulo, direccion)()
    return op_mock


def _sql(op_mock):
    return [str(c.args[0]) for c in op_mock.execute.call_args_list]


def test_encadena_sobre_vendedor_y_la_cabeza_es_la_del_aviso():
    guion = ScriptDirectory.from_config(Config(str(_RAIZ / "alembic_motored.ini")))

    assert guion.get_heads() == ["b5d91e3a7c42"]
    assert _cargar().down_revision == "e8c2a5f17b93"


def test_upgrade_normaliza_codigos_y_cambia_el_unico():
    op_mock = _correr("upgrade")

    assert any("SET codigo = trim(codigo)" in s for s in _sql(op_mock))
    op_mock.drop_constraint.assert_called_once_with(
        "uq_referencia_codigo_proveedor", "referencia", type_="unique")
    op_mock.create_unique_constraint.assert_called_once_with(
        "uq_referencia_codigo", "referencia", ["codigo"])


def test_la_guarda_corre_antes_de_tocar_nada():
    modulo = _cargar()
    orden = []
    with patch.object(modulo, "op") as op_mock:
        op_mock.get_bind.return_value.execute.side_effect = (
            lambda *a, **k: orden.append("guarda") or MagicMock(all=lambda: []))
        op_mock.execute.side_effect = lambda *a, **k: orden.append("update")
        op_mock.drop_constraint.side_effect = lambda *a, **k: orden.append("drop")
        modulo.upgrade()

    assert orden[0] == "guarda" and orden.index("guarda") < orden.index("update") < orden.index("drop")


def test_la_guarda_aborta_listando_los_codigos_duplicados():
    modulo = _cargar()
    with patch.object(modulo, "op") as op_mock:
        op_mock.get_bind.return_value.execute.return_value.all.return_value = [
            ("ABC-1", 2), ("XYZ-9", 3)]
        with pytest.raises(RuntimeError) as exc:
            modulo.upgrade()

    assert "ABC-1" in str(exc.value) and "XYZ-9" in str(exc.value)
    assert not op_mock.drop_constraint.called and not op_mock.create_unique_constraint.called
    assert not op_mock.execute.called


def test_la_guarda_lista_a_lo_sumo_50_codigos():
    duplicados = [(f"COD-{i:03d}", 2) for i in range(51)]
    modulo = _cargar()
    with patch.object(modulo, "op") as op_mock:
        op_mock.get_bind.return_value.execute.return_value.all.return_value = duplicados
        with pytest.raises(RuntimeError) as exc:
            modulo.upgrade()

    assert "COD-049" in str(exc.value) and "COD-050" not in str(exc.value)


def test_downgrade_restaura_el_unico_compuesto():
    op_mock = _correr("downgrade")

    op_mock.drop_constraint.assert_called_once_with(
        "uq_referencia_codigo", "referencia", type_="unique")
    op_mock.create_unique_constraint.assert_called_once_with(
        "uq_referencia_codigo_proveedor", "referencia", ["codigo", "proveedor_id"])
