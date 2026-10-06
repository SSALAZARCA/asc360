"""
Motored — columna "Bodegas secundarias" de la carga de Sucursales.

Una tienda puede tener varias bodegas, pero el archivo de Sucursales solo
traía "Bodega principal". La columna nueva lista los códigos de las bodegas
secundarias (separados por coma). Al cargar, cada código se guarda como una
fila `bodega` con `sucursal_id` = la tienda y `bodega_principal` = el
código de la bodega principal de esa tienda: la misma cadena que sigue
`ingesta.resolucion._resolver_sucursal_de_bodega` y de la que depende la
consolidación de INVENTARIO.

Dos pasos, los dos todo-o-nada junto con el resto del archivo:

- `resolver_filas` (validación, compartida por `validar` y `carga`): normaliza
  la celda, y devuelve errores de fila. Solo consulta la base si algún código
  aparece en el archivo.
- `aplicar` (escritura, dentro de `procesar_carga`, misma transacción):
  vincula lo listado y desvincula lo que ya no figura.

Reglas de desvinculación: sin la columna en el archivo no se toca ninguna
secundaria; con la columna, para cada sucursal DEL ARCHIVO los códigos
listados son sus secundarias y las que tenía vinculadas y ya no figuran
quedan con `sucursal_id` y `bodega_principal` en NULL (la fila `bodega`
nunca se borra).
Una celda en blanco desvincula todas las de esa tienda. Las sucursales que no
están en el archivo no se tocan. La fila `bodega` de la propia bodega principal
nunca se desvincula.

Each row keys on the store it writes (`sucursal_grupo.clave_de_fila`: the
saved store the C.O. resolver matched, or the new store of that row), never
on its name, so a store renamed in the same file keeps its bodegas.

Mover una secundaria de tienda en UNA sola carga: un código vinculado a otra
tienda se acepta si el mismo archivo lo libera, es decir, si la tienda dueña
también viene en el archivo con la columna y ya no lo lista. Si sigue siendo
su bodega principal (la del archivo o, en blanco, la guardada) se rechaza.

The principal bodega's own record (`sincronizar_principales`, run after
every row, the secondaries and the associations were applied): for every
store of the file with a principal code P, the record of P belongs to the
store and is the root of its chain (`bodega_principal` NULL), created when
missing; every other record of the store chains to P; and a record of
another store, or of none, that still chains to P has its chain cut
(`bodega_principal` NULL), so it resolves by its own `sucursal_id`, never
through P to a store it does not belong to. Ingest only follows the
records, never `sucursal.bodega_principal`, so without this a principal
moved to another store, or a secondary promoted to principal, kept
resolving to its old store or to none.

The Sucursales form (`guardar_de_sucursal`, wired in `api/maestros.py`)
saves ONE store's final list of secondaries with the same normalization,
rules, `aplicar` and `sincronizar_principales`, validated against the
state the save leaves, so a principal/secondary swap is one save. Unlike
the upload, it never moves a code owned by another store: that is
rejected naming the store (remove it there first, or use the upload).
"""
import uuid
from typing import Any, Dict, Hashable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import or_, select

from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.bodega import BodegaCreate, BodegaUpdate
from app.motored.schemas.carga import ResumenBodegasSecundarias
from app.motored.services import maestros
from app.motored.services.sucursal_grupo import (
    FILA_SUCURSAL_ID,
    clave_de_fila,
)
from app.motored.services.texto import split_multivalor

# Clave canónica de la columna tal como llega en cada fila del archivo.
COLUMNA = "bodegas_secundarias"
# Clave interna que deja `resolver_filas`: lista de códigos ya normalizados.
# Solo existe si la columna vino en el archivo (con `_` para que
# `_row_to_schema` la descarte antes de construir el schema de sucursal).
FILA_CLAVE = "_bodegas_secundarias"


# How a rejected code's message ends, per path: the upload re-reads the
# whole file; the form saves one store and never moves a code between
# stores (that is the upload's job, which can release it in the same file).
_REINTENTO_CARGA = "vuelva a subir el archivo"
_REINTENTO_FORMULARIO = (
    "vuelva a guardar (para moverla de una vez, use la carga masiva de "
    "Sucursales)"
)


class BodegasSecundariasInvalidasError(ValueError):
    """The secondaries a store's form lists break a rule of this module.
    The message, in Spanish, names every rejected code."""


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def normalizar_codigos(valor: Any) -> List[str]:
    """The bodega codes of a cell (upload) or a list (form): split on
    comma or semicolon, trimmed, upper-cased, without blanks or repeats,
    in order. `None` -> `[]`."""
    codigos: List[str] = []
    for codigo in split_multivalor(valor):
        codigo = codigo.upper()
        if codigo not in codigos:
            codigos.append(codigo)
    return codigos


def _motivo_sin_principal(nombre: str) -> str:
    return (
        f"La sucursal '{nombre}' lista 'Bodegas secundarias' "
        "pero no tiene 'Bodega principal'. Cárguela primero: "
        "las secundarias se enlazan a la principal."
    )


_SucursalDb = Tuple[uuid.UUID, str, Optional[str]]


def _principales_efectivas(
    filas: Sequence[Dict[str, Any]], sucursales_db: Sequence[_SucursalDb]
) -> Dict[Hashable, Optional[str]]:
    """clave de sucursal -> código de su bodega principal DESPUÉS de aplicar
    el archivo: el valor del archivo si la celda trae uno; si no, el guardado
    (una celda en blanco es "no provisto" y conserva lo que había)."""
    efectivas: Dict[Hashable, Optional[str]] = {
        sid: principal for sid, _, principal in sucursales_db
    }
    for index, fila in enumerate(filas, start=1):
        if not _texto(fila.get("nombre")):
            continue
        clave = clave_de_fila(index, fila)
        principal = _texto(fila.get("bodega_principal"))
        if principal:
            efectivas[clave] = principal
        else:
            efectivas.setdefault(clave, None)
    return efectivas


def _nombres_finales(
    filas: Sequence[Dict[str, Any]], sucursales_db: Sequence[_SucursalDb]
) -> Dict[Hashable, str]:
    """clave de sucursal -> su nombre DESPUÉS de aplicar el archivo (una fila
    puede renombrar su tienda), para los mensajes."""
    nombres: Dict[Hashable, str] = {
        sid: nombre for sid, nombre, _ in sucursales_db
    }
    for index, fila in enumerate(filas, start=1):
        nombre = _texto(fila.get("nombre"))
        if nombre:
            nombres[clave_de_fila(index, fila)] = nombre
    return nombres


def _errores_de_sucursal_repetida(
    filas: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Una misma tienda (por su clave, no por su nombre) en dos filas: la
    columna sería ambigua, error en la segunda."""
    errores: List[Dict[str, Any]] = []
    vistos: Dict[Hashable, int] = {}
    for index, fila in enumerate(filas, start=1):
        nombre = _texto(fila.get("nombre"))
        if not nombre:
            continue  # `validate_rows` ya la rechaza como campo requerido
        clave = clave_de_fila(index, fila)
        if clave not in vistos:
            vistos[clave] = index
            continue
        errores.append({
            "fila": index,
            "motivo": (
                f"La sucursal '{nombre}' aparece repetida en el "
                f"archivo (igual a la fila {vistos[clave]}). Dejá una "
                "sola fila por sucursal para que 'Bodegas "
                "secundarias' no sea ambigua."
            ),
        })
    return errores


async def resolver_filas(
    db, filas: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Retorna `(filas_resueltas, errores)` con el mismo shape `{fila, motivo}`
    (1-indexado) que el resto de los resolvers de `api/carga.py`. Sin la
    columna en el archivo devuelve las filas tal cual, sin consultar la
    base."""
    if not any(COLUMNA in fila for fila in filas):
        return filas, []

    resueltas: List[Dict[str, Any]] = []
    for fila in filas:
        fila = dict(fila)
        if COLUMNA in fila:
            # Por fila: una fila sin la clave (JSON) no toca las
            # secundarias de su sucursal.
            fila[FILA_CLAVE] = normalizar_codigos(fila.pop(COLUMNA))
        resueltas.append(fila)

    errores = _errores_de_sucursal_repetida(resueltas)
    todos_los_codigos = {
        codigo for fila in resueltas for codigo in fila.get(FILA_CLAVE, [])
    }
    if not todos_los_codigos:
        return resueltas, errores

    sucursales_db = [tuple(r) for r in (await db.execute(select(
        Sucursal.id, Sucursal.nombre, Sucursal.bodega_principal
    ))).all()]
    bodegas_db = dict(tuple(r) for r in (await db.execute(
        select(Bodega.codigo, Bodega.sucursal_id)
        .where(Bodega.codigo.in_(todos_los_codigos))
    )).all())
    errores += _errores_de_codigos(resueltas, sucursales_db, bodegas_db)
    errores.sort(key=lambda e: e["fila"])
    return resueltas, errores


def _codigos_liberados(
    filas: List[Dict[str, Any]],
    bodegas_db: Dict[str, Optional[uuid.UUID]],
) -> Set[str]:
    """Códigos que el propio archivo libera: su tienda dueña viene en el
    archivo CON la columna y ya no los lista. Si el código sigue siendo la
    principal de esa tienda lo rechaza `_motivo_de_codigo`. La tienda dueña
    es la que resolvió el C.O. (`FILA_SUCURSAL_ID`), no la del nombre."""
    liberados: Set[str] = set()
    for fila in filas:
        sucursal_id = fila.get(FILA_SUCURSAL_ID)
        if sucursal_id is None or FILA_CLAVE not in fila:
            continue
        listados = set(fila[FILA_CLAVE])
        liberados.update(
            codigo for codigo, duena in bodegas_db.items()
            if duena == sucursal_id and codigo not in listados
        )
    return liberados


def _errores_de_codigos(
    filas: List[Dict[str, Any]],
    sucursales_db: Sequence[Tuple[uuid.UUID, str, Optional[str]]],
    bodegas_db: Dict[str, Optional[uuid.UUID]],
) -> List[Dict[str, Any]]:
    liberados = _codigos_liberados(filas, bodegas_db)
    bodegas_db = {
        codigo: duena for codigo, duena in bodegas_db.items()
        if codigo not in liberados
    }
    efectivas = _principales_efectivas(filas, sucursales_db)
    nombres = _nombres_finales(filas, sucursales_db)
    principal_de: Dict[str, str] = {}
    for clave, principal in efectivas.items():
        if principal:
            principal_de.setdefault(principal, nombres.get(clave, ""))

    errores: List[Dict[str, Any]] = []
    primera_fila_de: Dict[str, int] = {}
    for index, fila in enumerate(filas, start=1):
        codigos = fila.get(FILA_CLAVE)
        nombre = _texto(fila.get("nombre"))
        if not codigos or not nombre:
            continue
        principal = efectivas.get(clave_de_fila(index, fila))
        if not principal:
            errores.append({
                "fila": index, "motivo": _motivo_sin_principal(nombre),
            })
            continue
        for codigo in codigos:
            motivo = _motivo_de_codigo(
                codigo, nombre, principal, principal_de, primera_fila_de,
                bodegas_db, fila.get(FILA_SUCURSAL_ID), nombres,
            )
            if motivo:
                errores.append({"fila": index, "motivo": motivo})
            primera_fila_de.setdefault(codigo, index)
    return errores


def _motivo_de_codigo(
    codigo: str,
    nombre: str,
    principal: str,
    principal_de: Dict[str, str],
    primera_fila_de: Dict[str, int],
    bodegas_db: Dict[str, Optional[uuid.UUID]],
    sucursal_id: Optional[uuid.UUID],
    nombre_por_sucursal_id: Dict[uuid.UUID, str],
    reintento: str = _REINTENTO_CARGA,
) -> Optional[str]:
    if codigo == principal:
        return (
            f"La bodega '{codigo}' es la bodega principal de esta "
            f"misma sucursal ('{nombre}'); no puede ser también "
            "secundaria."
        )
    duena = principal_de.get(codigo)
    if duena is not None:
        return (
            f"La bodega '{codigo}' es la bodega principal de la "
            f"sucursal '{duena}'; una bodega principal no puede ser "
            "secundaria de otra sucursal."
        )
    if codigo in primera_fila_de:
        return (
            f"La bodega '{codigo}' ya aparece como secundaria en la "
            f"fila {primera_fila_de[codigo]}; una bodega solo puede "
            "pertenecer a una sucursal."
        )
    vinculada_a = bodegas_db.get(codigo)
    if vinculada_a is not None and vinculada_a != sucursal_id:
        otra = nombre_por_sucursal_id.get(vinculada_a, "otra sucursal")
        return (
            f"La bodega '{codigo}' ya está asociada a la sucursal "
            f"'{otra}'. Quítela primero de 'Bodegas secundarias' de "
            f"'{otra}' y {reintento}."
        )
    return None


async def aplicar(
    db, entradas: List[Tuple[Sucursal, List[str]]],
    usuario_id: Optional[uuid.UUID],
) -> ResumenBodegasSecundarias:
    """Vincula y desvincula en la sesión (el `commit()` lo hace el caller).
    `entradas`: cada sucursal del archivo ya guardada, con su lista final de
    códigos secundarios (vacía = desvincular todas). Con UN solo query trae
    las bodegas listadas y las ya vinculadas a esas sucursales."""
    codigos = {codigo for _, lista in entradas for codigo in lista}
    ids = [sucursal.id for sucursal, _ in entradas]
    # A code another store of the file lists is moving, not being released:
    # skipping it keeps the result identical whatever the row order is.
    condiciones = [Bodega.sucursal_id.in_(ids)]
    if codigos:
        condiciones.append(Bodega.codigo.in_(codigos))
    existentes = (await db.execute(
        select(Bodega).where(or_(*condiciones))
    )).scalars().all()
    por_codigo = {b.codigo: b for b in existentes}

    resumen = ResumenBodegasSecundarias()
    for sucursal, listados in entradas:
        for codigo in listados:
            if await _vincular(db, codigo, sucursal, usuario_id, por_codigo):
                resumen.vinculadas.append(
                    {"sucursal": sucursal.nombre, "bodega": codigo}
                )
        for bodega in existentes:
            if (
                bodega.sucursal_id == sucursal.id
                and bodega.codigo != sucursal.bodega_principal
                and bodega.codigo not in codigos
            ):
                await _escribir(db, bodega, None, None, usuario_id)
                resumen.desvinculadas.append(
                    {"sucursal": sucursal.nombre, "bodega": bodega.codigo}
                )
    return resumen


async def _vincular(
    db, codigo: str, sucursal: Sucursal,
    usuario_id: Optional[uuid.UUID], por_codigo: Dict[str, Bodega],
) -> bool:
    """Links one listed secondary to its store. False when it already was."""
    principal = sucursal.bodega_principal
    bodega = por_codigo.get(codigo)
    if bodega is None:
        por_codigo[codigo] = await maestros.create_bodega(db, BodegaCreate(
            codigo=codigo, sucursal_id=sucursal.id,
            bodega_principal=principal,
        ), usuario_id)
        return True
    destino = (sucursal.id, principal)
    if (bodega.sucursal_id, bodega.bodega_principal) == destino:
        return False
    await _escribir(db, bodega, sucursal.id, principal, usuario_id)
    return True


async def _escribir(
    db, bodega: Bodega, sucursal_id: Optional[uuid.UUID],
    principal: Optional[str], usuario_id: Optional[uuid.UUID],
) -> None:
    await maestros.update_bodega(db, bodega, BodegaUpdate(
        sucursal_id=sucursal_id, bodega_principal=principal,
    ), usuario_id)


def _principales_de(
    sucursales: Sequence[Sucursal],
) -> Dict[str, uuid.UUID]:
    """principal code -> its store, for the stores that have one. The
    upload validation keeps a code as the principal of one store only."""
    raiz_de: Dict[str, uuid.UUID] = {}
    for sucursal in sucursales:
        codigo = _texto(sucursal.bodega_principal)
        if codigo:
            raiz_de[codigo] = sucursal.id
    return raiz_de


def _destino(
    bodega: Bodega,
    raiz_de: Dict[str, uuid.UUID],
    principal_de: Dict[uuid.UUID, str],
) -> Tuple[Optional[uuid.UUID], Optional[str]]:
    """`(sucursal_id, bodega_principal)` the record must end with: the root
    of its store when it is a principal; chained to its store's principal
    when that store is in the file; with its chain cut when it still
    chains to a principal of the file without belonging to that store
    (otherwise ingest would follow the chain into the wrong store);
    unchanged otherwise."""
    if bodega.codigo in raiz_de:
        return raiz_de[bodega.codigo], None
    principal = principal_de.get(bodega.sucursal_id)
    if principal is not None:
        return bodega.sucursal_id, principal
    if bodega.bodega_principal in raiz_de:
        return bodega.sucursal_id, None
    return bodega.sucursal_id, bodega.bodega_principal


async def sincronizar_principales(
    db, sucursales: Sequence[Sucursal], usuario_id: Optional[uuid.UUID],
) -> None:
    """Syncs the `bodega` records of the principals of `sucursales` (every
    store of the file, already saved). Runs after every other step of the
    upload, so it sees the final state whatever the row order. One query,
    and no query when no store has a principal. Writes only what changes,
    through the same audited service functions as `aplicar`."""
    raiz_de = _principales_de(sucursales)
    if not raiz_de:
        return
    principal_de = {sucursal_id: codigo
                    for codigo, sucursal_id in raiz_de.items()}
    # The session runs with autoflush off: the query must see the
    # secondaries `aplicar` just linked or created.
    await db.flush()
    bodegas = (await db.execute(select(Bodega).where(or_(
        Bodega.codigo.in_(raiz_de),
        Bodega.sucursal_id.in_(principal_de),
        Bodega.bodega_principal.in_(raiz_de),
    )))).scalars().all()
    existentes = {bodega.codigo for bodega in bodegas}
    for bodega in bodegas:
        destino = _destino(bodega, raiz_de, principal_de)
        if (bodega.sucursal_id, bodega.bodega_principal) != destino:
            await _escribir(db, bodega, *destino, usuario_id)
    for codigo, sucursal_id in raiz_de.items():
        if codigo not in existentes:
            await maestros.create_bodega(db, BodegaCreate(
                codigo=codigo, sucursal_id=sucursal_id,
            ), usuario_id)


async def _validar_de_sucursal(
    db, sucursal: Sucursal, codigos: List[str],
) -> None:
    """The form's rules for the secondaries of ONE store, against the
    final state: the store's principal is the one the save just set (in
    memory, never re-read), and the codes it owns may be listed, so a
    principal/secondary swap is one save. Two queries, none without
    codes. Raises `BodegasSecundariasInvalidasError` with every motive."""
    if not codigos:
        return
    principal = _texto(sucursal.bodega_principal)
    if not principal:
        raise BodegasSecundariasInvalidasError(
            _motivo_sin_principal(sucursal.nombre)
        )
    otras = (await db.execute(
        select(Sucursal.nombre, Sucursal.bodega_principal).where(
            Sucursal.bodega_principal.in_(codigos),
            Sucursal.id != sucursal.id,
        )
    )).all()
    duenas = (await db.execute(
        select(Bodega.codigo, Bodega.sucursal_id, Sucursal.nombre)
        .outerjoin(Sucursal, Sucursal.id == Bodega.sucursal_id)
        .where(Bodega.codigo.in_(codigos))
    )).all()
    principal_de = {codigo: nombre for nombre, codigo in otras}
    bodegas_db = {codigo: duena for codigo, duena, _ in duenas}
    nombres = {duena: nombre for _, duena, nombre in duenas if duena}
    motivos = [
        _motivo_de_codigo(
            codigo, sucursal.nombre, principal, principal_de, {},
            bodegas_db, sucursal.id, nombres, _REINTENTO_FORMULARIO,
        )
        for codigo in codigos
    ]
    motivos = [motivo for motivo in motivos if motivo]
    if motivos:
        raise BodegasSecundariasInvalidasError(" ".join(motivos))


async def guardar_de_sucursal(
    db, sucursal: Sucursal, codigos: Optional[Sequence[Any]],
    usuario_id: Optional[uuid.UUID],
) -> Optional[List[str]]:
    """The Sucursales form's save of a store's bodegas, after the store
    itself was created or updated in the session (the caller commits).
    `codigos` None leaves the secondaries as they are; a list (maybe empty)
    is the final set: validated, then linked and released by `aplicar`.
    Either way the principal's own record is synced last, as the upload
    does. Returns the normalized codes, or None when none were given."""
    # The session runs with autoflush off and `bodega` has no relationship
    # to `sucursal`: a store created by this save must be INSERTed before
    # a bodega row points at it (bodega_sucursal_id_fkey).
    await db.flush()
    normalizados = None
    if codigos is not None:
        normalizados = normalizar_codigos(list(codigos))
        await _validar_de_sucursal(db, sucursal, normalizados)
        await aplicar(db, [(sucursal, normalizados)], usuario_id)
    await sincronizar_principales(db, [sucursal], usuario_id)
    return normalizados


async def secundarias_por_sucursal(
    db, sucursales: Sequence[Sucursal],
) -> Dict[uuid.UUID, List[str]]:
    """store id -> the codes of its records other than its principal,
    sorted, for the stores given. One query; none without stores."""
    if not sucursales:
        return {}
    principal_de = {s.id: s.bodega_principal for s in sucursales}
    filas = (await db.execute(
        select(Bodega.sucursal_id, Bodega.codigo)
        .where(Bodega.sucursal_id.in_(list(principal_de)))
        .order_by(Bodega.codigo)
    )).all()
    resultado: Dict[uuid.UUID, List[str]] = {}
    for sucursal_id, codigo in filas:
        if codigo != principal_de.get(sucursal_id):
            resultado.setdefault(sucursal_id, []).append(codigo)
    return resultado
