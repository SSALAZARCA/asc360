"""
Motored Pedidos F3 "Motor" (S8a-1, ADR-10) — guarda de rutas de la
herramienta de regresión: los informes jamás se escriben dentro de un árbol
git y las rutas reales sólo llegan por argumento o variable de entorno.
"""
from pathlib import Path

import pytest

from app.motored.herramientas.regresion.rutas import (
    ENV_ACEPTACIONES,
    ENV_EXCEL,
    ENV_SALIDA,
    RutaInsegura,
    ruta_desde,
    ruta_salida_segura,
)


def _repositorio(base: Path) -> Path:
    repo = base / "repo"
    (repo / ".git").mkdir(parents=True)
    return repo


class TestRutaSalidaSegura:
    def test_rechaza_una_ruta_dentro_de_un_arbol_git(self, tmp_path):
        repo = _repositorio(tmp_path)
        with pytest.raises(RutaInsegura) as error:
            ruta_salida_segura(repo / "informes" / "a.json")
        assert str(repo.resolve()) in str(error.value)

    def test_rechaza_el_git_de_un_worktree_que_es_un_archivo(self, tmp_path):
        repo = tmp_path / "worktree"
        repo.mkdir()
        (repo / ".git").write_text("gitdir: /otro/lugar\n")
        with pytest.raises(RutaInsegura):
            ruta_salida_segura(repo / "a.json")

    def test_acepta_una_ruta_fuera_de_cualquier_repositorio(self, tmp_path):
        _repositorio(tmp_path)
        destino = tmp_path / "salida" / "a.json"
        assert ruta_salida_segura(destino) == destino.resolve()

    def test_rechaza_un_enlace_simbolico_hacia_el_repositorio(self, tmp_path):
        repo = _repositorio(tmp_path)
        enlace = tmp_path / "enlace"
        enlace.symlink_to(repo, target_is_directory=True)
        with pytest.raises(RutaInsegura):
            ruta_salida_segura(enlace / "a.json")

    def test_rechaza_el_repositorio_real_del_proyecto(self):
        with pytest.raises(RutaInsegura):
            ruta_salida_segura(Path(__file__).parent / "informe.json")


class TestRutaDesde:
    def test_el_argumento_gana_a_la_variable(self):
        entorno = {ENV_EXCEL: "/datos/entorno.xlsx"}
        ruta = ruta_desde("/datos/arg.xlsx", ENV_EXCEL, entorno)
        assert ruta == Path("/datos/arg.xlsx")

    def test_usa_la_variable_si_no_hay_argumento(self):
        entorno = {ENV_SALIDA: "/fuera/informe.json"}
        assert ruta_desde(None, ENV_SALIDA, entorno) == Path(
            "/fuera/informe.json"
        )

    def test_sin_argumento_ni_variable_no_hay_ruta(self):
        assert ruta_desde(None, ENV_ACEPTACIONES, {}) is None

    def test_las_variables_son_las_documentadas(self):
        assert ENV_EXCEL == "MOTORED_REGRESION_EXCEL"
        assert ENV_SALIDA == "MOTORED_REGRESION_SALIDA"
        assert ENV_ACEPTACIONES == "MOTORED_REGRESION_ACEPTACIONES"
