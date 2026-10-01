"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, ADR-3):
piezas compartidas por los routers de `/corridas` (`corridas.py` y
`corridas_pedido.py`), para que ninguno repita roles, traducción de errores
ni armado de líneas.

RBAC (F4-16): todo `/corridas` es sólo de ADMIN y COMPRAS. `alcance_de` se
conserva y devuelve `None` para los dos roles permitidos: las consultas
aceptan el alcance por sucursal como defensa en profundidad.
"""
import uuid
from typing import Any, Dict, FrozenSet, Optional

from fastapi import HTTPException, status

from app.motored.deps import MotoredUser, require_roles
from app.motored.schemas.corrida import LineaRead
from app.motored.services.corridas import codigos, proyecciones
from app.motored.services.corridas.codigos import ErrorCorrida

require_write = require_roles("ADMIN", "COMPRAS")
require_read = require_roles("ADMIN", "COMPRAS")

ROL_SUCURSAL = "SUCURSAL"
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


def linea_read(
    fila: Any, ultima: Optional[proyecciones.UltimaEdicion],
) -> LineaRead:
    """La línea ORM serializable, con el valor del sugerido, el aviso de
    empaque y las marcas de edición."""
    return LineaRead.model_validate(fila).model_copy(
        update=proyecciones.extras_linea(fila, ultima))
