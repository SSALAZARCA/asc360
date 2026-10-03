"""
Motored — carga de REFERENCIAS como reemplazo completo
(odd/tasks/motored-referencia-identidad.md, R2). El archivo es la verdad:

- Cada referencia del archivo queda EXACTAMENTE como dice el archivo: una celda
  opcional en blanco BORRA el valor guardado (nombre, línea comercial, precios,
  sustituta, homologados); `unidad_empaque` en blanco queda en 1 con aviso,
  nunca 0. `precio_venta` no es parte del layout y no se toca.
- Cambiar el proveedor MUEVE la referencia (mismo id, historial intacto).
- Las del archivo quedan activas (salvo las que tienen sustituta, que por
  regla del maestro quedan inactivas); las ACTIVAS que el archivo no trae se
  desactivan. Nunca se borra nada: 11 tablas tienen FK a `referencia`.
- Las que estaban inactivas y vuelven en el archivo se reactivan.

`planificar` calcula TODO en memoria contra el estado actual (un query por
tabla) y `construir_resumen` lo convierte en el dry-run que ve el usuario;
`aplicar` ejecuta ese mismo plan dentro de la transacción del caller. Como
`validar` y aplicar parsean el archivo por separado, aplicar recalcula el plan
y decide con el suyo (ver `services/carga.py`).

Esta lógica es SOLO de `referencia`: las demás cargas conservan su semántica
(celda en blanco = no provisto).
"""
import datetime
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func, select

from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.venta_mensual import VentaMensual
from app.motored.schemas.carga import GrupoInactivar, GrupoResumen, ResumenReemplazo
from app.motored.schemas.referencia import ReferenciaCreate, ReferenciaUpdate
from app.motored.services import auditoria, maestros

# Clave interna de fila (nunca llega al schema Pydantic): código de la
# sustituta cuando es OTRA fila del mismo archivo y proveedor. La setea
# `api/carga.py::_resolve_referencia_relaciones`; la consume `aplicar` en la
# segunda pasada (la sustituta puede ser una referencia que aún no existe).
SUSTITUTA_EN_ARCHIVO = "_sustituta_codigo_en_archivo"

MESES_VENTAS_ALERTA = 6
UMBRAL_DOBLE_CONFIRMACION = 0.10
MUESTRA_MAX = 50

_CENTAVOS = Decimal("0.01")
_ADVERTENCIA_UNIDAD_EMPAQUE = "unidad_empaque vacío: se dejó en 1"


@dataclass
class Objetivo:
    """Una fila del archivo ya validada, con el estado COMPLETO que la
    referencia debe tener (los campos opcionales ausentes son `None`/`[]`)."""

    fila: int
    datos: ReferenciaCreate
    sustituta_en_archivo: Optional[str]
    advertencias: List[str]

    @property
    def codigo(self) -> str:
        return self.datos.codigo

    @property
    def activa(self) -> bool:
        """Una referencia con sustituta queda inactiva (regla del maestro)."""
        return self.datos.sustituida_por is None and self.sustituta_en_archivo is None


@dataclass
class Plan:
    objetivos: List[Objetivo]
    existentes: Dict[str, Referencia]
    proveedores: Dict[uuid.UUID, str]
    activas_actuales: int
    errores: List[Dict[str, Any]] = field(default_factory=list)
    nuevas: List[Objetivo] = field(default_factory=list)
    actualizaciones: List[Tuple[Referencia, List[str]]] = field(default_factory=list)
    movimientos: List[Tuple[Referencia, uuid.UUID]] = field(default_factory=list)  # (referencia, proveedor nuevo)
    reactivar: List[Referencia] = field(default_factory=list)
    inactivar: List[Referencia] = field(default_factory=list)
    vinculos_cruzados: List[Tuple[Referencia, Referencia]] = field(default_factory=list)  # (apuntadora, destino)
    con_ventas_6m: Set[uuid.UUID] = field(default_factory=set)
    con_inventario: Set[uuid.UUID] = field(default_factory=set)
    modificadas: int = 0

    def advertencias_por_fila(self) -> List[Dict[str, Any]]:
        return [
            {"fila": o.fila, "advertencias": o.advertencias} for o in self.objetivos if o.advertencias
        ]


def construir_objetivos(valid_rows: List[Dict[str, Any]]) -> List[Objetivo]:
    objetivos: List[Objetivo] = []
    for index, row in enumerate(valid_rows, start=1):
        datos = ReferenciaCreate(**{k: v for k, v in row.items() if not k.startswith("_")})
        advertencias = list(row.get("_warnings") or [])
        if datos.unidad_empaque is None:
            advertencias.append(_ADVERTENCIA_UNIDAD_EMPAQUE)
        objetivos.append(Objetivo(index, datos, row.get(SUSTITUTA_EN_ARCHIVO), advertencias))
    return objetivos


def _centavos(valor: Optional[Decimal]) -> Optional[Decimal]:
    return None if valor is None else Decimal(valor).quantize(_CENTAVOS)


def _sustituta_final(objetivo: Objetivo, existentes: Dict[str, Referencia]) -> Any:
    """Id de la sustituta que quedará, o un marcador único cuando apunta a una
    referencia que todavía no existe (siempre es un cambio)."""
    if objetivo.sustituta_en_archivo is None:
        return objetivo.datos.sustituida_por
    destino = existentes.get(objetivo.sustituta_en_archivo)
    return destino.id if destino is not None else object()


def _campos_que_cambian(existente: Referencia, objetivo: Objetivo, existentes: Dict[str, Referencia]) -> List[str]:
    datos = objetivo.datos
    unidad = datos.unidad_empaque if datos.unidad_empaque is not None else 1
    comparaciones = (
        ("nombre", existente.nombre, datos.nombre),
        ("linea_comercial", existente.linea_comercial, datos.linea_comercial),
        ("unidad_empaque", existente.unidad_empaque, unidad),
        ("precio_normal", _centavos(existente.precio_normal), _centavos(datos.precio_normal)),
        ("precio_publico", _centavos(existente.precio_publico), _centavos(datos.precio_publico)),
        ("homologados", list(existente.homologados or []), list(datos.homologados)),
        ("sustituida_por", existente.sustituida_por, _sustituta_final(objetivo, existentes)),
    )
    campos = [nombre for nombre, actual, nuevo in comparaciones if actual != nuevo]
    if existente.activa and not objetivo.activa:
        campos.append("activa")  # la sustituta la deja inactiva
    return campos


def _errores_de_codigo(objetivos: List[Objetivo], referencias: List[Referencia]) -> List[Dict[str, Any]]:
    por_mayuscula = {r.codigo.upper(): r.codigo for r in referencias}
    exactos = {r.codigo for r in referencias}
    errores = []
    for objetivo in objetivos:
        if objetivo.codigo in exactos:
            continue
        parecido = por_mayuscula.get(objetivo.codigo.upper())
        if parecido is not None:
            errores.append({
                "fila": objetivo.fila,
                "motivo": (
                    f"Código '{objetivo.codigo}' coincide con '{parecido}', que ya existe, salvo por "
                    "mayúsculas/minúsculas. Escríbalo igual para actualizarla o use otro código."
                ),
            })
    return errores


async def _actividad(db, hoy: datetime.date) -> Tuple[Set[uuid.UUID], Set[uuid.UUID]]:
    """Ids de referencia con ventas en los últimos `MESES_VENTAS_ALERTA` meses
    (`venta_mensual`) y con existencias > 0 en el último corte de inventario.
    Sin parámetros `IN`: se traen los conjuntos completos y se cruzan en memoria."""
    desde = hoy.year * 12 + hoy.month - (MESES_VENTAS_ALERTA - 1)
    ventas = await db.execute(
        select(VentaMensual.referencia_id).where(VentaMensual.anio * 12 + VentaMensual.mes >= desde).distinct()
    )
    con_ventas = set(ventas.scalars().all())

    ultimo_corte = (await db.execute(select(func.max(InventarioSnapshot.fecha_corte)))).scalars().first()
    con_stock: Set[uuid.UUID] = set()
    if ultimo_corte is not None:
        stock = await db.execute(
            select(InventarioSnapshot.referencia_id)
            .where(InventarioSnapshot.fecha_corte == ultimo_corte, InventarioSnapshot.existencias > 0)
            .distinct()
        )
        con_stock = set(stock.scalars().all())
    return con_ventas, con_stock


def _clasificar(plan: Plan, referencias: List[Referencia]) -> None:
    codigos_archivo = {o.codigo for o in plan.objetivos}
    movidas: Dict[uuid.UUID, Referencia] = {}
    destino_proveedor: Dict[uuid.UUID, uuid.UUID] = {}

    for objetivo in plan.objetivos:
        existente = plan.existentes.get(objetivo.codigo)
        if existente is None:
            plan.nuevas.append(objetivo)
            continue
        campos = _campos_que_cambian(existente, objetivo, plan.existentes)
        reactiva = objetivo.activa and not existente.activa
        se_mueve = existente.proveedor_id != objetivo.datos.proveedor_id
        if campos:
            plan.actualizaciones.append((existente, campos))
        if reactiva:
            plan.reactivar.append(existente)
        if se_mueve:
            plan.movimientos.append((existente, objetivo.datos.proveedor_id))
            movidas[existente.id] = existente
            destino_proveedor[existente.id] = objetivo.datos.proveedor_id
        if campos or reactiva or se_mueve:
            plan.modificadas += 1

    plan.inactivar = [r for r in referencias if r.activa and r.codigo not in codigos_archivo]

    for apuntadora in referencias:
        if apuntadora.sustituida_por in movidas and apuntadora.codigo not in codigos_archivo:
            destino = movidas[apuntadora.sustituida_por]
            if apuntadora.proveedor_id != destino_proveedor[destino.id]:
                plan.vinculos_cruzados.append((apuntadora, destino))


async def planificar(db, valid_rows: List[Dict[str, Any]], hoy: Optional[datetime.date] = None) -> Plan:
    """Compara el archivo (`valid_rows`, ya validadas y con sustitutas
    resueltas) contra TODAS las referencias actuales. No escribe nada."""
    objetivos = construir_objetivos(valid_rows)
    referencias = list((await db.execute(select(Referencia))).scalars().all())
    proveedores = {p.id: p.codigo for p in (await db.execute(select(Proveedor))).scalars().all()}

    plan = Plan(
        objetivos=objetivos,
        existentes={r.codigo: r for r in referencias},
        proveedores=proveedores,
        activas_actuales=sum(1 for r in referencias if r.activa),
    )
    plan.errores = _errores_de_codigo(objetivos, referencias)
    if plan.errores:
        return plan

    _clasificar(plan, referencias)
    if plan.inactivar:
        plan.con_ventas_6m, plan.con_inventario = await _actividad(db, hoy or datetime.date.today())
    return plan


def _muestra(items: List[Any]) -> List[Any]:
    return items[:MUESTRA_MAX]


def _grupo_inactivar(plan: Plan) -> GrupoInactivar:
    marcadas = [
        {
            "codigo": r.codigo,
            "nombre": r.nombre,
            "con_ventas_6m": r.id in plan.con_ventas_6m,
            "con_inventario": r.id in plan.con_inventario,
        }
        for r in plan.inactivar
    ]
    # Las que vendieron o tienen stock van primero: son las que el usuario debe mirar.
    marcadas.sort(key=lambda m: (-(m["con_ventas_6m"] + m["con_inventario"]), m["codigo"]))
    return GrupoInactivar(
        total=len(marcadas),
        con_ventas_6m=sum(1 for m in marcadas if m["con_ventas_6m"]),
        con_inventario=sum(1 for m in marcadas if m["con_inventario"]),
        muestra=_muestra(marcadas),
    )


def construir_resumen(plan: Plan) -> ResumenReemplazo:
    pct = len(plan.inactivar) / plan.activas_actuales if plan.activas_actuales else 0.0
    return ResumenReemplazo(
        total_archivo=len(plan.objetivos),
        crear=GrupoResumen(
            total=len(plan.nuevas),
            muestra=_muestra([
                {"codigo": o.codigo, "proveedor": plan.proveedores.get(o.datos.proveedor_id, "?")}
                for o in plan.nuevas
            ]),
        ),
        actualizar=GrupoResumen(
            total=len(plan.actualizaciones),
            muestra=_muestra([{"codigo": r.codigo, "campos": campos} for r, campos in plan.actualizaciones]),
        ),
        mover_proveedor=GrupoResumen(
            total=len(plan.movimientos),
            muestra=_muestra([
                {
                    "codigo": r.codigo,
                    "proveedor_anterior": plan.proveedores.get(r.proveedor_id, "?"),
                    "proveedor_nuevo": plan.proveedores.get(nuevo, "?"),
                }
                for r, nuevo in plan.movimientos
            ]),
        ),
        inactivar=_grupo_inactivar(plan),
        reactivar=GrupoResumen(
            total=len(plan.reactivar),
            muestra=_muestra([{"codigo": r.codigo} for r in plan.reactivar]),
        ),
        vinculos_sustituta_limpiados=GrupoResumen(
            total=len(plan.vinculos_cruzados),
            muestra=_muestra([
                {"codigo": x.codigo, "sustituta": y.codigo} for x, y in plan.vinculos_cruzados
            ]),
        ),
        activas_actuales=plan.activas_actuales,
        pct_inactivar=pct,
        requiere_doble_confirmacion=pct > UMBRAL_DOBLE_CONFIRMACION,
    )


def texto_auditoria(resumen: ResumenReemplazo) -> str:
    return (
        f"archivo={resumen.total_archivo}; crear={resumen.crear.total}; "
        f"actualizar={resumen.actualizar.total}; mover={resumen.mover_proveedor.total}; "
        f"inactivar={resumen.inactivar.total}; reactivar={resumen.reactivar.total}; "
        f"vinculos_limpiados={resumen.vinculos_sustituta_limpiados.total}"
    )


def _campos_de_reemplazo(objetivo: Objetivo) -> Dict[str, Any]:
    """Lo que SIEMPRE se escribe sobre una referencia existente (aunque sea
    `None`/`[]`: es el reemplazo). `unidad_empaque=None` hace que
    `update_referencia` lo corrija a 1 y marque la advertencia."""
    datos = objetivo.datos
    campos: Dict[str, Any] = {
        "nombre": datos.nombre,
        "linea_comercial": datos.linea_comercial,
        "precio_normal": datos.precio_normal,
        "precio_publico": datos.precio_publico,
        "homologados": datos.homologados,
        "unidad_empaque": datos.unidad_empaque,
    }
    if objetivo.sustituta_en_archivo is None:
        campos["sustituida_por"] = datos.sustituida_por
    return campos


async def _escribir_fila(
    db, plan: Plan, objetivo: Objetivo, usuario_id: Optional[uuid.UUID]
) -> Referencia:
    existente = plan.existentes.get(objetivo.codigo)
    if existente is None:
        creada, _ = await maestros.create_referencia(db, objetivo.datos, usuario_id, verificar_sustituta=False)
        plan.existentes[creada.codigo] = creada
        return creada

    if existente.proveedor_id != objetivo.datos.proveedor_id:
        before, after = {"proveedor_id": existente.proveedor_id}, {"proveedor_id": objetivo.datos.proveedor_id}
        existente.proveedor_id = objetivo.datos.proveedor_id
        auditoria.diff_and_audit(db, "referencia", existente.id, usuario_id, before, after)
    await maestros.update_referencia(
        db, existente, ReferenciaUpdate(**_campos_de_reemplazo(objetivo)), usuario_id,
        verificar_sustituta=False,
    )
    if objetivo.activa and not existente.activa:
        existente.activa = True
        auditoria.audit_reactivate(db, "referencia", existente.id, usuario_id)
    return existente


async def aplicar(db, plan: Plan, resumen: ResumenReemplazo, usuario_id: Optional[uuid.UUID]) -> None:
    """Ejecuta el plan en la transacción del caller (sin `commit`). Orden:
    escribir cada fila (crear/actualizar/mover), enlazar las sustitutas que son
    otra fila del archivo, quitar los vínculos que el movimiento dejó cruzados
    y desactivar las ausentes. Nunca borra."""
    pendientes: List[Tuple[Referencia, str]] = []
    for objetivo in plan.objetivos:
        referencia = await _escribir_fila(db, plan, objetivo, usuario_id)
        if objetivo.sustituta_en_archivo:
            pendientes.append((referencia, objetivo.sustituta_en_archivo))

    if pendientes:
        await db.flush()
        for referencia, codigo_sustituta in pendientes:
            sustituta = plan.existentes[codigo_sustituta]
            await maestros.update_referencia(
                db, referencia, ReferenciaUpdate(sustituida_por=sustituta.id), usuario_id,
                verificar_sustituta=False,
            )

    avisos: List[str] = []
    for apuntadora, destino in plan.vinculos_cruzados:
        maestros.quitar_vinculo_sustituta(db, apuntadora, destino, usuario_id, avisos)

    for referencia in plan.inactivar:
        referencia.activa = False
        auditoria.audit_deactivate(db, "referencia", referencia.id, usuario_id)

    auditoria.audit_reemplazo_masivo(db, usuario_id, texto_auditoria(resumen))
