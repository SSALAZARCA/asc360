"""
Motored -- associated stores (`sucursal.principal_id`).

Some points have their own store code but operate under a principal store.
They keep their own identity and data (raw `sucursal_id` stays everywhere)
and roll up into the principal at READ time: pedido, KPIs, presupuestos and
vendedores. Only the principal gets a pedido.

Depth 1 only: a store cannot point at itself, an associated store cannot be
the principal of others, and a store that already has associated stores
cannot be associated. `motivo_asociacion` is the single rule; the CRUD
(`validar_principal`) and the Sucursales upload (`resolver_filas`) feed it.

Read helpers for consumers (KPIs, corridas):

- `principal_de(db)`: every sucursal id -> its effective principal id.
- `grupo_de(mapa, principal_id)`: the principal first, then its associates.
- `principal_efectivo_expr()`: the same mapping as a SQL expression.

Upload column "Sucursal principal": resolved BY NAME (the store-name
normalization) against existing stores AND stores of the same file. A blank
cell keeps the stored value; "Ninguna" or "-" dissociates. The rules are
checked on the state the whole file leaves together with the database.
"""
import uuid
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.motored.models.sucursal import Sucursal
from app.motored.services import auditoria
from app.motored.services.ingesta.resolucion import normalizar_texto_sucursal

# Raw key of the upload column, and the internal key `resolver_filas`
# leaves (with `_` so `_row_to_schema` drops it before the schema).
COLUMNA = "sucursal_principal"
FILA_CLAVE = "_sucursal_principal"
# Normalized cell texts that dissociate the store explicitly.
TEXTOS_NINGUNA = frozenset({"NINGUNA", "-"})

Fila = Dict[str, Any]
Error = Dict[str, Any]


class PrincipalInvalidaError(ValueError):
    """The requested principal breaks the depth-1 rules."""


class PrincipalPedida(NamedTuple):
    """What one upload row asks for. `clave` is the normalized name of the
    principal (None = dissociate); `sucursal_id` is its id when it already
    exists in the database (None when the same file creates it)."""

    clave: Optional[str]
    sucursal_id: Optional[uuid.UUID] = None


def principal_efectivo_expr():
    """SQL expression of a store's effective principal id."""
    return func.coalesce(Sucursal.principal_id, Sucursal.id)


async def principal_de(db) -> Dict[uuid.UUID, uuid.UUID]:
    """Every sucursal id -> its effective principal (itself when NULL)."""
    filas = await db.execute(select(Sucursal.id, Sucursal.principal_id))
    return {sid: pid or sid for sid, pid in filas.all()}


def grupo_de(
    mapa: Dict[uuid.UUID, uuid.UUID], principal_id: uuid.UUID
) -> List[uuid.UUID]:
    """The principal first, then its associated stores (stable order)."""
    asociadas = sorted(
        (sid for sid, pid in mapa.items()
         if pid == principal_id and sid != principal_id),
        key=str,
    )
    return [principal_id, *asociadas]


def motivo_asociacion(
    nombre: str,
    principal_nombre: str,
    *,
    misma: bool,
    principal_asociada_a: Optional[str],
    asociadas: Sequence[str],
) -> Optional[str]:
    """Why `nombre` cannot be associated to `principal_nombre`, or None.
    `principal_asociada_a` is the store the target is associated to;
    `asociadas` are the stores already associated to `nombre`."""
    if misma:
        return (
            f"La sucursal '{nombre}' no puede ser su propia tienda "
            "principal."
        )
    if principal_asociada_a:
        return (
            f"'{principal_nombre}' no puede ser tienda principal: ya está "
            f"asociada a '{principal_asociada_a}'. Elija una tienda "
            "principal."
        )
    if asociadas:
        return (
            f"'{nombre}' no puede asociarse a otra tienda: ya es la tienda "
            f"principal de {', '.join(sorted(asociadas))}. Quite primero "
            "esas asociaciones."
        )
    return None


async def validar_principal(
    db,
    sucursal: Optional[Sucursal],
    principal_id: Optional[uuid.UUID],
    nombre: Optional[str] = None,
) -> None:
    """CRUD check of `principal_id` for `sucursal` (None on create). Raises
    `PrincipalInvalidaError`. NULL (dissociate) is always valid."""
    if principal_id is None:
        return
    nombre = nombre or (sucursal.nombre if sucursal else "")
    if sucursal is not None and principal_id == sucursal.id:
        raise PrincipalInvalidaError(motivo_asociacion(
            nombre, nombre, misma=True, principal_asociada_a=None,
            asociadas=[],
        ))
    padre = aliased(Sucursal)
    destino = (await db.execute(
        select(Sucursal.id, Sucursal.nombre, padre.nombre)
        .outerjoin(padre, Sucursal.principal_id == padre.id)
        .where(Sucursal.id == principal_id)
    )).first()
    if destino is None:
        raise PrincipalInvalidaError("La tienda principal elegida no existe.")
    asociadas: List[str] = []
    if sucursal is not None:
        asociadas = [fila[0] for fila in (await db.execute(
            select(Sucursal.nombre).where(Sucursal.principal_id == sucursal.id)
        )).all()]
    motivo = motivo_asociacion(
        nombre, destino[1], misma=False, principal_asociada_a=destino[2],
        asociadas=asociadas,
    )
    if motivo:
        raise PrincipalInvalidaError(motivo)


def asignar_principal(
    db,
    sucursal: Sucursal,
    principal_id: Optional[uuid.UUID],
    usuario_id: Optional[uuid.UUID],
) -> None:
    """Sets an already-validated principal with a field-change audit entry
    (no-op when unchanged)."""
    antes = {"principal_id": sucursal.principal_id}
    sucursal.principal_id = principal_id
    auditoria.diff_and_audit(
        db, "sucursal", sucursal.id, usuario_id, antes,
        {"principal_id": principal_id},
    )


# ---------------------------------------------------------------------------
# Upload column "Sucursal principal"
# ---------------------------------------------------------------------------

def _clave(valor: Any) -> str:
    return normalizar_texto_sucursal(str(valor or ""))


def _sacar_textos(filas: List[Fila]) -> Tuple[List[Fila], Dict[int, str]]:
    """Copies the rows without the raw column (and without a raw
    `principal_id`: only the named column may set it in an upload).
    Returns the non-blank cell texts by 1-based row index."""
    copias: List[Fila] = []
    textos: Dict[int, str] = {}
    for index, fila in enumerate(filas, start=1):
        fila = dict(fila)
        fila.pop("principal_id", None)
        texto = str(fila.pop(COLUMNA, None) or "").strip()
        if texto:
            textos[index] = texto
        copias.append(fila)
    return copias, textos


class _Contexto(NamedTuple):
    """Stores known to the upload, keyed by normalized name."""

    nombres: Dict[str, str]
    ids: Dict[str, uuid.UUID]
    principal_db: Dict[str, str]


async def _contexto(db, filas: List[Fila]) -> _Contexto:
    sucursales = (await db.execute(
        select(Sucursal.id, Sucursal.nombre, Sucursal.principal_id)
    )).all()
    clave_por_id = {sid: _clave(nombre) for sid, nombre, _ in sucursales}
    nombres = {_clave(nombre): nombre for _, nombre, _ in sucursales}
    ids = {_clave(nombre): sid for sid, nombre, _ in sucursales}
    principal_db = {
        clave_por_id[sid]: clave_por_id[pid]
        for sid, _, pid in sucursales if pid in clave_por_id
    }
    for fila in filas:
        nombre = str(fila.get("nombre") or "").strip()
        if nombre:
            nombres.setdefault(_clave(nombre), nombre)
    return _Contexto(nombres, ids, principal_db)


def _pedida(
    texto: str, fila: Fila, ctx: _Contexto
) -> Tuple[Optional[PrincipalPedida], Optional[str]]:
    """Resolves one cell to `(pedida, None)` or `(None, motivo)`."""
    clave = _clave(texto)
    if clave in TEXTOS_NINGUNA:
        return PrincipalPedida(None), None
    if clave not in ctx.nombres:
        return None, (
            f"'Sucursal principal' '{texto}' no corresponde a ninguna "
            "sucursal existente ni del archivo."
        )
    nombre = str(fila.get("nombre") or "").strip()
    if clave == _clave(nombre):
        return None, motivo_asociacion(
            nombre, nombre, misma=True, principal_asociada_a=None,
            asociadas=[],
        )
    return PrincipalPedida(clave, ctx.ids.get(clave)), None


def _errores_de_profundidad(
    filas: List[Fila], ctx: _Contexto
) -> List[Error]:
    """Depth-1 rules on the final state: database plus the file."""
    final = dict(ctx.principal_db)
    for fila in filas:
        if FILA_CLAVE in fila:
            final[_clave(fila.get("nombre"))] = fila[FILA_CLAVE].clave
    errores: List[Error] = []
    for index, fila in enumerate(filas, start=1):
        pedida = fila.get(FILA_CLAVE)
        if pedida is None or pedida.clave is None:
            continue
        propia = _clave(fila.get("nombre"))
        abuelo = final.get(pedida.clave)
        motivo = motivo_asociacion(
            str(fila.get("nombre")).strip(), ctx.nombres[pedida.clave],
            misma=False,
            principal_asociada_a=ctx.nombres.get(abuelo) if abuelo else None,
            asociadas=[
                ctx.nombres.get(c, c) for c, p in final.items()
                if p == propia
            ],
        )
        if motivo:
            errores.append({"fila": index, "motivo": motivo})
    return errores


async def resolver_filas(
    db, filas: List[Fila]
) -> Tuple[List[Fila], List[Error]]:
    """Returns `(filas_resueltas, errores)` with the `{fila, motivo}` shape
    of the other `api/carga.py` resolvers. Each row with a non-blank cell
    gets `FILA_CLAVE` = `PrincipalPedida`. Queries the database only when
    some cell has a value."""
    if not any(COLUMNA in fila for fila in filas):
        return filas, []
    filas, textos = _sacar_textos(filas)
    if not textos:
        return filas, []
    ctx = await _contexto(db, filas)
    errores: List[Error] = []
    for index, texto in textos.items():
        pedida, motivo = _pedida(texto, filas[index - 1], ctx)
        if motivo:
            errores.append({"fila": index, "motivo": motivo})
        else:
            filas[index - 1][FILA_CLAVE] = pedida
    errores += _errores_de_profundidad(filas, ctx)
    errores.sort(key=lambda error: error["fila"])
    return filas, errores


async def aplicar(
    db,
    entradas: List[Tuple[Sucursal, PrincipalPedida]],
    guardadas: Sequence[Sucursal],
    usuario_id: Optional[uuid.UUID],
) -> None:
    """Applies the resolved principals after every row of the file was
    upserted (`guardadas`), so a principal created by the same file is
    known. Flushes first: the session runs with autoflush off, and the new
    principal rows must be inserted before a row points at them."""
    await db.flush()
    por_clave = {_clave(s.nombre): s.id for s in guardadas}
    for sucursal, pedida in entradas:
        principal_id = None
        if pedida.clave is not None:
            principal_id = por_clave.get(pedida.clave, pedida.sucursal_id)
        asignar_principal(db, sucursal, principal_id, usuario_id)
