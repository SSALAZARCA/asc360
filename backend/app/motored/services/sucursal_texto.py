"""
Motored -- resolves a sucursal from free text (C.O., name or alias).

Shared by the vendedores upload (`api/carga.py`) and the budgets upload
(`services/presupuestos.py`), so both match a "Tienda" cell the same way.
"""
import uuid
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.sucursal import Sucursal
from app.motored.schemas.sucursal import CODIGO_CO_PATRON, normalizar_codigo_co
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.services.ingesta.resolucion import normalizar_texto_sucursal


async def sucursal_id_por_texto(db: AsyncSession) -> Dict[str, uuid.UUID]:
    """`normalizar_texto_sucursal(codigo_co | nombre | alias)` -> `sucursal_id`.
    Prioridad: C.O. (el codigo identifica a la tienda), luego nombre, luego
    `sucursal_alias` (solo rellena lo que falte). Un nombre o alias que se vea
    como el C.O. de otra tienda NO se lo quita. DOS queries (sucursal con
    id, nombre y codigo_co; y alias)."""
    por_texto: Dict[str, uuid.UUID] = {}
    sucursales = (
        await db.execute(select(Sucursal.id, Sucursal.nombre, Sucursal.codigo_co))
    ).all()
    for sucursal_id, _, codigo_co in sucursales:
        codigo = normalizar_codigo_co(codigo_co)
        if codigo and CODIGO_CO_PATRON.match(codigo):
            por_texto[normalizar_texto_sucursal(codigo)] = sucursal_id
    codigos = set(por_texto)
    for sucursal_id, nombre, _ in sucursales:
        if nombre:
            clave = normalizar_texto_sucursal(nombre)
            if clave not in codigos:
                por_texto[clave] = sucursal_id
    alias_rows = (
        await db.execute(select(SucursalAlias.texto_normalizado, SucursalAlias.sucursal_id))
    ).all()
    for texto_normalizado, sucursal_id in alias_rows:
        por_texto.setdefault(texto_normalizado, sucursal_id)
    return por_texto
