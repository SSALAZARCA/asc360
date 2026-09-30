"""
Motored Pedidos F3 "Motor" (S8a, ADR-10) — corrida de los niveles A1 y A2.

`ejecutar_nivel_a` lee el libro UNA vez y corre los dos niveles; el informe
JSON (todas las diferencias, con códigos y números) se escribe sólo por
`escribir_informe`, que rechaza cualquier ruta dentro de un árbol git. El
texto de consola (`resumen_texto`) lleva conteos y una muestra acotada de
diferencias, nunca filas de datos completas.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from app.motored.herramientas.regresion.comparador import (
    Diferencia,
    ResultadoNivel,
    ejecutar_nivel_a1,
    ejecutar_nivel_a2,
)
from app.motored.herramientas.regresion.extractor_excel import (
    GrupoEmpate,
    informe_empates,
    leer_libro,
)
from app.motored.herramientas.regresion.rutas import ruta_salida_segura
from app.motored.herramientas.regresion.taxonomia import (
    CATEGORIAS,
    SIN_CATEGORIA,
)

MUESTRA_DIFERENCIAS = 5


@dataclass(frozen=True)
class InformeNivelA:
    """Resultado de A1 y A2 sobre un libro, más el informe de empates."""

    sucursal: str
    filas: int
    a1: ResultadoNivel
    a2: ResultadoNivel
    empates: tuple[GrupoEmpate, ...]


def ejecutar_nivel_a(ruta_excel,
                     aceptaciones: Optional[Mapping[str, str]] = None
                     ) -> InformeNivelA:
    """Corre A1 y A2 contra el libro en `ruta_excel`."""
    lectura = leer_libro(ruta_excel)
    return InformeNivelA(
        sucursal=lectura.sucursal.nombre,
        filas=len(lectura.filas),
        a1=ejecutar_nivel_a1(lectura, aceptaciones),
        a2=ejecutar_nivel_a2(lectura, aceptaciones),
        empates=informe_empates(lectura.filas),
    )


def _diferencia_dict(diferencia: Diferencia) -> dict:
    return {
        "codigo": diferencia.codigo,
        "fila": diferencia.fila,
        "columna": diferencia.columna,
        "valor_excel": diferencia.valor_excel,
        "valor_motor": diferencia.valor_motor,
        "delta": None if diferencia.delta is None else str(diferencia.delta),
        "categoria": diferencia.categoria,
    }


def _nivel_dict(resultado: ResultadoNivel) -> dict:
    return {
        "nivel": resultado.nivel,
        "filas_excel": resultado.filas_excel,
        "filas_exactas": resultado.filas_exactas,
        "filas_con_diferencias": resultado.filas_con_diferencias,
        "exacto": resultado.exacto,
        "paso": resultado.paso,
        "por_categoria": dict(resultado.por_categoria),
        "filas_por_categoria": dict(resultado.filas_por_categoria),
        "diferencias": [_diferencia_dict(d) for d in resultado.diferencias],
    }


def _empates_dict(empates: tuple[GrupoEmpate, ...]) -> dict:
    return {
        "grupos": len(empates),
        "coinciden": sum(1 for grupo in empates if grupo.coincide),
        "detalle": [
            {
                "n": str(grupo.n),
                "codigos_excel": list(grupo.codigos_excel),
                "codigos_asc": list(grupo.codigos_asc),
                "coincide": grupo.coincide,
            }
            for grupo in empates
        ],
    }


def informe_a_dict(informe: InformeNivelA) -> dict:
    """Informe serializable a JSON (los decimales van como texto)."""
    return {
        "sucursal": informe.sucursal,
        "filas": informe.filas,
        "a1": _nivel_dict(informe.a1),
        "a2": _nivel_dict(informe.a2),
        "empates": _empates_dict(informe.empates),
        "taxonomia": dict(CATEGORIAS),
    }


def escribir_informe(informe: InformeNivelA, destino) -> Path:
    """Escribe el informe JSON fuera del repositorio y devuelve la ruta."""
    ruta = ruta_salida_segura(destino)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(informe_a_dict(informe), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ruta


def _lineas_nivel(resultado: ResultadoNivel, muestra: int) -> list[str]:
    lineas = [
        f"{resultado.nivel}: {resultado.filas_exactas} de "
        f"{resultado.filas_excel} filas exactas; "
        f"{len(resultado.diferencias)} diferencias; "
        f"{'PASA' if resultado.paso else 'FALLA'}"
    ]
    for categoria, total in sorted(resultado.por_categoria.items()):
        filas = resultado.filas_por_categoria.get(categoria, 0)
        lineas.append(
            f"  {categoria}: {total} diferencias en {filas} filas"
        )
    # Primero lo inexplicado: es lo que hay que mirar.
    ordenadas = sorted(
        resultado.diferencias, key=lambda d: d.categoria != SIN_CATEGORIA
    )
    for d in ordenadas[:muestra]:
        lineas.append(
            f"    {d.codigo} {d.columna}: Excel {d.valor_excel} "
            f"motor {d.valor_motor} [{d.categoria}]"
        )
    return lineas


def resumen_texto(informe: InformeNivelA,
                  muestra: int = MUESTRA_DIFERENCIAS) -> list[str]:
    """Líneas de consola: conteos por nivel y categoría, y una muestra."""
    coinciden = sum(1 for grupo in informe.empates if grupo.coincide)
    return [
        f"Sucursal: {informe.sucursal} ({informe.filas} filas)",
        *_lineas_nivel(informe.a1, muestra),
        *_lineas_nivel(informe.a2, muestra),
        f"Empates de N: {len(informe.empates)} grupos, {coinciden} con el "
        f"mismo orden que código ascendente",
    ]
