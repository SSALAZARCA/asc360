"""
Motored Pedidos F3 "Motor" (S8b, ADR-10, decisiones #11 y #16) — libro de
comparación y de efecto de los switches para el dueño.

Hojas, en este orden (sólo las que el contenido trae):

- `Resumen`: sucursal, fecha de corte, fuente y una fila por nivel con
  conteos, categorías y resultado;
- `Antigüedad de datos`: la sección de la decisión #16;
- `Filas`: por referencia, diferencias de cada nivel y sus categorías;
- `A1`, `A2`, `B-entradas`, `B-salidas`: cada diferencia con el valor del
  Excel, el de la aplicación, la diferencia y su categoría (las entradas del
  nivel B van antes que las salidas);
- `Resumen switches` y una hoja `Delta ...` por cada switch medido (nivel C);
- `Taxonomía`: qué significa cada categoría.

Se escribe en modo `write_only` por `LibroSalida`, siempre fuera del
repositorio. No es el formato de exportación de HMCL.
"""
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

from app.motored.herramientas.regresion.antiguedad import FilaAntiguedad
from app.motored.herramientas.regresion.comparador import Diferencia
from app.motored.herramientas.regresion.delta import (
    NOMBRE_BASE,
    CambioLinea,
    ConjuntoLineas,
    ResultadoEscenario,
)
from app.motored.herramientas.regresion.informe_excel import hoja_antiguedad
from app.motored.herramientas.regresion.libro_excel import LibroSalida
from app.motored.herramientas.regresion.nivel_a import InformeNivelA
from app.motored.herramientas.regresion.nivel_b import (
    COLUMNA_FILA,
    ResultadoNivelB,
)
from app.motored.herramientas.regresion.taxonomia import CATEGORIAS

HOJA_RESUMEN = "Resumen"
HOJA_FILAS = "Filas"
HOJA_SWITCHES = "Resumen switches"
HOJA_TAXONOMIA = "Taxonomía"
PREFIJO_DELTA = "Delta "
NUMERO = re.compile(r"^-?\d+(\.\d+)?$")
ESTADO_BASE = "BASE"
ESTADO_MEDIDO = "MEDIDO"
ESTADO_NO_MEDIDO = "NO MEDIDO"
TIPO_TRANSFERIDA = "TRANSFERIDA"

ENCABEZADO_NIVELES = (
    "Nivel", "Filas en el Excel", "Filas exactas", "Diferencias",
    "Por categoría", "Resultado",
)
ENCABEZADO_DIFERENCIAS = (
    "Referencia / clase", "Fila Excel", "Columna", "Valor Excel",
    "Valor aplicación", "Diferencia", "Categoría",
    "Descripción de la categoría",
)
NOMBRES_NIVEL = ("A1", "A2", "B-entradas", "B-salidas")
ENCABEZADO_FILAS = (
    "Fila Excel", "Referencia", *(f"Dif. {n}" for n in NOMBRES_NIVEL),
    "Categorías",
)
ENCABEZADO_SWITCHES = (
    "Escenario", "Estado", "Líneas cambiadas", "Unidades base",
    "Unidades escenario", "Delta unidades", "Valor base", "Valor escenario",
    "Delta valor", "Movimientos de clase", "Transferidas", "Overrides",
    "Nota o motivo",
)
ENCABEZADO_DELTA = (
    "Referencia", "Tipo", "Clase base", "Clase escenario", "N base",
    "N escenario", "Pedido base", "Pedido escenario", "Delta pedido",
    "Valor base", "Valor escenario", "Delta valor", "Detalle",
)
ENCABEZADO_TAXONOMIA = ("Categoría", "Descripción")


@dataclass(frozen=True)
class ContenidoComparacion:
    """Lo que lleva el libro; cada parte es opcional salvo la cabecera."""

    titulo: str
    fecha_corte: date
    sucursal: str
    antiguedad: tuple[FilaAntiguedad, ...]
    nivel_a: Optional[InformeNivelA] = None
    nivel_b: Optional[ResultadoNivelB] = None
    deltas: tuple[ResultadoEscenario, ...] = ()


@dataclass(frozen=True)
class _Nivel:
    nombre: str
    filas_excel: int
    diferencias: Sequence[Diferencia]
    paso: bool


def _niveles(contenido: ContenidoComparacion) -> list[_Nivel]:
    niveles = []
    if contenido.nivel_a is not None:
        for resultado in (contenido.nivel_a.a1, contenido.nivel_a.a2):
            niveles.append(_Nivel(
                resultado.nivel, resultado.filas_excel,
                resultado.diferencias, resultado.paso,
            ))
    if contenido.nivel_b is not None:
        b = contenido.nivel_b
        niveles.append(_Nivel(
            "B-entradas", b.filas_excel, b.entradas, b.entradas_pasan
        ))
        niveles.append(_Nivel(
            "B-salidas", b.salidas.filas_excel, b.salidas.diferencias,
            b.salidas.paso,
        ))
    return niveles


def _por_categoria(diferencias: Sequence[Diferencia]) -> str:
    conteo: dict[str, int] = {}
    for d in diferencias:
        conteo[d.categoria] = conteo.get(d.categoria, 0) + 1
    return "; ".join(f"{c}: {n}" for c, n in sorted(conteo.items()))


def _filas_exactas(nivel: _Nivel) -> int:
    con_diferencias = {d.codigo for d in nivel.diferencias if d.fila}
    return nivel.filas_excel - len(con_diferencias)


def _filas_resumen(niveles: Sequence[_Nivel]) -> Iterator[tuple]:
    for nivel in niveles:
        yield (
            nivel.nombre, nivel.filas_excel, _filas_exactas(nivel),
            len(nivel.diferencias), _por_categoria(nivel.diferencias),
            "PASA" if nivel.paso else "FALLA",
        )


def _numero(texto: str) -> Any:
    return Decimal(texto) if NUMERO.match(texto) else texto


def _filas_diferencias(diferencias: Sequence[Diferencia]) -> Iterator[tuple]:
    for d in diferencias:
        yield (
            d.codigo, d.fila, d.columna, _numero(d.valor_excel),
            _numero(d.valor_motor), d.delta, d.categoria,
            CATEGORIAS.get(d.categoria, ""),
        )


def _filas_por_referencia(niveles: Sequence[_Nivel]) -> Iterator[tuple]:
    """Resumen por referencia: conteo de diferencias por nivel."""
    filas: dict[str, dict] = {}
    for nivel in niveles:
        for d in nivel.diferencias:
            if d.fila is None and d.columna != COLUMNA_FILA:
                continue  # cobertura y resumen no son de una referencia
            entrada = filas.setdefault(
                d.codigo, {"fila": d.fila, "conteo": {}, "categorias": set()}
            )
            entrada["fila"] = entrada["fila"] or d.fila
            conteo = entrada["conteo"]
            conteo[nivel.nombre] = conteo.get(nivel.nombre, 0) + 1
            entrada["categorias"].add(d.categoria)
    presentes = {n.nombre for n in niveles}
    for codigo, dato in sorted(
        filas.items(), key=lambda par: (par[1]["fila"] is None, par[1]["fila"])
    ):
        yield (
            dato["fila"], codigo,
            *(
                dato["conteo"].get(nombre, 0) if nombre in presentes else None
                for nombre in NOMBRES_NIVEL
            ),
            ", ".join(sorted(dato["categorias"])),
        )


# --- Switches (nivel C) -----------------------------------------------------


def _json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True)


def _sumas(conjunto: Optional[ConjuntoLineas]) -> tuple:
    if conjunto is None:
        return (None, None)
    lineas = conjunto.lineas.values()
    return (
        sum((linea.pedido for linea in lineas), Decimal(0)),
        sum((linea.valor for linea in lineas), Decimal(0)),
    )


def _fila_switch(resultado: ResultadoEscenario) -> tuple:
    escenario, delta = resultado.escenario, resultado.delta
    overrides = _json(dict(escenario.overrides))
    if delta is None:
        estado = (
            ESTADO_BASE if escenario.nombre == NOMBRE_BASE
            else ESTADO_NO_MEDIDO
        )
        unidades, valor = _sumas(resultado.conjunto)
        return (
            escenario.nombre, estado, None, unidades, None, None, valor,
            None, None, None, None, overrides,
            resultado.motivo_no_medido,
        )
    return (
        escenario.nombre, ESTADO_MEDIDO, delta.lineas_cambiadas,
        delta.unidades_base, delta.unidades_escenario,
        delta.unidades_escenario - delta.unidades_base,
        delta.valor_base, delta.valor_escenario,
        delta.valor_escenario - delta.valor_base,
        delta.movimientos_clase, len(delta.transferidas), overrides,
        resultado.nota,
    )


def _diferencia(base: Optional[Decimal], escenario: Optional[Decimal]
                ) -> Optional[Decimal]:
    if base is None and escenario is None:
        return None
    return (escenario or Decimal(0)) - (base or Decimal(0))


def _fila_cambio(cambio: CambioLinea) -> tuple:
    return (
        cambio.codigo, cambio.tipo, cambio.clase_base,
        cambio.clase_escenario, cambio.n_base, cambio.n_escenario,
        cambio.pedido_base, cambio.pedido_escenario,
        _diferencia(cambio.pedido_base, cambio.pedido_escenario),
        cambio.valor_base, cambio.valor_escenario,
        _diferencia(cambio.valor_base, cambio.valor_escenario), None,
    )


def _filas_delta(resultado: ResultadoEscenario) -> Iterator[tuple]:
    delta = resultado.delta
    for cambio in delta.cambios:
        yield _fila_cambio(cambio)
    for excluida in delta.transferidas:
        yield (
            excluida.codigo, TIPO_TRANSFERIDA, *(None,) * 10,
            f"Demanda transferida a {excluida.sustituta}",
        )


def _previas_delta(resultado: ResultadoEscenario) -> list[tuple]:
    escenario, delta = resultado.escenario, resultado.delta
    previas: list[tuple] = [
        ("Escenario", escenario.nombre),
        ("Descripción", escenario.descripcion),
        ("Overrides", _json(dict(escenario.overrides))),
    ]
    if resultado.nota:
        previas.append(("Nota", resultado.nota))
    previas += [
        ("Líneas base", delta.lineas_base),
        ("Líneas escenario", delta.lineas_escenario),
        ("Líneas cambiadas", delta.lineas_cambiadas),
        ("Movimientos de clase", delta.movimientos_clase),
        ("Transferidas", len(delta.transferidas)),
        ("Unidades base", delta.unidades_base),
        ("Unidades escenario", delta.unidades_escenario),
        ("Delta unidades", delta.unidades_escenario - delta.unidades_base),
        ("Valor base", delta.valor_base),
        ("Valor escenario", delta.valor_escenario),
        ("Delta valor", delta.valor_escenario - delta.valor_base),
        (),
    ]
    return previas


def _hojas_switches(libro: LibroSalida,
                    deltas: Sequence[ResultadoEscenario]) -> None:
    if not deltas:
        return
    libro.hoja(
        HOJA_SWITCHES, ENCABEZADO_SWITCHES,
        (_fila_switch(resultado) for resultado in deltas),
    )
    for resultado in deltas:
        if resultado.delta is None:
            continue
        libro.hoja(
            PREFIJO_DELTA + resultado.escenario.nombre, ENCABEZADO_DELTA,
            _filas_delta(resultado), previas=_previas_delta(resultado),
        )


def escribir_libro_comparacion(contenido: ContenidoComparacion,
                               destino) -> Path:
    """Escribe el libro en `destino` (fuera del repositorio)."""
    niveles = _niveles(contenido)
    libro = LibroSalida(destino)
    libro.hoja(
        HOJA_RESUMEN, ENCABEZADO_NIVELES, _filas_resumen(niveles),
        previas=[
            ("Sucursal", contenido.sucursal),
            ("Fecha de corte", contenido.fecha_corte),
            ("Fuente", contenido.titulo), (),
        ],
    )
    hoja_antiguedad(
        libro, contenido.titulo, contenido.fecha_corte, contenido.antiguedad
    )
    if niveles:
        libro.hoja(
            HOJA_FILAS, ENCABEZADO_FILAS, _filas_por_referencia(niveles)
        )
    for nivel in niveles:
        libro.hoja(
            nivel.nombre, ENCABEZADO_DIFERENCIAS,
            _filas_diferencias(nivel.diferencias),
        )
    _hojas_switches(libro, contenido.deltas)
    libro.hoja(
        HOJA_TAXONOMIA, ENCABEZADO_TAXONOMIA, list(CATEGORIAS.items())
    )
    return libro.guardar()
