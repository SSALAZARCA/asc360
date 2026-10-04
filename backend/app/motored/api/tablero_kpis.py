"""
KPI's de Motored (feature motored-kpis, B6): un endpoint por pestana.

Cuelga de `/tablero-asesores/kpis`, DENTRO del prefijo `/tablero-asesores` que
GERENCIA tiene permitido (`deps.GERENCIA_ALLOWED_PREFIXES`), y con los mismos
roles que el tablero de asesores: ADMIN, COMPRAS y GERENCIA.

Parametros de las tres pestanas (los errores son 422 con el motivo en espanol):
- `meses`: AAAA-MM separados por coma, obligatorio, hasta 12 (no tienen que ser consecutivos).
- `sucursales`: ids de sucursal separados por coma; sin ellos, todas.
- `hmcl`: `incluir` (por defecto), `excluir` o `solo`.

Respuestas (los importes son numeros, nunca texto; cada una repite `meses`,
`hmcl`, `sucursales` y `reglas` del filtro aplicado):
- `GET /kpis/ventas`: `total`, `tecnired` {venta, pct, clientes, venta_por_cliente,
  por_mes, por_linea, top5}, `cumplimiento` {red, tiendas, conteos}, `tiendas`
  (venta y costo por tienda), `venta_sin_linea`.
- `GET /kpis/tiendas`: `tiendas` (cada una con sus indicadores, `crecimiento`,
  `cumplimiento` y `dias_inventario`), `inventario` {fecha_corte, dias_ventana,
  tiendas, red}, `cumplimiento`, `resumen_crecimiento`, `venta_sin_linea`.
- `GET /kpis/asesores`: el tablero de asesores mas `cumplimiento` {asesores,
  conteos, advertencias}.
- `GET /kpis/opciones` (sin filtros): `meses_disponibles` (AAAA-MM con ventas),
  `ultimo_mes` y `tiendas` [{id, nombre}] activas, para armar los filtros (el
  "ano corrido" va de enero al `ultimo_mes` de ese ano).
"""
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.api.tablero_asesores import _error_422, _sucursales
from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.services import tablero_asesores_consultas as consultas
from app.motored.services import tablero_kpis as kpis
from app.motored.services.tablero_asesores import HMCL_EXCLUIR, HMCL_INCLUIR, HMCL_SOLO, Filtro

router = APIRouter(
    prefix="/tablero-asesores/kpis",
    tags=["motored-kpis"],
    dependencies=[Depends(require_motored_ready)],
)

_require_rol = require_roles("ADMIN", "COMPRAS", "GERENCIA")


async def _filtro(
    user: MotoredUser = Depends(_require_rol),  # first: a 403 wins over a 422
    meses: Optional[str] = Query(None, description="Meses AAAA-MM separados por coma (maximo 12)"),
    sucursales: Optional[str] = Query(None, description="Ids de sucursal separados por coma; sin ellos, todas"),
    hmcl: str = Query(HMCL_INCLUIR, description="incluir, excluir o solo"),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Filtro:
    if not meses or not meses.strip():
        raise _error_422("Indique 'meses' (AAAA-MM separados por coma).")
    if hmcl not in (HMCL_INCLUIR, HMCL_EXCLUIR, HMCL_SOLO):
        raise _error_422("El parámetro 'hmcl' debe ser incluir, excluir o solo.")
    ids: Optional[List[uuid.UUID]] = _sucursales(sucursales)
    try:
        return await consultas.cargar_filtro(db, [m.strip() for m in meses.split(",")], hmcl, ids)
    except ValueError as exc:
        raise _error_422(str(exc))


@router.get("/ventas")
async def kpis_ventas(
    filtro: Filtro = Depends(_filtro), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await kpis.calcular_kpis_ventas(db, filtro)


@router.get("/tiendas")
async def kpis_tiendas(
    filtro: Filtro = Depends(_filtro), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await kpis.calcular_kpis_tiendas(db, filtro)


@router.get("/asesores")
async def kpis_asesores(
    filtro: Filtro = Depends(_filtro), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await kpis.calcular_kpis_asesores(db, filtro)


@router.get("/opciones")
async def kpis_opciones(
    user: MotoredUser = Depends(_require_rol), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await kpis.calcular_opciones(db)
