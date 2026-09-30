"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S1-3) — el motor puro
no importa I/O: ni `sqlalchemy`, ni modelos, ni `database`, ni `asyncio`.
"""
import ast
from pathlib import Path

import pytest

import app.motored.services as servicios_pkg

PAQUETE = Path(servicios_pkg.__file__).parent / "motor"
MODULOS_ESPERADOS = {
    "__init__", "aritmetica", "tipos", "ventana",
    "demanda", "cobertura", "pedido",
    "clasificacion", "puntos", "resumen", "motor", "sustitucion",
}
PROHIBIDOS = (
    "sqlalchemy",
    "app.motored.models",
    "app.motored.database",
    "asyncio",
)


def _importaciones(ruta: Path):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                yield alias.name
        elif isinstance(nodo, ast.ImportFrom):
            base = nodo.module or ""
            yield base
            for alias in nodo.names:
                yield f"{base}.{alias.name}"


def _es_prohibido(nombre: str) -> bool:
    return any(
        nombre == p or nombre.startswith(p + ".") for p in PROHIBIDOS
    )


def test_el_paquete_del_motor_existe_con_los_modulos_de_s1_y_s2():
    presentes = {p.stem for p in PAQUETE.glob("*.py")}
    assert MODULOS_ESPERADOS <= presentes


@pytest.mark.parametrize(
    "ruta", sorted(PAQUETE.glob("*.py")) or [PAQUETE / "no_existe.py"],
    ids=lambda p: p.name,
)
def test_ningun_modulo_del_motor_importa_io(ruta):
    prohibidas = [n for n in _importaciones(ruta) if _es_prohibido(n)]
    assert prohibidas == []


def test_el_detector_reconoce_imports_prohibidos(tmp_path):
    ejemplo = tmp_path / "malo.py"
    ejemplo.write_text(
        "import asyncio\nfrom sqlalchemy import select\n"
        "from app.motored.models import x\n", encoding="utf-8",
    )
    assert [n for n in _importaciones(ejemplo) if _es_prohibido(n)]
