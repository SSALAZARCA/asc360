"""
Motored Pedidos — `parametro_metodologia` (sdd/motored-pedidos-cimientos,
Fase 3, task 3.6, §6.10). Versionado por INSERCIÓN: `registrar_cambio`
SIEMPRE agrega una fila nueva (`db.add`), jamás modifica ni hace `merge`/
UPDATE de una fila existente (spec "Updating a parameter creates a new
version"). Solo estructura en Fase 1 -- ningún motor lee esto todavía.
"""
import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import select

from app.motored.models.parametro_metodologia import ParametroMetodologia


async def registrar_cambio(
    db,
    clave: str,
    valor: Any,
    vigente_desde: date,
    usuario_id: Optional[uuid.UUID] = None,
) -> ParametroMetodologia:
    """Un "cambio" es SIEMPRE una fila nueva. La fila anterior (si existe)
    ni se toca ni se consulta aquí -- este método no necesita saber si hay
    una versión previa para insertar la siguiente."""
    nueva_version = ParametroMetodologia(
        id=uuid.uuid4(),
        clave=clave,
        valor=valor,
        vigente_desde=vigente_desde,
        created_by=usuario_id,
    )
    db.add(nueva_version)
    return nueva_version


async def obtener_vigente(db, clave: str, en_fecha: date) -> Optional[ParametroMetodologia]:
    """La versión vigente para `clave` en `en_fecha`: la de mayor
    `vigente_desde` que sea `<= en_fecha`."""
    result = await db.execute(
        select(ParametroMetodologia)
        .where(ParametroMetodologia.clave == clave, ParametroMetodologia.vigente_desde <= en_fecha)
        .order_by(ParametroMetodologia.vigente_desde.desc())
        .limit(1)
    )
    return result.scalars().first()
