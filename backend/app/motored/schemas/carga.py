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
    # Referencias ausentes del archivo que el usuario eligió inactivar (R3).
    # Por defecto (omitido o vacío) no se desactiva ninguna.
    codigos_inactivar: List[str] = Field(default_factory=list)


class CargaErrorRow(BaseModel):
    fila: int
    motivo: str


class GrupoResumen(BaseModel):
    """Un grupo del resumen del reemplazo: el total REAL y una muestra de a lo
    sumo 50 elementos (cada elemento es un dict corto y legible)."""

    total: int = 0
    muestra: List[Dict[str, Any]] = Field(default_factory=list)


class GrupoAusentes(BaseModel):
    """Las referencias ACTIVAS que el archivo no trae (R3): se listan completas
    en `items` (codigo, nombre, proveedor, con_ventas_6m, con_inventario) y
    siguen activas salvo las que el usuario elija inactivar. `total` es el
    total real; el dry-run devuelve la lista entera, el apply no la repite."""

    total: int = 0
    con_ventas_6m: int = 0
    con_inventario: int = 0
    items: List[Dict[str, Any]] = Field(default_factory=list)


class ResumenReemplazo(BaseModel):
    """Dry-run de la carga de referencias (reemplazo completo). `pct_inactivar`
    es una fracción (0.12 = 12%) de las referencias activas de hoy que terminan
    inactivas: las ABSENTES ELEGIDAS (`seleccionadas`, 0 en el dry-run) más
    `inactivar_por_sustituta`; `requiere_doble_confirmacion` es
    `pct_inactivar > 0.10`. `pct_inactivar_si_todas` es lo mismo suponiendo que
    se eligieran todas las ausentes (el frontend calcula el % de su selección
    con `activas_actuales`)."""

    total_archivo: int
    crear: GrupoResumen
    actualizar: GrupoResumen
    mover_proveedor: GrupoResumen
    ausentes: GrupoAusentes
    # Ausentes elegidas para inactivar (apply); 0 en el dry-run.
    seleccionadas: int = 0
    # Activas que el archivo deja con sustituta (quedan inactivas por regla del
    # maestro, siempre). Cuentan para `pct_inactivar` junto con las elegidas.
    inactivar_por_sustituta: GrupoResumen
    reactivar: GrupoResumen
    vinculos_sustituta_limpiados: GrupoResumen
    activas_actuales: int
    pct_inactivar: float
    pct_inactivar_si_todas: float = 0.0
    requiere_doble_confirmacion: bool


class ResumenBodegasSecundarias(BaseModel):
    """Lo que la columna "Bodegas secundarias" de Sucursales vinculó o
    desvinculó en esta carga. Cada elemento: `{"sucursal": nombre, "bodega":
    código}`. Solo se reportan los cambios reales."""

    vinculadas: List[Dict[str, str]] = Field(default_factory=list)
    desvinculadas: List[Dict[str, str]] = Field(default_factory=list)


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
    # Solo `sucursal` con la columna "Bodegas secundarias" en el archivo.
    bodegas_secundarias: Optional[ResumenBodegasSecundarias] = None
