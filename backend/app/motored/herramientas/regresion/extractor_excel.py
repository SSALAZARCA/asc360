"""
Motored Pedidos F3 "Motor" (S8a, ADR-10) — extractor de la hoja `Pedido`.

Lee el libro de referencia con `openpyxl` en modo `read_only`, en dos
pasadas sobre la misma hoja:

1. texto de fórmula (`data_only=False`): el divisor de N de cada fila (/18 o
   /21) y si la clase S es fórmula o texto estático;
2. valores cacheados (`data_only=True`): insumos E:J, K, T, U, V, W, X, Z,
   salidas N..AD, factores de cobertura E2:N3, resumen AA1:AE11 y, en la
   hoja `Meses de cobertura`, los días de la sucursal.

El libro real es sólo referencia de ESTRUCTURA y nunca se copia al
repositorio: la ruta llega por argumento o variable de entorno. Los números
pasan a `Decimal` (los `float` de Excel por su `repr`, que es el decimal más
corto que los identifica) para alimentar el motor exacto.
"""
import re
import zipfile
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Mapping, Optional

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

HOJA_PEDIDO = "Pedido"
HOJA_COBERTURA = "Meses de cobertura"
ETIQUETA_TOTAL = "Total general"
PRIMERA_FILA_DATOS = 14
PRIMERA_FILA_COBERTURA = 6
PATRON_DIVISOR = re.compile(r"/\s*(\d+)\s*$")

# Columnas de `Pedido` (índices desde 0: A = 0).
COL_CODIGO, COL_E, COL_K = 0, 4, 10
COL_N, COL_O, COL_P, COL_Q, COL_R, COL_S = 13, 14, 15, 16, 17, 18
COL_T, COL_U, COL_V, COL_W, COL_X, COL_Y, COL_Z = 19, 20, 21, 22, 23, 24, 25
COL_AA, COL_AB, COL_AC, COL_AD = 26, 27, 28, 29
COL_RESUMEN = 26
MESES_CERRADOS = 6
FACTORES = (4, 14)  # E3:N3 -> columnas 4..13
# Filas 2..12 (índice desde 0): el Excel real trae 9 clases y el total en
# la 11; con las 10 clases el total baja a la 12.
FILAS_RESUMEN = range(1, 12)


class ErrorExtractor(ValueError):
    """El libro no tiene la estructura esperada."""


@dataclass(frozen=True)
class SucursalExcel:
    nombre: str
    bodega: str
    sic: Optional[int]
    dias_empaque: Decimal
    dias_transito: Decimal
    dias_seguridad: Decimal


@dataclass(frozen=True)
class FilaExcel:
    """Una fila de `Pedido`: insumos, salidas cacheadas y texto de fórmula."""

    fila: int
    codigo: str
    ventas: tuple[Decimal, ...]
    perdida: Decimal
    precio: Optional[Decimal]
    unidad_empaque: int
    inventario: Decimal
    transito: Decimal
    backorder: Decimal
    ajuste: Decimal
    n: Decimal
    peso: Optional[Decimal]
    acumulado: Optional[Decimal]
    clase_abc: str
    clase_fms: str
    clase_estatica: str
    inventario_final: Decimal
    stock_objetivo: Decimal
    pedido: Decimal
    valor_pedido: Decimal
    cobertura_final: Optional[Decimal]
    divisor: Optional[int]
    s_es_formula: bool


@dataclass(frozen=True)
class FilaResumenExcel:
    etiqueta: str
    unidades: Decimal
    referencias: int
    valor: Decimal
    peso: Optional[Decimal]


@dataclass(frozen=True)
class LecturaExcel:
    sucursal: SucursalExcel
    filas: tuple[FilaExcel, ...]
    coberturas: Mapping[str, Decimal]
    resumen: tuple[FilaResumenExcel, ...]
    total: Optional[FilaResumenExcel]


@dataclass(frozen=True)
class InfoFormula:
    divisor: Optional[int]
    s_es_formula: bool


@dataclass(frozen=True)
class GrupoEmpate:
    """Filas con la misma N: orden del Excel frente a código ascendente."""

    n: Decimal
    codigos_excel: tuple[str, ...]
    codigos_asc: tuple[str, ...]
    coincide: bool


def _dec(valor) -> Optional[Decimal]:
    """`Decimal` de un número de Excel; texto, error o vacío dan `None`."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, Decimal)):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(repr(valor))
    return None


def _dec0(valor) -> Decimal:
    numero = _dec(valor)
    return Decimal(0) if numero is None else numero


def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


def _celda(fila: tuple, indice: int):
    return fila[indice] if indice < len(fila) else None


def _fila_de(filas: list[tuple], indice: int) -> tuple:
    return filas[indice] if indice < len(filas) else ()


@contextmanager
def _libro(ruta: Path, data_only: bool) -> Iterator[openpyxl.Workbook]:
    try:
        libro = openpyxl.load_workbook(
            ruta, read_only=True, data_only=data_only
        )
    except (InvalidFileException, zipfile.BadZipFile) as error:
        raise ErrorExtractor(
            f"El archivo {ruta} no es un libro .xlsx válido ({error})"
        ) from error
    try:
        yield libro
    finally:
        libro.close()


def _hoja(libro, nombre: str):
    if nombre not in libro.sheetnames:
        raise ErrorExtractor(f"El libro no tiene la hoja {nombre!r}")
    return libro[nombre]


def _info_formula(fila: tuple) -> InfoFormula:
    formula_n = _celda(fila, COL_N)
    coincidencia = (
        PATRON_DIVISOR.search(formula_n) if isinstance(formula_n, str)
        else None
    )
    clase = _celda(fila, COL_S)
    return InfoFormula(
        int(coincidencia.group(1)) if coincidencia else None,
        isinstance(clase, str) and clase.startswith("="),
    )


def _pasada_formulas(ruta: Path) -> dict[int, InfoFormula]:
    """`{fila: InfoFormula}` de las filas con referencia en la columna A."""
    info = {}
    with _libro(ruta, data_only=False) as libro:
        hoja = _hoja(libro, HOJA_PEDIDO)
        filas = hoja.iter_rows(min_row=PRIMERA_FILA_DATOS, values_only=True)
        for numero, fila in enumerate(filas, start=PRIMERA_FILA_DATOS):
            if _texto(_celda(fila, COL_CODIGO)):
                info[numero] = _info_formula(fila)
    return info


def _entero(valor, codigo: str) -> int:
    numero = _dec(valor)
    if numero is None:
        return 0
    if numero != numero.to_integral_value():
        raise ErrorExtractor(
            f"Unidad de empaque no entera para {codigo}: {valor}"
        )
    return int(numero)


def _fila_excel(numero: int, fila: tuple, info: InfoFormula) -> FilaExcel:
    codigo = _texto(_celda(fila, COL_CODIGO))
    return FilaExcel(
        fila=numero,
        codigo=codigo,
        ventas=tuple(
            _dec0(_celda(fila, COL_E + i)) for i in range(MESES_CERRADOS)
        ),
        perdida=_dec0(_celda(fila, COL_K)),
        precio=_dec(_celda(fila, COL_T)),
        unidad_empaque=_entero(_celda(fila, COL_U), codigo),
        inventario=_dec0(_celda(fila, COL_V)),
        transito=_dec0(_celda(fila, COL_W)),
        backorder=_dec0(_celda(fila, COL_X)),
        ajuste=_dec0(_celda(fila, COL_Z)),
        n=_dec0(_celda(fila, COL_N)),
        peso=_dec(_celda(fila, COL_O)),
        acumulado=_dec(_celda(fila, COL_P)),
        clase_abc=_texto(_celda(fila, COL_Q)),
        clase_fms=_texto(_celda(fila, COL_R)),
        clase_estatica=_texto(_celda(fila, COL_S)),
        inventario_final=_dec0(_celda(fila, COL_Y)),
        stock_objetivo=_dec0(_celda(fila, COL_AA)),
        pedido=_dec0(_celda(fila, COL_AB)),
        valor_pedido=_dec0(_celda(fila, COL_AC)),
        cobertura_final=_dec(_celda(fila, COL_AD)),
        divisor=info.divisor,
        s_es_formula=info.s_es_formula,
    )


def _coberturas(filas: list[tuple]) -> dict[str, Decimal]:
    """Factores de cobertura por clase: etiquetas en E2:N2, valores E3:N3."""
    etiquetas, valores = _fila_de(filas, 1), _fila_de(filas, 2)
    resultado = {}
    for columna in range(*FACTORES):
        etiqueta = _texto(_celda(etiquetas, columna))
        valor = _dec(_celda(valores, columna))
        if etiqueta and valor is not None:
            resultado[etiqueta] = valor
    return resultado


def _resumen(filas: list[tuple]
             ) -> tuple[tuple[FilaResumenExcel, ...],
                        Optional[FilaResumenExcel]]:
    """Bloque AA1:AE11: filas por clase y fila de totales."""
    clases, total = [], None
    for indice in FILAS_RESUMEN:
        fila = _fila_de(filas, indice)
        etiqueta = _texto(_celda(fila, COL_RESUMEN))
        if not etiqueta:
            continue
        bloque = FilaResumenExcel(
            etiqueta,
            _dec0(_celda(fila, COL_RESUMEN + 1)),
            int(_dec0(_celda(fila, COL_RESUMEN + 2))),
            _dec0(_celda(fila, COL_RESUMEN + 3)),
            _dec(_celda(fila, COL_RESUMEN + 4)),
        )
        if etiqueta == ETIQUETA_TOTAL:
            total = bloque
        else:
            clases.append(bloque)
    return tuple(clases), total


def _sic(valor) -> Optional[int]:
    numero = _dec(valor)
    return None if numero is None else int(numero)


def _sucursal(encabezado: list[tuple], cobertura: list[tuple]
              ) -> SucursalExcel:
    nombre = _texto(_celda(_fila_de(encabezado, 3), 3))
    for fila in cobertura:
        if not nombre or _texto(_celda(fila, 0)) != nombre:
            continue
        empaque = _dec0(_celda(fila, 5))
        transito = _dec0(_celda(fila, 6))
        return SucursalExcel(
            nombre=nombre,
            bodega=_texto(_celda(_fila_de(encabezado, 4), 4)),
            sic=_sic(_celda(_fila_de(encabezado, 5), 4)),
            dias_empaque=empaque,
            dias_transito=transito,
            dias_seguridad=_dec0(_celda(fila, 8)) - empaque - transito,
        )
    raise ErrorExtractor(
        f"La sucursal {nombre!r} no está en la hoja {HOJA_COBERTURA!r}"
    )


def _pasada_valores(ruta: Path) -> tuple[list, list, list]:
    """(encabezado filas 1..13, filas de datos, hoja de cobertura)."""
    with _libro(ruta, data_only=True) as libro:
        hoja = _hoja(libro, HOJA_PEDIDO)
        todas = list(hoja.iter_rows(values_only=True))
        cobertura = list(_hoja(libro, HOJA_COBERTURA).iter_rows(
            min_row=PRIMERA_FILA_COBERTURA, values_only=True
        ))
    encabezado = todas[:PRIMERA_FILA_DATOS - 1]
    datos = [
        (numero, fila)
        for numero, fila in enumerate(todas, start=1)
        if numero >= PRIMERA_FILA_DATOS and _texto(_celda(fila, COL_CODIGO))
    ]
    return encabezado, datos, cobertura


def _sin_repetidas(filas: tuple[FilaExcel, ...]) -> None:
    vistos = set()
    for fila in filas:
        if fila.codigo in vistos:
            raise ErrorExtractor(f"Referencia repetida: {fila.codigo}")
        vistos.add(fila.codigo)


def leer_libro(ruta) -> LecturaExcel:
    """Extrae la hoja `Pedido` y la sucursal de `Meses de cobertura`."""
    ruta = Path(ruta)
    formulas = _pasada_formulas(ruta)
    encabezado, datos, cobertura = _pasada_valores(ruta)
    sin_formula = InfoFormula(None, False)
    filas = tuple(
        _fila_excel(numero, fila, formulas.get(numero, sin_formula))
        for numero, fila in datos
    )
    _sin_repetidas(filas)
    resumen, total = _resumen(encabezado)
    return LecturaExcel(
        sucursal=_sucursal(encabezado, cobertura),
        filas=filas,
        coberturas=_coberturas(encabezado),
        resumen=resumen,
        total=total,
    )


def informe_empates(filas: tuple[FilaExcel, ...]
                    ) -> tuple[GrupoEmpate, ...]:
    """Grupos de filas con la misma N (distinta de 0): Excel frente a asc."""
    grupos: dict[Decimal, list[FilaExcel]] = defaultdict(list)
    for fila in filas:
        if fila.n != 0:
            grupos[fila.n].append(fila)
    informe = []
    for n, miembros in grupos.items():
        if len(miembros) < 2:
            continue
        excel = tuple(f.codigo for f in miembros)
        ascendente = tuple(sorted(excel))
        informe.append(GrupoEmpate(n, excel, ascendente, excel == ascendente))
    return tuple(informe)
