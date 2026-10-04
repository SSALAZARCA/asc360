"""Partir un upsert masivo en sentencias que respeten el limite de
parametros de bind de PostgreSQL/asyncpg (32 767 por sentencia)."""
from typing import Dict, Iterator, TypeVar

K = TypeVar("K")
V = TypeVar("V")

# Todas las tablas del ingesto tienen <= 10 columnas por fila: 2000 filas
# dejan el conteo de parametros muy por debajo de 32 767.
FILAS_POR_SENTENCIA = 2000


def partir(mapa: Dict[K, V], tamano: int = FILAS_POR_SENTENCIA) -> Iterator[Dict[K, V]]:
    """Trozos consecutivos del dict (orden de insercion preservado)."""
    items = list(mapa.items())
    for inicio in range(0, len(items), tamano):
        yield dict(items[inicio:inicio + tamano])
