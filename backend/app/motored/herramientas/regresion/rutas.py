"""
Motored Pedidos F3 "Motor" (S8a, ADR-10) — rutas de la regresión.

Los archivos reales (libro de Excel, aceptaciones, informes) entran sólo por
argumento o variable de entorno, y los informes se escriben fuera del
repositorio: `ruta_salida_segura` rechaza cualquier ruta cuyo árbol tenga un
`.git` (directorio, o archivo en un worktree). Los enlaces simbólicos se
resuelven antes de mirar, así que un enlace hacia el repositorio también se
rechaza.
"""
import os
from pathlib import Path
from typing import Mapping, Optional

ENV_EXCEL = "MOTORED_REGRESION_EXCEL"
ENV_SALIDA = "MOTORED_REGRESION_SALIDA"
ENV_ACEPTACIONES = "MOTORED_REGRESION_ACEPTACIONES"
ENV_DB_URL = "MOTORED_REGRESION_DB_URL"


class RutaInsegura(ValueError):
    """La ruta de salida cae dentro de un árbol git."""


def _raiz_git(ruta: Path) -> Optional[Path]:
    """Primer ancestro (incluida la propia ruta) que contiene `.git`."""
    for candidata in (ruta, *ruta.parents):
        if (candidata / ".git").exists():
            return candidata
    return None


def ruta_salida_segura(ruta) -> Path:
    """Ruta absoluta y resuelta, o `RutaInsegura` si está dentro de git."""
    resuelta = Path(ruta).expanduser().resolve()
    raiz = _raiz_git(resuelta)
    if raiz is not None:
        raise RutaInsegura(
            f"La ruta de salida {resuelta} está dentro del repositorio "
            f"{raiz}: los informes con datos reales deben escribirse fuera "
            f"de cualquier árbol git."
        )
    return resuelta


def ruta_desde(argumento: Optional[str], variable: str,
               entorno: Optional[Mapping[str, str]] = None
               ) -> Optional[Path]:
    """Ruta del argumento; si falta, la de la variable; si no, `None`."""
    entorno = os.environ if entorno is None else entorno
    valor = argumento or entorno.get(variable)
    return Path(valor) if valor else None
