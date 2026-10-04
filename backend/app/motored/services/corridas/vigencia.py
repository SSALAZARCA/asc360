"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S5a, ADR-6/ADR-12,
decisiones #14/#16): preflight de la corrida.

Antes de calcular nada verifica, de forma global para todas las sucursales:

- las ventas de los seis meses cerrados están cubiertas por cargas
  aplicadas (E-CORRIDA-001) y existe el maestro de referencias (008);
- inventario, backorder, facturas e ingresos existen y no son más viejos que
  SU límite (E-CORRIDA-002..007). Un límite por tipo, ajustable por el
  administrador; sólo mueve la compuerta, nunca el cálculo;
- la demanda perdida ausente es un aviso (A-CORRIDA-101), nunca un bloqueo;
- el modo efectivo del mes en curso, con `resolver_mes_en_curso` del motor
  (A-CORRIDA-105/106). El mes en curso nunca bloquea.

Cada corrida registra, por tipo, la carga usada, la fecha usada, su
antigüedad, el límite y la fuente del límite (`seleccion_datos`, decisión
#16). El bloque viaja también dentro del error, para que un rechazo diga qué
tan viejo era cada dato.

`evaluar_vigencia` es puro; `cargar_hechos` hace la lectura. Nadie llama a
este módulo todavía: lo conecta la creación de la corrida (S6a).
"""
import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import select

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.services.corridas import codigos
from app.motored.services.corridas.parametros_corrida import ParametrosCorrida
from app.motored.services.motor import mes_en_curso as mes
from app.motored.services.motor.tipos import Advertencia
from app.motored.services.reloj import hoy_bogota

ESTADO_APLICADO = "APLICADO"
MESES_CERRADOS = 6

_TIPOS_PREFLIGHT = (
    "VENTAS", "INVENTARIO", "BACKORDER", "FACTURAS_PEDIDOS",
    "INGRESOS_FACTURAS",
)
# tipo de vigencia -> (tipo de carga, nombre para el usuario,
# código si falta, código si es viejo, ¿fecha = periodo declarado?)
_TIPOS = {
    "inventario": (
        "INVENTARIO", "inventario", codigos.E_CORRIDA_INVENTARIO_AUSENTE,
        codigos.E_CORRIDA_INVENTARIO_VIEJO, True),
    "backorder": (
        "BACKORDER", "backorder", codigos.E_CORRIDA_BACKORDER_AUSENTE,
        codigos.E_CORRIDA_BACKORDER_VIEJO, True),
    "facturas": (
        "FACTURAS_PEDIDOS", "facturas de pedidos",
        codigos.E_CORRIDA_FACTURAS_AUSENTE_O_VIEJA,
        codigos.E_CORRIDA_FACTURAS_AUSENTE_O_VIEJA, False),
    "ingresos": (
        "INGRESOS_FACTURAS", "ingresos de facturas",
        codigos.E_CORRIDA_INGRESOS_AUSENTE_O_VIEJO,
        codigos.E_CORRIDA_INGRESOS_AUSENTE_O_VIEJO, False),
}
_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
_SIN_FECHA = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class CargaVista:
    """Una carga tal como la ve el preflight."""

    carga_id: UUID
    tipo: str
    estado: str
    periodo_desde: Optional[date]
    periodo_hasta: Optional[date]
    aplicado_en: Optional[datetime]
    fecha_max_detectada: Optional[date]


@dataclass(frozen=True)
class HechosVigencia:
    cargas: Tuple[CargaVista, ...]
    hay_referencias: bool
    hay_demanda_perdida: bool


@dataclass(frozen=True)
class ResultadoVigencia:
    antiguedad: Mapping[str, Mapping[str, Any]]
    mes_en_curso: mes.ResolucionMesEnCurso
    seleccion_datos: Mapping[str, Any]
    advertencias: Tuple[Advertencia, ...]
    cargas_usadas: Mapping[str, Tuple[UUID, ...]]


class ErrorVigencia(Exception):
    """Preflight rechazado: `codigo` es el primer error, `detalle` lleva el
    bloque de antigüedades y la lista completa de errores."""

    def __init__(self, errores: List[Dict[str, str]], antiguedad: Mapping):
        self.codigo = errores[0]["codigo"]
        self.mensaje = errores[0]["mensaje"]
        self.detalle = {"antiguedad": antiguedad, "errores": errores}
        super().__init__(self.mensaje)


def _error(codigo: str, **datos) -> Dict[str, str]:
    return {"codigo": codigo, "mensaje": codigos.mensaje(codigo, **datos)}


# --- Ventas de los seis meses cerrados --------------------------------------


def _mes_anterior(anio: int, mes_: int, atras: int) -> Tuple[int, int]:
    indice = anio * 12 + (mes_ - 1) - atras
    return indice // 12, indice % 12 + 1


def meses_cerrados(fecha_corte: date) -> List[date]:
    """Primer día de cada uno de los seis meses cerrados, del más viejo."""
    return [
        date(*_mes_anterior(fecha_corte.year, fecha_corte.month, atras), 1)
        for atras in range(MESES_CERRADOS, 0, -1)
    ]


def _ultimo_dia(primero: date) -> date:
    return primero.replace(
        day=calendar.monthrange(primero.year, primero.month)[1])


def _unir(intervalos: Sequence[Tuple[date, date]]):
    """Une intervalos que se solapan o son contiguos."""
    unidos: List[List[date]] = []
    for desde, hasta in sorted(intervalos):
        if unidos and desde <= unidos[-1][1] + timedelta(days=1):
            unidos[-1][1] = max(unidos[-1][1], hasta)
        else:
            unidos.append([desde, hasta])
    return unidos


def _meses_sin_cubrir(vivas, meses: Sequence[date]) -> List[date]:
    unidos = _unir([
        (c.periodo_desde, c.periodo_hasta) for c in vivas
        if c.tipo == "VENTAS" and c.periodo_desde and c.periodo_hasta
    ])
    return [
        primero for primero in meses
        if not any(d <= primero and _ultimo_dia(primero) <= h
                   for d, h in unidos)
    ]


def _nombre_mes(primero: date) -> str:
    return f"{_MESES[primero.month - 1]} de {primero.year}"


def _ventas_usadas(vivas, meses: Sequence[date], fecha_corte: date):
    """Cargas de ventas que tocan la ventana cerrada o el mes en curso."""
    fin = _ultimo_dia(fecha_corte.replace(day=1))
    return tuple(
        c.carga_id for c in vivas
        if c.tipo == "VENTAS" and c.periodo_desde and c.periodo_hasta
        and c.periodo_desde <= fin and c.periodo_hasta >= meses[0]
    )


# --- Vigencia por tipo de dato ----------------------------------------------


def _fecha_bogota(instante: datetime) -> date:
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return hoy_bogota(instante)


def _elegir(vivas, tipo_carga: str, fecha_corte: date, por_periodo: bool):
    """`(carga, fecha usada)` o `(None, None)`.

    INVENTARIO/BACKORDER: la foto con `periodo_desde` más reciente que no
    pase el corte. FACTURAS/INGRESOS (sin período declarado): la última
    carga aplicada, por su fecha de aplicación en Bogotá; una carga
    posterior al corte es válida.
    """
    candidatas = [c for c in vivas if c.tipo == tipo_carga]
    if por_periodo:
        candidatas = [
            c for c in candidatas
            if c.periodo_desde and c.periodo_desde <= fecha_corte]
    else:
        candidatas = [c for c in candidatas if c.aplicado_en]
    if not candidatas:
        return None, None

    def clave(c):
        propia = c.periodo_desde if por_periodo else None
        return (propia or date.min, c.aplicado_en or _SIN_FECHA,
                str(c.carga_id))

    elegida = max(candidatas, key=clave)
    fecha = (elegida.periodo_desde if por_periodo
             else _fecha_bogota(elegida.aplicado_en))
    return elegida, fecha


# API pública para quien necesite las MISMAS reglas fuera del preflight (el
# aviso anticipado de antigüedad): la tabla de tipos y la elección de carga.
TIPOS_ANTIGUEDAD = _TIPOS


def elegir_carga_vigente(vivas, tipo: str, fecha_corte: date):
    """`(carga, fecha usada)` o `(None, None)` del tipo de vigencia `tipo`
    (`inventario`, `backorder`, `facturas`, `ingresos`), con la regla exacta
    del preflight. `vivas` son las cargas APLICADAS."""
    espec = _TIPOS[tipo]
    return _elegir(vivas, espec[0], fecha_corte, espec[4])


def _limite(params: ParametrosCorrida, tipo: str) -> Tuple[int, Any]:
    fuente = params.snapshot["limites_antiguedad"][tipo]["fuente"]
    return params.limites_antiguedad[tipo], fuente


def _revisar_tipo(vivas, fecha_corte: date, params, tipo: str):
    """`(entrada del bloque, error o None, carga usada o None)`."""
    tipo_carga, nombre, cod_falta, cod_viejo, por_periodo = _TIPOS[tipo]
    limite, fuente = _limite(params, tipo)
    carga, fecha = _elegir(vivas, tipo_carga, fecha_corte, por_periodo)
    edad = None if fecha is None else max(0, (fecha_corte - fecha).days)
    entrada = {
        "carga_id": None if carga is None else str(carga.carga_id),
        "fecha_usada": None if fecha is None else fecha.isoformat(),
        "antiguedad_dias": edad,
        "limite_dias": limite,
        "fuente_limite": fuente,
    }
    if edad is not None and edad <= limite:
        return entrada, None, carga
    codigo = cod_falta if edad is None else cod_viejo
    error = {
        "codigo": codigo,
        "mensaje": codigos.mensaje_vigencia(codigo, nombre, edad, limite),
    }
    return entrada, error, carga


# --- Mes en curso ------------------------------------------------------------


def _bloque_mes_en_curso(params, resolucion, cubren, ultima) -> dict:
    efectivo = resolucion.mes_en_curso
    aviso = resolucion.advertencia
    return {
        "modo_configurado": params.modo_mes_en_curso,
        "modo_efectivo": "EXCLUIDO" if efectivo is None else efectivo.modo,
        "d": None if efectivo is None else efectivo.dias_transcurridos,
        "D": None if efectivo is None else efectivo.dias_del_mes,
        "w0": None if efectivo is None else str(mes.peso_m0(efectivo)),
        "fecha_ultima_venta_m0": None if ultima is None
        else ultima.isoformat(),
        "carga_ids": [str(c.carga_id) for c in cubren],
        "motivo": None if aviso is None else aviso.codigo,
    }


def _resolver_mes_en_curso(vivas, fecha_corte: date, params):
    """Modo efectivo de M0 y su bloque de `seleccion_datos`."""
    primero = fecha_corte.replace(day=1)
    fin = _ultimo_dia(primero)
    cubren = [
        c for c in vivas
        if c.tipo == "VENTAS" and c.periodo_desde and c.periodo_hasta
        and c.periodo_desde <= fin and c.periodo_hasta >= primero
    ]
    fechas = [c.fecha_max_detectada for c in cubren
              if c.fecha_max_detectada]
    ultima = max(fechas) if fechas else None
    resolucion = mes.resolver_mes_en_curso(
        params.modo_mes_en_curso, fecha_corte, ultima,
        params.tope_mes_en_curso, params.min_dias_mes_en_curso)
    return resolucion, _bloque_mes_en_curso(
        params, resolucion, cubren, ultima)


# --- Preflight ---------------------------------------------------------


def evaluar_vigencia(
    hechos: HechosVigencia, fecha_corte: date, params: ParametrosCorrida,
) -> ResultadoVigencia:
    """Preflight puro. Falla con `ErrorVigencia` antes de calcular nada."""
    vivas = [c for c in hechos.cargas if c.estado == ESTADO_APLICADO]
    meses = meses_cerrados(fecha_corte)
    errores: List[Dict[str, str]] = []
    sin_cubrir = _meses_sin_cubrir(vivas, meses)
    if sin_cubrir:
        errores.append(_error(
            codigos.E_CORRIDA_VENTAS_SIN_CUBRIR,
            mes=", ".join(_nombre_mes(m) for m in sin_cubrir)))
    if not hechos.hay_referencias:
        errores.append(
            _error(codigos.E_CORRIDA_MAESTRO_REFERENCIAS_AUSENTE))
    antiguedad: Dict[str, Any] = {}
    usadas: Dict[str, Tuple[UUID, ...]] = {
        "ventas": _ventas_usadas(vivas, meses, fecha_corte)}
    for tipo in _TIPOS:
        entrada, error, carga = _revisar_tipo(
            vivas, fecha_corte, params, tipo)
        antiguedad[tipo] = entrada
        if error:
            errores.append(error)
        if carga is not None:
            usadas[tipo] = (carga.carga_id,)
    if errores:
        raise ErrorVigencia(errores, antiguedad)
    return _resultado(
        hechos, vivas, fecha_corte, params, meses, antiguedad, usadas)


def _resultado(hechos, vivas, fecha_corte, params, meses, antiguedad,
               usadas) -> ResultadoVigencia:
    resolucion, bloque = _resolver_mes_en_curso(vivas, fecha_corte, params)
    avisos: List[Advertencia] = []
    if not hechos.hay_demanda_perdida:
        avisos.append(Advertencia(
            codigos.A_CORRIDA_DEMANDA_PERDIDA_AUSENTE,
            codigos.mensaje(codigos.A_CORRIDA_DEMANDA_PERDIDA_AUSENTE)))
    if resolucion.advertencia is not None:
        avisos.append(resolucion.advertencia)
    seleccion = {
        "antiguedad": antiguedad,
        "cortes": {
            tipo: antiguedad[tipo]["fecha_usada"]
            for tipo in ("inventario", "backorder")},
        "meses_cerrados": [m.strftime("%Y-%m") for m in meses],
        "mes_en_curso": bloque,
        "cargas_usadas": {
            tipo: [str(i) for i in ids] for tipo, ids in usadas.items()},
    }
    return ResultadoVigencia(
        antiguedad, resolucion, seleccion, tuple(avisos), usadas)


# --- Lectura -----------------------------------------------------------


def _fecha_iso(texto: Optional[str]) -> Optional[date]:
    return None if not texto else date.fromisoformat(texto[:10])


async def cargar_hechos(db, fecha_corte: date) -> HechosVigencia:
    """Tres lecturas acotadas: las cargas aplicadas de los cinco tipos del
    preflight (nunca las cabeceras del bot de demanda perdida, que son
    cientos de miles) y dos existencias."""
    cargas = await db.execute(
        select(
            CargaArchivo.id, CargaArchivo.tipo, CargaArchivo.estado,
            CargaArchivo.periodo_desde, CargaArchivo.periodo_hasta,
            CargaArchivo.aplicado_en,
            CargaArchivo.log["fecha_max_detectada"].astext.label(
                "fecha_max"),
        ).where(
            CargaArchivo.estado == ESTADO_APLICADO,
            CargaArchivo.tipo.in_(_TIPOS_PREFLIGHT),
        )
    )
    referencias = await db.execute(
        select(Referencia.id)
        .join(Proveedor, Proveedor.id == Referencia.proveedor_id)
        .where(Proveedor.es_principal.is_(True)).limit(1)
    )
    perdida = await db.execute(
        select(CargaArchivo.id).where(
            CargaArchivo.tipo == "DEMANDA_PERDIDA",
            CargaArchivo.estado == ESTADO_APLICADO).limit(1)
    )
    vistas = tuple(
        CargaVista(
            carga_id=f.id, tipo=f.tipo, estado=f.estado,
            periodo_desde=f.periodo_desde, periodo_hasta=f.periodo_hasta,
            aplicado_en=f.aplicado_en,
            fecha_max_detectada=_fecha_iso(f.fecha_max),
        ) for f in cargas.all()
    )
    return HechosVigencia(
        cargas=vistas,
        hay_referencias=referencias.first() is not None,
        hay_demanda_perdida=perdida.first() is not None,
    )


async def ejecutar_preflight(
    db, fecha_corte: date, params: ParametrosCorrida,
) -> ResultadoVigencia:
    """Lee los hechos y evalúa la vigencia (un solo punto de entrada)."""
    return evaluar_vigencia(
        await cargar_hechos(db, fecha_corte), fecha_corte, params)
