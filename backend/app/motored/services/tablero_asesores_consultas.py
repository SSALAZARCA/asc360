"""
Tablero de asesores (feature motored-tablero-asesores, T4): consultas SQL.

Todo se calcula con GROUP BY en PostgreSQL: con ~1M de lineas en 6 meses nunca
se cargan lineas en Python, solo las filas ya agregadas (un cubo por fila del
tablero, mes, linea y banderas, mas facturas y clientes). El reparto en filas y
los indicadores viven en `tablero_asesores.py` (puro, sin base).

Reglas que comparten TODAS las consultas (`_desde_ventas`):
- Solo cargas VENTAS no ANULADAS (anular nunca borra el detalle).
- `fecha` dentro de rangos [inicio, fin) unidos con OR (uno por grupo de meses
  consecutivos), las sucursales elegidas y el filtro HMCL (`incluir`/`excluir`/
  `solo`; el cubo lo aplica en Python para conservar la venta con HMCL).
- Venta de una linea = `valor_bruto - valor_descuentos`.
- Linea = `referencia.linea_comercial` (recortada, mayusculas, sin tildes).
- Cliente normalizado con la MISMA regla que `normalizar_nit` (ver
  `_expr_cliente_norm`), para cruzar con HMCL y con la lista Tecnired.
- Fila del tablero (`_expr_clave`): una persona por asesor de repuestos (una
  persona = una CEDULA: todos los nombres del ERP con la misma cedula son una
  fila; sin cedula, una fila por nombre), un grupo para asesores comerciales,
  otro para otros cargos y "resto" para quien no esta (activo) en el maestro. El mapa cargo -> grupo, las lineas, los NIT HMCL
  y el semaforo salen de Configuracion (`Reglas`, vigentes en el ultimo mes
  elegido); sus valores por defecto son las constantes de `tablero_asesores`.

Costo unitario por referencia: MEDIANA de los costos > 0 de las lineas de
`inventario_detalle` del ultimo `fecha_corte` con carga no ANULADA
(`percentile_cont(0.5)`, la misma mediana de la hoja COSTO REFERENCIA del
Excel); si la referencia no tiene costo en ese corte, su `precio_normal` (> 0). Es especifico de PostgreSQL: la suite prueba estas consultas solo con
`pg_real` (los dobles de sesion no ejecutan SQL), asi que no hay respaldo
portable.
"""
import datetime
import uuid
from decimal import Decimal
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple

from sqlalchemy import Numeric, String, and_, case, cast, false, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.schemas.vendedor import limpiar_cedula
from app.motored.services import parametros
from app.motored.services import tablero_asesores as t
from app.motored.services.tablero_asesores import (
    CLAVE_TOTAL, DIM_ASESOR, DIM_SUCURSAL, DIM_TOTAL, FilaClientes, FilaCubo, FilaFacturas, FilaPersona, Filtro,
    Reglas,
)

TOP_CLIENTES = 5


def _constante(texto: str):
    """Texto fijo como literal SQL (no parametro): asi la misma expresion en el
    SELECT y en el GROUP BY es identica para PostgreSQL. Solo valores propios
    del codigo (constantes), nunca datos del usuario."""
    assert "'" not in texto
    return literal_column(f"'{texto}'")


# --- Expresiones ----------------------------------------------------------------------------


def _expr_identidad():
    """Quien es la persona detras de la linea: su cedula (el maestro tiene una
    fila por nombre del ERP, todas con la misma cedula) o, sin cedula, el propio
    vendedor; para quien no esta en el maestro, su nombre normalizado. Misma
    regla que `tablero_asesores.identidad_de_vendedor`."""
    cedula = func.nullif(func.trim(Vendedor.cedula), _constante(""))
    return case(
        (Vendedor.id.is_(None), VentaDetalle.vendedor_norm),
        else_=func.coalesce(cedula, cast(Vendedor.id, String)),
    )


def _expr_clave(reglas: Reglas):
    """Fila del tablero a la que pertenece cada linea de venta."""
    mapa = reglas.grupo_por_cargo
    ramas = []
    personas = [c for c, g in mapa.items() if g == t.TIPO_PERSONA]
    ramas.append((Vendedor.id.is_(None), _constante(t.GRUPO_RESTO)))
    ramas.append((Vendedor.cargo.in_(personas), _constante(t.PREFIJO_PERSONA).concat(_expr_identidad())))
    for grupo in sorted(set(mapa.values()) - {t.TIPO_PERSONA}):
        cargos = [c for c, g in mapa.items() if g == grupo]
        ramas.append((Vendedor.cargo.in_(cargos), _constante(grupo)))
    return case(*ramas, else_=_constante(t.GRUPO_OTROS))


def _expr_dimension(dimension: str, reglas: Reglas):
    """Clave de la fila del cubo segun la dimension: el asesor/grupo del tablero,
    la sucursal de la venta (todas las ventas, tambien las de RESTO y COMERCIALES)
    o una sola fila TOTAL."""
    if dimension == DIM_ASESOR:
        return _expr_clave(reglas)
    if dimension == DIM_SUCURSAL:
        return cast(VentaDetalle.sucursal_id, String)
    assert dimension == DIM_TOTAL, dimension
    return _constante(CLAVE_TOTAL)


def _expr_cliente_norm():
    """Misma regla que `schemas.cliente_tecnired.normalizar_nit`: sin espacios,
    sin puntos finales y sin el `.0` de un entero leido como decimal. (Quitar
    los puntos finales primero y luego el `.0+` da el mismo punto fijo que el
    bucle de Python; `pg_real` lo compara con la funcion real.)"""
    sin_espacios = func.regexp_replace(VentaDetalle.cliente_factura, r"\s+", "", "g")
    sin_puntos = func.regexp_replace(sin_espacios, r"\.+$", "")
    return case(
        (sin_puntos.op("~")(r"^\d+\.0+$"), func.regexp_replace(sin_puntos, r"\.0+$", "")),
        else_=sin_puntos,
    )


def _lineas_por_referencia(reglas: Reglas):
    """CTE `(id, linea)` por referencia: la linea comercial normalizada
    (recortada, mayusculas, sin tildes) si es una de las 7, y NULL en cualquier
    otro caso. Se calcula UNA vez por referencia (miles) y no por cada linea de
    venta (millones); MATERIALIZED evita que PostgreSQL la vuelva a inlinear."""
    normalizada = func.upper(func.translate(
        func.trim(Referencia.linea_comercial), t.TILDES_ORIGEN, t.TILDES_DESTINO))
    return (
        select(
            Referencia.id.label("id"),
            case((normalizada.in_(list(reglas.lineas)), normalizada), else_=None).label("linea"),
        )
        .cte("linea_por_referencia")
        .prefix_with("MATERIALIZED")
    )


def _expr_venta():
    return VentaDetalle.valor_bruto - VentaDetalle.valor_descuentos


def _expr_mes():
    return func.to_char(VentaDetalle.fecha, "YYYY-MM")


def _expr_es_hmcl(cliente_norm, reglas: Reglas):
    """Un cliente NULL cuenta como NO HMCL (`NOT IN` con NULL daria NULL y la
    linea desapareceria del filtro `excluir`)."""
    return func.coalesce(cliente_norm.in_(list(reglas.hmcl_nits)), false())


def _expr_es_mostrador():
    return func.upper(func.trim(VentaDetalle.origen)) == "MOSTRADOR"


FUENTE_INVENTARIO, FUENTE_MAESTRO = "inventario", "maestro"


def _mediana_de_inventario(fecha_corte: Optional[datetime.date]):
    """Mediana de los costos positivos de cada referencia en el corte dado."""
    mediana = func.percentile_cont(0.5).within_group(InventarioDetalle.costo_unitario)
    return (
        select(
            InventarioDetalle.referencia_id.label("referencia_id"),
            cast(mediana, Numeric(18, 4)).label("costo_unitario"),
        )
        .join(CargaArchivo, CargaArchivo.id == InventarioDetalle.carga_id)
        .where(
            InventarioDetalle.fecha_corte == fecha_corte,
            InventarioDetalle.costo_unitario > 0,
            CargaArchivo.estado != "ANULADO",
        )
        .group_by(InventarioDetalle.referencia_id)
        .subquery("costos_inventario")
    )


def _subconsulta_costos(fecha_corte: Optional[datetime.date]):
    """Costo unitario por referencia, `(referencia_id, costo_unitario, fuente)`:
    la mediana de los costos positivos del corte (`fuente = 'inventario'`) y, si la
    referencia no esta en ese corte o su costo es nulo o no positivo, su
    `precio_normal` cuando es > 0 (`fuente = 'maestro'`); sin ninguno, no hay fila.
    Es LA regla de costo: el resumen `kpi_resumen` la reutiliza tal cual."""
    inventario = _mediana_de_inventario(fecha_corte)
    maestro = cast(Referencia.precio_normal, Numeric(18, 4))
    con_inventario = inventario.c.costo_unitario.is_not(None)
    return (
        select(
            Referencia.id.label("referencia_id"),
            case((con_inventario, inventario.c.costo_unitario), else_=maestro).label("costo_unitario"),
            case((con_inventario, _constante(FUENTE_INVENTARIO)), else_=_constante(FUENTE_MAESTRO)).label("fuente"),
        )
        .select_from(Referencia)
        .outerjoin(inventario, inventario.c.referencia_id == Referencia.id)
        .where(or_(con_inventario, Referencia.precio_normal > 0))
        .subquery("costos")
    )


def _expr_costo_estimado(costos):
    """Parte del costo de una linea de venta tomada del maestro (`precio_normal`)."""
    return func.coalesce(func.sum(case(
        (costos.c.fuente == FUENTE_MAESTRO, VentaDetalle.cantidad * costos.c.costo_unitario), else_=0)), 0)


def _valoracion_inventario():
    """`(valor, sin_costo, costo_maestro)` por linea de `inventario_detalle` (hay que
    cruzar con `Referencia`): una linea vale `existencia x costo` si su costo es > 0,
    si no `existencia x precio_normal` (> 0), si no queda sin costo (vale 0)."""
    con_costo = func.coalesce(InventarioDetalle.costo_unitario > 0, False)
    con_maestro = and_(~con_costo, func.coalesce(Referencia.precio_normal > 0, False))
    valor = case((con_costo, InventarioDetalle.existencia * InventarioDetalle.costo_unitario),
                 (con_maestro, InventarioDetalle.existencia * Referencia.precio_normal), else_=0)
    return (
        func.coalesce(func.sum(valor), 0),
        func.coalesce(func.sum(case((or_(con_costo, con_maestro), 0), else_=1)), 0),
        func.coalesce(func.sum(case((con_maestro, 1), else_=0)), 0),
    )


def _desde_ventas(
    consulta, filtro: Filtro, lineas, *, solo_lineas_reconocidas, costos=None, aplicar_hmcl=True,
    con_vendedor=True,
):
    """FROM/JOIN/WHERE comunes de todas las consultas del tablero. Las fechas
    son rangos `fecha >= a AND fecha < b` unidos con OR (sin funciones sobre la
    columna: el indice `venta_detalle(sucursal_id, fecha)` sigue sirviendo).
    `aplicar_hmcl=False` deja el modo HMCL para Python (ver el cubo).
    `con_vendedor=False` omite el cruce con el maestro (solo la dimension
    `asesor` y las personas lo necesitan)."""
    consulta = (
        consulta.select_from(VentaDetalle)
        .join(CargaArchivo, CargaArchivo.id == VentaDetalle.carga_id)
        .join(lineas, lineas.c.id == VentaDetalle.referencia_id)
    )
    if con_vendedor:
        consulta = consulta.outerjoin(
            Vendedor, (Vendedor.nombre_norm == VentaDetalle.vendedor_norm) & Vendedor.activo.is_(True))
    if costos is not None:
        consulta = consulta.outerjoin(costos, costos.c.referencia_id == VentaDetalle.referencia_id)
    consulta = consulta.where(
        CargaArchivo.estado != "ANULADO",
        or_(*[and_(VentaDetalle.fecha >= inicio, VentaDetalle.fecha < fin) for inicio, fin in filtro.rangos]),
    )
    if filtro.sucursal_ids:
        consulta = consulta.where(VentaDetalle.sucursal_id.in_(sorted(filtro.sucursal_ids, key=str)))
    if aplicar_hmcl and filtro.modo_hmcl == t.HMCL_SOLO:
        consulta = consulta.where(_expr_es_hmcl(_expr_cliente_norm(), filtro.reglas))
    elif aplicar_hmcl and filtro.modo_hmcl == t.HMCL_EXCLUIR:
        consulta = consulta.where(~_expr_es_hmcl(_expr_cliente_norm(), filtro.reglas))
    if solo_lineas_reconocidas:
        consulta = consulta.where(lineas.c.linea.is_not(None))
    return consulta


# --- Consultas -------------------------------------------------------------------------------


async def fecha_corte_costos(db: AsyncSession) -> Optional[datetime.date]:
    """Ultimo `fecha_corte` de inventario con carga no ANULADA."""
    return (
        await db.execute(
            select(func.max(InventarioDetalle.fecha_corte))
            .join(CargaArchivo, CargaArchivo.id == InventarioDetalle.carga_id)
            .where(CargaArchivo.estado != "ANULADO")
        )
    ).scalar()


async def meses_disponibles(db: AsyncSession) -> List[str]:
    mes = _expr_mes()
    filas = await db.execute(
        select(mes)
        .select_from(VentaDetalle)
        .join(CargaArchivo, CargaArchivo.id == VentaDetalle.carga_id)
        .where(CargaArchivo.estado != "ANULADO")
        .group_by(mes)
        .order_by(mes)
    )
    return [m for (m,) in filas.all()]


async def consultar_cubo(db, filtro: Filtro, fecha_corte, dimension: str = DIM_ASESOR) -> List[FilaCubo]:
    """Cubo con HMCL SIEMPRE incluido: el modo HMCL lo aplica el llamador en
    Python con `es_hmcl` (`tablero_asesores.filtrar_cubo_por_hmcl`). La clave
    de cada fila sale de `dimension` (asesor, sucursal o total)."""
    reglas = filtro.reglas
    costos = _subconsulta_costos(fecha_corte)
    lineas = _lineas_por_referencia(reglas)
    cliente = _expr_cliente_norm()
    columnas = [
        _expr_dimension(dimension, reglas).label("clave"),
        _expr_mes().label("mes"),
        lineas.c.linea.label("linea"),
        _expr_es_hmcl(cliente, reglas).label("es_hmcl"),
        cliente.in_(select(ClienteTecnired.nit)).label("es_tecnired"),
        _expr_es_mostrador().label("es_mostrador"),
        costos.c.costo_unitario.is_not(None).label("con_costo"),
    ]
    consulta = select(
        *columnas,
        func.sum(_expr_venta()),
        func.sum(VentaDetalle.valor_bruto),
        func.sum(VentaDetalle.valor_descuentos),
        func.sum(VentaDetalle.cantidad),
        func.count(),
        func.coalesce(func.sum(VentaDetalle.cantidad * costos.c.costo_unitario), 0),
        _expr_costo_estimado(costos),
    ).group_by(*columnas)
    consulta = _desde_ventas(
        consulta, filtro, lineas, solo_lineas_reconocidas=False, costos=costos, aplicar_hmcl=False,
        con_vendedor=dimension == DIM_ASESOR,
    )
    return [
        FilaCubo(clave, mes, linea, hmcl, tec, mostr, costo_ok,
                 Decimal(venta), Decimal(bruto), Decimal(desc), Decimal(cant), int(n), Decimal(costo),
                 Decimal(estimado))
        for clave, mes, linea, hmcl, tec, mostr, costo_ok, venta, bruto, desc, cant, n, costo, estimado
        in (await db.execute(consulta)).all()
    ]


async def consultar_facturas(db, filtro: Filtro, *, dimension: str) -> List[FilaFacturas]:
    """Una factura = (nro_documento, sucursal) distinta DENTRO de la fila: por
    cada una se marca que lineas trae y cuantas lineas distintas tiene."""
    reglas = filtro.reglas
    lineas = _lineas_por_referencia(reglas)
    linea = lineas.c.linea
    por_grupo = dimension != DIM_TOTAL
    clave = _expr_dimension(dimension, reglas).label("clave")
    marcas = [
        func.max(case((linea == nombre, 1), else_=0)).label(f"l{i}")
        for i, nombre in enumerate(reglas.lineas)
    ]
    por_factura = [VentaDetalle.nro_documento, VentaDetalle.sucursal_id] + ([clave] if por_grupo else [])
    interna = _desde_ventas(
        select(clave, func.count(func.distinct(linea)).label("lineas_distintas"), *marcas)
        .group_by(*por_factura),
        filtro, lineas, solo_lineas_reconocidas=True, con_vendedor=dimension == DIM_ASESOR,
    ).subquery("por_factura")
    externa = select(
        interna.c.clave if por_grupo else _constante(CLAVE_TOTAL),
        func.count(),
        func.coalesce(func.sum(case((interna.c.lineas_distintas > 1, 1), else_=0)), 0),
        *[func.coalesce(func.sum(interna.c[f"l{i}"]), 0) for i in range(len(reglas.lineas))],
    )
    if por_grupo:
        externa = externa.group_by(interna.c.clave)
    return [
        FilaFacturas(fila[0], int(fila[1]), int(fila[2]), tuple(int(n) for n in fila[3:]))
        for fila in (await db.execute(externa)).all()
    ]


async def consultar_clientes(db, filtro: Filtro, *, dimension: str) -> List[FilaClientes]:
    """Clientes distintos y venta de los 5 mayores, por fila."""
    reglas = filtro.reglas
    lineas = _lineas_por_referencia(reglas)
    cliente = _expr_cliente_norm().label("cliente")
    por_grupo = dimension != DIM_TOTAL
    clave = _expr_dimension(dimension, reglas).label("clave")
    por_cliente = [cliente] + ([clave] if por_grupo else [])
    interna = _desde_ventas(
        select(clave, cliente, func.sum(_expr_venta()).label("venta")).group_by(*por_cliente),
        filtro, lineas, solo_lineas_reconocidas=True, con_vendedor=dimension == DIM_ASESOR,
    ).subquery("por_cliente")
    posicion = func.row_number().over(
        partition_by=interna.c.clave if por_grupo else None, order_by=interna.c.venta.desc())
    medio = select(interna.c.clave, interna.c.venta, posicion.label("posicion")).subquery("ordenados")
    externa = select(
        medio.c.clave if por_grupo else _constante(CLAVE_TOTAL),
        func.count(),
        func.coalesce(func.sum(case((medio.c.posicion <= TOP_CLIENTES, medio.c.venta), else_=0)), 0),
    )
    if por_grupo:
        externa = externa.group_by(medio.c.clave)
    return [
        FilaClientes(clave_, int(n), Decimal(top5))
        for clave_, n, top5 in (await db.execute(externa)).all()
    ]


async def consultar_personas(db, filtro: Filtro) -> List[FilaPersona]:
    """Quienes hay detras de cada fila: cuantas personas distintas (por cedula) y,
    para una persona, su nombre, cargo y punto de venta (sucursal principal) --
    los del nombre del ERP con mas ventas en el rango. La venta es la misma del
    tablero (solo las 7 lineas)."""
    reglas = filtro.reglas
    lineas = _lineas_por_referencia(reglas)
    clave = _expr_clave(reglas).label("clave")
    identidad = _expr_identidad().label("identidad")
    columnas = [
        clave, identidad, VentaDetalle.vendedor_norm, Vendedor.nombre, Vendedor.cargo, Sucursal.nombre,
    ]
    consulta = _desde_ventas(
        select(*columnas, func.sum(_expr_venta())).group_by(*columnas),
        filtro, lineas, solo_lineas_reconocidas=True,
    ).outerjoin(Sucursal, Sucursal.id == Vendedor.sucursal_id)
    filas = [
        t.FilaVendedorVenta(clave_, identidad_, nombre, cargo, punto, Decimal(venta))
        for clave_, identidad_, _norm, nombre, cargo, punto, venta in (await db.execute(consulta)).all()
    ]
    return t.construir_personas(filas)


async def cargar_reglas(db: AsyncSession, fecha: datetime.date) -> Reglas:
    """Reglas de Configuracion vigentes al dia 1 del mes de `fecha`. Sin fila
    vigente (o con una invalida) rige el valor por defecto del registro."""
    defecto = t.REGLAS_POR_DEFECTO
    valores = await parametros.leer_valores(db, fecha, {
        "lineas_comerciales": list(defecto.lineas),
        "hmcl_nits": list(defecto.hmcl_nits),
        "grupo_por_cargo": dict(defecto.grupo_por_cargo),
        "kpi_semaforo_cortes": dict(defecto.semaforo),
        "cumplimiento_base": defecto.cumplimiento_base,
    })
    return t.reglas_desde_valores(valores)


def eco_reglas(reglas: Reglas, vigencia: str) -> Dict[str, Any]:
    return {
        "semaforo": dict(reglas.semaforo),
        "cumplimiento_base": reglas.cumplimiento_base,
        "vigencia": vigencia,
    }


class FilaVentana(NamedTuple):
    clave: str
    mes: str
    es_hmcl: bool
    venta: Decimal


async def consultar_ventana_mensual(db, filtro: Filtro, dimension: str) -> List[FilaVentana]:
    """Venta mensual por fila de `filtro.rangos` (la ventana de crecimiento), sin
    costos, facturas ni clientes: es la consulta liviana que evita ampliar el
    cubo con los 6 meses de calendario. Mismas reglas de venta que el cubo (7
    lineas, HMCL siempre incluido con su bandera para filtrarlo en Python)."""
    reglas = filtro.reglas
    lineas = _lineas_por_referencia(reglas)
    cliente = _expr_cliente_norm()
    columnas = [
        _expr_dimension(dimension, reglas).label("clave"), _expr_mes().label("mes"),
        _expr_es_hmcl(cliente, reglas).label("es_hmcl"),
    ]
    consulta = _desde_ventas(
        select(*columnas, func.sum(_expr_venta())).group_by(*columnas),
        filtro, lineas, solo_lineas_reconocidas=True, aplicar_hmcl=False,
        con_vendedor=dimension == DIM_ASESOR,
    )
    return [FilaVentana(c, m, bool(h), Decimal(v)) for c, m, h, v in (await db.execute(consulta)).all()]


async def consultar_sucursales(db: AsyncSession, ids: Iterable[str]) -> Dict[str, Tuple[str, Optional[datetime.date]]]:
    """`{id: (nombre, fecha_apertura)}` de las sucursales pedidas (ids como texto)."""
    pedidas = sorted({uuid.UUID(i) for i in ids}, key=str)
    if not pedidas:
        return {}
    filas = await db.execute(
        select(Sucursal.id, Sucursal.nombre, Sucursal.fecha_apertura).where(Sucursal.id.in_(pedidas)))
    return {str(id_): (nombre, apertura) for id_, nombre, apertura in filas.all()}


async def consultar_nombres_por_cedula(db: AsyncSession, cedulas: Iterable[str]) -> Dict[str, str]:
    """`{cedula limpia: nombre}` del maestro de vendedores (un nombre por cedula:
    el de un registro activo si lo hay y, entre iguales, el primero alfabetico).
    Sirve para rotular a quien tiene presupuesto pero no vendio en el rango."""
    pedidas = set(cedulas)
    if not pedidas:
        return {}
    filas = await db.execute(
        select(Vendedor.cedula, Vendedor.nombre)
        .where(Vendedor.cedula.is_not(None))
        .order_by(Vendedor.activo.desc(), func.upper(Vendedor.nombre), Vendedor.nombre))
    nombres: Dict[str, str] = {}
    for cedula, nombre in filas.all():
        try:
            limpia = limpiar_cedula(cedula)
        except ValueError:
            continue
        if limpia in pedidas:
            nombres.setdefault(limpia, nombre)
    return nombres


async def cargar_filtro(
    db: AsyncSession, meses: List[str], modo_hmcl: str, sucursal_ids: Optional[Iterable[Any]] = None,
) -> Filtro:
    """Filtro listo para las consultas: valida los meses y carga las reglas de
    Configuracion vigentes en el ULTIMO mes elegido. `ValueError` si la lista no es valida."""
    meses = t.validar_meses(meses)
    ultimo = datetime.date(int(meses[-1][:4]), int(meses[-1][5:]), 1)
    return t.filtro_de_meses(meses, modo_hmcl, sucursal_ids, await cargar_reglas(db, ultimo))


async def tablero_de_filtro(db: AsyncSession, filtro: Filtro) -> Tuple[Dict[str, Any], List[FilaCubo]]:
    """Tablero de asesores y el cubo de asesores SIN filtrar por HMCL (lo necesita
    el cumplimiento, que mide la venta con HMCL aunque el modo la excluya)."""
    meses, reglas, modo_hmcl = list(filtro.meses), filtro.reglas, filtro.modo_hmcl
    corte = await fecha_corte_costos(db)

    cubo_completo = await consultar_cubo(db, filtro, corte)
    cubo = t.filtrar_cubo_por_hmcl(cubo_completo, modo_hmcl)
    facturas = (await consultar_facturas(db, filtro, dimension=DIM_ASESOR)
                + await consultar_facturas(db, filtro, dimension=DIM_TOTAL))
    clientes = (await consultar_clientes(db, filtro, dimension=DIM_ASESOR)
                + await consultar_clientes(db, filtro, dimension=DIM_TOTAL))
    personas = await consultar_personas(db, filtro)

    tablero = t.construir_tablero(cubo, facturas, clientes, personas, meses, reglas)
    tablero.update(
        desde=meses[0],
        hasta=meses[-1],
        hmcl=modo_hmcl,
        meses=meses,
        sucursales=sorted(str(s) for s in (filtro.sucursal_ids or ())),
        reglas=eco_reglas(reglas, meses[-1]),
        meses_disponibles=await meses_disponibles(db),
        fecha_corte_costos=corte.isoformat() if corte else None,
    )
    return tablero, cubo_completo


async def _calcular(
    db: AsyncSession, meses: List[str], modo_hmcl: str, sucursal_ids: Optional[Iterable[Any]],
) -> Dict[str, Any]:
    filtro = await cargar_filtro(db, meses, modo_hmcl, sucursal_ids)
    return (await tablero_de_filtro(db, filtro))[0]


async def calcular_tablero_por_meses(
    db: AsyncSession, meses: List[str], modo_hmcl: str, sucursal_ids: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Tablero de una lista de meses AAAA-MM (no tienen que ser consecutivos) y,
    opcionalmente, de ciertas sucursales de venta. `ValueError` si la lista no es valida."""
    return await _calcular(db, t.validar_meses(meses), modo_hmcl, sucursal_ids)


async def calcular_tablero(
    db: AsyncSession, desde: str, hasta: str, modo_hmcl: str, *, sucursal_ids: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Tablero del rango `desde`..`hasta` (AAAA-MM): los meses del rango, ver
    `calcular_tablero_por_meses`. Lanza `ValueError` si el rango no es valido."""
    return await _calcular(db, t.validar_rango(desde, hasta), modo_hmcl, sucursal_ids)
