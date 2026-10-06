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

Upload column "Sucursal principal": a store code (C.O., preferred) or a
name, resolved against existing stores AND stores of the same file, by
their final code and name. A value with the C.O. format is looked up as a
code first. Rows key on the store they write (`clave_de_fila`), never on
their name, so a rename works in the same file. A blank cell keeps the
stored value; "Ninguna" or "-" dissociates. The rules are checked on the
state the whole file leaves together with the database.
"""
import uuid
from typing import (
    Any,
    Dict,
    Hashable,
    List,
    NamedTuple,
    Optional,
    Sequence,
    Tuple,
)

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.motored.models.sucursal import Sucursal
from app.motored.schemas.sucursal import (
    CODIGO_CO_PATRON,
    normalizar_codigo_co,
)
from app.motored.services import auditoria
from app.motored.services.ingesta.resolucion import normalizar_texto_sucursal

# Raw key of the upload column, and the internal key `resolver_filas`
# leaves (with `_` so `_row_to_schema` drops it before the schema).
COLUMNA = "sucursal_principal"
FILA_CLAVE = "_sucursal_principal"
# Normalized cell texts that dissociate the store explicitly.
TEXTOS_NINGUNA = frozenset({"NINGUNA", "-"})
# Internal key `maestros.resolver_sucursales_carga` leaves on each upload
# row: the id of the saved store the row writes (None = a new store).
FILA_SUCURSAL_ID = "_sucursal_id"

Fila = Dict[str, Any]
Error = Dict[str, Any]


class PrincipalInvalidaError(ValueError):
    """The requested principal breaks the depth-1 rules."""


class PrincipalPedida(NamedTuple):
    """What one upload row asks for. `clave` is the principal's store key
    (`clave_de_fila`; None = dissociate); `sucursal_id` is its id when it
    already exists in the database (None when the same file creates it)."""

    clave: Optional[Hashable]
    sucursal_id: Optional[uuid.UUID] = None


def clave_de_fila(index: int, fila: Fila) -> Hashable:
    """The store upload row `index` (1-based) writes: the saved store's id
    (`FILA_SUCURSAL_ID`), or `("fila", index)` for a store the file
    creates."""
    sucursal_id = fila.get(FILA_SUCURSAL_ID)
    return sucursal_id if sucursal_id is not None else ("fila", index)


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
    """Stores known to the upload in their final state (database plus
    file), keyed by store key (`clave_de_fila`)."""

    nombres: Dict[Hashable, str]
    por_nombre: Dict[str, Hashable]
    por_codigo: Dict[str, Hashable]
    principal_db: Dict[Hashable, Hashable]


async def _contexto(db, filas: List[Fila]) -> _Contexto:
    sucursales = (await db.execute(select(
        Sucursal.id, Sucursal.nombre, Sucursal.principal_id,
        Sucursal.codigo_co,
    ))).all()
    nombres: Dict[Hashable, str] = {sid: n for sid, n, _, _ in sucursales}
    codigos: Dict[Hashable, str] = {
        sid: codigo for sid, _, _, codigo in sucursales if codigo
    }
    principal_db = {
        sid: pid for sid, _, pid, _ in sucursales if pid in nombres
    }
    for index, fila in enumerate(filas, start=1):
        clave = clave_de_fila(index, fila)
        nombre = str(fila.get("nombre") or "").strip()
        if nombre:
            nombres[clave] = nombre
        codigo = normalizar_codigo_co(fila.get("codigo_co"))
        if codigo:
            codigos[clave] = codigo
    return _Contexto(
        nombres,
        {_clave(nombre): clave for clave, nombre in nombres.items()},
        {codigo: clave for clave, codigo in codigos.items()},
        principal_db,
    )


def _destino(texto: str, ctx: _Contexto) -> Optional[Hashable]:
    """The store a cell names: a C.O. first, then a name."""
    codigo = normalizar_codigo_co(texto)
    if codigo and CODIGO_CO_PATRON.match(codigo) and codigo in ctx.por_codigo:
        return ctx.por_codigo[codigo]
    return ctx.por_nombre.get(_clave(texto))


def _pedida(
    texto: str, index: int, fila: Fila, ctx: _Contexto
) -> Tuple[Optional[PrincipalPedida], Optional[str]]:
    """Resolves one cell to `(pedida, None)` or `(None, motivo)`."""
    if _clave(texto) in TEXTOS_NINGUNA:
        return PrincipalPedida(None), None
    destino = _destino(texto, ctx)
    if destino is None:
        return None, (
            f"'Sucursal principal' '{texto}' no corresponde a ningún "
            "Código C.O. ni nombre de sucursal existente ni del archivo."
        )
    if destino == clave_de_fila(index, fila):
        nombre = str(fila.get("nombre") or "").strip()
        return None, motivo_asociacion(
            nombre, nombre, misma=True, principal_asociada_a=None,
            asociadas=[],
        )
    sucursal_id = destino if isinstance(destino, uuid.UUID) else None
    return PrincipalPedida(destino, sucursal_id), None


def _errores_de_profundidad(
    filas: List[Fila], ctx: _Contexto
) -> List[Error]:
    """Depth-1 rules on the final state: database plus the file."""
    final = dict(ctx.principal_db)
    for index, fila in enumerate(filas, start=1):
        if FILA_CLAVE in fila:
            final[clave_de_fila(index, fila)] = fila[FILA_CLAVE].clave
    errores: List[Error] = []
    for index, fila in enumerate(filas, start=1):
        pedida = fila.get(FILA_CLAVE)
        if pedida is None or pedida.clave is None:
            continue
        propia = clave_de_fila(index, fila)
        abuelo = final.get(pedida.clave)
        motivo = motivo_asociacion(
            ctx.nombres.get(propia, ""), ctx.nombres[pedida.clave],
            misma=False,
            principal_asociada_a=ctx.nombres.get(abuelo) if abuelo else None,
            asociadas=[
                ctx.nombres.get(c, str(c)) for c, p in final.items()
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
    gets `FILA_CLAVE` = `PrincipalPedida`. A raw `principal_id` is always
    dropped, even without the column: only the named column associates
    stores, so a JSON row cannot skip the depth-1 checks. Queries the
    database only when some cell has a value."""
    filas, textos = _sacar_textos(filas)
    if not textos:
        return filas, []
    ctx = await _contexto(db, filas)
    errores: List[Error] = []
    for index, texto in textos.items():
        pedida, motivo = _pedida(texto, index, filas[index - 1], ctx)
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
    upserted (`guardadas`, in file order), so a principal created by the
    same file (`("fila", n)` key) is known. Flushes first: the session
    runs with autoflush off, and the new principal rows must be inserted
    before a row points at them."""
    await db.flush()
    for sucursal, pedida in entradas:
        principal_id = pedida.sucursal_id
        if principal_id is None and pedida.clave is not None:
            principal_id = guardadas[pedida.clave[1] - 1].id
        asignar_principal(db, sucursal, principal_id, usuario_id)
