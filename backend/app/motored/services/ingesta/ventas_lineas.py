"""
VENTAS: which rows count, decided by the ERP sale-type denylist and by the
commercial line of the referencia master.

Rules (owner decisions of 2026-10-06):
- A row whose file "Tipo inventario" matches `ventas_tipos_excluidos` (ERP
  codes, prefix or exact) is discarded and counted, never a carga_error.
- The line of a row is ONLY the CURRENT `referencia.linea_comercial`
  (trimmed, upper-cased, without accents, like the KPI summaries). A line in
  `tipos_inventario_incluidos` keeps the row; any other non-empty line is
  `fuera_de_linea` (discarded, counted); an empty line is `sin_linea` and
  blocks the apply until a user assigns one.
- The class is stored in the staging payload at dry-run (for the counters)
  and re-evaluated against the live master at apply and in the report.
"""
from __future__ import annotations

import unicodedata
import uuid
from collections import defaultdict
from decimal import Decimal
from enum import Enum
from typing import (
    Any, Dict, FrozenSet, Iterable, List, Mapping, NamedTuple, Optional,
    Sequence, Set, Tuple,
)

from sqlalchemy import func, select

from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.referencia import Referencia
from app.motored.services.ingesta import errores as errores_mod

CLAVE_CLASE_LINEA = "linea_clase"
CLASE_INCLUIDA = "incluida"
CLASE_FUERA_DE_LINEA = "fuera_de_linea"
CLASE_SIN_LINEA = "sin_linea"
CLAVE_SOLO_DETALLE = "solo_detalle"

MODO_PREFIJO = "prefijo"
LINEA_NO_COMERCIAL = "NO COMERCIAL"
_LOTE_IDS = 5000

ReglasExcluidas = Tuple[Tuple[str, str], ...]


class MarcaTipoExcluido(Enum):
    """Resultado de `ventas.procesar_fila`: la fila es de un tipo de venta
    del ERP que no es de repuestos y se descarta (se cuenta aparte)."""

    TIPO_EXCLUIDO = "tipo_excluido"


class FilaAplicable(NamedTuple):
    """Fila staged con su clase evaluada contra el maestro vigente. Misma
    forma (`payload`, `sucursal_id`, `referencia_id`) que lee `ventas`."""

    fila: int
    sucursal_id: Optional[uuid.UUID]
    referencia_id: Optional[uuid.UUID]
    payload: Dict[str, Any]


def normalizar_linea(valor: Any) -> str:
    """Trim, mayúsculas y sin tildes; vacío si no hay texto."""
    if valor is None:
        return ""
    descompuesto = unicodedata.normalize("NFD", str(valor).strip())
    sin_tildes = "".join(
        c for c in descompuesto if unicodedata.category(c) != "Mn")
    return sin_tildes.upper()


def normalizar_incluidas(tipos: Iterable[Any]) -> FrozenSet[str]:
    return frozenset(n for n in (normalizar_linea(t) for t in tipos) if n)


def compilar_excluidos(valor: Any) -> ReglasExcluidas:
    """`ventas_tipos_excluidos` como pares `(CODIGO, modo)` normalizados."""
    reglas = []
    for fila in valor or ():
        codigo = str(fila.get("codigo", "")).strip().upper()
        if codigo:
            reglas.append((codigo, fila.get("modo")))
    return tuple(reglas)


def es_tipo_excluido(tipo_erp: Any, reglas: ReglasExcluidas) -> bool:
    """True si el código de tipo del archivo cae en alguna regla. Un código
    vacío nunca cae."""
    codigo = "" if tipo_erp is None else str(tipo_erp).strip().upper()
    if not codigo:
        return False
    return any(
        codigo.startswith(regla) if modo == MODO_PREFIJO else codigo == regla
        for regla, modo in reglas)


def clasificar(linea_norm: str, incluidas: FrozenSet[str]) -> str:
    if not linea_norm:
        return CLASE_SIN_LINEA
    return CLASE_INCLUIDA if linea_norm in incluidas else CLASE_FUERA_DE_LINEA


async def leer_lineas(
    session, ids: Optional[Iterable[uuid.UUID]] = None
) -> Dict[uuid.UUID, str]:
    """`{referencia_id: línea normalizada}` del maestro vigente; las
    referencias sin línea no aparecen. Sin `ids`, una sola lectura de todo
    el maestro (dry-run); con `ids`, sólo esas, por lotes."""
    lineas: Dict[uuid.UUID, str] = {}
    if ids is None:
        consultas = [select(Referencia.id, Referencia.linea_comercial)]
    else:
        lista = list(ids)
        consultas = [
            select(Referencia.id, Referencia.linea_comercial)
            .where(Referencia.id.in_(lista[i:i + _LOTE_IDS]))
            for i in range(0, len(lista), _LOTE_IDS)]
    for consulta in consultas:
        for referencia_id, linea in (await session.execute(consulta)).all():
            norm = normalizar_linea(linea)
            if norm:
                lineas[referencia_id] = norm
    return lineas


def clase_de_fila(
    referencia_id: Optional[uuid.UUID], lineas: Mapping[uuid.UUID, str],
    incluidas: FrozenSet[str],
) -> Optional[str]:
    """Clase de una fila con referencia resuelta; `None` sin referencia."""
    if referencia_id is None:
        return None
    return clasificar(lineas.get(referencia_id, ""), incluidas)


def reclasificar(
    filas_staging: Sequence[CargaFilaStaging],
    lineas: Mapping[uuid.UUID, str], incluidas: FrozenSet[str],
) -> List[FilaAplicable]:
    """Las filas que SÍ se aplican, evaluadas contra el maestro vigente.
    Una fila con clase (staged por esta versión) y referencia resuelta se
    queda sólo si su línea vigente está incluida; las demás clases se
    descartan por completo. Una fila sin referencia resuelta, o staged por
    una versión anterior (sin clase), pasa tal cual: `Aplicar` ya la ignora
    o la trata como siempre."""
    aplicables: List[FilaAplicable] = []
    for fila in filas_staging:
        payload = dict(fila.payload)
        if CLAVE_CLASE_LINEA in payload and fila.referencia_id is not None:
            clase = clase_de_fila(fila.referencia_id, lineas, incluidas)
            if clase != CLASE_INCLUIDA:
                continue
            payload.pop(CLAVE_SOLO_DETALLE, None)
            payload[CLAVE_CLASE_LINEA] = clase
        aplicables.append(FilaAplicable(
            fila.fila, fila.sucursal_id, fila.referencia_id, payload))
    return aplicables


def _a_decimal(payload: Mapping[str, Any], clave: str) -> Decimal:
    try:
        return Decimal(str(payload.get(clave, "0")))
    except Exception:  # noqa: BLE001 -- un payload viejo no tumba el informe
        return Decimal("0")


async def informe(
    session, carga_id: uuid.UUID, incluidas: FrozenSet[str],
    sucursal_ids: Optional[Set[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Lo que el usuario debe resolver antes de aplicar, VIVO contra el
    maestro de hoy: `sin_linea` (por referencia, mayor valor primero),
    `fuera_de_linea` (por línea) y `no_encontradas` (por código). Con
    `sucursal_ids` (rol SUCURSAL) sólo cuenta las filas de esas sucursales."""
    filas = (await session.execute(
        select(
            CargaFilaStaging.fila, CargaFilaStaging.sucursal_id,
            CargaFilaStaging.referencia_id, CargaFilaStaging.payload)
        .where(CargaFilaStaging.carga_id == carga_id)
    )).all()
    if sucursal_ids is not None:
        filas = [f for f in filas
                 if f.sucursal_id is not None
                 and str(f.sucursal_id) in sucursal_ids]
    ids = {f.referencia_id for f in filas if f.referencia_id is not None}
    lineas = await leer_lineas(session, ids)

    sin: Dict[uuid.UUID, Dict[str, Any]] = {}
    fuera: Dict[str, int] = defaultdict(int)
    for fila in filas:
        clase = clase_de_fila(fila.referencia_id, lineas, incluidas)
        if clase == CLASE_FUERA_DE_LINEA:
            fuera[lineas[fila.referencia_id]] += 1
        elif clase == CLASE_SIN_LINEA:
            acum = sin.setdefault(fila.referencia_id, {
                "referencia_id": fila.referencia_id, "filas": 0,
                "unidades": Decimal("0"), "valor": Decimal("0")})
            acum["filas"] += 1
            acum["unidades"] += _a_decimal(fila.payload, "cantidad")
            acum["valor"] += (_a_decimal(fila.payload, "valor_bruto")
                              - _a_decimal(fila.payload, "valor_descuentos"))
    sin_linea = await _con_datos_de_referencia(session, sin)
    return {
        "sin_linea": sin_linea,
        "fuera_de_linea": [
            {"linea": linea, "filas": n} for linea, n in sorted(fuera.items())],
        "no_encontradas": await _no_encontradas(
            session, carga_id, filas if sucursal_ids is not None else None),
    }


async def _con_datos_de_referencia(
    session, sin: Dict[uuid.UUID, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if not sin:
        return []
    datos = {
        i: (codigo, nombre) for i, codigo, nombre in (await session.execute(
            select(Referencia.id, Referencia.codigo, Referencia.nombre)
            .where(Referencia.id.in_(list(sin))))).all()}
    lista = []
    for referencia_id, acum in sin.items():
        codigo, nombre = datos.get(referencia_id, ("", None))
        lista.append({
            "referencia_id": referencia_id, "codigo": codigo,
            "nombre": nombre, "filas": acum["filas"],
            "unidades": float(acum["unidades"]), "valor": float(acum["valor"])})
    lista.sort(key=lambda r: (-r["valor"], -r["filas"], r["codigo"]))
    return lista


async def _no_encontradas(
    session, carga_id: uuid.UUID, filas_visibles: Optional[Sequence[Any]]
) -> List[Dict[str, Any]]:
    """Códigos que el maestro no tenía en el dry-run, por código; salen de
    la lista los que ya existen. `filas_visibles` (rol SUCURSAL) limita a
    las filas staged de sus sucursales."""
    errores = (await session.execute(
        select(CargaError.fila, CargaError.valor)
        .where(CargaError.carga_id == carga_id,
               CargaError.codigo_error
               == errores_mod.CODIGO_REFERENCIA_NO_ENCONTRADA))).all()
    if filas_visibles is not None:
        visibles = {f.fila for f in filas_visibles}
        errores = [e for e in errores if e.fila in visibles]
    por_codigo: Dict[str, int] = defaultdict(int)
    for _, valor in errores:
        por_codigo[(valor or "").strip()] += 1
    if not por_codigo:
        return []
    existentes = set((await session.execute(
        select(Referencia.codigo)
        .where(Referencia.codigo.in_(list(por_codigo))))).scalars().all())
    return [
        {"codigo": codigo, "filas": n}
        for codigo, n in sorted(por_codigo.items()) if codigo not in existentes]


def mensaje_sin_linea(cantidad: int) -> str:
    return (f"Hay {cantidad} referencias sin línea: "
            "asígnelas antes de aplicar.")
