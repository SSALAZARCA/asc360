"""
Motored budgets (odd/motored-presupuestos-gerencia, T2): `/presupuestos`.

Monthly sales budget per asesor, versioned (see `services/presupuestos.py`).
ADMIN and GERENCIA only on every endpoint: budgets are personal data (Ley 1581)
and GERENCIA, confined by path in `deps.py`, cannot list vendedores, so names
are resolved server-side.

The upload reuses the generic Excel plumbing (`carga_excel.parse_excel_rows`
through `api/carga.py::_parse_excel_upload`: size guard, bounded read, row
limit) but is NOT a registered maestro: "presupuesto" is deliberately absent
from `_SCHEMA_BY_ENTIDAD`, so the generic ADMIN|COMPRAS bulk routes never see it.

Static routes (`plantilla.xlsx`, `validar`, `aplicar`) have no `{param}` sibling
at the same depth, so declaration order does not matter.
"""
import datetime
import io
import uuid
from typing import Any, Awaitable, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Request, UploadFile, status
from openpyxl import Workbook
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.motored.api.carga import _parse_excel_upload
from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.schemas.presupuesto import (
    AplicadoOut,
    MesListadoOut,
    PresupuestoAsesorEdit,
    TiendaOpcionOut,
    ValidacionOut,
    VersionCreadaOut,
    VersionDetalleOut,
    VersionHistorialOut,
)
from app.motored.services import presupuestos
from app.motored.services.carga_excel import column_labels

_require_rol = require_roles("ADMIN", "GERENCIA")

router = APIRouter(
    prefix="/presupuestos",
    tags=["motored-presupuestos"],
    dependencies=[Depends(require_motored_ready), Depends(_require_rol)],
)

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MES_PATH = Path(pattern=r"^[1-9]\d{3}-(0[1-9]|1[0-2])$", description="Mes, formato AAAA-MM")
_CEDULA_PATH = Path(max_length=30)
_EJEMPLOS = [
    (2026, 10, "1130123456", "Nombre de una tienda", 1500000),
    (2026, 10, "1130654321", "Nombre de una tienda", 1200000),
]


_ARCHIVO_NOMBRE_MAX = 255  # presupuesto_version.archivo_nombre column length


def _nombre_archivo(nombre: Optional[str]) -> Optional[str]:
    """Fits the upload's file name in its column, keeping the extension."""
    if not nombre or len(nombre) <= _ARCHIVO_NOMBRE_MAX:
        return nombre
    base, punto, extension = nombre.rpartition(".")
    if not punto or len(extension) > 10:
        return nombre[:_ARCHIVO_NOMBRE_MAX]
    return base[: _ARCHIVO_NOMBRE_MAX - len(extension) - 1] + "." + extension


def _mes(texto: str) -> datetime.date:
    anio, mes = texto.split("-")
    return datetime.date(int(anio), int(mes), 1)


async def _ejecutar(db: AsyncSession, operacion: Awaitable[Any], escribe: bool = False) -> Any:
    """Runs a service call and maps its errors to HTTP; a write commits here
    (the service only flushes) and is rolled back on any failure."""
    try:
        resultado = await operacion
        if escribe:
            await db.commit()
        return resultado
    except presupuestos.PresupuestoInvalido as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"mensaje": "El presupuesto tiene errores", "errores": exc.errores},
        )
    except presupuestos.PresupuestoNoEncontrado as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (presupuestos.PresupuestoConflicto, IntegrityError) as exc:
        await db.rollback()
        detalle = str(exc) if isinstance(exc, presupuestos.PresupuestoConflicto) else (
            "Otra persona está modificando este presupuesto. Intente de nuevo.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)


@router.get("/plantilla.xlsx")
async def descargar_plantilla() -> Response:
    libro = Workbook()
    libro.active.append(column_labels("presupuesto"))
    for ejemplo in _EJEMPLOS:
        libro.active.append(list(ejemplo))
    buffer = io.BytesIO()
    libro.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type=_XLSX,
        headers={"Content-Disposition": 'attachment; filename="plantilla_presupuestos.xlsx"'},
    )


@router.post("/validar", response_model=ValidacionOut)
async def validar(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Dry-run: summary per month, errors and warnings. Writes nothing."""
    filas = await _parse_excel_upload("presupuesto", request, file)
    return await _ejecutar(db, presupuestos.validar_archivo(db, filas))


@router.post("/aplicar", response_model=AplicadoOut)
async def aplicar(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
):
    """Re-validates and, with no errors, creates a new version per month in the file."""
    filas = await _parse_excel_upload("presupuesto", request, file)
    return await _ejecutar(
        db, presupuestos.aplicar_archivo(db, filas, _nombre_archivo(file.filename), uuid.UUID(user.user_id)), escribe=True)


@router.get("/tiendas", response_model=List[TiendaOpcionOut])
async def listar_tiendas(db: AsyncSession = Depends(get_motored_db_or_503)):
    """Active stores for the manual edit (GERENCIA cannot read /maestros/sucursales)."""
    return await _ejecutar(db, presupuestos.listar_tiendas(db))


@router.get("/meses", response_model=List[MesListadoOut])
async def listar_meses(db: AsyncSession = Depends(get_motored_db_or_503)):
    return await _ejecutar(db, presupuestos.listar_meses(db))


@router.get("/meses/{mes}", response_model=VersionDetalleOut)
async def detalle_mes(mes: str = _MES_PATH, db: AsyncSession = Depends(get_motored_db_or_503)):
    return await _ejecutar(db, presupuestos.detalle_mes(db, _mes(mes)))


@router.get("/meses/{mes}/versiones", response_model=List[VersionHistorialOut])
async def historial_mes(mes: str = _MES_PATH, db: AsyncSession = Depends(get_motored_db_or_503)):
    return await _ejecutar(db, presupuestos.historial_mes(db, _mes(mes)))


@router.get("/versiones/{version_id}", response_model=VersionDetalleOut)
async def detalle_version(version_id: uuid.UUID, db: AsyncSession = Depends(get_motored_db_or_503)):
    return await _ejecutar(db, presupuestos.detalle_version(db, version_id))


@router.put("/meses/{mes}/asesores/{cedula}", response_model=VersionCreadaOut)
async def editar_asesor(
    payload: PresupuestoAsesorEdit,
    mes: str = _MES_PATH,
    cedula: str = _CEDULA_PATH,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
):
    """Adds or changes one asesor's budget: creates a new MANUAL version."""
    return await _ejecutar(
        db,
        presupuestos.editar_asesor(
            db, _mes(mes), cedula, payload.sucursal_id, payload.monto, payload.nota, uuid.UUID(user.user_id)),
        escribe=True,
    )


@router.delete("/meses/{mes}/asesores/{cedula}", response_model=VersionCreadaOut)
async def quitar_asesor(
    mes: str = _MES_PATH,
    cedula: str = _CEDULA_PATH,
    nota: Optional[str] = Query(default=None, max_length=500),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
):
    """Removes one asesor from the month: creates a new MANUAL version without him."""
    nota = (nota or "").strip() or None
    return await _ejecutar(
        db, presupuestos.quitar_asesor(db, _mes(mes), cedula, nota, uuid.UUID(user.user_id)), escribe=True)
