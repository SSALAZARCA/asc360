"""
VENTAS: which rows count, decided by the ERP sale-type denylist and by the
commercial line of the referencia master.

Rules (owner decisions of 2026-10-06):
- A row whose file "Tipo inventario" matches `ventas_tipos_excluidos` (ERP
  codes, prefix or exact) is never demand and never a carga_error: it is
  counted (`filas_tipo_excluido`) and, like a row of another line, kept only
  in `venta_detalle` (payload `solo_detalle`, as since f7fce06) when its
  referencia and sucursal resolve.
- The line of a row is ONLY the CURRENT `referencia.linea_comercial`
  (trimmed, upper-cased, without accents, like the KPI summaries). A line in
  the `lineas_comerciales` IN FORCE (read like the KPI reads them, at the
  first day of the month of the carga's period) keeps the row; any other
  non-empty line (e.g. "NO COMERCIAL") is `fuera_de_linea` (counted, and
  kept only in `venta_detalle`; it never enters `venta_mensual`, the valid
  rows, the period histogram or `fecha_max_detectada`); an empty line is `sin_linea` and blocks the apply until a user
  assigns one. `tipos_inventario_incluidos` is NOT used by VENTAS.
- Empty-apply guard: if the file has rows that were considered (not
  excluded by bodega or by the type denylist) but none of them is kept (an
  included line, or an unknown referencia, which keeps its row error),
  nothing is applied: the dry-run marks the carga CON_ERRORES and the apply
  answers 409 (`MENSAJE_NINGUNA_LINEA`). Rows `sin_linea` are still pending,
  so they count as not yet decided.
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

from sqlalchemy import func, select, tuple_

from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services import parametros, parametros_claves
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import periodo as periodo_mod

CLAVE_REEMPLAZA_MES = "reemplaza_mes_completo"
CLAVE_CLASE_LINEA = "linea_clase"
CLASE_INCLUIDA = "incluida"
CLASE_FUERA_DE_LINEA = "fuera_de_linea"
CLASE_SIN_LINEA = "sin_linea"
CLASE_TIPO_EXCLUIDO = "tipo_excluido"
CLAVE_SOLO_DETALLE = "solo_detalle"

MODO_PREFIJO = "prefijo"
LINEA_NO_COMERCIAL = "NO COMERCIAL"
_LOTE_IDS = 5000

ReglasExcluidas = Tuple[Tuple[str, str], ...]


class MarcaTipoExcluido(Enum):
    """Resultado de `ventas.procesar_fila`: la fila es de un tipo de venta
    del ERP que no es de repuestos y no se puede guardar ni en el detalle
    (algo de la fila no resuelve): se omite y se cuenta aparte."""

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


def clase_de_staging(
    payload: Mapping[str, Any], referencia_id: Optional[uuid.UUID],
    lineas: Mapping[uuid.UUID, str], incluidas: FrozenSet[str],
) -> Optional[str]:
    """Clase VIVA de una fila staged. Una fila de tipo excluido lo es siempre
    (la lista de lineas no la toca); el resto sigue al maestro de hoy."""
    if payload.get(CLAVE_CLASE_LINEA) == CLASE_TIPO_EXCLUIDO:
        return CLASE_TIPO_EXCLUIDO
    return clase_de_fila(referencia_id, lineas, incluidas)


def reclasificar(
    filas_staging: Sequence[CargaFilaStaging],
    lineas: Mapping[uuid.UUID, str], incluidas: FrozenSet[str],
) -> List[FilaAplicable]:
    """Las filas que se aplican, evaluadas contra el maestro vigente. Una
    fila con clase (staged por esta versión) y referencia resuelta entra a
    `venta_mensual` y `venta_detalle` sólo si su línea vigente está en las
    líneas comerciales; las demás (otra línea, tipo excluido) pasan como
    `solo_detalle`: sólo `venta_detalle`, como siempre. Una fila sin
    referencia resuelta, o staged por una versión anterior (sin clase),
    pasa tal cual: `Aplicar` ya la ignora o la trata como siempre."""
    aplicables: List[FilaAplicable] = []
    for fila in filas_staging:
        payload = dict(fila.payload)
        if CLAVE_CLASE_LINEA in payload and fila.referencia_id is not None:
            clase = clase_de_staging(
                payload, fila.referencia_id, lineas, incluidas)
            if clase == CLASE_INCLUIDA:
                payload.pop(CLAVE_SOLO_DETALLE, None)
            else:
                payload[CLAVE_SOLO_DETALLE] = True
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
        clase = clase_de_staging(
            fila.payload, fila.referencia_id, lineas, incluidas)
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


MENSAJE_NINGUNA_LINEA = (
    "Ninguna fila quedó en las líneas incluidas: revise la configuración "
    "de líneas comerciales.")


async def leer_lineas_comerciales(db, en_fecha) -> FrozenSet[str]:
    """Las `lineas_comerciales` vigentes al dia 1 del mes de `en_fecha`
    (normalizadas), leidas como las lee el KPI (`parametros.leer_valores`:
    sin fila vigente o con una invalida rige el default del registro)."""
    clave = "lineas_comerciales"
    valores = await parametros.leer_valores(
        db, en_fecha, {clave: list(parametros_claves.REGISTRO[clave].default)})
    return normalizar_incluidas(valores[clave])


def mensaje_sin_linea(cantidad: int) -> str:
    return (f"Hay {cantidad} referencias sin línea: "
            "asígnelas antes de aplicar.")


Clave = Tuple[uuid.UUID, int, int]


async def _claves_del_archivo(
    session, carga: Any, incluidas: FrozenSet[str]
) -> Set[Clave]:
    """`(sucursal, anio, mes)` de las ventas que se aplicarian a
    `venta_mensual` contra el maestro de hoy, dentro del periodo declarado
    (las filas solo-detalle no cuentan)."""
    filas = (await session.execute(
        select(
            CargaFilaStaging.fila, CargaFilaStaging.sucursal_id,
            CargaFilaStaging.referencia_id, CargaFilaStaging.payload)
        .where(CargaFilaStaging.carga_id == carga.id))).all()
    lineas = await leer_lineas(
        session, {f.referencia_id for f in filas if f.referencia_id})
    declarados = periodo_mod.meses_en_rango(
        carga.periodo_desde, carga.periodo_hasta)
    claves: Set[Clave] = set()
    for f in reclasificar(filas, lineas, incluidas):
        mes = (f.payload["anio"], f.payload["mes"])
        if (mes in declarados and f.sucursal_id is not None
                and f.referencia_id is not None
                and not f.payload.get(CLAVE_SOLO_DETALLE)):
            claves.add((f.sucursal_id, *mes))
    return claves


async def _ventas_actuales(session, meses) -> List[Tuple[Any, ...]]:
    """`(sucursal, anio, mes, filas)` de `venta_mensual` de esos meses; las
    cargas anuladas no cuentan."""
    return (await session.execute(
        select(VentaMensual.sucursal_id, VentaMensual.anio, VentaMensual.mes,
               func.count())
        .join(CargaArchivo, CargaArchivo.id == VentaMensual.carga_id)
        .where(tuple_(VentaMensual.anio, VentaMensual.mes).in_(meses),
               CargaArchivo.estado != "ANULADO")
        .group_by(VentaMensual.sucursal_id, VentaMensual.anio,
                  VentaMensual.mes))).all()


async def vaciado_previsto(
    session, carga: Any, incluidas: FrozenSet[str]
) -> List[Dict[str, Any]]:
    """VIVO: las tiendas con ventas en los meses del archivo que el archivo
    NO trae para ese mes, y que un `reemplaza_mes_completo` borraria. `mes`
    sale 'YYYY-MM'; `filas_actuales` cuenta las filas de `venta_mensual`.
    Vacio sin el flag o sin staging."""
    if not (carga.log or {}).get(CLAVE_REEMPLAZA_MES):
        return []
    en_archivo = await _claves_del_archivo(session, carga, incluidas)
    meses = sorted({(anio, mes) for _, anio, mes in en_archivo})
    if not meses:
        return []
    ausentes = [
        (sucursal, anio, mes, cantidad)
        for sucursal, anio, mes, cantidad in await _ventas_actuales(session, meses)
        if (sucursal, anio, mes) not in en_archivo]
    nombres = dict((await session.execute(
        select(Sucursal.id, Sucursal.nombre)
        .where(Sucursal.id.in_({fila[0] for fila in ausentes})))).all()
    ) if ausentes else {}
    lista = [
        {"sucursal_id": sucursal, "nombre": nombres.get(sucursal, ""),
         "mes": f"{anio:04d}-{mes:02d}", "filas_actuales": cantidad}
        for sucursal, anio, mes, cantidad in ausentes]
    lista.sort(key=lambda r: (r["mes"], r["nombre"]))
    return lista
