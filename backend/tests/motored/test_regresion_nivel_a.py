"""
Motored Pedidos F3 "Motor" (S8a-1, ADR-10) — corrida de los niveles A1/A2
contra un libro, informe JSON y CLI. Todo con libros sintéticos: el informe
de datos reales se escribe fuera del repositorio y la CLI imprime sólo
conteos y una muestra acotada de diferencias.
"""
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.motored.herramientas.regresion import cli
from app.motored.herramientas.regresion.nivel_a import (
    MUESTRA_DIFERENCIAS,
    ejecutar_nivel_a,
    escribir_informe,
    informe_a_dict,
    resumen_texto,
)
from app.motored.herramientas.regresion.rutas import (
    ENV_ACEPTACIONES,
    ENV_EXCEL,
    ENV_SALIDA,
    RutaInsegura,
)
from tests.motored.fixtures.regresion.conjuntos import (
    filas_base,
    filas_con_empate,
)
from tests.motored.fixtures.regresion.libro_sintetico import escribir_libro
from tests.motored.fixtures.regresion.oraculo_excel import (
    CLASES,
    FilaSintetica,
)


def _libro(tmp_path, filas=None, **opciones) -> Path:
    ruta = tmp_path / "datos" / "libro.xlsx"
    ruta.parent.mkdir(exist_ok=True)
    escribir_libro(ruta, filas or filas_base(), etiquetas=CLASES, **opciones)
    return ruta


def _ejecutar(argumentos, entorno=None):
    salida = io.StringIO()
    codigo = cli.main(argumentos, entorno or {}, salida)
    return codigo, salida.getvalue()


class TestEjecutarNivelA:
    def test_corre_a1_y_a2_sobre_el_mismo_libro(self, tmp_path):
        informe = ejecutar_nivel_a(_libro(tmp_path))
        assert informe.sucursal == "SUCURSAL SINTETICA"
        assert informe.filas == 6
        assert informe.a1.exacto and informe.a1.filas_exactas == 6
        assert informe.a2.paso and not informe.a2.exacto

    def test_incluye_el_informe_de_empates(self, tmp_path):
        ruta = _libro(tmp_path, filas_con_empate())
        informe = ejecutar_nivel_a(ruta)
        assert [g.coincide for g in informe.empates] == [False]

    def test_las_aceptaciones_llegan_a_ambos_niveles(self, tmp_path):
        filas = filas_base() + [
            FilaSintetica("Z-000", (0,) * 6, precio=5.0, inventario=3)
        ]
        informe = ejecutar_nivel_a(
            _libro(tmp_path, filas), {"Z-000": "T7"}
        )
        assert informe.a1.paso and informe.a2.paso
        assert informe.a1.filas_por_categoria == {"T7": 1}


class TestInforme:
    def test_dict_con_conteos_categorias_y_diferencias(self, tmp_path):
        informe = ejecutar_nivel_a(_libro(tmp_path))
        datos = informe_a_dict(informe)
        assert datos["sucursal"] == "SUCURSAL SINTETICA"
        assert datos["filas"] == 6
        assert datos["a1"]["exacto"] is True
        assert datos["a1"]["diferencias"] == []
        a2 = datos["a2"]
        assert a2["paso"] is True and a2["filas_exactas"] == 0
        assert a2["por_categoria"]["T1"] >= 1
        primera = a2["diferencias"][0]
        assert set(primera) == {
            "codigo", "fila", "columna", "valor_excel", "valor_motor",
            "delta", "categoria",
        }
        assert {"T1", "SIN_CATEGORIA"} <= set(datos["taxonomia"])

    def test_dict_es_serializable_y_el_delta_va_como_texto(self, tmp_path):
        datos = informe_a_dict(ejecutar_nivel_a(_libro(tmp_path)))
        recargado = json.loads(json.dumps(datos))
        assert isinstance(recargado["a2"]["diferencias"][0]["delta"], str)

    def test_empates_se_resumen_en_el_informe(self, tmp_path):
        informe = ejecutar_nivel_a(_libro(tmp_path, filas_con_empate()))
        empates = informe_a_dict(informe)["empates"]
        assert empates["grupos"] == 1 and empates["coinciden"] == 0
        assert empates["detalle"][0]["codigos_excel"] == ["G-2", "G-1"]

    def test_escribe_fuera_del_repositorio_y_crea_las_carpetas(
        self, tmp_path
    ):
        informe = ejecutar_nivel_a(_libro(tmp_path))
        destino = tmp_path / "salida" / "sub" / "informe.json"
        escrito = escribir_informe(informe, destino)
        assert escrito == destino.resolve()
        assert json.loads(destino.read_text(encoding="utf-8"))["filas"] == 6

    def test_rechaza_escribir_dentro_de_un_repositorio(self, tmp_path):
        informe = ejecutar_nivel_a(_libro(tmp_path))
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        destino = tmp_path / "repo" / "informe.json"
        with pytest.raises(RutaInsegura):
            escribir_informe(informe, destino)
        assert not destino.exists()


class TestResumenTexto:
    def test_conteos_y_categorias_sin_filas_de_datos(self, tmp_path):
        informe = ejecutar_nivel_a(_libro(tmp_path))
        texto = "\n".join(resumen_texto(informe))
        assert "A1: 6 de 6 filas exactas" in texto
        assert "A2: 0 de 6 filas exactas" in texto
        assert "T1" in texto and "PASA" in texto

    def test_la_muestra_de_diferencias_esta_acotada(self, tmp_path):
        informe = ejecutar_nivel_a(_libro(tmp_path))
        assert len(informe.a2.diferencias) > MUESTRA_DIFERENCIAS
        lineas = [
            linea for linea in resumen_texto(informe)
            if linea.startswith("    ")
        ]
        assert len(lineas) == MUESTRA_DIFERENCIAS

    def test_un_nivel_con_sin_categoria_se_marca_como_falla(self, tmp_path):
        ruta = _libro(tmp_path, sobrescribe={"A-100": {"AB": 1}})
        lineas = resumen_texto(ejecutar_nivel_a(ruta))
        a1 = next(linea for linea in lineas if linea.startswith("A1:"))
        assert a1.endswith("FALLA")

    def test_la_muestra_empieza_por_lo_inexplicado(self, tmp_path):
        ruta = _libro(tmp_path, sobrescribe={"A-100": {"AB": 1}})
        lineas = resumen_texto(ejecutar_nivel_a(ruta))
        desde_a2 = lineas[next(
            i for i, linea in enumerate(lineas) if linea.startswith("A2:")
        ):]
        primera = next(x for x in desde_a2 if x.startswith("    "))
        assert "[SIN_CATEGORIA]" in primera


class TestCli:
    def test_corre_y_escribe_el_informe_con_argumentos(self, tmp_path):
        ruta = _libro(tmp_path)
        destino = tmp_path / "fuera" / "informe.json"
        codigo, texto = _ejecutar(
            ["--excel", str(ruta), "--salida", str(destino)]
        )
        assert codigo == 0
        assert json.loads(destino.read_text(encoding="utf-8"))["filas"] == 6
        assert "A1: 6 de 6 filas exactas" in texto
        assert str(destino.resolve()) in texto

    def test_las_rutas_pueden_venir_del_entorno(self, tmp_path):
        ruta = _libro(tmp_path)
        destino = tmp_path / "fuera" / "informe.json"
        codigo, _ = _ejecutar([], {
            ENV_EXCEL: str(ruta), ENV_SALIDA: str(destino),
        })
        assert codigo == 0 and destino.exists()

    def test_aplica_el_archivo_de_aceptaciones(self, tmp_path):
        filas = filas_base() + [
            FilaSintetica("Z-000", (0,) * 6, precio=5.0, inventario=3)
        ]
        ruta = _libro(tmp_path, filas)
        aceptaciones = tmp_path / "aceptaciones.json"
        aceptaciones.write_text(json.dumps({"Z-000": "T7"}))
        destino = tmp_path / "fuera" / "informe.json"
        argumentos = ["--excel", str(ruta), "--salida", str(destino)]
        assert _ejecutar(argumentos)[0] == 1
        con = argumentos + ["--aceptaciones", str(aceptaciones)]
        assert _ejecutar(con)[0] == 0
        entorno = {ENV_ACEPTACIONES: str(aceptaciones)}
        assert _ejecutar(argumentos, entorno)[0] == 0

    def test_falla_con_codigo_1_si_un_nivel_tiene_sin_categoria(
        self, tmp_path
    ):
        ruta = _libro(tmp_path, sobrescribe={"A-100": {"AB": 1}})
        destino = tmp_path / "fuera" / "informe.json"
        codigo, texto = _ejecutar(
            ["--excel", str(ruta), "--salida", str(destino)]
        )
        assert codigo == 1
        assert destino.exists() and "FALLA" in texto

    def test_falla_si_solo_a2_tiene_sin_categoria(self, tmp_path, monkeypatch):
        informe = ejecutar_nivel_a(_libro(tmp_path))
        roto = replace(informe, a2=replace(informe.a2, paso=False))
        monkeypatch.setattr(cli, "ejecutar_nivel_a", lambda *a: roto)
        ruta = _libro(tmp_path)
        destino = tmp_path / "fuera" / "informe.json"
        codigo, _ = _ejecutar(["--excel", str(ruta), "--salida", str(destino)])
        assert codigo == 1

    def test_aceptaciones_inexistentes_es_error_de_uso(self, tmp_path):
        ruta = _libro(tmp_path)
        faltante = tmp_path / "no_hay.json"
        codigo, texto = _ejecutar([
            "--excel", str(ruta), "--salida", str(tmp_path / "f" / "i.json"),
            "--aceptaciones", str(faltante),
        ])
        assert codigo == 2 and "no_hay.json" in texto
        assert texto.startswith("Error de archivo")
        assert "Traceback" not in texto

    def test_informe_que_no_se_puede_escribir_es_error_de_uso(
        self, tmp_path, monkeypatch
    ):
        def sin_permiso(*args):
            raise PermissionError(13, "denegado", "informe.json")

        monkeypatch.setattr(cli, "escribir_informe", sin_permiso)
        codigo, texto = _ejecutar([
            "--excel", str(_libro(tmp_path)),
            "--salida", str(tmp_path / "f" / "i.json"),
        ])
        assert codigo == 2 and "informe.json" in texto
        assert texto.startswith("Error de archivo")

    @pytest.mark.parametrize("nombre", ["falso.xlsx", "falso.txt"])
    def test_libro_que_no_es_un_xlsx_valido_es_error_de_uso(
        self, tmp_path, nombre
    ):
        falso = tmp_path / nombre
        falso.write_text("esto no es un libro de Excel")
        codigo, texto = _ejecutar([
            "--excel", str(falso), "--salida", str(tmp_path / "f" / "i.json"),
        ])
        assert codigo == 2 and texto.startswith("Error: ")
        assert "xlsx" in texto and "Traceback" not in texto

    def test_sin_libro_no_hace_nada_y_avisa(self, tmp_path):
        codigo, texto = _ejecutar(
            ["--salida", str(tmp_path / "fuera" / "i.json")]
        )
        assert codigo == 2 and ENV_EXCEL in texto

    def test_sin_salida_no_hace_nada_y_avisa(self, tmp_path):
        codigo, texto = _ejecutar(["--excel", str(_libro(tmp_path))])
        assert codigo == 2 and ENV_SALIDA in texto

    def test_libro_inexistente(self, tmp_path):
        codigo, texto = _ejecutar([
            "--excel", str(tmp_path / "no_existe.xlsx"),
            "--salida", str(tmp_path / "fuera" / "i.json"),
        ])
        assert codigo == 2 and "no_existe.xlsx" in texto

    def test_salida_dentro_del_repositorio_se_rechaza(self, tmp_path):
        ruta = _libro(tmp_path)
        destino = Path(__file__).parent / "informe_prohibido.json"
        codigo, texto = _ejecutar(
            ["--excel", str(ruta), "--salida", str(destino)]
        )
        assert codigo == 2 and "repositorio" in texto
        assert not destino.exists()
