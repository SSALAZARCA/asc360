"""
Motored Pedidos — Fase 2 "Ingesta" (sdd/motored-pedidos-ingesta, ADR-7).

Utilidades de texto COMPARTIDAS entre Fase 1's `carga_excel.py` (maestros,
all-or-nothing) y Fase 2's transforms de movimiento (`services/ingesta/*`,
tolerante fila-a-fila). ADR-7 es explícito sobre qué se comparte: la
normalización de encabezados sí, `validate_rows`/`procesar_carga` no.

`normalizar_encabezado` es la extracción textual de lo que antes era
`carga_excel._normalize_header` -- Fase 1 sigue llamándola con el default
(`quitar_separadores=False`) y obtiene EXACTAMENTE el mismo resultado que
antes de la extracción (ver `tests/motored/test_texto.py`, que fija ese
comportamiento con un caso real: "Días de seguridad" -> "dias de
seguridad").
"""
import re
import unicodedata
from typing import Any

_SEPARADORES_RE = re.compile(r"[ _\-.]")


def normalizar_encabezado(valor: Any, quitar_separadores: bool = False) -> str:
    """Saca tildes/diacríticos, recorta espacios y pasa a minúsculas -- para
    que "Días de seguridad", "dias_seguridad" y "DIAS SEGURIDAD" comparen
    igual (mismo criterio que `normalizeHeader` en `BulkUploadModal.js`).

    `quitar_separadores=False` (default): comportamiento IDÉNTICO al de
    Fase 1's `_normalize_header` -- necesario para que `carga_excel.py` no
    cambie de comportamiento con esta extracción.

    `quitar_separadores=True`: además elimina espacios, guiones bajos,
    guiones y puntos -- Fase 2 lo necesita para encabezados de archivos de
    movimiento como "Dct.referencia" -> "dctreferencia", donde el separador
    real varía entre planilla y planilla y no vale la pena listar cada
    combinación como alias literal."""
    if valor is None:
        return ""
    decomposed = unicodedata.normalize("NFD", str(valor))
    without_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    normalized = without_accents.strip().lower()
    if quitar_separadores:
        normalized = _SEPARADORES_RE.sub("", normalized)
    return normalized
