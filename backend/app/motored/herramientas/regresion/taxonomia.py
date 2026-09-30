"""
Motored Pedidos F3 "Motor" (S8a, ADR-10) — taxonomía de diferencias.

Toda diferencia entre el Excel y el motor en los niveles A1/A2 lleva una
categoría documentada. Una diferencia que ninguna regla explica queda como
`SIN_CATEGORIA` y hace fallar el nivel, salvo que el archivo de aceptaciones
(`{código de referencia: categoría}`) la acepte de forma explícita.

T6, T7 y T8 describen divergencias de datos que sólo aparecen en el nivel B
(pipeline completo); a nivel de fórmulas únicamente entran por aceptación.
T11 es la etiqueta DS de la clase D (decisión #19).
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

SIN_CATEGORIA = "SIN_CATEGORIA"

CATEGORIAS: Mapping[str, str] = {
    "T1": "Divisor /18 de la plantilla en lugar de 21 (error de plantilla).",
    "T2": "Efecto en cascada: cambian la suma de N y el orden, y con ellos "
          "el peso, el acumulado y la clase ABC de otras filas.",
    "T3": "Empate de N: el Excel clasifica fila por fila según el orden "
          "físico; el motor da a todo el grupo empatado la clase de su "
          "primera posición (decisión #17) y ordena por código (H5).",
    "T4": "La clase S estática del Excel contradice su propia fórmula Q y R, "
          "y el stock objetivo del Excel se calculó con esa S estática.",
    "T5": "Unidad de empaque 0 en el Excel (IFERROR da pedido 0); la base "
          "de datos nunca guarda U = 0.",
    "T6": "Tránsito recalculado al corte frente a la bandera congelada del "
          "Excel (nivel B).",
    "T7": "Datos cambiados después de la revisión del dueño (nivel B).",
    "T8": "Etiquetas de mes desplazadas: Excel feb..jul frente a la ventana "
          "de la aplicación (nivel B).",
    "T9": "Frontera de punto flotante binario: el Excel redondea un .5 o un "
          "corte ABC exacto hacia el otro lado que la aritmética exacta.",
    "T10": "Etiqueta del resumen AA1:AE11: la fila CF figura como CM y el "
           "total del Excel no suma CF.",
    "T11": "Etiqueta de clase D: el Excel rotula DM o DF a las filas con "
           "N <= 0 según su letra FMS; el motor las rotula todas DS "
           "(decisión #19) y no cambia ninguna cantidad.",
    SIN_CATEGORIA: "Diferencia sin explicación: hace fallar el nivel salvo "
                   "que esté en el archivo de aceptaciones.",
}

_COLUMNAS_CLASE = frozenset({"S", "AA", "AB", "AC", "AD"})
_COLUMNAS_PEDIDO = frozenset({"AB", "AC", "AD"})
_COLUMNAS_ABC = frozenset({"Q", "S", "AA", "AB", "AC", "AD"})
# La cobertura depende sólo de la letra FMS (y D): la cascada de la suma de N
# mueve peso, acumulado y clase ABC, pero jamás AA..AD de una fila sin cambio
# de N.
_COLUMNAS_CASCADA = frozenset({"O", "P", "Q", "S"})


@dataclass(frozen=True)
class ContextoFila:
    """Hechos de una fila que deciden la categoría de sus diferencias.

    `columnas_empate` son las columnas de la fila cuyo valor cambia SÓLO por
    el desempate (orden físico del Excel frente a código ascendente).
    """

    nivel: str = "A1"
    divisor_distinto: bool = False
    hay_divisor_distinto: bool = False
    estatica_inconsistente: bool = False
    u_cero: bool = False
    columnas_empate: frozenset[str] = frozenset()
    frontera_medio: bool = False
    frontera_abc: bool = False
    d_como_ds: bool = False


def _t1(columna: str, ctx: ContextoFila) -> bool:
    return ctx.nivel == "A2" and ctx.divisor_distinto


def _t4(columna: str, ctx: ContextoFila) -> bool:
    return ctx.estatica_inconsistente and columna in _COLUMNAS_CLASE


def _t5(columna: str, ctx: ContextoFila) -> bool:
    return ctx.u_cero and columna in _COLUMNAS_PEDIDO


def _t9(columna: str, ctx: ContextoFila) -> bool:
    medio = ctx.frontera_medio and columna in _COLUMNAS_PEDIDO
    return medio or (ctx.frontera_abc and columna in _COLUMNAS_ABC)


def _t11(columna: str, ctx: ContextoFila) -> bool:
    return ctx.d_como_ds and columna == "S"


def _t3(columna: str, ctx: ContextoFila) -> bool:
    return columna in ctx.columnas_empate


def _t2(columna: str, ctx: ContextoFila) -> bool:
    return (
        ctx.nivel == "A2" and ctx.hay_divisor_distinto
        and columna in _COLUMNAS_CASCADA
    )


# El orden es la precedencia: la causa más específica de la fila gana.
_REGLAS: tuple[tuple[str, Callable[[str, ContextoFila], bool]], ...] = (
    ("T1", _t1), ("T4", _t4), ("T5", _t5), ("T9", _t9), ("T11", _t11),
    ("T3", _t3), ("T2", _t2),
)


def clasificar(columna: str, ctx: ContextoFila) -> str:
    """Categoría de una diferencia en `columna` de una fila con `ctx`."""
    for categoria, regla in _REGLAS:
        if regla(columna, ctx):
            return categoria
    return SIN_CATEGORIA


def cargar_aceptaciones(ruta: Path) -> Mapping[str, str]:
    """Lee `{código: categoría}`; rechaza formas o categorías inválidas."""
    contenido = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if not isinstance(contenido, dict):
        raise ValueError("El archivo de aceptaciones debe ser un objeto JSON")
    for codigo, categoria in contenido.items():
        if categoria not in CATEGORIAS or categoria == SIN_CATEGORIA:
            raise ValueError(
                f"Categoría inválida para {codigo!r}: {categoria!r}"
            )
    return dict(contenido)


def aplicar_aceptacion(categoria: str, codigo: str,
                       aceptaciones: Mapping[str, str]) -> str:
    """Sustituye `SIN_CATEGORIA` por la categoría aceptada del código."""
    if categoria == SIN_CATEGORIA and codigo in aceptaciones:
        return aceptaciones[codigo]
    return categoria
