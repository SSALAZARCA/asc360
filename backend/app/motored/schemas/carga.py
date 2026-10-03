from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CargaRequest(BaseModel):
    """Payload de la Fase 4: filas YA ESTRUCTURADAS (list[dict]) para una
    `entidad` a la vez. El parseo de un archivo .xlsx crudo a filas queda
    fuera de este slice (ver `app/motored/api/carga.py`)."""

    filas: List[Dict[str, Any]]
    # Solo para la carga de `referencia` (reemplazo completo): el cliente debe
    # confirmar el reemplazo y, si el resumen lo exige, la desactivación masiva.
    confirmar_reemplazo: bool = False
    confirmar_inactivacion_masiva: bool = False


class CargaErrorRow(BaseModel):
    fila: int
    motivo: str


class GrupoResumen(BaseModel):
    """Un grupo del resumen del reemplazo: el total REAL y una muestra de a lo
    sumo 50 elementos (cada elemento es un dict corto y legible)."""

    total: int = 0
    muestra: List[Dict[str, Any]] = Field(default_factory=list)


class GrupoInactivar(GrupoResumen):
    """Las referencias activas que el archivo deja afuera, con cuántas
    vendieron en los últimos 6 meses o tienen stock en el último corte."""

    con_ventas_6m: int = 0
    con_inventario: int = 0


class ResumenReemplazo(BaseModel):
    """Dry-run de la carga de referencias (reemplazo completo). `pct_inactivar`
    es una fracción (0.12 = 12%) sobre las referencias activas de hoy;
    `requiere_doble_confirmacion` es `pct_inactivar > 0.10`."""

    total_archivo: int
    crear: GrupoResumen
    actualizar: GrupoResumen
    mover_proveedor: GrupoResumen
    inactivar: GrupoInactivar
    reactivar: GrupoResumen
    vinculos_sustituta_limpiados: GrupoResumen
    activas_actuales: int
    pct_inactivar: float
    requiere_doble_confirmacion: bool


class CargaResultado(BaseModel):
    ok: bool
    total_filas: int
    errores: List[CargaErrorRow] = []
    insertados: int = 0
    actualizados: int = 0
    # Solo para cargas que REEMPLAZAN la lista completa (CLIENTES TECNIRED):
    # cuantas filas anteriores se borraron.
    eliminados: int = 0
    advertencias: List[Any] = []
    # Solo `referencia`: lo que el reemplazo hará (validar) o hizo (aplicar).
    resumen_reemplazo: Optional[ResumenReemplazo] = None
