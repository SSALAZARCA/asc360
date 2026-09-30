"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6a, ADR-3/ADR-4,
decisión #14/#16): persistencia de una sucursal calculada.

Tres piezas:

1. `armar_filas` (PURA) convierte el resultado exacto del motor (`Fraction`)
   en las filas de `corrida_linea`, `corrida_resumen` y `corrida_sucursal`.
   Es el ÚNICO lugar donde se cuantiza, con ROUND_HALF_UP (lejos de cero), y
   la comparten `guardar_sucursal` y la reproducción, así lo escrito y lo
   recalculado se comparan columna a columna.
2. `guardar_sucursal` escribe una sucursal en un solo paso, guardado por
   `corrida.estado = 'CALCULANDO'`: si la corrida se anuló o cerró, no toca
   nada (T18) y el llamador se detiene de forma cooperativa. Es idempotente:
   borra las filas sueltas de un intento anterior antes de insertar.
3. `registrar_cargas` vincula la corrida con las cargas que usó
   (`corrida_carga`, fuente de la guarda de anulación).

Cada línea guarda las entradas CRUDAS propias (antes de la consolidación de
sustituidas) junto a las salidas; `y_recibido` es el stock (V+W+X) que la
línea recibió de sus referencias sustituidas. Lo que la consolidación usó y no
quedó en ninguna fila (una vieja con sólo demanda perdida, o la final en
ceros que recibe stock) se guarda en `corrida_sucursal.parametros` como
`entradas_auxiliares`, para que la reproducción reconstruya el mismo juego de
entradas. Las advertencias de la sucursal (motor + A-CORRIDA-104 derivada de
las banderas de sus líneas) van en `parametros["advertencias"]`.
"""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_resumen import CorridaResumen
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.services.corridas import codigos, estados
from app.motored.services.corridas.cargador import (
    BANDERA_SIN_PRECIO, DatosSucursal)
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.motor.aritmetica import a_fraccion, cuantizar
from app.motored.services.motor.motor import ResultadoSucursal
from app.motored.services.motor.pedido import inventario_efectivo
from app.motored.services.motor.tipos import (
    Advertencia,
    AtributosSucursal,
    EntradaReferencia,
    LineaExcluida,
    LineaPedido,
    NodoMaestro,
)
from app.motored.services.motor.ventana import construir_ventana

# Un INSERT multi-valores lleva ~58 parámetros por línea y asyncpg admite
# 32.767 por sentencia: 300 líneas usan ~17.400.
TAMANO_BLOQUE = 300
MESES = (6, 5, 4, 3, 2, 1)
TIPO_CARGA = {
    "ventas": "VENTAS",
    "inventario": "INVENTARIO",
    "backorder": "BACKORDER",
    "facturas": "FACTURAS_PEDIDOS",
    "ingresos": "INGRESOS_FACTURAS",
}

_SALIDAS = (
    "demanda_perdida", "demanda_perdida_mensualizada", "demanda_prom_simple",
    "venta_m0_proyectada", "demanda_ponderada", "peso_pct", "peso_acum_pct",
    "orden_abc", "clase_abc", "clase_fms", "clase", "meses_con_venta",
    "meses_cobertura", "inventario_final", "y_recibido", "stock_objetivo",
    "pedido_sugerido", "pedido_final", "valor_pedido", "cobertura_final",
    "cobertura_actual", "punto_minimo", "punto_maximo", "estado_quiebre",
    "motivo_exclusion", "sustituta_final_id", "detalle_consolidacion",
)


@dataclass(frozen=True)
class FilasSucursal:
    """Todo lo que una sucursal escribe: líneas (incluidas las excluidas),
    resumen por clase y los valores de su fila de `corrida_sucursal`."""

    lineas: List[Dict[str, Any]]
    resumen: List[Dict[str, Any]]
    sucursal: Dict[str, Any]


def _q(valor: Optional[Fraction], lugares: int) -> Optional[Decimal]:
    return None if valor is None else cuantizar(valor, lugares)


def _texto(valor: Optional[Decimal]) -> Optional[str]:
    return None if valor is None else str(valor)


def bloques(filas: List[Any], tamano: int) -> Iterator[List[Any]]:
    """Trozos consecutivos de `tamano` filas (el último puede ser menor)."""
    for inicio in range(0, len(filas), tamano):
        yield filas[inicio:inicio + tamano]


# --- Entradas crudas: filas y JSON ------------------------------------------


def _fila_entrada(cruda: EntradaReferencia) -> Dict[str, Any]:
    fila: Dict[str, Any] = {
        "referencia_id": cruda.referencia_id,
        "codigo_referencia": cruda.codigo,
        "nombre_parte": cruda.nombre,
        "linea_comercial": cruda.linea_comercial,
        "ultima_fecha_entrada": None,
        "venta_m0": cruda.venta_m0,
        "perdida_m0": cruda.perdida_m0,
        "precio": cruda.precio,
        "unidad_empaque": cruda.unidad_empaque,
        "inventario": cruda.inventario,
        "transito": cruda.transito,
        "backorder": cruda.backorder,
        "ajuste": cruda.ajuste,
    }
    for mes, venta, perdida in zip(MESES, cruda.ventas, cruda.perdidas):
        fila[f"venta_m{mes}"] = venta
        fila[f"perdida_m{mes}"] = perdida
    return fila


def entrada_desde_fila(fila: Any) -> EntradaReferencia:
    """Inversa de `_fila_entrada`: la entrada cruda de una línea guardada."""
    return EntradaReferencia(
        referencia_id=fila.referencia_id,
        codigo=fila.codigo_referencia,
        nombre=fila.nombre_parte,
        linea_comercial=fila.linea_comercial,
        precio=fila.precio,
        unidad_empaque=fila.unidad_empaque,
        ventas=tuple(getattr(fila, f"venta_m{m}") for m in MESES),
        perdidas=tuple(getattr(fila, f"perdida_m{m}") for m in MESES),
        venta_m0=fila.venta_m0,
        perdida_m0=fila.perdida_m0,
        inventario=fila.inventario,
        transito=fila.transito,
        backorder=fila.backorder,
        ajuste=fila.ajuste,
        banderas=frozenset(fila.banderas or ()),
    )


def serializar_entrada(entrada: EntradaReferencia) -> Dict[str, Any]:
    """JSON de una entrada (decimales como texto exacto, nunca floats)."""
    return {
        "referencia_id": str(entrada.referencia_id),
        "codigo": entrada.codigo,
        "nombre": entrada.nombre,
        "linea_comercial": entrada.linea_comercial,
        "precio": _texto(entrada.precio),
        "unidad_empaque": entrada.unidad_empaque,
        "ventas": [str(v) for v in entrada.ventas],
        "perdidas": [str(p) for p in entrada.perdidas],
        "venta_m0": _texto(entrada.venta_m0),
        "perdida_m0": _texto(entrada.perdida_m0),
        "inventario": str(entrada.inventario),
        "transito": str(entrada.transito),
        "backorder": str(entrada.backorder),
        "ajuste": str(entrada.ajuste),
        "banderas": sorted(entrada.banderas),
    }


def _decimal(texto: Optional[str]) -> Optional[Decimal]:
    return None if texto is None else Decimal(texto)


def deserializar_entrada(datos: Mapping[str, Any]) -> EntradaReferencia:
    return EntradaReferencia(
        referencia_id=UUID(datos["referencia_id"]),
        codigo=datos["codigo"],
        nombre=datos["nombre"],
        linea_comercial=datos["linea_comercial"],
        precio=_decimal(datos["precio"]),
        unidad_empaque=datos["unidad_empaque"],
        ventas=tuple(Decimal(v) for v in datos["ventas"]),
        perdidas=tuple(Decimal(p) for p in datos["perdidas"]),
        venta_m0=_decimal(datos["venta_m0"]),
        perdida_m0=_decimal(datos["perdida_m0"]),
        inventario=Decimal(datos["inventario"]),
        transito=Decimal(datos["transito"]),
        backorder=Decimal(datos["backorder"]),
        ajuste=Decimal(datos["ajuste"]),
        banderas=frozenset(datos["banderas"]),
    )


def maestro_a_json(
    maestro: Mapping[UUID, NodoMaestro],
) -> List[Dict[str, Any]]:
    """Maestro de sustitución congelado, ordenado para ser determinista."""
    nodos = sorted(maestro.values(), key=lambda nodo: str(nodo.referencia_id))
    return [
        {"referencia_id": str(nodo.referencia_id), "activa": nodo.activa,
         "sustituida_por": None if nodo.sustituida_por is None
         else str(nodo.sustituida_por)}
        for nodo in nodos
    ]


def maestro_desde_json(
    datos: Optional[Iterable[Mapping[str, Any]]],
) -> Dict[UUID, NodoMaestro]:
    nodos = [
        NodoMaestro(
            UUID(d["referencia_id"]), d["activa"],
            None if d["sustituida_por"] is None
            else UUID(d["sustituida_por"]))
        for d in (datos or ())
    ]
    return {nodo.referencia_id: nodo for nodo in nodos}


# --- Filas de línea ---------------------------------------------------------


def _cantidad(valor: Decimal) -> str:
    """Texto canónico a la escala de las fuentes (2 decimales): la misma
    cantidad da el mismo texto venga del cargador o de la base."""
    return str(cuantizar(a_fraccion(valor), 2))


def _detalle(origenes: Iterable[LineaExcluida]) -> Optional[Dict[str, Any]]:
    """Las referencias sustituidas que la línea absorbió (informativo)."""
    origenes = sorted(origenes, key=lambda o: o.entrada.codigo)
    if not origenes:
        return None
    return {"origenes": [
        {"referencia_id": str(o.entrada.referencia_id),
         "codigo": o.entrada.codigo,
         "inventario": _cantidad(o.entrada.inventario),
         "transito": _cantidad(o.entrada.transito),
         "backorder": _cantidad(o.entrada.backorder)}
        for o in origenes
    ]}


def _salidas(linea: LineaPedido, cruda: EntradaReferencia) -> Dict[str, Any]:
    pedido = _q(linea.pedido, 2)
    recibido = linea.inventario_efectivo - inventario_efectivo(cruda)
    return {
        "demanda_perdida": _q(linea.k_perdida, 6),
        "demanda_perdida_mensualizada": _q(linea.l_ultimo_mes, 6),
        "demanda_prom_simple": _q(linea.m_promedio, 6),
        "venta_m0_proyectada": _q(linea.venta_m0_proyectada, 6),
        "demanda_ponderada": _q(linea.n, 6),
        "peso_pct": _q(linea.peso, 10),
        "peso_acum_pct": _q(linea.acumulado, 10),
        "orden_abc": linea.orden_abc,
        "clase_abc": linea.clase_abc,
        "clase_fms": linea.clase_fms,
        "clase": linea.clase,
        "meses_con_venta": linea.meses_con_venta,
        "meses_cobertura": _q(linea.cobertura, 6),
        "inventario_final": _q(linea.inventario_efectivo, 2),
        "y_recibido": _q(recibido, 2),
        "stock_objetivo": _q(linea.stock_objetivo, 6),
        "pedido_sugerido": pedido,
        "pedido_final": pedido,
        "valor_pedido": _q(linea.valor_pedido, 2),
        "cobertura_final": _q(linea.cobertura_final, 6),
        "cobertura_actual": _q(linea.cobertura_actual, 6),
        "punto_minimo": _q(linea.punto_minimo, 6),
        "punto_maximo": _q(linea.punto_maximo, 6),
        "estado_quiebre": linea.estado_quiebre,
    }


def fila_linea(
    corrida_id: UUID, sucursal_id: UUID, linea: LineaPedido,
    cruda: EntradaReferencia, origenes: Iterable[LineaExcluida] = (),
) -> Dict[str, Any]:
    """Fila de `corrida_linea` de una línea del pedido.

    `cruda` es la entrada PROPIA de la referencia (antes de recibir lo de sus
    sustituidas); `origenes` son las excluidas que le transfirieron.
    """
    return {
        "corrida_id": corrida_id,
        "sucursal_id": sucursal_id,
        **_fila_entrada(cruda),
        **dict.fromkeys(_SALIDAS),
        **_salidas(linea, cruda),
        "banderas": sorted(set(cruda.banderas) | set(linea.advertencias)),
        "detalle_consolidacion": _detalle(origenes),
    }


def fila_excluida(
    corrida_id: UUID, sucursal_id: UUID, excluida: LineaExcluida,
) -> Dict[str, Any]:
    """Fila de una referencia que salió del pedido: sin ningún cálculo."""
    entrada = excluida.entrada
    return {
        "corrida_id": corrida_id,
        "sucursal_id": sucursal_id,
        **_fila_entrada(entrada),
        **dict.fromkeys(_SALIDAS),
        "motivo_exclusion": excluida.motivo,
        "sustituta_final_id": excluida.sustituta_final_id,
        "banderas": sorted(entrada.banderas),
    }


# --- Resumen y fila de la sucursal ------------------------------------------


def _filas_resumen(
    corrida_id: UUID, sucursal_id: UUID, resultado: ResultadoSucursal,
) -> List[Dict[str, Any]]:
    if resultado.estado != estados.SUC_OK:
        return []
    return [
        {"corrida_id": corrida_id, "sucursal_id": sucursal_id,
         "clase": fila.clase, "unidades": _q(fila.unidades, 2),
         "referencias": fila.referencias, "valor": _q(fila.valor, 2),
         "porcentaje_peso": _q(fila.porcentaje_peso, 6)}
        for fila in (*resultado.resumen.filas, resultado.resumen.total)
    ]


def _bucket_operados(sucursal: AtributosSucursal) -> int:
    """Bitmask de los meses cerrados operados: bit 0 = M6 .. bit 5 = M1."""
    ventana = construir_ventana(sucursal.fecha_corte, sucursal.fecha_apertura)
    return sum(1 << i for i, peso in enumerate(ventana.pesos) if peso > 0)


def _dias(valor: Decimal) -> Decimal:
    return cuantizar(a_fraccion(valor), 2)


def _sin_precio(resultado: ResultadoSucursal) -> List[Advertencia]:
    """A-CORRIDA-104 de cada línea del pedido cuya entrada no trae precio."""
    return [
        Advertencia(
            codigos.A_CORRIDA_SIN_PRECIO,
            codigos.mensaje(
                codigos.A_CORRIDA_SIN_PRECIO,
                referencia=linea.entrada.codigo))
        for linea in sorted(
            resultado.lineas, key=lambda ln: ln.entrada.codigo)
        if BANDERA_SIN_PRECIO in linea.entrada.banderas
    ]


def _advertencias(resultado: ResultadoSucursal) -> List[Dict[str, str]]:
    return [
        {"codigo": aviso.codigo, "mensaje": aviso.mensaje}
        for aviso in (*resultado.advertencias, *_sin_precio(resultado))
    ]


def _auxiliares(
    entradas: Iterable[EntradaReferencia], guardadas: set, consolidar: bool,
) -> List[Dict[str, Any]]:
    """Entradas que la consolidación pudo usar y no tienen fila propia."""
    if not consolidar:
        return []
    return [
        serializar_entrada(entrada)
        for entrada in sorted(entradas, key=lambda e: e.codigo)
        if entrada.referencia_id not in guardadas
    ]


def _coberturas(resultado: ResultadoSucursal) -> Dict[str, str]:
    return {
        linea.clase: str(linea.cobertura)
        for linea in sorted(resultado.lineas, key=lambda ln: ln.clase)
    }


def _valores_sucursal(
    sucursal: AtributosSucursal, resultado: ResultadoSucursal,
    excluidas: int, auxiliares: List[Dict[str, Any]],
) -> Dict[str, Any]:
    omitida = resultado.estado == estados.SUC_OMITIDA
    aviso = resultado.advertencias[0] if omitida else None
    total = resultado.resumen.total
    return {
        "estado": resultado.estado,
        "codigo": None if aviso is None else aviso.codigo,
        "mensaje": None if aviso is None else aviso.mensaje,
        "fecha_apertura": sucursal.fecha_apertura,
        "divisor": resultado.divisor,
        "buckets_operados": _bucket_operados(sucursal),
        "dias_empaque": _dias(sucursal.dias_empaque),
        "dias_transito": _dias(sucursal.dias_transito),
        "dias_seguridad": _dias(sucursal.dias_seguridad),
        "dias_entre_pedidos": _dias(sucursal.dias_entre_pedidos),
        "parametros": {
            "nombre": sucursal.nombre,
            "advertencias": _advertencias(resultado),
            "entradas_auxiliares": auxiliares,
        },
        "coberturas": _coberturas(resultado),
        "lineas": len(resultado.lineas),
        "excluidas": excluidas,
        "unidades": _q(total.unidades, 2),
        "valor": _q(total.valor, 2),
    }


def armar_filas(
    corrida_id: UUID, sucursal: AtributosSucursal,
    entradas: Iterable[EntradaReferencia], resultado: ResultadoSucursal,
    *, consolidar: bool,
) -> FilasSucursal:
    """Filas de una sucursal calculada; pura y determinista.

    `entradas` son las del cargador (crudas, antes de consolidar).
    """
    entradas = list(entradas)
    crudas = {e.referencia_id: e for e in entradas}
    origenes = defaultdict(list)
    for excluida in resultado.excluidas:
        if excluida.sustituta_final_id is not None:
            origenes[excluida.sustituta_final_id].append(excluida)
    sucursal_id = sucursal.sucursal_id
    lineas = [
        fila_linea(
            corrida_id, sucursal_id, linea,
            crudas[linea.entrada.referencia_id],
            origenes.get(linea.entrada.referencia_id, ()))
        for linea in resultado.lineas
    ]
    lineas += [
        fila_excluida(corrida_id, sucursal_id, excluida)
        for excluida in resultado.excluidas
    ]
    guardadas = {fila["referencia_id"] for fila in lineas}
    return FilasSucursal(
        lineas=lineas,
        resumen=_filas_resumen(corrida_id, sucursal_id, resultado),
        sucursal=_valores_sucursal(
            sucursal, resultado, len(resultado.excluidas),
            _auxiliares(entradas, guardadas, consolidar)),
    )


# --- Escritura --------------------------------------------------------------


async def _guardia(db, corrida_id: UUID) -> None:
    """Sólo una corrida CALCULANDO admite escrituras (T18); de paso late."""
    resultado = await db.execute(
        update(Corrida)
        .where(Corrida.id == corrida_id,
               Corrida.estado == estados.CALCULANDO)
        .values(latido_en=func.now())
        .returning(Corrida.id)
        .execution_options(synchronize_session=False))
    if resultado.first() is None:
        raise ErrorCorrida(
            codigos.E_CORRIDA_ESTADO_NO_ADMITE,
            codigos.mensaje(
                codigos.E_CORRIDA_ESTADO_NO_ADMITE,
                estado=f"no es {estados.CALCULANDO}"))


async def _actualizar_sucursal(
    db, corrida_id: UUID, sucursal_id: UUID, valores: Dict[str, Any],
) -> None:
    await db.execute(
        update(CorridaSucursal)
        .where(CorridaSucursal.corrida_id == corrida_id,
               CorridaSucursal.sucursal_id == sucursal_id)
        .values(
            **valores,
            intentos=CorridaSucursal.intentos + 1,
            iniciado_en=func.coalesce(
                CorridaSucursal.iniciado_en, func.now()),
            terminado_en=func.now())
        .execution_options(synchronize_session=False))


async def _actualizar_progreso(db, corrida_id: UUID) -> None:
    """Procesadas = sucursales que dejaron de estar PENDIENTES (idempotente
    ante el reintento de una misma sucursal)."""
    terminadas = (
        select(func.count())
        .select_from(CorridaSucursal)
        .where(CorridaSucursal.corrida_id == corrida_id,
               CorridaSucursal.estado != estados.SUC_PENDIENTE)
        .scalar_subquery())
    await db.execute(
        update(Corrida)
        .where(Corrida.id == corrida_id)
        .values(sucursales_procesadas=terminadas)
        .execution_options(synchronize_session=False))


async def guardar_sucursal(
    db, corrida_id: UUID, datos: DatosSucursal, resultado: ResultadoSucursal,
    *, consolidar: bool = False,
) -> None:
    """Escribe una sucursal calculada (ver el docstring del módulo).

    Levanta `ErrorCorrida` E-CORRIDA-040 sin tocar nada si la corrida ya no
    está CALCULANDO.
    """
    filas = armar_filas(
        corrida_id, datos.atributos, datos.entradas, resultado,
        consolidar=consolidar)
    sucursal_id = datos.atributos.sucursal_id
    await _guardia(db, corrida_id)
    for tabla in (CorridaLinea, CorridaResumen):
        await db.execute(delete(tabla).where(
            tabla.corrida_id == corrida_id, tabla.sucursal_id == sucursal_id))
    for bloque in bloques(filas.lineas, TAMANO_BLOQUE):
        await db.execute(insert(CorridaLinea).values(bloque))
    if filas.resumen:
        await db.execute(insert(CorridaResumen).values(filas.resumen))
    await _actualizar_sucursal(db, corrida_id, sucursal_id, filas.sucursal)
    await _actualizar_progreso(db, corrida_id)


async def marcar_sucursal_fallida(
    db, corrida_id: UUID, sucursal_id: UUID, codigo: str, mensaje: str,
) -> None:
    """Deja la sucursal FALLIDA con su error; no se reintenta (decisión de
    falla parcial: las demás siguen)."""
    await _guardia(db, corrida_id)
    await _actualizar_sucursal(db, corrida_id, sucursal_id, {
        "estado": estados.SUC_FALLIDA, "codigo": codigo,
        "mensaje": mensaje})
    await _actualizar_progreso(db, corrida_id)


def registrar_cargas(
    db, corrida_id: UUID, usadas: Mapping[str, Iterable[UUID]],
) -> None:
    """Vincula la corrida con las cargas que usó, por su tipo de carga."""
    for clave, carga_ids in usadas.items():
        for carga_id in carga_ids:
            db.add(CorridaCarga(
                corrida_id=corrida_id, carga_id=carga_id,
                tipo=TIPO_CARGA[clave]))
