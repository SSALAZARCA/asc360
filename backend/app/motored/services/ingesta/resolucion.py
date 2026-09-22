"""
Motored Pedidos — Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"
(sdd/motored-pedidos-ingesta, task 3.4; design ADR-8, spec "sucursal_alias
resolution write path").

ADR-8: la resolución cache-first NO es una optimización, es OBLIGATORIA --
un lookup por fila contra la base de datos tomaría una conexión del pool
compartido (5+10) de Motored por cada fila, el mecanismo real por el que
una ingesta degradaría el resto del tráfico de Motored. `construir_cache`
hace exactamente 4 SELECTs (sucursal, bodega, sucursal_alias, referencia),
sin importar cuántas filas tenga el archivo; después de eso,
`resolver_sucursal`/`resolver_referencia` son lookups O(1) puros en
memoria -- NUNCA vuelven a tocar `session`.

Consolidación bodega-principal (`BA066 -> BA061`) se resuelve DENTRO del
cache: una bodega secundaria resuelve a la sucursal de su bodega principal,
no a la suya propia (design "A secondary bodega's stock rolls into the
principal").

Fase 2 "Ingesta", Phase 7 "BACKORDER + DEMANDA_PERDIDA" (PR7) agrega
`sucursal_por_sic` (spec §5.3 BACKORDER: "SIC | sucursal (vía
`sucursal.sic`)") -- BACKORDER es el único tipo cuyo archivo trae un código
de OTRO sistema (el SIC/SIIC del proveedor HMCL) en vez de un texto de
sucursal, así que `resolver_sucursal` (matching por nombre normalizado) no
puede resolverlo: hace falta un segundo lookup puro en memoria,
`resolver_sucursal_por_sic`, sobre la MISMA columna `Sucursal.sic` que ya
se lee en el único `SELECT` de sucursales -- sigue sin agregar una quinta
query (ADR-8 intacto, siguen siendo 4 en total).
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Dict, NamedTuple, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.bodega import Bodega
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.sucursal_alias import SucursalAlias

_PREFIJO_MR_RE = re.compile(r"^\s*MR\s+", re.IGNORECASE)
_ESPACIOS_MULTIPLES_RE = re.compile(r"\s+")


def normalizar_texto_sucursal(valor: str) -> str:
    """Normaliza un texto de sucursal (nombre de una fila del archivo, o un
    `codigo` de bodega) para comparación: saca tildes, recorta el prefijo
    `MR ` (variantes de "Mister"/apodo comercial visto en los exports),
    colapsa espacios múltiples y pasa a MAYÚSCULAS -- el mismo formato en
    que `sucursal_alias.texto_normalizado` ya se persiste (spec: "a
    normalized (uppercase, unaccented, collapsed-spaces, `MR ` prefix
    stripped) mapping row"). Distinta de `texto.normalizar_encabezado`
    (que es para NOMBRES DE COLUMNA, no valores de fila, y normaliza a
    minúsculas)."""
    descompuesto = unicodedata.normalize("NFD", valor)
    sin_acentos = "".join(ch for ch in descompuesto if unicodedata.category(ch) != "Mn")
    sin_prefijo = _PREFIJO_MR_RE.sub("", sin_acentos.strip())
    colapsado = _ESPACIOS_MULTIPLES_RE.sub(" ", sin_prefijo).strip()
    return colapsado.upper()


class CacheResolucion(NamedTuple):
    """Snapshot en memoria construido UNA vez por job. `sucursal_por_texto`
    ya incluye la consolidación bodega-principal y el fallback de alias --
    el caller nunca necesita saber de dónde vino cada entrada.
    `sucursal_por_sic` (Phase 7) es un índice INDEPENDIENTE por
    `sucursal.sic` -- no comparte namespace con `sucursal_por_texto`, un SIC
    numérico y un nombre de sucursal nunca podrían colisionar de todos
    modos. Default `{}` para que los callers existentes (VENTAS/INVENTARIO,
    Phases 4/6) que construyen un `CacheResolucion` a mano en sus tests
    sigan funcionando sin pasar este campo."""

    sucursal_por_texto: Dict[str, uuid.UUID]
    referencia_por_codigo_proveedor: Dict[Tuple[str, uuid.UUID], uuid.UUID]
    sucursal_por_sic: Dict[str, uuid.UUID] = {}


def _resolver_sucursal_de_bodega(
    codigo: str,
    bodega_por_codigo: Dict[str, Tuple[Optional[uuid.UUID], Optional[str]]],
    visitados: Optional[set] = None,
) -> Optional[uuid.UUID]:
    """Sigue la cadena `bodega_principal` hasta encontrar la bodega raíz
    (la que no delega en ninguna otra) y retorna SU `sucursal_id`. `codigo`
    puede ser el de una bodega secundaria (`BA066`) o ya el de la principal
    (`BA061`) -- ambos resuelven al mismo resultado. `visitados` corta un
    ciclo mal cargado en vez de recursión infinita (nunca debería pasar en
    datos reales, pero nunca debe colgar el proceso de ingesta)."""
    visitados = visitados or set()
    if codigo in visitados:
        return None
    visitados.add(codigo)

    entrada = bodega_por_codigo.get(codigo)
    if entrada is None:
        return None

    sucursal_id, bodega_principal = entrada
    if bodega_principal and bodega_principal in bodega_por_codigo:
        return _resolver_sucursal_de_bodega(bodega_principal, bodega_por_codigo, visitados)
    return sucursal_id


async def construir_cache(session: AsyncSession) -> CacheResolucion:
    """Carga TODO lo necesario para resolver sucursal/referencia en
    exactamente 4 queries, sin importar el tamaño del archivo (ADR-8).
    Prioridad de `sucursal_por_texto` cuando dos fuentes normalizan al
    mismo texto: nombre real de sucursal / código de bodega consolidada
    primero, `sucursal_alias` solo rellena lo que falte -- un alias existe
    justamente para texto que NO matcheó un maestro real."""
    sucursales = (await session.execute(select(Sucursal.id, Sucursal.nombre, Sucursal.sic))).all()
    bodegas = (
        await session.execute(select(Bodega.codigo, Bodega.sucursal_id, Bodega.bodega_principal))
    ).all()
    alias_rows = (
        await session.execute(select(SucursalAlias.texto_normalizado, SucursalAlias.sucursal_id))
    ).all()
    referencias = (
        await session.execute(select(Referencia.codigo, Referencia.proveedor_id, Referencia.id))
    ).all()

    sucursal_por_texto: Dict[str, uuid.UUID] = {}
    sucursal_por_sic: Dict[str, uuid.UUID] = {}
    for sucursal_id, nombre, sic in sucursales:
        if nombre:
            sucursal_por_texto[normalizar_texto_sucursal(nombre)] = sucursal_id
        if sic:
            sucursal_por_sic[str(sic).strip()] = sucursal_id

    bodega_por_codigo = {
        codigo: (sucursal_id, bodega_principal)
        for codigo, sucursal_id, bodega_principal in bodegas
    }
    for codigo in bodega_por_codigo:
        sucursal_id = _resolver_sucursal_de_bodega(codigo, bodega_por_codigo)
        if sucursal_id is not None:
            sucursal_por_texto.setdefault(normalizar_texto_sucursal(codigo), sucursal_id)

    for texto_normalizado, sucursal_id in alias_rows:
        sucursal_por_texto.setdefault(texto_normalizado, sucursal_id)

    referencia_por_codigo_proveedor = {
        (codigo, proveedor_id): referencia_id
        for codigo, proveedor_id, referencia_id in referencias
    }

    return CacheResolucion(
        sucursal_por_texto=sucursal_por_texto,
        referencia_por_codigo_proveedor=referencia_por_codigo_proveedor,
        sucursal_por_sic=sucursal_por_sic,
    )


def resolver_sucursal(cache: CacheResolucion, texto: Optional[str]) -> Optional[uuid.UUID]:
    """Lookup PURO en memoria -- NUNCA toca la base de datos (ADR-8)."""
    if not texto:
        return None
    return cache.sucursal_por_texto.get(normalizar_texto_sucursal(texto))


def resolver_sucursal_por_sic(cache: CacheResolucion, sic: Optional[str]) -> Optional[uuid.UUID]:
    """Lookup PURO en memoria por `sucursal.sic` (Phase 7, spec §5.3
    BACKORDER) -- NUNCA toca la base de datos (ADR-8), mismo contrato que
    `resolver_sucursal`/`resolver_referencia`. Distinto de `resolver_
    sucursal`: el SIC es un código numérico del sistema del PROVEEDOR
    (HMCL), sin relación con `bodega.codigo` ni con `sucursal.nombre` --
    solo se recorta espacio en blanco, nunca se normaliza como texto de
    sucursal (mayúsculas/tildes/prefijo `MR `)."""
    if not sic:
        return None
    return cache.sucursal_por_sic.get(sic.strip())


def resolver_referencia(
    cache: CacheResolucion, codigo: Optional[str], proveedor_id: uuid.UUID
) -> Optional[uuid.UUID]:
    """Lookup PURO en memoria -- NUNCA toca la base de datos (ADR-8)."""
    if not codigo:
        return None
    return cache.referencia_por_codigo_proveedor.get((codigo.strip(), proveedor_id))
