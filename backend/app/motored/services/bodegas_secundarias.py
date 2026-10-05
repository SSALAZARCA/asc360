"""
Motored — columna "Bodegas secundarias" de la carga de Sucursales.

Una tienda puede tener varias bodegas, pero el archivo de Sucursales solo traía
"Bodega principal". La columna nueva lista los códigos de las bodegas
secundarias (separados por coma). Al cargar, cada código se guarda como una fila
`bodega` con `sucursal_id` = la tienda y `bodega_principal` = el código de la
bodega principal de esa tienda: la misma cadena que sigue
`ingesta.resolucion._resolver_sucursal_de_bodega` y de la que depende la
consolidación de INVENTARIO.

Dos pasos, los dos todo-o-nada junto con el resto del archivo:

- `resolver_filas` (validación, compartida por `validar` y `carga`): normaliza
  la celda, y devuelve errores de fila. Solo consulta la base si algún código
  aparece en el archivo.
- `aplicar` (escritura, dentro de `procesar_carga`, misma transacción):
  vincula lo listado y desvincula lo que ya no figura.

Reglas de desvinculación: sin la columna en el archivo no se toca ninguna
secundaria; con la columna, para cada sucursal DEL ARCHIVO los códigos listados
son sus secundarias y las que tenía vinculadas y ya no figuran quedan con
`sucursal_id` y `bodega_principal` en NULL (la fila `bodega` nunca se borra).
Una celda en blanco desvincula todas las de esa tienda. Las sucursales que no
están en el archivo no se tocan. La fila `bodega` de la propia bodega principal
nunca se desvincula.

Mover una secundaria de tienda en UNA sola carga: un código vinculado a otra
tienda se acepta si el mismo archivo lo libera, es decir, si la tienda dueña
también viene en el archivo con la columna y ya no lo lista. Si sigue siendo
su bodega principal (la del archivo o, en blanco, la guardada) se rechaza.
"""
import uuid
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import or_, select

from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.bodega import BodegaCreate, BodegaUpdate
from app.motored.schemas.carga import ResumenBodegasSecundarias
from app.motored.services import maestros
from app.motored.services.texto import split_multivalor

# Clave canónica de la columna tal como llega en cada fila del archivo.
COLUMNA = "bodegas_secundarias"
# Clave interna que deja `resolver_filas`: lista de códigos ya normalizados.
# Solo existe si la columna vino en el archivo (con `_` para que `_row_to_schema`
# la descarte antes de construir el schema de sucursal).
FILA_CLAVE = "_bodegas_secundarias"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def _principales_efectivas(
    filas: Sequence[Dict[str, Any]], sucursales_db: Sequence[Tuple[uuid.UUID, str, Optional[str]]]
) -> Dict[str, Optional[str]]:
    """nombre de sucursal -> código de su bodega principal DESPUÉS de aplicar
    el archivo: el valor del archivo si la celda trae uno; si no, el guardado
    (una celda en blanco es "no provisto" y conserva lo que había)."""
    efectivas: Dict[str, Optional[str]] = {nombre: principal for _, nombre, principal in sucursales_db}
    for fila in filas:
        nombre = _texto(fila.get("nombre"))
        if not nombre:
            continue
        principal = _texto(fila.get("bodega_principal"))
        if principal:
            efectivas[nombre] = principal
        else:
            efectivas.setdefault(nombre, None)
    return efectivas


async def resolver_filas(
    db, filas: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Retorna `(filas_resueltas, errores)` con el mismo shape `{fila, motivo}`
    (1-indexado) que el resto de los resolvers de `api/carga.py`. Sin la
    columna en el archivo devuelve las filas tal cual, sin consultar la base."""
    if not any(COLUMNA in fila for fila in filas):
        return filas, []

    resueltas: List[Dict[str, Any]] = []
    for fila in filas:
        fila = dict(fila)
        if COLUMNA in fila:
            # Por fila: una fila sin la clave (JSON) no toca las secundarias de su sucursal.
            fila[FILA_CLAVE] = split_multivalor(fila.pop(COLUMNA))
        resueltas.append(fila)

    errores: List[Dict[str, Any]] = []
    vistos: Dict[str, int] = {}
    for index, fila in enumerate(resueltas, start=1):
        nombre = _texto(fila.get("nombre"))
        if not nombre:
            continue  # `validate_rows` ya la rechaza como campo requerido
        if nombre in vistos:
            errores.append({
                "fila": index,
                "motivo": (
                    f"La sucursal '{nombre}' aparece repetida en el archivo (igual a la fila {vistos[nombre]}). "
                    "Dejá una sola fila por sucursal para que 'Bodegas secundarias' no sea ambigua."
                ),
            })
        else:
            vistos[nombre] = index

    todos_los_codigos = {codigo for fila in resueltas for codigo in fila.get(FILA_CLAVE, [])}
    if not todos_los_codigos:
        return resueltas, errores

    sucursales_db = [tuple(r) for r in (
        await db.execute(select(Sucursal.id, Sucursal.nombre, Sucursal.bodega_principal))
    ).all()]
    bodegas_db = dict(
        tuple(r) for r in (
            await db.execute(select(Bodega.codigo, Bodega.sucursal_id).where(Bodega.codigo.in_(todos_los_codigos)))
        ).all()
    )
    errores += _errores_de_codigos(resueltas, sucursales_db, bodegas_db)
    errores.sort(key=lambda e: e["fila"])
    return resueltas, errores


def _codigos_liberados(
    filas: List[Dict[str, Any]],
    sucursales_db: Sequence[Tuple[uuid.UUID, str, Optional[str]]],
    bodegas_db: Dict[str, Optional[uuid.UUID]],
) -> Set[str]:
    """Códigos que el propio archivo libera: su tienda dueña viene en el
    archivo CON la columna y ya no los lista. Si el código sigue siendo la
    principal de esa tienda lo rechaza `_motivo_de_codigo`."""
    id_por_nombre = {nombre: sid for sid, nombre, _ in sucursales_db}
    liberados: Set[str] = set()
    for fila in filas:
        sucursal_id = id_por_nombre.get(_texto(fila.get("nombre")))
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
    liberados = _codigos_liberados(filas, sucursales_db, bodegas_db)
    bodegas_db = {
        codigo: duena for codigo, duena in bodegas_db.items()
        if codigo not in liberados
    }
    efectivas = _principales_efectivas(filas, sucursales_db)
    principal_de: Dict[str, str] = {}
    for nombre, principal in efectivas.items():
        if principal:
            principal_de.setdefault(principal, nombre)
    sucursal_id_por_nombre = {nombre: sid for sid, nombre, _ in sucursales_db}
    nombre_por_sucursal_id = {sid: nombre for sid, nombre, _ in sucursales_db}

    errores: List[Dict[str, Any]] = []
    primera_fila_de: Dict[str, int] = {}
    for index, fila in enumerate(filas, start=1):
        codigos = fila.get(FILA_CLAVE)
        nombre = _texto(fila.get("nombre"))
        if not codigos or not nombre:
            continue
        principal = efectivas.get(nombre)
        if not principal:
            errores.append({
                "fila": index,
                "motivo": (
                    f"La sucursal '{nombre}' lista 'Bodegas secundarias' pero no tiene 'Bodega principal'. "
                    "Cárguela primero: las secundarias se enlazan a la principal."
                ),
            })
            continue
        for codigo in codigos:
            motivo = _motivo_de_codigo(
                codigo, nombre, principal, principal_de, primera_fila_de,
                bodegas_db, sucursal_id_por_nombre.get(nombre), nombre_por_sucursal_id,
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
) -> Optional[str]:
    if codigo == principal:
        return (
            f"La bodega '{codigo}' es la bodega principal de esta misma sucursal ('{nombre}'); "
            "no puede ser también secundaria."
        )
    duena = principal_de.get(codigo)
    if duena is not None:
        return (
            f"La bodega '{codigo}' es la bodega principal de la sucursal '{duena}'; "
            "una bodega principal no puede ser secundaria de otra sucursal."
        )
    if codigo in primera_fila_de:
        return (
            f"La bodega '{codigo}' ya aparece como secundaria en la fila {primera_fila_de[codigo]}; "
            "una bodega solo puede pertenecer a una sucursal."
        )
    vinculada_a = bodegas_db.get(codigo)
    if vinculada_a is not None and vinculada_a != sucursal_id:
        otra = nombre_por_sucursal_id.get(vinculada_a, "otra sucursal")
        return (
            f"La bodega '{codigo}' ya está asociada a la sucursal '{otra}'. "
            f"Quítela primero de 'Bodegas secundarias' de '{otra}' y vuelva a subir el archivo."
        )
    return None


async def aplicar(
    db, entradas: List[Tuple[Sucursal, List[str]]], usuario_id: Optional[uuid.UUID]
) -> ResumenBodegasSecundarias:
    """Vincula y desvincula en la sesión (el `commit()` lo hace el caller).
    `entradas`: cada sucursal del archivo ya guardada, con su lista final de
    códigos secundarios (vacía = desvincular todas). Con UN solo query trae las
    bodegas listadas y las ya vinculadas a esas sucursales."""
    codigos = {codigo for _, lista in entradas for codigo in lista}
    ids = [sucursal.id for sucursal, _ in entradas]
    # A code another store of the file lists is moving, not being released:
    # skipping it keeps the result identical whatever the row order is.
    condiciones = [Bodega.sucursal_id.in_(ids)]
    if codigos:
        condiciones.append(Bodega.codigo.in_(codigos))
    existentes = (await db.execute(select(Bodega).where(or_(*condiciones)))).scalars().all()
    por_codigo = {b.codigo: b for b in existentes}

    resumen = ResumenBodegasSecundarias()
    for sucursal, listados in entradas:
        principal = sucursal.bodega_principal
        for codigo in listados:
            bodega = por_codigo.get(codigo)
            if bodega is None:
                await _crear(db, codigo, sucursal, principal, usuario_id, por_codigo)
            elif bodega.sucursal_id == sucursal.id and bodega.bodega_principal == principal:
                continue
            else:
                await maestros.update_bodega(
                    db, bodega, BodegaUpdate(sucursal_id=sucursal.id, bodega_principal=principal), usuario_id
                )
            resumen.vinculadas.append({"sucursal": sucursal.nombre, "bodega": codigo})
        for bodega in existentes:
            if (
                bodega.sucursal_id == sucursal.id
                and bodega.codigo != principal
                and bodega.codigo not in codigos
            ):
                await maestros.update_bodega(
                    db, bodega, BodegaUpdate(sucursal_id=None, bodega_principal=None), usuario_id
                )
                resumen.desvinculadas.append({"sucursal": sucursal.nombre, "bodega": bodega.codigo})
    return resumen


async def _crear(
    db, codigo: str, sucursal: Sucursal, principal: Optional[str],
    usuario_id: Optional[uuid.UUID], por_codigo: Dict[str, Bodega],
) -> None:
    creada = await maestros.create_bodega(
        db, BodegaCreate(codigo=codigo, sucursal_id=sucursal.id, bodega_principal=principal), usuario_id
    )
    por_codigo[codigo] = creada
