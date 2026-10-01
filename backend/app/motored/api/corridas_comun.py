"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, ADR-3):
piezas compartidas por los routers de `/corridas` (`corridas.py` y
`corridas_pedido.py`), para que ninguno repita roles, traducción de errores,
armado de líneas ni entrega de archivos.

RBAC (F4-16): todo `/corridas` es sólo de ADMIN y COMPRAS. `alcance_de` se
conserva y devuelve `None` para los dos roles permitidos: las consultas
aceptan el alcance por sucursal como defensa en profundidad.
"""
import uuid
from typing import Any, Dict, FrozenSet, Optional

from fastapi import HTTPException, status
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app.motored.deps import MotoredUser, require_roles
from app.motored.schemas.corrida import LineaRead
from app.motored.services.corridas import (
    codigos,
    exportacion_hmcl,
    proyecciones,
)
from app.motored.services.corridas.codigos import ErrorCorrida

require_write = require_roles("ADMIN", "COMPRAS")
require_read = require_roles("ADMIN", "COMPRAS")

ROL_ADMIN = "ADMIN"
ROL_SUCURSAL = "SUCURSAL"
TAMANO_BLOQUE = 64 * 1024
# Rechazos por el estado o el contenido de la corrida o del pedido (el resto
# es 422).
CONFLICTOS = frozenset({
    codigos.E_CORRIDA_ESTADO_NO_ADMITE,
    codigos.E_CORRIDA_INVALIDADA,
    codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA,
    codigos.E_CORRIDA_SUCURSAL_FALLIDA,
    codigos.E_CORRIDA_PEDIDO_NO_BORRADOR,
    codigos.E_CORRIDA_LINEA_EXCLUIDA,
    codigos.E_CORRIDA_SIN_PEDIDO,
    codigos.E_CORRIDA_EDICION_DESACTUALIZADA,
    codigos.E_CORRIDA_REABRIR_BORRADOR,
    codigos.E_CORRIDA_REABRIR_ENVIADO,
    codigos.E_CORRIDA_CERRAR_NO_BORRADOR,
    codigos.E_CORRIDA_ANULAR_CON_PEDIDOS,
    codigos.E_CORRIDA_ENVIAR_NO_CERRADO,
    codigos.E_CORRIDA_ENVIAR_YA_ENVIADO,
    codigos.E_CORRIDA_ENVIO_DUPLICADO,
    codigos.E_CORRIDA_NADA_QUE_ENVIAR,
    codigos.E_CORRIDA_CORREGIR_NO_ENVIADO,
    codigos.E_CORRIDA_EXPORTAR_NO_CERRADO,
    codigos.E_CORRIDA_EXPORTAR_SIN_SIC,
})


def alcance_de(user: MotoredUser) -> Optional[FrozenSet[uuid.UUID]]:
    """Sucursales visibles: `None` (todas) salvo para el rol SUCURSAL."""
    if user.role != ROL_SUCURSAL:
        return None
    propias = set()
    for texto in user.sucursal_ids:
        try:
            propias.add(uuid.UUID(str(texto)))
        except ValueError:
            continue
    return frozenset(propias)


def rechazo(error: ErrorCorrida) -> HTTPException:
    """422 (la petición no es válida ahora) o 409 (la corrida o el pedido no
    admite la operación), con `{code, message[, detalle]}`."""
    cuerpo: Dict[str, Any] = {
        "code": error.codigo, "message": error.mensaje}
    if error.detalle:
        cuerpo["detalle"] = error.detalle
    estado = (
        status.HTTP_409_CONFLICT if error.codigo in CONFLICTOS
        else status.HTTP_422_UNPROCESSABLE_ENTITY)
    return HTTPException(status_code=estado, detail=cuerpo)


def no_existe(texto: str = "Corrida no encontrada.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=texto)


def exigir_admin_para_overrides(
    user: MotoredUser, overrides: Optional[Dict[str, Any]],
) -> None:
    """E-CORRIDA-062: sólo ADMIN lanza un escenario. Un diccionario vacío
    cuenta como sin overrides (una corrida real, DM-04)."""
    if overrides and user.role != ROL_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": codigos.E_CORRIDA_OVERRIDES_SOLO_ADMIN,
                    "message": codigos.mensaje(
                        codigos.E_CORRIDA_OVERRIDES_SOLO_ADMIN)})


async def ejecutar(db, operacion):
    """Espera `operacion` (un servicio de escritura) y confirma. 404 si
    algo no existe y el rechazo codificado si una regla lo impide; en ambos
    casos deshace la transacción."""
    try:
        resultado = await operacion
    except LookupError as error:
        await db.rollback()
        raise no_existe(str(error)) from error
    except ErrorCorrida as error:
        await db.rollback()
        raise rechazo(error) from error
    await db.commit()
    return resultado


def linea_read(
    fila: Any, ultima: Optional[proyecciones.UltimaEdicion],
) -> LineaRead:
    """La línea ORM serializable, con el valor del sugerido, el aviso de
    empaque y las marcas de edición."""
    return LineaRead.model_validate(fila).model_copy(
        update=proyecciones.extras_linea(fila, ultima))


def _bloques(archivo):
    """Los bytes del archivo temporal por bloques; lo cierra al terminar o
    si el cliente corta la descarga."""
    try:
        while True:
            bloque = archivo.read(TAMANO_BLOQUE)
            if not bloque:
                return
            yield bloque
    finally:
        archivo.close()


def respuesta_de_archivo(
    archivo: Any, tamano: int, nombre: str, tipo: str,
    extra: Optional[Dict[str, str]] = None,
) -> StreamingResponse:
    """Entrega un archivo temporal ya construido (rebobinado, de `tamano`
    bytes) como descarga: `Content-Disposition` con el nombre ASCII y el
    RFC 5987, `Content-Length` exacto y sin caché (siempre los datos de
    ahora). El archivo se cierra al terminar de enviarlo."""
    cabeceras = {
        "Content-Disposition": exportacion_hmcl.content_disposition(nombre),
        "Content-Length": str(tamano),
        "Cache-Control": "no-store",
        **(extra or {}),
    }
    return StreamingResponse(
        _bloques(archivo), media_type=tipo, headers=cabeceras,
        background=BackgroundTask(archivo.close))
