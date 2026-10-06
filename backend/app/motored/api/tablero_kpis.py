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
- `GET /kpis/asesores/detalle?cedula=`: la vista de UN asesor (mismos parametros del filtro; 404
  "Asesor no encontrado" sin ventas, presupuesto ni maestro en el filtro; 422 con una cedula invalida).
- `GET /kpis/asesores/opciones`: (mismos parametros del filtro) `asesores` [{cedula, nombre, tienda,
  sucursal_id, venta}], quienes vendieron en el periodo y las tiendas elegidas, la de mayor venta
  primero (la seleccion por defecto del filtro "Asesor", que no tiene "Todos").
- `GET /kpis/comisiones`: liquida el ULTIMO mes de `meses` (`mes_liquidado`) con las reglas de
  comision vigentes ese mes: `reglas` (con `comision_*`), `resumen`, `tramos` (con la cuenta de
  asesores de cada uno), `asesores` (mayor comision primero), `cerca_de_subir` y `advertencias` {sin_presupuesto,
  cargo_desconocido, sin_cedula, sin_presupuestos}. El selector `hmcl` no cambia las bases. Bonos por linea
  (`comision_lineas`, compuerta `comision_bono_umbral_pct`): cada asesor trae `gate`, `bonos`, `bono_total` y
  `total_a_pagar` (comision + bonos); `resumen` suma `bonos_total`, `total_a_pagar` y `por_linea`.
- `GET /kpis/comisiones/excel`: el mismo calculo en un .xlsx (`comisiones_AAAA-MM.xlsx`): hoja
  "Comisiones" (encabezado con mes, tiendas y reglas, una fila por asesor con su cedula como TEXTO,
  totales) y hoja "Sin presupuesto".
- `GET /kpis/estado` (ADMIN, COMPRAS, GERENCIA): `actualizado_en`, `sucio`,
  `reconstruyendo`, `ultima_reconstruccion_total` y `usando_resumen` de las
  tablas resumen (ver `services/trabajos/supervisor_kpis`).
- `POST /kpis/recalcular` (SOLO ADMIN): pide una reconstruccion completa de las
  tablas resumen (la hace el loop en segundo plano) y devuelve el estado. 409 si
  una reconstruccion en curso no deja tomar el candado a tiempo.
- Las tres pestanas agregan `usando_resumen` y `datos_actualizados_en` (la hora
  de las tablas resumen; null cuando contesta la consulta en vivo).
- `GET /kpis/opciones` (sin filtros): `meses_disponibles` (AAAA-MM con ventas),
  `ultimo_mes` y `tiendas` [{id, nombre}] activas, para armar los filtros (el
  "ano corrido" va de enero al `ultimo_mes` de ese ano).
"""
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.api.tablero_asesores import _error_422, _sucursales
from app.motored.schemas.vendedor import limpiar_cedula
from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.services import kpi_resumen
from app.motored.services import tablero_asesores_consultas as consultas
from app.motored.services import tablero_comisiones_excel as comisiones_excel
from app.motored.services import tablero_kpis as kpis
from app.motored.services.tablero_asesores import HMCL_EXCLUIR, HMCL_INCLUIR, HMCL_SOLO, Filtro

router = APIRouter(
    prefix="/tablero-asesores/kpis",
    tags=["motored-kpis"],
    dependencies=[Depends(require_motored_ready)],
)

_require_rol = require_roles("ADMIN", "COMPRAS", "GERENCIA")
_require_admin = require_roles("ADMIN")


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


@router.get("/asesores/detalle")
async def kpis_asesor_detalle(
    cedula: Optional[str] = Query(None, description="Cédula del asesor"),
    filtro: Filtro = Depends(_filtro), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    try:
        limpia = limpiar_cedula(cedula)
    except ValueError as exc:
        raise _error_422(str(exc))
    resultado = await kpis.calcular_kpis_asesor_detalle(db, filtro, limpia)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asesor no encontrado")
    return resultado


@router.get("/asesores/opciones")
async def kpis_asesores_opciones(
    filtro: Filtro = Depends(_filtro), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await kpis.calcular_opciones_asesores(db, filtro)


@router.get("/comisiones")
async def kpis_comisiones(
    filtro: Filtro = Depends(_filtro), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await kpis.calcular_kpis_comisiones(db, filtro)


@router.get("/comisiones/excel")
async def kpis_comisiones_excel(
    filtro: Filtro = Depends(_filtro), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Response:
    datos = await kpis.calcular_kpis_comisiones(db, filtro)
    tiendas = await consultas.consultar_sucursales(db, datos["sucursales"])
    nombres = sorted(nombre for nombre, _ in tiendas.values())
    return Response(
        content=comisiones_excel.construir_libro(datos, nombres),
        media_type=comisiones_excel.XLSX,
        headers={"Content-Disposition": f'attachment; filename="{comisiones_excel.nombre_de_archivo(datos)}"'},
    )


@router.get("/opciones")
async def kpis_opciones(
    user: MotoredUser = Depends(_require_rol), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await kpis.calcular_opciones(db)


@router.get("/estado")
async def kpis_estado(
    user: MotoredUser = Depends(_require_rol), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await kpis.calcular_estado(db)


@router.post("/recalcular")
async def kpis_recalcular(
    user: MotoredUser = Depends(_require_admin), db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    await kpi_resumen.solicitar_recalculo(db)  # a busy lock is a 409 (router-level translation)
    await db.commit()
    return await kpis.calcular_estado(db)
