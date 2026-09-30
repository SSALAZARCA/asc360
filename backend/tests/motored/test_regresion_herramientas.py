"""
Motored Pedidos F3 "Motor" (S8a-1, ADR-10) — guardas estructurales de la
herramienta de regresión:

- ningún sitio de producción pasa `AjustesPrueba` (el /18 del Excel y el
  orden físico son sólo del arnés, nivel A1);
- ningún módulo de la aplicación importa `app.motored.herramientas`;
- el repositorio no contiene libros de Excel (los datos reales viven fuera).

El resto de la herramienta se prueba en `test_regresion_rutas.py`,
`test_regresion_taxonomia.py`, `test_regresion_extractor.py`,
`test_regresion_comparador.py` y `test_regresion_nivel_a.py`.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
HERRAMIENTAS = APP / "motored" / "herramientas"
ARCHIVOS_DE_DATOS = ("*.xlsx", "*.xlsm", "*.xlsb", "*.xls")


def _usos_de_ajustes(fuente: str) -> list[int]:
    """Líneas que construyen `AjustesPrueba` o pasan `ajustes_prueba=`."""
    lineas = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.Call):
            continue
        funcion = nodo.func
        nombre = getattr(funcion, "id", None) or getattr(funcion, "attr", "")
        pasa_keyword = any(k.arg == "ajustes_prueba" for k in nodo.keywords)
        if nombre == "AjustesPrueba" or pasa_keyword:
            lineas.append(nodo.lineno)
    return lineas


def _modulos_de(directorio: Path):
    return sorted(
        ruta for ruta in directorio.rglob("*.py")
        if "__pycache__" not in ruta.parts
    )


class TestDeteccionDeAjustes:
    def test_detecta_la_construccion(self):
        assert _usos_de_ajustes("x = AjustesPrueba(orden_explicito=[])") == [1]

    def test_detecta_la_construccion_con_modulo(self):
        fuente = "x = tipos.AjustesPrueba()"
        assert _usos_de_ajustes(fuente) == [1]

    def test_detecta_el_keyword_en_una_llamada(self):
        fuente = "calcular_sucursal(a, b, c, ajustes_prueba=x)"
        assert _usos_de_ajustes(fuente) == [1]

    def test_ignora_la_definicion_y_las_llamadas_sin_ajustes(self):
        fuente = (
            "def calcular(a, *, ajustes_prueba=None):\n"
            "    return otra(a, ajustes_prueba)\n"
            "calcular(1)\n"
        )
        assert _usos_de_ajustes(fuente) == []


class TestGuardaDeProduccion:
    def test_ningun_sitio_de_produccion_pasa_ajustes_de_prueba(self):
        infractores = {}
        for ruta in _modulos_de(APP):
            if HERRAMIENTAS in ruta.parents:
                continue
            lineas = _usos_de_ajustes(ruta.read_text(encoding="utf-8"))
            if lineas:
                infractores[str(ruta.relative_to(APP))] = lineas
        assert infractores == {}

    def test_el_arnes_si_los_usa_y_el_escaneo_lo_ve(self):
        comparador = HERRAMIENTAS / "regresion" / "comparador.py"
        usos = _usos_de_ajustes(comparador.read_text(encoding="utf-8"))
        assert len(usos) >= 2  # AjustesPrueba(...) y ajustes_prueba=...

    def test_los_modulos_del_motor_estan_cubiertos_por_el_escaneo(self):
        motor = _modulos_de(APP / "motored" / "services" / "motor")
        assert len(motor) >= 10
        assert all(HERRAMIENTAS not in ruta.parents for ruta in motor)


class TestAislamiento:
    def test_la_aplicacion_no_importa_las_herramientas(self):
        importadores = []
        for ruta in _modulos_de(APP):
            if HERRAMIENTAS in ruta.parents:
                continue
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                modulos = []
                if isinstance(nodo, ast.ImportFrom):
                    modulos = [nodo.module or ""]
                elif isinstance(nodo, ast.Import):
                    modulos = [alias.name for alias in nodo.names]
                if any("motored.herramientas" in m for m in modulos):
                    importadores.append(str(ruta.relative_to(APP)))
        assert importadores == []

    def test_el_paquete_de_herramientas_existe(self):
        assert (HERRAMIENTAS / "regresion" / "comparador.py").is_file()
        assert (HERRAMIENTAS / "regresion" / "extractor_excel.py").is_file()


class TestSinDatosReales:
    def test_no_hay_libros_de_excel_en_el_codigo_ni_en_los_tests(self):
        encontrados = [
            str(ruta.relative_to(BACKEND))
            for directorio in (APP / "motored", BACKEND / "tests" / "motored")
            for patron in ARCHIVOS_DE_DATOS
            for ruta in directorio.rglob(patron)
        ]
        assert encontrados == []
