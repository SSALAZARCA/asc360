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
from sqlalchemy.orm import aliased

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
from app.motored.services import tablero_comisiones as comisiones
from app.motored.services.tablero_asesores import (
    CLAVE_TOTAL, DIM_ASESOR, DIM_SUCURSAL, DIM_TOTAL, FilaClientes, FilaCubo, FilaFacturas, FilaPersona, Filtro,
    Reglas,
)

TOP_CLIENTES = 5

# Associated stores roll into their principal at READ time (`sucursal.principal_id`). `SP` is the
# store row of a raw `sucursal_id` (joined with `con_principal`); the principal is its
# `principal_id`, or the store itself. `PV0`/`PV1` do the same for a vendedor's point of sale.
SP = aliased(Sucursal, name="sp")
PV0 = aliased(Sucursal, name="pv0")
PV1 = aliased(Sucursal, name="pv1")
_GRUPO = aliased(Sucursal, name="grupo")


def con_principal(consulta, sucursal):
    """Joins `SP` to the raw store column, so `principal_expr(sucursal)` can be used."""
    return consulta.outerjoin(SP, SP.id == sucursal)


def principal_expr(sucursal):
    """The effective principal of the raw store column `sucursal` (needs `con_principal`)."""
    return func.coalesce(SP.principal_id, sucursal)


def donde_sucursales(sucursal, ids):
    """`sucursal` is one of the stores selected in the UI (principals) or one associated to
    them: a selected principal includes its associates."""
    grupo = select(_GRUPO.id).where(
        func.coalesce(_GRUPO.principal_id, _GRUPO.id).in_(sorted(ids, key=str))).correlate(None)
    return sucursal.in_(grupo)


def con_punto_de_venta(consulta, sucursal):
    """Joins the principal of the store column `sucursal` (a vendedor's store) as `PV1`."""
    return consulta.outerjoin(PV0, PV0.id == sucursal).outerjoin(
        PV1, PV1.id == func.coalesce(PV0.principal_id, PV0.id))


def _constante(texto: str):
    """Texto fijo como literal SQL (no parametro): asi la misma expresion en el
    SELECT y en el GROUP BY es identica para PostgreSQL. Solo valores propios
    del codigo (constantes), nunca datos del usuario."""
    assert "'" not in texto
    return literal_column(f"'{texto}'")


# --- Expresiones ----------------------------------------------------------------------------


def _expr_identidad(vendedor_norm=None):
    """Quien es la persona detras de la linea: su cedula (el maestro tiene una
    fila por nombre del ERP, todas con la misma cedula) o, sin cedula, el propio
    vendedor; para quien no esta en el maestro, su nombre normalizado. Misma
    regla que `tablero_asesores.identidad_de_vendedor`. `vendedor_norm` es la
    columna del nombre normalizado (por defecto la de la venta; el resumen pasa la suya)."""
    vendedor_norm = VentaDetalle.vendedor_norm if vendedor_norm is None else vendedor_norm
    cedula = func.nullif(func.trim(Vendedor.cedula), _constante(""))
    return case(
        (Vendedor.id.is_(None), vendedor_norm),
        else_=func.coalesce(cedula, cast(Vendedor.id, String)),
    )


def _expr_clave(reglas: Reglas, vendedor_norm=None):
    """Fila del tablero a la que pertenece cada linea de venta."""
    mapa = reglas.grupo_por_cargo
    ramas = []
    personas = [c for c, g in mapa.items() if g == t.TIPO_PERSONA]
    ramas.append((Vendedor.id.is_(None), _constante(t.GRUPO_RESTO)))
    ramas.append((Vendedor.cargo.in_(personas), _constante(t.PREFIJO_PERSONA).concat(_expr_identidad(vendedor_norm))))
    for grupo in sorted(set(mapa.values()) - {t.TIPO_PERSONA}):
        cargos = [c for c, g in mapa.items() if g == grupo]
        ramas.append((Vendedor.cargo.in_(cargos), _constante(grupo)))
    return case(*ramas, else_=_constante(t.GRUPO_OTROS))


def _expr_dimension(dimension: str, reglas: Reglas, sucursal=None, vendedor_norm=None):
    """Clave de la fila del cubo segun la dimension: el asesor/grupo del tablero,
    la sucursal PRINCIPAL de la venta (todas las ventas, tambien las de RESTO y COMERCIALES;
    la consulta debe llamar `con_principal`) o una sola fila TOTAL. `sucursal` y `vendedor_norm` son las columnas de origen
    (por defecto las de la venta; el resumen pasa las suyas)."""
    if dimension == DIM_ASESOR:
        return _expr_clave(reglas, vendedor_norm)
    if dimension == DIM_SUCURSAL:
        return cast(principal_expr(VentaDetalle.sucursal_id if sucursal is None else sucursal), String)
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


def _con_costo_real(costo):
    """The line carries a real ERP cost (`venta_detalle.costo` not NULL and not 0)."""
    return and_(costo.is_not(None), costo != 0)


def _expr_costo_fila(cantidad, costo, unitario):
    """LA regla de costo por linea de venta (todo lector de margen/costo la usa, tambien el
    resumen): con costo real y cantidad != 0, `signo(cantidad) x |costo|` (el signo lo manda
    la cantidad); sin costo real, `cantidad x costo unitario` de respaldo (negativo en una
    devolucion; 0 si la referencia no tiene respaldo); con cantidad 0, el costo tal cual o 0."""
    por_cantidad = case((cantidad > 0, func.abs(costo)), else_=-func.abs(costo))
    return func.coalesce(case(
        (and_(_con_costo_real(costo), cantidad != 0), por_cantidad),
        (_con_costo_real(costo), costo),
        (cantidad != 0, cantidad * unitario),
        else_=0), 0)


def _expr_con_costo(costo, unitario):
    """The line has a cost: the real one, or the unit fallback (else it stays out of the margin)."""
    return or_(_con_costo_real(costo), unitario.is_not(None))


def _expr_costo_estimado_fila(cantidad, costo, unitario, fuente):
    """Parte del costo de una linea que no trae costo real y se valoro con `precio_normal`."""
    return case((and_(~_con_costo_real(costo), fuente == FUENTE_MAESTRO), cantidad * unitario), else_=0)


def _costo_de_venta(costos):
    """`_expr_costo_fila` over `venta_detalle` and the live `costos` join."""
    return _expr_costo_fila(VentaDetalle.cantidad, VentaDetalle.costo, costos.c.costo_unitario)


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
    con_vendedor=True, por_sucursal=False,
):
    """FROM/JOIN/WHERE comunes de todas las consultas del tablero. Las fechas
    son rangos `fecha >= a AND fecha < b` unidos con OR (sin funciones sobre la
    columna: el indice `venta_detalle(sucursal_id, fecha)` sigue sirviendo).
    `aplicar_hmcl=False` deja el modo HMCL para Python (ver el cubo).
    `con_vendedor=False` omite el cruce con el maestro (solo la dimension
    `asesor` y las personas lo necesitan). `por_sucursal=True` cruza con la sucursal
    principal de la venta (la dimension `sucursal` y el costo de venta por tienda)."""
    consulta = (
        consulta.select_from(VentaDetalle)
        .join(CargaArchivo, CargaArchivo.id == VentaDetalle.carga_id)
        .join(lineas, lineas.c.id == VentaDetalle.referencia_id)
    )
    if con_vendedor:
        consulta = consulta.outerjoin(
            Vendedor, (Vendedor.nombre_norm == VentaDetalle.vendedor_norm) & Vendedor.activo.is_(True))
    if por_sucursal:
        consulta = con_principal(consulta, VentaDetalle.sucursal_id)
    if costos is not None:
        consulta = consulta.outerjoin(costos, costos.c.referencia_id == VentaDetalle.referencia_id)
    consulta = consulta.where(
        CargaArchivo.estado != "ANULADO",
        or_(*[and_(VentaDetalle.fecha >= inicio, VentaDetalle.fecha < fin) for inicio, fin in filtro.rangos]),
    )
    if filtro.sucursal_ids:
        consulta = consulta.where(donde_sucursales(VentaDetalle.sucursal_id, filtro.sucursal_ids))
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


async def ultima_fecha_venta(
    db, mes: str, sucursal_ids=None, hasta: Optional[datetime.date] = None,
) -> Optional[datetime.date]:
    """Day of the latest loaded (not ANULADO) sale of `mes` ("YYYY-MM") in the chosen stores (on or before
    `hasta` when given), None when the month has none. The summaries keep months, not days, so the live and summary paths both ask
    here and agree."""
    inicio = datetime.date(int(mes[:4]), int(mes[5:]), 1)
    fin = (inicio + datetime.timedelta(days=32)).replace(day=1)
    consulta = (
        select(func.max(VentaDetalle.fecha))
        .select_from(VentaDetalle)
        .join(CargaArchivo, CargaArchivo.id == VentaDetalle.carga_id)
        .where(CargaArchivo.estado != "ANULADO", VentaDetalle.fecha >= inicio, VentaDetalle.fecha < fin)
    )
    if hasta is not None:
        consulta = consulta.where(VentaDetalle.fecha <= hasta)
    if sucursal_ids:
        consulta = consulta.where(donde_sucursales(VentaDetalle.sucursal_id, sucursal_ids))
    return (await db.execute(consulta)).scalar()


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
        _expr_con_costo(VentaDetalle.costo, costos.c.costo_unitario).label("con_costo"),
    ]
    consulta = select(
        *columnas,
        func.sum(_expr_venta()),
        func.sum(VentaDetalle.valor_bruto),
        func.sum(VentaDetalle.valor_descuentos),
        func.sum(VentaDetalle.cantidad),
        func.count(),
        func.coalesce(func.sum(_costo_de_venta(costos)), 0),
        func.coalesce(func.sum(_expr_costo_estimado_fila(
            VentaDetalle.cantidad, VentaDetalle.costo, costos.c.costo_unitario, costos.c.fuente)), 0),
    ).group_by(*columnas)
    consulta = _desde_ventas(
        consulta, filtro, lineas, solo_lineas_reconocidas=False, costos=costos, aplicar_hmcl=False,
        con_vendedor=dimension == DIM_ASESOR, por_sucursal=dimension == DIM_SUCURSAL,
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
        por_sucursal=dimension == DIM_SUCURSAL,
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


async def consultar_clientes(db, filtro: Filtro, *, dimension: str, solo_unicos: bool = False) -> List[FilaClientes]:
    """Clientes distintos y venta de los 5 mayores, por fila. Con `solo_unicos` no ordena a los clientes para
    sacar los 5 mayores (la venta de los 5 mayores queda en 0): para quien solo necesita cuantos son."""
    reglas = filtro.reglas
    lineas = _lineas_por_referencia(reglas)
    cliente = _expr_cliente_norm().label("cliente")
    por_grupo = dimension != DIM_TOTAL
    clave = _expr_dimension(dimension, reglas).label("clave")
    por_cliente = [cliente] + ([clave] if por_grupo else [])
    interna = _desde_ventas(
        select(clave, cliente, func.sum(_expr_venta()).label("venta")).group_by(*por_cliente),
        filtro, lineas, solo_lineas_reconocidas=True, con_vendedor=dimension == DIM_ASESOR,
        por_sucursal=dimension == DIM_SUCURSAL,
    ).subquery("por_cliente")
    return _filas_de_clientes(await db.execute(_agregar_clientes(interna, por_grupo, solo_unicos)))


def _agregar_clientes(interna, por_grupo: bool, solo_unicos: bool = False):
    """`(clave, clientes distintos, venta de los 5 mayores)` sobre una subconsulta
    `(clave, venta)` con una fila por cliente y fila. La comparte la lectura del resumen. Con `solo_unicos`
    la venta de los 5 mayores es 0 y no se calcula (sin la ventana que ordena a todos los clientes)."""
    if solo_unicos:
        externa = select(
            interna.c.clave if por_grupo else _constante(CLAVE_TOTAL), func.count(), literal_column("0"),
        ).select_from(interna)
        return externa.group_by(interna.c.clave) if por_grupo else externa
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
    return externa


def _filas_de_clientes(resultado) -> List[FilaClientes]:
    return [FilaClientes(clave_, int(n), Decimal(top5)) for clave_, n, top5 in resultado.all()]


async def consultar_personas(db, filtro: Filtro) -> List[FilaPersona]:
    """Quienes hay detras de cada fila: cuantas personas distintas (por cedula) y,
    para una persona, su nombre, cargo y punto de venta (la tienda principal de su sucursal) --
    los del nombre del ERP con mas ventas en el rango. La venta es la misma del
    tablero (solo las 7 lineas)."""
    reglas = filtro.reglas
    lineas = _lineas_por_referencia(reglas)
    clave = _expr_clave(reglas).label("clave")
    identidad = _expr_identidad().label("identidad")
    columnas = [
        clave, identidad, VentaDetalle.vendedor_norm, Vendedor.nombre, Vendedor.cargo, PV1.nombre,
    ]
    consulta = _desde_ventas(
        select(*columnas, func.sum(_expr_venta())).group_by(*columnas),
        filtro, lineas, solo_lineas_reconocidas=True,
    )
    consulta = con_punto_de_venta(consulta, Vendedor.sucursal_id)
    filas = [
        t.FilaVendedorVenta(clave_, identidad_, nombre, cargo, punto, Decimal(venta))
        for clave_, identidad_, _norm, nombre, cargo, punto, venta in (await db.execute(consulta)).all()
    ]
    return t.construir_personas(filas)


class FilaAsesorMaestro(NamedTuple):
    """Una persona del maestro de vendedores con cedula valida: su nombre, cargo y la tienda PRINCIPAL
    de su punto de venta (`sucursal_id` como texto)."""
    cedula: str
    nombre: str
    cargo: str
    activo: bool
    sucursal_id: Optional[str]
    tienda: Optional[str]


async def consultar_asesores_maestro(db: AsyncSession) -> List[FilaAsesorMaestro]:
    """Una fila por cedula valida del maestro (varios nombres del ERP comparten cedula): la de un
    registro activo si lo hay y, entre iguales, la del primer nombre alfabetico."""
    consulta = (
        select(Vendedor.cedula, Vendedor.nombre, Vendedor.cargo, Vendedor.activo, PV1.id, PV1.nombre)
        .select_from(Vendedor)
        .where(Vendedor.cedula.is_not(None))
        .order_by(Vendedor.activo.desc(), func.upper(Vendedor.nombre), Vendedor.nombre)
    )
    consulta = con_punto_de_venta(consulta, Vendedor.sucursal_id)
    filas: Dict[str, FilaAsesorMaestro] = {}
    for cedula, nombre, cargo, activo, tienda_id, tienda in (await db.execute(consulta)).all():
        try:
            limpia = limpiar_cedula(cedula)
        except ValueError:
            continue
        filas.setdefault(limpia, FilaAsesorMaestro(
            limpia, nombre, cargo, bool(activo), None if tienda_id is None else str(tienda_id), tienda))
    return sorted(filas.values(), key=lambda f: (f.nombre.upper(), f.cedula))


class FilaTecniredAsesor(NamedTuple):
    nit: str
    razon_social: Optional[str]
    venta: Decimal


def _ventas_tecnired_de_asesor(consulta, filtro: Filtro, clave: str):
    """Ventas de clientes Tecnired (lineas reconocidas, con el filtro) de la fila `clave` del tablero."""
    lineas = _lineas_por_referencia(filtro.reglas)
    consulta = _desde_ventas(consulta, filtro, lineas, solo_lineas_reconocidas=True, con_vendedor=True)
    return consulta.where(_expr_cliente_norm().in_(select(ClienteTecnired.nit)), _expr_clave(filtro.reglas) == clave)


async def consultar_clientes_tecnired_de_asesor(db, filtro: Filtro, clave: str) -> int:
    """Clientes Tecnired distintos que compraron a la fila `clave` del tablero."""
    consulta = _ventas_tecnired_de_asesor(select(func.count(func.distinct(_expr_cliente_norm()))), filtro, clave)
    return int((await db.execute(consulta)).scalar() or 0)


async def consultar_top_tecnired_de_asesor(
    db, filtro: Filtro, clave: str, limite: int = TOP_CLIENTES,
) -> List[FilaTecniredAsesor]:
    """Los `limite` clientes Tecnired de mayor venta de la fila `clave`; empates por NIT."""
    venta = func.sum(_expr_venta())
    consulta = _ventas_tecnired_de_asesor(select(ClienteTecnired.nit, ClienteTecnired.razon_social, venta), filtro, clave)
    consulta = (
        consulta.join(ClienteTecnired, ClienteTecnired.nit == _expr_cliente_norm())
        .group_by(ClienteTecnired.nit, ClienteTecnired.razon_social)
        .order_by(venta.desc(), ClienteTecnired.nit)
        .limit(limite)
    )
    return [FilaTecniredAsesor(nit, razon, Decimal(v)) for nit, razon, v in (await db.execute(consulta)).all()]


async def consultar_tecnired_por_asesor(db, filtro: Filtro) -> Dict[str, List[FilaTecniredAsesor]]:
    """ONE grouped query for the Tecnired clients of EVERY tablero row: `{clave: clientes}`, each list from the
    biggest sale to the smallest (ties by NIT). Same filter as `consultar_top_tecnired_de_asesor`, which asks for
    one asesor at a time; the daily report needs all of them without one query each."""
    venta = func.sum(_expr_venta())
    clave = _expr_clave(filtro.reglas)
    lineas = _lineas_por_referencia(filtro.reglas)
    consulta = _desde_ventas(
        select(clave, ClienteTecnired.nit, ClienteTecnired.razon_social, venta), filtro, lineas,
        solo_lineas_reconocidas=True, con_vendedor=True)
    consulta = (
        consulta.where(_expr_cliente_norm().in_(select(ClienteTecnired.nit)))
        .join(ClienteTecnired, ClienteTecnired.nit == _expr_cliente_norm())
        .group_by(clave, ClienteTecnired.nit, ClienteTecnired.razon_social)
        .order_by(clave, venta.desc(), ClienteTecnired.nit)
    )
    por_clave: Dict[str, List[FilaTecniredAsesor]] = {}
    for clave_, nit, razon, total in (await db.execute(consulta)).all():
        por_clave.setdefault(clave_, []).append(FilaTecniredAsesor(nit, razon, Decimal(total)))
    return por_clave


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


async def cargar_reglas_comision(db: AsyncSession, mes: str) -> comisiones.ReglasComision:
    """Reglas de comision vigentes al dia 1 de `mes` (AAAA-MM); lo invalido vuelve al defecto."""
    fecha = datetime.date(int(mes[:4]), int(mes[5:]), 1)
    return comisiones.reglas_desde_valores(await parametros.leer_valores(db, fecha, comisiones.respaldos()))


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
        con_vendedor=dimension == DIM_ASESOR, por_sucursal=dimension == DIM_SUCURSAL,
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


async def consultar_cargos_por_cedula(db: AsyncSession, cedulas: Iterable[str]) -> Dict[str, Tuple[str, ...]]:
    """`{cedula limpia: cargos}` del maestro de vendedores (los de sus registros activos; si ninguno
    esta activo, los de todos). Sirve para quien tiene presupuesto pero no vendio en el mes."""
    pedidas = set(cedulas)
    if not pedidas:
        return {}
    filas = await db.execute(
        select(Vendedor.cedula, Vendedor.cargo, Vendedor.activo).where(Vendedor.cedula.is_not(None)))
    activos: Dict[str, set] = {}
    todos: Dict[str, set] = {}
    for cedula, cargo, activo in filas.all():
        try:
            limpia = limpiar_cedula(cedula)
        except ValueError:
            continue
        if limpia in pedidas and cargo:
            todos.setdefault(limpia, set()).add(cargo)
            if activo:
                activos.setdefault(limpia, set()).add(cargo)
    return {c: tuple(sorted(activos.get(c) or todos[c])) for c in todos}


async def cargar_filtro(
    db: AsyncSession, meses: List[str], modo_hmcl: str, sucursal_ids: Optional[Iterable[Any]] = None,
) -> Filtro:
    """Filtro listo para las consultas: valida los meses y carga las reglas de
    Configuracion vigentes en el ULTIMO mes elegido. `ValueError` si la lista no es valida."""
    meses = t.validar_meses(meses)
    ultimo = datetime.date(int(meses[-1][:4]), int(meses[-1][5:]), 1)
    ids = await _principales(db, sucursal_ids)
    return t.filtro_de_meses(meses, modo_hmcl, ids, await cargar_reglas(db, ultimo))


async def _principales(db: AsyncSession, sucursal_ids: Optional[Iterable[Any]]) -> Optional[Iterable[Any]]:
    """The stores selected in the UI as their principals (a stale id of an associated store
    means its principal). The queries expand each principal to its group."""
    pedidas = list(sucursal_ids) if sucursal_ids else []
    if not pedidas:
        return sucursal_ids
    # Imported here: the summary reads import this module for the shared expressions.
    from app.motored.services import kpi_resumen_lectura as lectura

    mapa = await lectura.principales(db)
    ids = [i if isinstance(i, uuid.UUID) else uuid.UUID(str(i)) for i in pedidas]
    return [mapa.get(i, i) for i in ids]


class _Alcance(NamedTuple):
    """What a tablero is built with. The complete one is the tab's; the others leave out the reads whose
    figures their caller never looks at (the detail of one asesor, the options of the filter)."""
    costos: bool = True  # the cost cut: the cube carries the margin
    facturas: bool = True
    clientes: Optional[str] = "top5"  # "top5", "unicos" (how many, not the top 5 share) or None
    clientes_de_la_red: bool = True  # the TOTAL row of the clients
    contexto: bool = True  # the months available and the cost cut date


_ALCANCE_DETALLE = _Alcance(clientes="unicos", clientes_de_la_red=False, contexto=False)
_ALCANCE_OPCIONES = _Alcance(costos=False, facturas=False, clientes=None, clientes_de_la_red=False, contexto=False)


async def _tablero(db: AsyncSession, filtro: Filtro, alcance: _Alcance) -> Tuple[Dict[str, Any], List[FilaCubo]]:
    # Imported here: the summary reads import this module for the shared expressions.
    from app.motored.services import kpi_resumen_lectura as lectura

    meses, reglas, modo_hmcl = list(filtro.meses), filtro.reglas, filtro.modo_hmcl
    corte = await lectura.fecha_corte_costos(db) if alcance.costos else None

    cubo_completo = await lectura.cubo(db, filtro, corte)
    cubo = t.filtrar_cubo_por_hmcl(cubo_completo, modo_hmcl)
    facturas, clientes = [], []
    if alcance.facturas:
        facturas = (await lectura.facturas(db, filtro, dimension=DIM_ASESOR)
                    + await lectura.facturas(db, filtro, dimension=DIM_TOTAL))
    if alcance.clientes:
        aparte = {"solo_unicos": True} if alcance.clientes == "unicos" else {}
        clientes = await lectura.clientes(db, filtro, dimension=DIM_ASESOR, **aparte)
        if alcance.clientes_de_la_red:
            clientes = clientes + await lectura.clientes(db, filtro, dimension=DIM_TOTAL, **aparte)
    personas = await lectura.personas(db, filtro)

    tablero = t.construir_tablero(cubo, facturas, clientes, personas, meses, reglas)
    tablero.update(
        desde=meses[0],
        hasta=meses[-1],
        hmcl=modo_hmcl,
        meses=meses,
        sucursales=sorted(str(s) for s in (filtro.sucursal_ids or ())),
        reglas=eco_reglas(reglas, meses[-1]),
    )
    if alcance.contexto:
        tablero.update(
            meses_disponibles=await lectura.meses(db),
            fecha_corte_costos=corte.isoformat() if corte else None,
        )
    return tablero, cubo_completo


async def tablero_de_filtro(db: AsyncSession, filtro: Filtro) -> Tuple[Dict[str, Any], List[FilaCubo]]:
    """Tablero de asesores y el cubo de asesores SIN filtrar por HMCL (lo necesita
    el cumplimiento, que mide la venta con HMCL aunque el modo la excluya)."""
    return await _tablero(db, filtro, _Alcance())


async def tablero_para_detalle(db: AsyncSession, filtro: Filtro) -> Tuple[Dict[str, Any], List[FilaCubo]]:
    """`tablero_de_filtro` for the detail of one asesor: the same figures it reads, without the share of
    the top 5 clients (it only counts them), the clients of the whole network, the months available nor
    the cost cut date, which it never looks at."""
    return await _tablero(db, filtro, _ALCANCE_DETALLE)


async def tablero_para_opciones(db: AsyncSession, filtro: Filtro) -> Dict[str, Any]:
    """The tablero of the "Asesor" options: only who sold how much (the cube and the people), without
    invoices, clients, costs nor the context the tab shows."""
    return (await _tablero(db, filtro, _ALCANCE_OPCIONES))[0]


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
