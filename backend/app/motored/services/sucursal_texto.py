"""
Motored -- resolves a sucursal from free text (name or alias).

Shared by the vendedores upload (`api/carga.py`) and the budgets upload
(`services/presupuestos.py`), so both match a "Tienda" cell the same way.
"""
import uuid
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.sucursal import Sucursal
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.services.ingesta.resolucion import normalizar_texto_sucursal


async def sucursal_id_por_texto(db: AsyncSession) -> Dict[str, uuid.UUID]:
    """`normalizar_texto_sucursal(nombre | alias)` -> `sucursal_id`, con DOS
    queries (nombres reales primero, `sucursal_alias` solo rellena lo que
    falte) -- la misma prioridad que `ingesta.resolucion.construir_cache`."""
    por_texto: Dict[str, uuid.UUID] = {}
    for sucursal_id, nombre in (await db.execute(select(Sucursal.id, Sucursal.nombre))).all():
        if nombre:
            por_texto[normalizar_texto_sucursal(nombre)] = sucursal_id
    alias_rows = (
        await db.execute(select(SucursalAlias.texto_normalizado, SucursalAlias.sucursal_id))
    ).all()
    for texto_normalizado, sucursal_id in alias_rows:
        por_texto.setdefault(texto_normalizado, sucursal_id)
    return por_texto
