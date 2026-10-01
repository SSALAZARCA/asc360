"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B4, ADR-7,
decisión F4-1): constructores PUROS del archivo de pedido para HMCL.

Nada de base de datos ni de HTTP acá: reciben los datos ya leídos y escriben
en un archivo (en memoria o temporal) que el llamador entrega.

- `nombre_archivo` y `nombre_zip`: `Pedido_SIC<sic>_<tienda>_<corte>.xlsx` y
  `Pedidos_<corrida>_<corte>.zip`. Del nombre se quitan los acentos, los
  espacios pasan a `_` y todo lo que no sea letra, dígito, `_` o `-` se
  descarta, así el nombre sirve en cualquier sistema de archivos.
- `escribir_libro`: un libro `openpyxl` de sólo escritura (memoria acotada)
  con la cabecera (tienda, SIC, fecha de corte) y la tabla `Código |
  Cantidad`. SÓLO las cantidades mayores que 0, en orden de código. Todo
  texto se escribe como cadena (`data_type` "s", formato "@"): los ceros a la
  izquierda se conservan y un valor que empieza con `=`, `+`, `-` o `@` nunca
  se interpreta como fórmula (inyección de fórmulas).
- `empaquetar`: un zip con un archivo por tienda; los nombres van en UTF-8 y
  uno repetido no pisa al anterior.
- `content_disposition` y `cabecera_omitidas`: las cabeceras de la
  respuesta, siempre ASCII (RFC 5987 para el nombre).
"""
import datetime
import json
import re
import unicodedata
import zipfile
from decimal import Decimal
from typing import Any, BinaryIO, Dict, List, NamedTuple, Sequence, Tuple
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

HOJA = "Pedido"
FORMATO_FECHA = "yyyy-mm-dd"
TIENDA_SIN_NOMBRE = "Tienda"
_NO_PERMITIDO = re.compile(r"[^A-Za-z0-9_-]")
_ESPACIOS = re.compile(r"\s+")
_GUIONES_BAJOS = re.compile(r"_+")


class DatosTienda(NamedTuple):
    """Lo que lleva el archivo de una tienda: su nombre, su SIC, la fecha de
    corte y las líneas `(código, cantidad)` (en cualquier orden y con ceros:
    el libro filtra y ordena)."""

    nombre: str
    sic: str
    fecha_corte: datetime.date
    lineas: Sequence[Tuple[str, Decimal]]


# --- Nombres ----------------------------------------------------------------


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _seguro(texto: str) -> str:
    """El texto sin acentos, con los espacios como `_` y sólo letras,
    dígitos, `_` y `-`; sin `_` repetidos ni en los bordes."""
    sin_acentos = _sin_acentos(texto.strip())
    con_guiones = _ESPACIOS.sub("_", sin_acentos)
    limpio = _NO_PERMITIDO.sub("", con_guiones)
    return _GUIONES_BAJOS.sub("_", limpio).strip("_")


def nombre_archivo(sic: str, sucursal: str, fecha: datetime.date) -> str:
    """`Pedido_SIC<sic>_<tienda>_<AAAA-MM-DD>.xlsx`."""
    tienda = _seguro(sucursal) or TIENDA_SIN_NOMBRE
    return f"Pedido_SIC{_seguro(sic)}_{tienda}_{fecha.isoformat()}.xlsx"


def nombre_zip(codigo_corrida: str, fecha: datetime.date) -> str:
    """`Pedidos_<corrida>_<AAAA-MM-DD>.zip`."""
    return f"Pedidos_{_seguro(codigo_corrida)}_{fecha.isoformat()}.zip"


# --- El libro ---------------------------------------------------------------


def _texto(hoja, valor: str) -> WriteOnlyCell:
    """Una celda de texto: nunca fórmula, ceros a la izquierda a salvo."""
    celda = WriteOnlyCell(hoja, value=ILLEGAL_CHARACTERS_RE.sub("", valor))
    celda.data_type = "s"
    celda.number_format = "@"
    return celda


def _fecha(hoja, valor: datetime.date) -> WriteOnlyCell:
    celda = WriteOnlyCell(hoja, value=valor)
    celda.number_format = FORMATO_FECHA
    return celda


def _cantidad(valor: Decimal) -> Any:
    """Un entero cuando la cantidad es entera; si no, el decimal."""
    return int(valor) if valor == valor.to_integral_value() else valor


def _a_pedir(lineas: Sequence[Tuple[str, Decimal]]) -> List[Tuple[str, Any]]:
    """Las líneas con cantidad mayor que 0, en orden de código."""
    return [
        (codigo, _cantidad(cantidad))
        for codigo, cantidad in sorted(lineas, key=lambda par: par[0])
        if cantidad > 0]


def escribir_libro(datos: DatosTienda, destino: BinaryIO) -> None:
    """Escribe el `.xlsx` de la tienda en `destino` (un archivo binario con
    `seek`): cabecera, una fila en blanco, `Código | Cantidad` y las
    líneas."""
    libro = Workbook(write_only=True)
    hoja = libro.create_sheet(HOJA)
    hoja.append([_texto(hoja, "Tienda"), _texto(hoja, datos.nombre)])
    hoja.append([_texto(hoja, "SIC"), _texto(hoja, datos.sic)])
    hoja.append([_texto(hoja, "Fecha"), _fecha(hoja, datos.fecha_corte)])
    hoja.append([])
    hoja.append([_texto(hoja, "Código"), _texto(hoja, "Cantidad")])
    for codigo, cantidad in _a_pedir(datos.lineas):
        hoja.append([_texto(hoja, codigo), cantidad])
    libro.save(destino)


# --- El zip -----------------------------------------------------------------


def _nombre_unico(nombre: str, usados: Dict[str, int]) -> str:
    """`a.xlsx`, `a_2.xlsx`, `a_3.xlsx`... cuando el nombre se repite."""
    veces = usados.get(nombre, 0) + 1
    usados[nombre] = veces
    if veces == 1:
        return nombre
    base, punto, extension = nombre.rpartition(".")
    if not punto:
        return f"{nombre}_{veces}"
    return f"{base}_{veces}.{extension}"


def empaquetar(
    archivos: Sequence[Tuple[str, bytes]], destino: BinaryIO,
) -> None:
    """Un zip comprimido con cada `(nombre, contenido)`, en orden."""
    usados: Dict[str, int] = {}
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as paquete:
        for nombre, contenido in archivos:
            paquete.writestr(_nombre_unico(nombre, usados), contenido)


# --- Cabeceras de la respuesta ----------------------------------------------


def content_disposition(nombre: str) -> str:
    """`attachment` con un nombre ASCII de respaldo y el nombre completo en
    `filename*` (RFC 5987). Las comillas y los saltos de línea nunca pasan al
    respaldo."""
    respaldo = _sin_acentos(nombre)
    respaldo = re.sub(r'[^\x20-\x7e]|["\\]', "", respaldo)
    return (
        f'attachment; filename="{respaldo}"; '
        f"filename*=UTF-8''{quote(nombre, safe='')}")


def cabecera_omitidas(omitidas: Sequence[Dict[str, Any]]) -> str:
    """El JSON de las tiendas omitidas, con porcentaje: ASCII puro, apto
    para una cabecera HTTP."""
    texto = json.dumps(list(omitidas), ensure_ascii=False,
                       separators=(",", ":"))
    return quote(texto, safe="")
