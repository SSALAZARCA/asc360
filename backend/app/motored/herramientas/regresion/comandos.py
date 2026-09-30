"""
Motored Pedidos F3 "Motor" (S8b, ADR-10) — subcomandos de la regresión.

    python scripts/motored_regresion.py nivel-a  --excel X --salida CARPETA
    python scripts/motored_regresion.py nivel-b  --excel X --salida CARPETA \\
        --db-url URL --sucursal-id UUID --fecha-corte AAAA-MM-DD
    python scripts/motored_regresion.py delta    --excel X --salida CARPETA
    python scripts/motored_regresion.py exportar-corrida --excel X \\
        --salida CARPETA

- `nivel-a`: A1 y A2 contra el libro; JSON y libro de comparación.
- `nivel-b`: pipeline contra una base de pruebas ya cargada con los archivos
  revisados (entradas primero, salidas después) y sus hojas en el libro.
- `delta` (nivel C): efecto de cada switch solo y de todos juntos. Con
  `--excel` mide con el motor puro sobre los insumos del libro (los switches
  sin insumos quedan "NO MEDIDO" con el motivo) y exige que el nivel A pase
  antes; con `--sucursal-id` corre una corrida escenario real por switch.
- `exportar-corrida`: libro de corrida simple, con los insumos del libro de
  Excel (`--excel`) o desde una corrida guardada (`--corrida-id`).

Todas las salidas van a una carpeta (`--salida` o `MOTORED_REGRESION_SALIDA`)
que jamás puede estar dentro de un árbol git. Códigos de salida: 0 todo pasa,
1 algún nivel tiene diferencias sin categoría, 2 uso incorrecto o error.
"""
import argparse
import asyncio
import os
import re
import sys
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import IO, Callable, Mapping, Optional, Sequence
from uuid import UUID

from app.motored.herramientas.regresion.antiguedad import (
    desde_seleccion,
    sin_datos,
)
from app.motored.herramientas.regresion.comparador import (
    FECHA_CORTE_ARNES,
    atributos_de,
    entradas_de,
)
from app.motored.herramientas.regresion.delta import (
    NOMBRE_BASE,
    InsumosMemoria,
    ResultadoEscenario,
    escenarios_estandar,
    medir_en_memoria,
)
from app.motored.herramientas.regresion.extractor_excel import leer_libro
from app.motored.herramientas.regresion.informe_comparacion import (
    ContenidoComparacion,
    escribir_libro_comparacion,
)
from app.motored.herramientas.regresion.informe_excel import (
    DatosCorrida,
    SucursalCorrida,
    escribir_libro_corrida,
)
from app.motored.herramientas.regresion.nivel_a import (
    InformeNivelA,
    ejecutar_nivel_a,
    escribir_informe,
    resumen_texto,
)
from app.motored.herramientas.regresion.nivel_b import (
    ejecutar_nivel_b,
    resumen_texto_b,
)
from app.motored.herramientas.regresion.rutas import (
    ENV_ACEPTACIONES,
    ENV_DB_URL,
    ENV_EXCEL,
    ENV_SALIDA,
    ruta_desde,
    ruta_salida_segura,
)
from app.motored.herramientas.regresion.taxonomia import cargar_aceptaciones
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.tipos import ParametrosMotor

SALIDA_OK = 0
SALIDA_FALLA = 1
SALIDA_USO = 2
MOTIVO_EXCEL = "libro de Excel de referencia (sin fecha de carga por tipo)"
TITULO_EXCEL = "Insumos del libro de Excel"
AVISO_CORTE = "fecha de corte de referencia del arnés (el libro no la trae)"


def _db():
    """`comandos_db`, cargado sólo al usar una base: arrastra `app.config`,
    que exige las variables de entorno de producción."""
    from app.motored.herramientas.regresion import comandos_db
    return comandos_db


class ErrorUso(ValueError):
    """Faltan opciones o son inválidas: código de salida 2."""


@dataclass(frozen=True)
class Contexto:
    """Argumentos, entorno, consola y fábrica de sesiones de un comando."""

    args: argparse.Namespace
    entorno: Mapping[str, str]
    salida: IO[str]
    abrir_sesion: Optional[Callable]
    confirmar: bool


# --- Opciones ---------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="motored_regresion",
        description="Regresión de Motored Pedidos F3 contra el Excel.",
    )
    comandos = parser.add_subparsers(dest="comando", required=True)
    a = comandos.add_parser("nivel-a", help="A1 y A2 contra el libro")
    _salida_y_excel(a)
    b = comandos.add_parser("nivel-b", help="pipeline contra una base")
    _salida_y_excel(b)
    _base(b, corrida=True)
    d = comandos.add_parser("delta", help="efecto de cada switch (nivel C)")
    _salida_y_excel(d)
    _base(d, corrida=False)
    d.add_argument("--factores", default="1", help="factores de demanda "
                   "perdida, separados por coma (por defecto 1)")
    d.add_argument("--dias", default="7,15", help="períodos de revisión, "
                   "separados por coma (por defecto 7,15)")
    e = comandos.add_parser("exportar-corrida", help="libro de una corrida")
    _salida_y_excel(e)
    e.add_argument("--db-url", help=f"base de pruebas (o {ENV_DB_URL})")
    e.add_argument("--corrida-id", help="corrida guardada a exportar")
    return parser


def _salida_y_excel(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--excel", help=f"libro (o {ENV_EXCEL})")
    parser.add_argument("--salida", help=f"carpeta (o {ENV_SALIDA})")
    parser.add_argument(
        "--aceptaciones", help=f"JSON {{código: categoría}} "
        f"(o {ENV_ACEPTACIONES})",
    )


def _base(parser: argparse.ArgumentParser, *, corrida: bool) -> None:
    parser.add_argument("--db-url", help=f"base de pruebas (o {ENV_DB_URL})")
    parser.add_argument("--sucursal-id", help="sucursal a medir (UUID)")
    parser.add_argument("--fecha-corte", help="corte AAAA-MM-DD")
    if corrida:
        parser.add_argument(
            "--corrida-id", help="corrida base ya calculada (si no, se crea)"
        )


def _carpeta(ctx: Contexto) -> Path:
    ruta = ruta_desde(ctx.args.salida, ENV_SALIDA, ctx.entorno)
    if ruta is None:
        raise ErrorUso(f"Falta la carpeta: use --salida o {ENV_SALIDA}.")
    return ruta_salida_segura(ruta)


def _excel(ctx: Contexto) -> Path:
    ruta = ruta_desde(ctx.args.excel, ENV_EXCEL, ctx.entorno)
    if ruta is None:
        raise ErrorUso(f"Falta el libro: use --excel o {ENV_EXCEL}.")
    if not ruta.is_file():
        raise ErrorUso(f"No se encontró el libro: {ruta}")
    return ruta


def _carpeta_y_excel(ctx: Contexto) -> tuple[Path, Path]:
    """Carpeta y libro; si faltan, el error nombra todo lo que falta."""
    faltan = []
    if not (ctx.args.salida or ctx.entorno.get(ENV_SALIDA)):
        faltan.append(f"--salida o {ENV_SALIDA}")
    if not (ctx.args.excel or ctx.entorno.get(ENV_EXCEL)):
        faltan.append(f"--excel o {ENV_EXCEL}")
    if faltan:
        raise ErrorUso("Faltan rutas: use " + " y ".join(faltan) + ".")
    return _carpeta(ctx), _excel(ctx)


def _aceptaciones(ctx: Contexto) -> Mapping[str, str]:
    ruta = ruta_desde(ctx.args.aceptaciones, ENV_ACEPTACIONES, ctx.entorno)
    return cargar_aceptaciones(ruta) if ruta else {}


def _url(ctx: Contexto) -> str:
    url = ctx.args.db_url or ctx.entorno.get(ENV_DB_URL)
    if not url:
        raise ErrorUso(
            f"Falta la base de pruebas: use --db-url o {ENV_DB_URL}."
        )
    return url


def _uuid(texto: Optional[str], opcion: str) -> UUID:
    try:
        return UUID(str(texto))
    except ValueError as error:
        raise ErrorUso(f"{opcion} no es un UUID válido: {texto}") from error


def _fecha(ctx: Contexto) -> date:
    texto = ctx.args.fecha_corte
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError) as error:
        raise ErrorUso(
            f"--fecha-corte debe ser AAAA-MM-DD (recibió {texto!r})."
        ) from error


def _lista(texto: str, opcion: str, convertir: Callable) -> tuple:
    try:
        return tuple(convertir(t.strip()) for t in texto.split(",") if t)
    except ValueError as error:
        raise ErrorUso(f"{opcion} no es una lista válida: {texto}") from error


# --- Consola ----------------------------------------------------------------


def _signo(valor) -> str:
    return f"{valor:+}"


def _linea_switch(resultado: ResultadoEscenario) -> str:
    nombre, delta = resultado.escenario.nombre, resultado.delta
    if delta is None:
        if nombre == NOMBRE_BASE:
            return f"  {nombre}: BASE"
        return f"  {nombre}: NO MEDIDO ({resultado.motivo_no_medido})"
    return (
        f"  {nombre}: MEDIDO; {delta.lineas_cambiadas} líneas cambiadas; "
        f"unidades {delta.unidades_base} -> {delta.unidades_escenario} "
        f"({_signo(delta.unidades_escenario - delta.unidades_base)}); "
        f"valor {delta.valor_base} -> {delta.valor_escenario} "
        f"({_signo(delta.valor_escenario - delta.valor_base)}); "
        f"{delta.movimientos_clase} movimientos de clase; "
        f"{len(delta.transferidas)} transferidas"
    )


def _imprimir(ctx: Contexto, lineas: Sequence[str]) -> None:
    for linea in lineas:
        ctx.salida.write(linea + "\n")


def _codigo(*pasos: bool) -> int:
    return SALIDA_OK if all(pasos) else SALIDA_FALLA


# --- nivel-a ----------------------------------------------------------------


def _contenido_a(excel: Path, informe: InformeNivelA
                 ) -> ContenidoComparacion:
    return ContenidoComparacion(
        titulo=f"{TITULO_EXCEL} ({excel.name}); {AVISO_CORTE}",
        fecha_corte=FECHA_CORTE_ARNES,
        sucursal=informe.sucursal,
        antiguedad=sin_datos(MOTIVO_EXCEL),
        nivel_a=informe,
    )


async def _nivel_a(ctx: Contexto) -> int:
    carpeta, excel = _carpeta_y_excel(ctx)
    informe = ejecutar_nivel_a(excel, _aceptaciones(ctx))
    json_ruta = escribir_informe(informe, carpeta / "nivel_a.json")
    libro = escribir_libro_comparacion(
        _contenido_a(excel, informe), carpeta / "comparacion_nivel_a.xlsx"
    )
    _imprimir(ctx, [
        *resumen_texto(informe),
        f"Informe JSON: {json_ruta}", f"Libro de Excel: {libro}",
    ])
    return _codigo(informe.a1.paso, informe.a2.paso)


# --- nivel-b ----------------------------------------------------------------


async def _nivel_b(ctx: Contexto) -> int:
    carpeta, excel = _carpeta_y_excel(ctx)
    url = _url(ctx)
    sucursal_id = _uuid(ctx.args.sucursal_id, "--sucursal-id")
    corrida = ctx.args.corrida_id
    fecha = None if corrida else _fecha(ctx)
    aceptaciones = _aceptaciones(ctx)
    lectura, informe = leer_libro(excel), ejecutar_nivel_a(excel, aceptaciones)
    db = _db()
    leida = await db.leer_para_nivel_b(
        db.fabrica_de_sesiones(ctx.abrir_sesion), url, sucursal_id,
        _uuid(corrida, "--corrida-id") if corrida else None, fecha,
        ctx.confirmar,
    )
    resultado = ejecutar_nivel_b(
        lectura, leida.app, aceptaciones, leida.reproduccion_identica
    )
    libro = escribir_libro_comparacion(
        ContenidoComparacion(
            titulo=leida.codigo,
            fecha_corte=leida.app.atributos.fecha_corte,
            sucursal=lectura.sucursal.nombre,
            antiguedad=desde_seleccion(leida.seleccion_datos),
            nivel_a=informe, nivel_b=resultado,
        ),
        carpeta / "comparacion_nivel_b.xlsx",
    )
    _imprimir(ctx, [
        *resumen_texto(informe), *resumen_texto_b(resultado),
        f"Libro de Excel: {libro}",
    ])
    return _codigo(informe.a1.paso, informe.a2.paso, resultado.paso)


# --- delta ------------------------------------------------------------------


def _escenarios(ctx: Contexto) -> tuple:
    factores = _lista(ctx.args.factores, "--factores", str)
    dias = _lista(ctx.args.dias, "--dias", int)
    if not factores or not dias:
        raise ErrorUso("--factores y --dias necesitan al menos un valor.")
    return escenarios_estandar(factores=factores, dias=dias)


def _escribir_delta(ctx: Contexto, carpeta: Path,
                    contenido: ContenidoComparacion) -> Path:
    libro = escribir_libro_comparacion(
        contenido, carpeta / "efecto_switches.xlsx"
    )
    _imprimir(ctx, [
        *(_linea_switch(r) for r in contenido.deltas),
        f"Libro de Excel: {libro}",
    ])
    return libro


async def _delta_excel(ctx: Contexto, carpeta: Path, escenarios) -> int:
    excel = _excel(ctx)
    informe = ejecutar_nivel_a(excel, _aceptaciones(ctx))
    contenido = _contenido_a(excel, informe)
    if not (informe.a1.paso and informe.a2.paso):
        _escribir_delta(ctx, carpeta, contenido)
        _imprimir(ctx, [
            *resumen_texto(informe),
            "El nivel A no pasa con todo apagado: no se mide ningún switch "
            "hasta que pase.",
        ])
        return SALIDA_FALLA
    lectura = leer_libro(excel)
    insumos = InsumosMemoria(
        tuple(entradas_de(lectura)), atributos_de(lectura), ParametrosMotor()
    )
    resultados = medir_en_memoria(insumos, escenarios)
    _escribir_delta(ctx, carpeta, replace(contenido, deltas=resultados))
    return SALIDA_OK


async def _delta_base(ctx: Contexto, carpeta: Path, escenarios) -> int:
    url = _url(ctx)
    sucursal_id = _uuid(ctx.args.sucursal_id, "--sucursal-id")
    fecha = _fecha(ctx)
    db = _db()
    medicion = await db.medir(
        db.fabrica_de_sesiones(ctx.abrir_sesion), url, sucursal_id, fecha,
        escenarios, ctx.confirmar,
    )
    _escribir_delta(ctx, carpeta, ContenidoComparacion(
        titulo=medicion.codigo_base, fecha_corte=fecha,
        sucursal=medicion.sucursal,
        antiguedad=desde_seleccion(medicion.seleccion_datos),
        deltas=medicion.resultados,
    ))
    return SALIDA_OK


async def _delta(ctx: Contexto) -> int:
    carpeta, escenarios = _carpeta(ctx), _escenarios(ctx)
    if ctx.args.sucursal_id:
        return await _delta_base(ctx, carpeta, escenarios)
    return await _delta_excel(ctx, carpeta, escenarios)


# --- exportar-corrida -------------------------------------------------------


def _slug(texto: str) -> str:
    return re.sub(r"[^\w-]+", "_", texto.strip()).strip("_") or "corrida"


def _corrida_del_libro(excel: Path) -> DatosCorrida:
    """Motor con divisor 21 (A2) sobre los insumos del libro."""
    lectura = leer_libro(excel)
    atributos = atributos_de(lectura)
    resultado = calcular_sucursal(
        entradas_de(lectura), atributos, ParametrosMotor()
    )
    return DatosCorrida(
        titulo=(
            f"{TITULO_EXCEL} ({excel.name}); Z del Excel; {AVISO_CORTE}"
        ),
        fecha_corte=atributos.fecha_corte,
        sucursales=(SucursalCorrida(atributos, resultado),),
        antiguedad=sin_datos(MOTIVO_EXCEL),
    )


async def _exportar_corrida(ctx: Contexto) -> int:
    carpeta = _carpeta(ctx)
    if ctx.args.corrida_id:
        corrida_id = _uuid(ctx.args.corrida_id, "--corrida-id")
        db = _db()
        datos = await db.leer_datos_corrida(
            db.fabrica_de_sesiones(ctx.abrir_sesion), _url(ctx), corrida_id
        )
    else:
        datos = _corrida_del_libro(_excel(ctx))
    nombre = datos.titulo if ctx.args.corrida_id else (
        datos.sucursales[0].atributos.nombre
    )
    libro = escribir_libro_corrida(
        datos, carpeta / f"corrida_{_slug(nombre)}.xlsx"
    )
    _imprimir(ctx, [
        f"Corrida: {datos.titulo} ({len(datos.sucursales)} sucursales)",
        f"Libro de Excel: {libro}",
    ])
    return SALIDA_OK


# --- Punto de entrada -------------------------------------------------------

_COMANDOS: Mapping[str, Callable] = {
    "nivel-a": _nivel_a,
    "nivel-b": _nivel_b,
    "delta": _delta,
    "exportar-corrida": _exportar_corrida,
}


async def ejecutar(argv: Optional[Sequence[str]] = None,
                   entorno: Optional[Mapping[str, str]] = None,
                   salida: Optional[IO[str]] = None, *,
                   abrir_sesion: Optional[Callable] = None,
                   confirmar: bool = True) -> int:
    """Corre un subcomando y devuelve el código de salida del proceso."""
    try:
        args = _parser().parse_args(argv)
    except SystemExit as salida_argparse:
        return int(salida_argparse.code or 0)
    ctx = Contexto(
        args, os.environ if entorno is None else entorno,
        salida or sys.stdout, abrir_sesion, confirmar,
    )
    try:
        return await _COMANDOS[args.comando](ctx)
    except ErrorCorrida as error:
        ctx.salida.write(f"Error: {error.codigo}: {error.mensaje}\n")
    except (ValueError, LookupError) as error:
        ctx.salida.write(f"Error: {error}\n")
    except OSError as error:
        ctx.salida.write(
            f"Error de archivo: no se pudo acceder a "
            f"{error.filename or 'una ruta'} ({error.strerror or error})\n"
        )
    return SALIDA_USO


def main(argv: Optional[Sequence[str]] = None,
         entorno: Optional[Mapping[str, str]] = None,
         salida: Optional[IO[str]] = None) -> int:
    """Punto de entrada síncrono de `scripts/motored_regresion.py`."""
    return asyncio.run(ejecutar(argv, entorno, salida))

