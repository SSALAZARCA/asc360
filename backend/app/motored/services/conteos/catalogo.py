"""
Inventory counts -- the referencia master a pair device downloads
(odd/motored-conteos-inventario, WU8; design ADR-6, §1.2, §9.5).

`[[code, name], ...]` of ALL referencias (inactive included, like the
ingest: a store may hold inactive items), codes normalized exactly like a
scan (`upper(btrim(codigo))`). It is the global master, not the store's
snapshot: it carries no quantity, cost or snapshot data, so the blind
count holds and a pair may still find what the system does not expect.

Built at most once every 10 minutes per process and kept in memory with
its gzip form. The ETag is a hash of the content, so a rebuild with the
same referencias keeps the ETag and devices keep getting 304.
"""
import gzip
import hashlib
import json
import time
from typing import Iterable, NamedTuple, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.referencia import Referencia

VIGENCIA_SEGUNDOS = 600


class Catalogo(NamedTuple):
    etag: str
    cuerpo: bytes
    comprimido: bytes
    armado_en: float


_cache: Optional[Catalogo] = None


def limpiar_cache() -> None:
    global _cache
    _cache = None


def armar(
        filas: Iterable[Tuple[str, Optional[str]]],
        ahora: float = 0.0) -> Catalogo:
    """The JSON body (`{"version", "referencias"}`), its gzip and ETag.
    A repeated normalized code keeps its first name."""
    vistos = {}
    for codigo, nombre in filas:
        if codigo and codigo not in vistos:
            vistos[codigo] = nombre or ""
    referencias = [[c, n] for c, n in sorted(vistos.items())]
    contenido = json.dumps(
        referencias, ensure_ascii=False, separators=(",", ":"))
    version = hashlib.sha256(contenido.encode()).hexdigest()[:32]
    cuerpo = json.dumps(
        {"version": version, "referencias": referencias},
        ensure_ascii=False, separators=(",", ":")).encode()
    return Catalogo(
        f'"{version}"', cuerpo, gzip.compress(cuerpo, mtime=0), ahora)


async def obtener(db: AsyncSession) -> Catalogo:
    """The cached catalogue, rebuilt when older than 10 minutes."""
    global _cache
    ahora = time.monotonic()
    if _cache is not None and ahora - _cache.armado_en < VIGENCIA_SEGUNDOS:
        return _cache
    filas = (await db.execute(
        select(func.upper(func.btrim(Referencia.codigo)), Referencia.nombre)
    )).all()
    _cache = armar(((f[0], f[1]) for f in filas), ahora)
    return _cache


def coincide(etag: str, si_no_coincide: Optional[str]) -> bool:
    """`If-None-Match` names this ETag (weak or strong) or `*`."""
    if not si_no_coincide:
        return False
    for valor in si_no_coincide.split(","):
        valor = valor.strip()
        if valor.startswith("W/"):
            valor = valor[2:]
        if valor in ("*", etag):
            return True
    return False
