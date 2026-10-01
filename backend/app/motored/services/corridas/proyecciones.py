"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S7, ADR-9, decisión
#16): proyecciones PURAS de la API de corridas.

Reciben lo que leyó `consultas.py` (la cabecera, las filas por sucursal, el
resumen y las cargas) y arman los diccionarios que la API serializa. Nada de
base de datos ni de HTTP acá, así el alcance por sucursal (T19) se prueba sin
infraestructura:

- la cabecera (`sucursales_total` / `sucursales_procesadas`), el resumen por
  clase, los totales y el progreso se RECALCULAN sobre las sucursales que el
  usuario puede ver: un usuario de SUCURSAL nunca recibe el total de la red,
  el nombre de otra sucursal ni sus valores;
- el snapshot de parámetros se recorta a las sucursales visibles;
- el bloque de antigüedades por tipo de dato (decisión #16) sube al primer
  nivel del detalle, para que aparezca en todo resultado de corrida.

`alcance` es `None` (sin restricción) o el conjunto de sucursales visibles.

Fase 4 (sdd/motored-pedidos-ui, B2): la línea y el detalle suman lo que el
comprador edita (`extras_linea`: valor sugerido, aviso de empaque y última
edición; `resumen_a_pedir`: el resumen por clase sobre `pedido_final`) SIN
tocar las cifras del sugerido, que siguen siendo las del motor.

Fase 4 (B3a): cada sucursal del detalle suma el estado de su pedido, lo que se
va a pedir, su último evento y las acciones que admite (`acciones_de`), y el
detalle y la lista traen el resumen de pedidos ("3 de 47 enviadas").
"""
import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Tuple,
)
from uuid import UUID

from app.motored.services.corridas import codigos, estados, valores
from app.motored.services.motor.resumen import CLASE_TOTAL

Alcance = Optional[FrozenSet[UUID]]

_SEIS_DECIMALES = Decimal("0.000001")
_ABC, _FMS = "ABCD", "FMS"


# --- Nota y snapshot --------------------------------------------------------


def nota_de(log: Optional[Iterable[Mapping[str, Any]]]) -> Optional[str]:
    """La nota libre del POST: vive en el evento CREADA del `log`."""
    for evento in log or ():
        if evento.get("evento") == "CREADA":
            return evento.get("nota")
    return None


def recortar_snapshot(
    snapshot: Optional[Mapping[str, Any]], alcance: Alcance,
) -> Dict[str, Any]:
    """El snapshot de parámetros; con alcance, sólo los valores por sucursal
    de las visibles (los demás llevan ids de sucursales ajenas)."""
    if snapshot is None:
        return {}
    if alcance is None:
        return dict(snapshot)
    propias = {str(sucursal_id) for sucursal_id in alcance}
    por_sucursal = snapshot.get("dias_entre_pedidos_por_sucursal") or {}
    return {
        **snapshot,
        "dias_entre_pedidos_por_sucursal": {
            clave: valor for clave, valor in por_sucursal.items()
            if clave in propias},
    }


# --- Resumen por clase ------------------------------------------------------


def _orden_clase(clase: str):
    """AF, AM, AS, BF, ..., DS (el orden del Excel), luego las clases raras
    y TOTAL al final."""
    if clase == CLASE_TOTAL:
        return (2, 0, 0, clase)
    if len(clase) == 2 and clase[0] in _ABC and clase[1] in _FMS:
        return (0, _ABC.index(clase[0]), _FMS.index(clase[1]), clase)
    return (1, 0, 0, clase)


def _peso(unidades: Decimal, total: Decimal) -> Decimal:
    if not total:
        return Decimal(0)
    return (unidades / total).quantize(_SEIS_DECIMALES, ROUND_HALF_UP)


def resumen_por_clase(filas: Iterable[Any]) -> List[Dict[str, Any]]:
    """Suma cada clase sobre las filas dadas y recalcula el peso sobre el
    total de ESAS filas (las visibles)."""
    acumulado: Dict[str, List[Any]] = {}
    for fila in filas:
        suma = acumulado.setdefault(fila.clase, [Decimal(0), 0, Decimal(0)])
        suma[0] += fila.unidades
        suma[1] += fila.referencias
        suma[2] += fila.valor
    total = acumulado.get(CLASE_TOTAL, [Decimal(0)])[0]
    return [
        {"sucursal_id": None, "clase": clase, "unidades": unidades,
         "referencias": referencias, "valor": valor,
         "porcentaje_peso": _peso(unidades, total)}
        for clase, (unidades, referencias, valor) in sorted(
            acumulado.items(), key=lambda par: _orden_clase(par[0]))
    ]


def totales(por_clase: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Unidades, referencias y valor de la fila TOTAL agregada."""
    for fila in por_clase:
        if fila["clase"] == CLASE_TOTAL:
            return {"unidades": fila["unidades"],
                    "referencias": fila["referencias"],
                    "valor": fila["valor"]}
    return {"unidades": Decimal(0), "referencias": 0, "valor": Decimal(0)}


def _resumen_por_sucursal(resumen, sucursales) -> List[Dict[str, Any]]:
    orden = {s.sucursal_id: s.orden for s in sucursales}
    filas = sorted(
        resumen,
        key=lambda f: (orden.get(f.sucursal_id, 10 ** 9),
                       _orden_clase(f.clase)))
    return [
        {"sucursal_id": f.sucursal_id, "clase": f.clase,
         "unidades": f.unidades, "referencias": f.referencias,
         "valor": f.valor, "porcentaje_peso": f.porcentaje_peso}
        for f in filas]


def _sumar_por_clase(filas: Iterable[Any]) -> Dict[Any, Dict[str, list]]:
    """`{sucursal_id: {clase: [unidades, referencias, valor]}}`."""
    sumas: Dict[Any, Dict[str, list]] = {}
    for fila in filas:
        suma = sumas.setdefault(fila.sucursal_id, {}).setdefault(
            fila.clase, [Decimal(0), 0, Decimal(0)])
        suma[0] += fila.unidades
        suma[1] += fila.referencias
        suma[2] += fila.valor
    return sumas


def _filas_de_sucursal(sucursal_id, clases, total) -> List[Dict[str, Any]]:
    """Las filas de una sucursal (clases en el orden del Excel y TOTAL)."""
    pares = sorted(
        [*clases.items(), (CLASE_TOTAL, total)],
        key=lambda par: _orden_clase(par[0]))
    return [
        {"sucursal_id": sucursal_id, "clase": clase, "unidades": unidades,
         "referencias": refs, "valor": valor,
         "porcentaje_peso": _peso(unidades, total[0])}
        for clase, (unidades, refs, valor) in pares]


def resumen_a_pedir(
    filas: Iterable[Any], sucursales: Iterable[Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """El resumen por clase de lo que se va a PEDIR (`pedido_final`), con la
    misma forma que `resumen`: una fila por sucursal y clase, más su fila
    TOTAL con el peso recalculado, y los totales de lo visible.

    `filas` trae `sucursal_id, clase, unidades, referencias, valor` ya
    agrupados por la consulta; sólo lo visible llega hasta acá."""
    orden = {s.sucursal_id: s.orden for s in sucursales}
    sumas = _sumar_por_clase(filas)
    salida: List[Dict[str, Any]] = []
    general = [Decimal(0), 0, Decimal(0)]
    for sucursal_id in sorted(sumas, key=lambda i: orden.get(i, 10 ** 9)):
        clases = sumas[sucursal_id]
        total = [sum(c[i] for c in clases.values()) for i in range(3)]
        salida += _filas_de_sucursal(sucursal_id, clases, total)
        general = [general[i] + total[i] for i in range(3)]
    return salida, {
        "unidades": general[0], "referencias": general[1],
        "valor": general[2]}


# --- Línea: lo que agrega la edición (F4, B2) -------------------------------


class UltimaEdicion(NamedTuple):
    """La última fila del historial de una línea (quién, cuándo, motivo)."""

    usuario: str
    creado_en: datetime.datetime
    motivo: str


def extras_linea(
    fila: Any, ultima: Optional[UltimaEdicion],
) -> Dict[str, Any]:
    """Los campos de `LineaRead` que no son columnas: el valor del
    sugerido, el aviso de empaque y las marcas de edición.

    `editada` es "la cantidad difiere del sugerido": volver al sugerido la
    apaga, pero `editado_por`/`editado_en` siguen diciendo quién tocó la
    línea por última vez (el historial es de sólo inserción)."""
    return {
        "valor_sugerido": valores.valor_sugerido(fila),
        "fuera_de_empaque": valores.fuera_de_empaque(
            fila.pedido_final, fila.unidad_empaque),
        "editada": (
            fila.pedido_final is not None
            and fila.pedido_final != fila.pedido_sugerido),
        "editado_por": None if ultima is None else ultima.usuario,
        "editado_en": None if ultima is None else ultima.creado_en,
        "motivo_edicion": None if ultima is None else ultima.motivo,
    }


# --- Pedido por tienda (F4, B3a) -------------------------------------------


class UltimoEvento(NamedTuple):
    """El último `pedido_evento` de una tienda (quién y cuándo)."""

    evento: str
    usuario: Optional[str]
    creado_en: datetime.datetime


def acciones_de(corrida, estado_pedido: Optional[str]) -> Dict[str, bool]:
    """Qué puede hacer el comprador con el pedido de una tienda, según el
    estado del pedido y el de la corrida (el rol ya lo filtró la API).

    Nada en un escenario ni en una corrida cuyo cálculo no terminó; una
    corrida invalidada sólo deja reabrir (devolver a BORRADOR)."""
    operable = (
        not corrida.es_escenario and corrida.estado in estados.CALCULADAS)
    abierta = operable and not corrida.invalidada
    borrador = estado_pedido == estados.PEDIDO_BORRADOR
    return {
        "cerrar": abierta and borrador,
        "reabrir": operable and estado_pedido == estados.PEDIDO_CERRADO,
        "editar": abierta and borrador,
        "enviar": abierta and estado_pedido == estados.PEDIDO_CERRADO,
        "corregir_envio": operable and estado_pedido == estados.PEDIDO_ENVIADO,
    }


def unidades_valor_a_pedir(
    filas: Iterable[Any],
) -> Dict[Any, Tuple[Decimal, Decimal]]:
    """`{sucursal_id: (unidades, valor)}` a pedir, sumando las clases."""
    sumas: Dict[Any, List[Decimal]] = {}
    for fila in filas:
        suma = sumas.setdefault(fila.sucursal_id, [Decimal(0), Decimal(0)])
        suma[0] += fila.unidades
        suma[1] += fila.valor
    return {clave: (u, v) for clave, (u, v) in sumas.items()}


def resumen_de_pedidos(
    sucursales: Iterable[Any], unidades: Mapping[Any, Decimal],
) -> Dict[str, int]:
    """El resumen de pedidos de las tiendas OK visibles: cuántas hay y
    cuántas en cada estado, y `sin_pedido`: las que no tienen nada para
    pedir (suma 0 o sin líneas)."""
    ok = [s for s in sucursales if s.estado == estados.SUC_OK]

    def en(estado: str) -> int:
        return sum(1 for s in ok if s.estado_pedido == estado)

    return {
        "total": len(ok), "borrador": en(estados.PEDIDO_BORRADOR),
        "cerrados": en(estados.PEDIDO_CERRADO),
        "enviados": en(estados.PEDIDO_ENVIADO),
        "sin_pedido": sum(
            1 for s in ok if not unidades.get(s.sucursal_id)),
    }


def resumen_de_lista(
    conteos: Optional[Mapping[str, int]],
) -> Dict[str, Optional[int]]:
    """El resumen de la lista: lo agrupado por la consulta (ceros si la
    corrida no tiene tiendas OK). `sin_pedido` sólo lo trae el detalle."""
    base = {"total": 0, "borrador": 0, "cerrados": 0, "enviados": 0}
    return {**base, **(conteos or {}), "sin_pedido": None}


def _ultimo_evento(
    evento: Optional[UltimoEvento],
) -> Optional[Dict[str, Any]]:
    if evento is None:
        return None
    return {"evento": evento.evento, "usuario": evento.usuario,
            "creado_en": evento.creado_en}


def cabecera_tienda(
    corrida, tienda, nombre: str, sic: Optional[str],
    totales_tienda: Mapping[str, Decimal], ultimo: Optional[UltimoEvento],
) -> Dict[str, Any]:
    """La cabecera de la pantalla del pedido de UNA tienda."""
    return {
        "corrida_id": corrida.id, "corrida_codigo": corrida.codigo,
        "fecha_corte": corrida.fecha_corte, "corrida_estado": corrida.estado,
        "es_escenario": corrida.es_escenario,
        "invalidada": corrida.invalidada,
        "sucursal_id": tienda.sucursal_id, "nombre": nombre.strip(),
        "sic": sic, "estado": tienda.estado, "codigo": tienda.codigo,
        "mensaje": tienda.mensaje, "estado_pedido": tienda.estado_pedido,
        "totales": dict(totales_tienda),
        "ultimo_evento": _ultimo_evento(ultimo),
        "acciones": acciones_de(corrida, tienda.estado_pedido),
    }


# --- Piezas comunes ---------------------------------------------------------


def _fila_aviso(sucursal_id, sucursal, aviso: Mapping[str, str]):
    return {"sucursal_id": sucursal_id, "sucursal": sucursal,
            "codigo": aviso["codigo"], "mensaje": aviso["mensaje"]}


def avisos(corrida, sucursales) -> List[Dict[str, Any]]:
    """Avisos de la corrida (preflight), luego los de cada sucursal visible."""
    seleccion = corrida.seleccion_datos or {}
    salida = [
        _fila_aviso(None, None, aviso)
        for aviso in seleccion.get("advertencias", [])]
    for sucursal in sucursales:
        propios = (sucursal.parametros or {}).get("advertencias", [])
        salida.extend(
            _fila_aviso(sucursal.sucursal_id, sucursal.nombre.strip(), aviso)
            for aviso in propios)
    return salida


def _procesadas(sucursales) -> int:
    return sum(1 for s in sucursales if s.estado != estados.SUC_PENDIENTE)


def cabecera(corrida, sucursales) -> Dict[str, Any]:
    """Campos de la lista, con los contadores sobre las sucursales visibles."""
    return {
        "id": corrida.id, "codigo": corrida.codigo,
        "proveedor_id": corrida.proveedor_id,
        "fecha_corte": corrida.fecha_corte, "estado": corrida.estado,
        "es_escenario": corrida.es_escenario, "alcance": corrida.alcance,
        "invalidada": corrida.invalidada,
        "sucursales_total": len(sucursales),
        "sucursales_procesadas": _procesadas(sucursales),
        "nota": nota_de(corrida.log), "created_at": corrida.created_at,
        "terminado_en": corrida.terminado_en,
        "cerrada_en": corrida.cerrada_en,
    }


def item_de_fila(fila) -> Dict[str, Any]:
    """Un renglón de la lista a partir de la fila de `consultas.listar`."""
    return {
        "id": fila.id, "codigo": fila.codigo,
        "proveedor_id": fila.proveedor_id, "fecha_corte": fila.fecha_corte,
        "estado": fila.estado, "es_escenario": fila.es_escenario,
        "alcance": fila.alcance, "invalidada": fila.invalidada,
        "sucursales_total": fila.sucursales_total,
        "sucursales_procesadas": fila.sucursales_procesadas,
        "nota": fila.nota, "created_at": fila.created_at,
        "terminado_en": fila.terminado_en, "cerrada_en": fila.cerrada_en,
    }


def _estado_sucursal(
    s, corrida, a_pedir: Mapping[Any, Tuple[Decimal, Decimal]],
    eventos: Mapping[Any, UltimoEvento],
) -> Dict[str, Any]:
    unidades, valor = a_pedir.get(s.sucursal_id, (Decimal(0), Decimal(0)))
    return {
        "estado_pedido": s.estado_pedido, "unidades_a_pedir": unidades,
        "valor_a_pedir": valor,
        "ultimo_evento": _ultimo_evento(eventos.get(s.sucursal_id)),
        "acciones": acciones_de(corrida, s.estado_pedido),
        "sucursal_id": s.sucursal_id, "nombre": s.nombre.strip(),
        "orden": s.orden, "estado": s.estado, "codigo": s.codigo,
        "mensaje": s.mensaje, "lineas": s.lineas, "excluidas": s.excluidas,
        "unidades": s.unidades, "valor": s.valor,
        "fecha_apertura": s.fecha_apertura, "divisor": s.divisor,
        "dias_empaque": s.dias_empaque, "dias_transito": s.dias_transito,
        "dias_seguridad": s.dias_seguridad,
        "dias_entre_pedidos": s.dias_entre_pedidos, "intentos": s.intentos,
    }


def agrupar_cargas(cargas: Iterable[Any]) -> Dict[str, List[Dict[str, Any]]]:
    """`cargas_usadas` por tipo de carga."""
    usadas: Dict[str, List[Dict[str, Any]]] = {}
    for carga in cargas:
        usadas.setdefault(carga.tipo, []).append({
            "carga_id": carga.id, "nombre_archivo": carga.nombre_archivo,
            "estado": carga.estado, "periodo_desde": carga.periodo_desde,
            "periodo_hasta": carga.periodo_hasta})
    return usadas


# --- Detalle ----------------------------------------------------------------


def armar_detalle(
    corrida, sucursales, resumen, cargas, alcance: Alcance, a_pedir=(),
    eventos: Optional[Mapping[Any, UltimoEvento]] = None,
) -> Dict[str, Any]:
    """El detalle completo de la corrida para quien tiene `alcance`.
    `a_pedir` son las filas por sucursal y clase de `pedido_final` y
    `eventos` el último evento de pedido de cada sucursal."""
    seleccion = corrida.seleccion_datos or {}
    por_clase = resumen_por_clase(resumen)
    pedir, totales_pedir = resumen_a_pedir(a_pedir, sucursales)
    por_sucursal = unidades_valor_a_pedir(a_pedir)
    return {
        **cabecera(corrida, sucursales),
        "pedidos": resumen_de_pedidos(
            sucursales, {k: v[0] for k, v in por_sucursal.items()}),
        "parametros_en_fecha": corrida.parametros_en_fecha,
        "overrides": corrida.overrides,
        "motivo_invalidacion": corrida.motivo_invalidacion,
        "motivo_anulacion": corrida.motivo_anulacion,
        "iniciado_en": corrida.iniciado_en,
        "anulada_en": corrida.anulada_en,
        "intentos": corrida.intentos,
        "cargas_usadas": agrupar_cargas(cargas),
        "parametros": recortar_snapshot(corrida.parametros_snapshot, alcance),
        "antiguedad": seleccion.get("antiguedad", {}),
        "mes_en_curso": seleccion.get("mes_en_curso"),
        "advertencias": avisos(corrida, sucursales),
        "sucursales": [
            _estado_sucursal(s, corrida, por_sucursal, eventos or {})
            for s in sucursales],
        "resumen": _resumen_por_sucursal(resumen, sucursales),
        "resumen_por_clase": por_clase,
        "totales": totales(por_clase),
        "resumen_a_pedir": pedir,
        "totales_a_pedir": totales_pedir,
    }


# --- Progreso ---------------------------------------------------------------


def _actual(corrida, sucursales, alcance: Alcance) -> Optional[str]:
    """Texto `Sucursal 12 de 47 — NOMBRE`. Con alcance no se nombra ninguna:
    sería decir el nombre (y el total) de sucursales que el usuario no ve."""
    if alcance is not None or corrida.estado != estados.CALCULANDO:
        return None
    pendientes = sorted(
        (s for s in sucursales if s.estado == estados.SUC_PENDIENTE),
        key=lambda s: s.orden)
    if not pendientes:
        return None
    primera = pendientes[0]
    nombre = primera.nombre.strip()
    return f"Sucursal {primera.orden} de {len(sucursales)} — {nombre}"


def _error_terminal(corrida) -> List[Dict[str, Any]]:
    """El código que dejó la corrida FALLIDA (E-030 al finalizar, E-031 al
    agotar reintentos), leído del último evento del `log` que lo trae."""
    if corrida.estado != estados.FALLIDA:
        return []
    for evento in reversed(corrida.log or []):
        codigo = evento.get("codigo")
        if codigo:
            mensaje = codigos.CATALOGO.get(codigo, codigo)
            return [{"sucursal_id": None, "sucursal": None,
                     "codigo": codigo, "mensaje": mensaje}]
    return []


def armar_progreso(corrida, sucursales, alcance: Alcance) -> Dict[str, Any]:
    """Estado y avance de la corrida sobre las sucursales visibles."""
    def cuantas(estado: str) -> int:
        return sum(1 for s in sucursales if s.estado == estado)

    errores = _error_terminal(corrida) + [
        {"sucursal_id": s.sucursal_id, "sucursal": s.nombre.strip(),
         "codigo": s.codigo, "mensaje": s.mensaje}
        for s in sucursales if s.estado == estados.SUC_FALLIDA]
    return {
        "estado": corrida.estado,
        "total": len(sucursales),
        "procesadas": _procesadas(sucursales),
        "ok": cuantas(estados.SUC_OK),
        "omitidas": cuantas(estados.SUC_OMITIDA),
        "fallidas": cuantas(estados.SUC_FALLIDA),
        "actual": _actual(corrida, sucursales, alcance),
        "latido_en": corrida.latido_en,
        "intentos": corrida.intentos,
        "errores": errores,
        "advertencias": avisos(corrida, sucursales),
    }
