"""
Motored Pedidos F3 "Motor" (S8a, ADR-10) — CLI de los niveles A1/A2.

    python -m app.motored.herramientas.regresion.cli \\
        --excel RUTA_DEL_LIBRO.xlsx --salida RUTA_FUERA_DEL_REPO/informe.json

Las rutas también pueden venir de `MOTORED_REGRESION_EXCEL`,
`MOTORED_REGRESION_SALIDA` y `MOTORED_REGRESION_ACEPTACIONES`. El informe
completo se escribe en la ruta de salida, que jamás puede estar dentro de un
árbol git; en consola sólo salen conteos y una muestra acotada.

Códigos de salida: 0 ambos niveles pasan; 1 algún nivel tiene diferencias
`SIN_CATEGORIA`; 2 uso incorrecto o libro con otra estructura.
"""
import argparse
import os
import sys
from pathlib import Path
from typing import IO, Mapping, Optional, Sequence

from app.motored.herramientas.regresion.nivel_a import (
    ejecutar_nivel_a,
    escribir_informe,
    resumen_texto,
)
from app.motored.herramientas.regresion.rutas import (
    ENV_ACEPTACIONES,
    ENV_EXCEL,
    ENV_SALIDA,
    ruta_desde,
    ruta_salida_segura,
)
from app.motored.herramientas.regresion.taxonomia import cargar_aceptaciones

SALIDA_OK = 0
SALIDA_FALLA = 1
SALIDA_USO = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="regresion-nivel-a",
        description="Niveles A1/A2 de la regresión contra el Excel.",
    )
    parser.add_argument("--excel", help=f"libro (o {ENV_EXCEL})")
    parser.add_argument("--salida", help=f"informe JSON (o {ENV_SALIDA})")
    parser.add_argument(
        "--aceptaciones",
        help=f"JSON {{código: categoría}} (o {ENV_ACEPTACIONES})",
    )
    return parser


def _rutas(argumentos, entorno: Mapping[str, str]) -> tuple:
    return (
        ruta_desde(argumentos.excel, ENV_EXCEL, entorno),
        ruta_desde(argumentos.salida, ENV_SALIDA, entorno),
        ruta_desde(argumentos.aceptaciones, ENV_ACEPTACIONES, entorno),
    )


def _correr(excel: Path, destino: Path, aceptaciones: Optional[Path],
            salida: IO[str]) -> int:
    destino = ruta_salida_segura(destino)
    if not excel.is_file():
        raise ValueError(f"No se encontró el libro: {excel}")
    aceptadas = cargar_aceptaciones(aceptaciones) if aceptaciones else {}
    informe = ejecutar_nivel_a(excel, aceptadas)
    escrito = escribir_informe(informe, destino)
    for linea in resumen_texto(informe):
        salida.write(linea + "\n")
    salida.write(f"Informe completo: {escrito}\n")
    ok = informe.a1.paso and informe.a2.paso
    return SALIDA_OK if ok else SALIDA_FALLA


def main(argv: Optional[Sequence[str]] = None,
         entorno: Optional[Mapping[str, str]] = None,
         salida: Optional[IO[str]] = None) -> int:
    """Punto de entrada; devuelve el código de salida del proceso."""
    salida = salida or sys.stdout
    entorno = os.environ if entorno is None else entorno
    excel, destino, aceptaciones = _rutas(_parser().parse_args(argv), entorno)
    if excel is None or destino is None:
        salida.write(
            f"Faltan rutas: use --excel y --salida, o las variables "
            f"{ENV_EXCEL} y {ENV_SALIDA}.\n"
        )
        return SALIDA_USO
    try:
        return _correr(excel, destino, aceptaciones, salida)
    except ValueError as error:
        # Ruta insegura, libro con otra estructura, precondición del preset
        # o aceptaciones inválidas: todos son errores de uso, no fallas.
        salida.write(f"Error: {error}\n")
        return SALIDA_USO
    except OSError as error:
        # Aceptaciones inexistentes, informe sin permiso de escritura, etc.
        salida.write(
            f"Error de archivo: no se pudo acceder a "
            f"{error.filename or 'una ruta'} ({error.strerror or error})\n"
        )
        return SALIDA_USO


if __name__ == "__main__":
    raise SystemExit(main())
