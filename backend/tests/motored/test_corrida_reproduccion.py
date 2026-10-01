"""
Motored Pedidos F3 "Motor", S6a (sdd/motored-pedidos-motor, ADR-4, T17, T18):
reproducción pura de una corrida desde su snapshot.

`reproducir` reconstruye las entradas del motor SOLO con lo persistido
(`corrida`, `corrida_sucursal`, `corrida_linea`, `corrida_resumen`), vuelve a
calcular y compara cada columna de salida. Nunca lee ventas, inventario,
referencias, sucursales ni parámetros vivos: un espía sobre la sesión lo
verifica.
"""
import dataclasses
import datetime
import uuid
from decimal import Decimal
from fractions import Fraction

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_resumen import CorridaResumen
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.services import parametros
from app.motored.services.corridas import parametros_corrida as pcorr
from app.motored.services.corridas import persistencia as pe
from app.motored.services.corridas import reproduccion as rp
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import MesEnCurso, NodoMaestro
from tests.motored.conftest import _ExecuteResult
from tests.motored.fixtures.motor.constructores import (
    atributos,
    entrada,
    fila_patron,
)

CORTE = datetime.date(2026, 9, 29)
IDS = {letra: uuid.UUID(int=i) for i, letra in enumerate("ABCDE", start=1)}
SUC_1, SUC_2 = uuid.UUID(int=201), uuid.UUID(int=202)
CEROS = (0, 0, 0, 0, 0, 0)
TABLAS_PERMITIDAS = {
    "corrida", "corrida_sucursal", "corrida_linea", "corrida_resumen"}
TABLAS_PROHIBIDAS = {
    "venta_mensual", "inventario_snapshot", "backorder_linea", "referencia",
    "sucursal", "parametro_metodologia", "demanda_perdida"}


def _ref(letra, ventas=CEROS, perdidas=CEROS, **kw):
    return entrada(
        ventas, perdidas, codigo=f"REF-{letra}",
        referencia_id=IDS[letra], **kw)


class Almacen:
    """Lo que el motor dejó persistido, servido por una sesión de juguete."""

    def __init__(self, corrida, sucursales, lineas, resumen):
        self.corrida = corrida
        self.sucursales = sucursales
        self.lineas = lineas
        self.resumen = resumen
        self.tablas_leidas = []

    async def execute(self, sentencia):
        tabla = sentencia.get_final_froms()[0].name
        self.tablas_leidas.append(tabla)
        return _ExecuteResult({
            "corrida": [self.corrida],
            "corrida_sucursal": self.sucursales,
            "corrida_linea": self.lineas,
            "corrida_resumen": self.resumen,
        }[tabla])


def _sucursal_de(fila):
    """La fila persistida de la sucursal, con su clave y orden."""
    return CorridaSucursal(**fila)


def _almacenar(sucursales, *, overrides=None, nodos=(), m0=None):
    """Corre el motor y persiste en memoria con las MISMAS funciones de
    escritura que usa `guardar_sucursal`."""
    ids = [a.sucursal_id for a, _ in sucursales]
    vigentes = parametros.VigentesMotor.desde_filas(
        [], CORTE, overrides=overrides)
    params = pcorr.construir_parametros_corrida(vigentes, ids)
    motor = dataclasses.replace(params.motor, mes_en_curso=m0)
    resoluciones = resolver_cadenas({n.referencia_id: n for n in nodos})
    consolidar = motor.consolidar_sustituidas
    corrida = Corrida(
        id=uuid.uuid4(), codigo="PED-2026-S40-001", estado="BORRADOR",
        fecha_corte=CORTE, parametros_snapshot=params.snapshot,
        seleccion_datos={"mes_en_curso": _bloque(m0)},
        maestro_sustitucion=[
            {"referencia_id": str(n.referencia_id), "activa": n.activa,
             "sustituida_por": None if n.sustituida_por is None
             else str(n.sustituida_por)} for n in nodos])
    filas_sucursal, lineas, resumen = [], [], []
    for orden, (sucursal, entradas) in enumerate(sucursales, 1):
        resultado = calcular_sucursal(entradas, sucursal, motor, resoluciones)
        filas = pe.armar_filas(
            corrida.id, sucursal, entradas, resultado, consolidar=consolidar)
        filas_sucursal.append(_sucursal_de({
            "corrida_id": corrida.id, "sucursal_id": sucursal.sucursal_id,
            "orden": orden, **filas.sucursal}))
        lineas += [CorridaLinea(**f) for f in filas.lineas]
        resumen += [CorridaResumen(**f) for f in filas.resumen]
    return Almacen(corrida, filas_sucursal, lineas, resumen)


def _bloque(m0):
    if m0 is None:
        return {"modo_efectivo": "EXCLUIDO", "d": None, "D": None}
    return {
        "modo_efectivo": "PONDERADO", "d": m0.dias_transcurridos,
        "D": m0.dias_del_mes}


def _dos_sucursales():
    primera = dataclasses.replace(atributos(nombre="UNO"), sucursal_id=SUC_1)
    segunda = dataclasses.replace(
        atributos(nombre="DOS", dias_entre_pedidos="7"), sucursal_id=SUC_2)
    return [
        (primera, [fila_patron(), _ref("A", (9, 8, 7, 6, 5, 4), precio="10")]),
        (segunda, [_ref("B", (1, 0, 2, 0, 3, 0), inventario=4, precio="5")]),
    ]


async def _reproducir(almacen):
    return await rp.reproducir(almacen, almacen.corrida.id)


def _linea(almacen, letra):
    return next(
        f for f in almacen.lineas if f.referencia_id == IDS[letra])


# --- Reproducción idéntica --------------------------------------------------


async def test_a_two_sucursal_corrida_replays_identical():
    almacen = _almacenar(_dos_sucursales())

    reporte = await _reproducir(almacen)

    assert reporte.identico is True
    assert reporte.diferencias == ()
    assert len(almacen.lineas) == 3


async def test_the_replay_reads_only_the_corrida_tables():
    almacen = _almacenar(_dos_sucursales())

    await _reproducir(almacen)

    leidas = set(almacen.tablas_leidas)
    assert leidas == TABLAS_PERMITIDAS
    assert not leidas & TABLAS_PROHIBIDAS


async def test_the_replay_rebuilds_the_per_sucursal_days_from_stored_rows():
    almacen = _almacenar(_dos_sucursales())
    for fila in almacen.sucursales:
        if fila.sucursal_id == SUC_2:
            fila.dias_entre_pedidos = Decimal("30.00")

    reporte = await _reproducir(almacen)

    assert reporte.identico is False
    assert {d.sucursal_id for d in reporte.diferencias} == {SUC_2}


async def test_a_closed_corrida_replays_identical_without_live_parameters():
    almacen = _almacenar(_dos_sucursales())
    almacen.corrida.estado = "CERRADA"

    reporte = await _reproducir(almacen)

    assert reporte.identico is True
    assert "parametro_metodologia" not in almacen.tablas_leidas


async def test_the_same_inputs_persist_identical_rows_twice_t17():
    sucursales = _dos_sucursales()

    primera = _almacenar(sucursales)
    segunda = _almacenar(sucursales)

    def _sin_corrida(almacen):
        return [
            {c.key: getattr(f, c.key) for c in CorridaLinea.__table__.columns
             if c.key not in ("id", "corrida_id")} for f in almacen.lineas]

    assert len(primera.lineas) == 3
    assert _sin_corrida(primera) == _sin_corrida(segunda)


# --- El estado del pedido por tienda no entra al reproceso (F4, ADR-4) ------


async def test_the_replay_ignores_the_pedido_state_of_each_tienda():
    almacen = _almacenar(_dos_sucursales())
    for fila, estado in zip(almacen.sucursales, ("CERRADO", "ENVIADO")):
        assert CorridaSucursal.estado_pedido.property.columns[0].name == (
            "estado_pedido")
        fila.estado_pedido = estado

    reporte = await _reproducir(almacen)

    assert reporte.identico is True and reporte.diferencias == ()


def test_armar_filas_keys_are_pinned_and_carry_no_pedido_state():
    sucursal, entradas = _dos_sucursales()[0]
    resultado = calcular_sucursal(
        entradas, sucursal, pcorr.parametros_motor_desde_snapshot(
            pcorr.construir_parametros_corrida(
                parametros.VigentesMotor.desde_filas([], CORTE),
                [sucursal.sucursal_id]).snapshot,
            {"mes_en_curso": _bloque(None)}), {})

    filas = pe.armar_filas(
        uuid.uuid4(), sucursal, entradas, resultado, consolidar=False)

    assert set(filas.sucursal) == {
        "estado", "codigo", "mensaje", "fecha_apertura", "divisor",
        "buckets_operados", "dias_empaque", "dias_transito",
        "dias_seguridad", "dias_entre_pedidos", "parametros", "coberturas",
        "lineas", "excluidas", "unidades", "valor"}
    columnas = {k for fila in filas.lineas + filas.resumen for k in fila}
    assert "estado_pedido" not in columnas


# --- Detección de alteraciones ----------------------------------------------


async def test_a_tampered_output_is_reported_with_column_and_values():
    almacen = _almacenar(_dos_sucursales())
    _linea(almacen, "A").pedido_sugerido = Decimal("999.00")

    reporte = await _reproducir(almacen)

    assert reporte.identico is False
    diferencia = next(
        d for d in reporte.diferencias if d.columna == "pedido_sugerido")
    assert diferencia.sucursal_id == SUC_1
    assert diferencia.clave == "REF-A"
    assert diferencia.almacenado == Decimal("999.00")
    assert diferencia.esperado != diferencia.almacenado


async def test_a_tampered_input_changes_the_recomputed_outputs():
    almacen = _almacenar(_dos_sucursales())
    _linea(almacen, "B").venta_m1 = Decimal("500.00")

    reporte = await _reproducir(almacen)

    columnas = {d.columna for d in reporte.diferencias}
    assert reporte.identico is False
    assert "demanda_ponderada" in columnas


async def test_a_missing_line_is_caught_by_the_stored_line_count():
    almacen = _almacenar(_dos_sucursales())
    almacen.lineas.remove(_linea(almacen, "A"))

    reporte = await _reproducir(almacen)

    diferencia = next(
        d for d in reporte.diferencias
        if d.clave == "sucursal" and d.columna == "lineas")
    assert reporte.identico is False
    assert diferencia.sucursal_id == SUC_1
    assert (diferencia.esperado, diferencia.almacenado) == (1, 2)


async def test_an_extra_stored_line_is_caught_by_the_stored_line_count():
    almacen = _almacenar(_dos_sucursales())
    intrusa = CorridaLinea(**{
        c.key: getattr(_linea(almacen, "A"), c.key)
        for c in CorridaLinea.__table__.columns if c.key != "id"})
    intrusa.referencia_id = IDS["E"]
    intrusa.codigo_referencia = "REF-E"
    almacen.lineas.append(intrusa)

    reporte = await _reproducir(almacen)

    diferencia = next(
        d for d in reporte.diferencias
        if d.clave == "sucursal" and d.columna == "lineas")
    assert (diferencia.esperado, diferencia.almacenado) == (3, 2)


async def test_a_tampered_resumen_row_is_reported():
    almacen = _almacenar(_dos_sucursales())
    fila = next(
        r for r in almacen.resumen
        if r.sucursal_id == SUC_1 and r.clase == "TOTAL")
    fila.unidades = fila.unidades + 1

    reporte = await _reproducir(almacen)

    assert any(
        d.clave == "resumen:TOTAL" and d.columna == "unidades"
        for d in reporte.diferencias)


async def test_a_tampered_sucursal_summary_is_reported():
    almacen = _almacenar(_dos_sucursales())
    almacen.sucursales[0].valor = Decimal("1.00")

    reporte = await _reproducir(almacen)

    assert any(
        d.clave == "sucursal" and d.columna == "valor"
        for d in reporte.diferencias)


# --- Estados de sucursal ----------------------------------------------------


async def test_an_omitted_sucursal_replays_identical():
    nueva = dataclasses.replace(
        atributos(nombre="NUEVA", fecha_apertura=datetime.date(2026, 9, 10)),
        sucursal_id=SUC_2)
    almacen = _almacenar([_dos_sucursales()[0], (nueva, [])])

    reporte = await _reproducir(almacen)

    assert reporte.identico is True
    assert almacen.sucursales[1].estado == "OMITIDA"


async def test_a_failed_sucursal_is_left_out_of_the_replay():
    almacen = _almacenar(_dos_sucursales())
    fallida = almacen.sucursales[1]
    fallida.estado = "FALLIDA"
    almacen.lineas = [f for f in almacen.lineas if f.sucursal_id != SUC_2]
    almacen.resumen = [r for r in almacen.resumen if r.sucursal_id != SUC_2]

    assert (await _reproducir(almacen)).identico is True


async def test_a_pending_sucursal_is_left_out_of_the_replay():
    almacen = _almacenar(_dos_sucursales())
    pendiente = almacen.sucursales[1]
    pendiente.estado = "PENDIENTE"
    almacen.lineas = [f for f in almacen.lineas if f.sucursal_id != SUC_2]
    almacen.resumen = [r for r in almacen.resumen if r.sucursal_id != SUC_2]

    assert (await _reproducir(almacen)).identico is True


# --- Interruptores: consolidación y mes en curso ----------------------------


def _sucursal_con_sustitucion():
    sucursal = dataclasses.replace(atributos(), sucursal_id=SUC_1)
    entradas = [
        _ref("A", (5, 0, 3, 0, 2, 4), inventario=30, transito=20,
             backorder=5),
        _ref("B", (1, 1, 1, 1, 1, 1), inventario=10, precio="7"),
        _ref("C", CEROS, (0, 0, 0, 0, 0, 8)),
        _ref("D", (2, 2, 2, 2, 2, 2), precio="3"),
    ]
    nodos = [NodoMaestro(IDS["A"], False, IDS["B"]),
             NodoMaestro(IDS["C"], False, IDS["B"])]
    return sucursal, entradas, nodos


async def test_a_consolidated_corrida_replays_identical_with_excluded_lines():
    sucursal, entradas, nodos = _sucursal_con_sustitucion()
    almacen = _almacenar(
        [(sucursal, entradas)], nodos=nodos,
        overrides={"consolidar_sustituidas": True})

    reporte = await _reproducir(almacen)

    assert reporte.identico is True
    assert any(f.motivo_exclusion == "SUSTITUIDA" for f in almacen.lineas)


async def test_a_lost_only_transferring_reference_is_still_reproduced():
    sucursal, entradas, nodos = _sucursal_con_sustitucion()
    almacen = _almacenar(
        [(sucursal, entradas)], nodos=nodos,
        overrides={"consolidar_sustituidas": True,
                   "incluir_demanda_perdida_en_ponderada": True})

    reporte = await _reproducir(almacen)

    assert reporte.identico is True
    assert almacen.sucursales[0].parametros["entradas_auxiliares"]


async def test_dropping_the_auxiliary_input_breaks_the_replay():
    sucursal, entradas, nodos = _sucursal_con_sustitucion()
    almacen = _almacenar(
        [(sucursal, entradas)], nodos=nodos,
        overrides={"consolidar_sustituidas": True,
                   "incluir_demanda_perdida_en_ponderada": True})
    almacen.sucursales[0].parametros = {
        **almacen.sucursales[0].parametros, "entradas_auxiliares": []}

    reporte = await _reproducir(almacen)

    assert reporte.identico is False


async def test_a_tampered_auxiliary_input_that_becomes_a_line_is_reported():
    sucursal = dataclasses.replace(atributos(), sucursal_id=SUC_1)
    entradas = [_ref("A", CEROS, inventario=9), _ref("B", CEROS)]
    nodos = [NodoMaestro(IDS["A"], False, IDS["B"])]
    almacen = _almacenar(
        [(sucursal, entradas)], nodos=nodos,
        overrides={"consolidar_sustituidas": True})
    parametros_fila = almacen.sucursales[0].parametros
    auxiliar = dict(parametros_fila["entradas_auxiliares"][0])
    auxiliar["ventas"] = ["0", "0", "0", "0", "0", "9"]
    almacen.sucursales[0].parametros = {
        **parametros_fila, "entradas_auxiliares": [auxiliar]}

    reporte = await _reproducir(almacen)

    assert any(
        d.clave == "REF-B" and d.columna == "*" and d.almacenado == "ausente"
        for d in reporte.diferencias)


async def test_a_ponderado_corrida_replays_identical():
    sucursal = dataclasses.replace(atributos(), sucursal_id=SUC_1)
    fila = dataclasses.replace(
        fila_patron(), venta_m0=Decimal("63"), perdida_m0=Decimal("0"))
    m0 = MesEnCurso("PONDERADO", 14, 30, Fraction(3))
    almacen = _almacenar([(sucursal, [fila])], m0=m0)

    reporte = await _reproducir(almacen)

    assert reporte.identico is True
    assert almacen.lineas[0].venta_m0_proyectada == Decimal("135.000000")
    assert almacen.lineas[0].pedido_sugerido == Decimal("61.00")


# --- Parámetros desde el snapshot -------------------------------------------


def _snapshot(overrides=None, sucursales=(SUC_1, SUC_2)):
    vigentes = parametros.VigentesMotor.desde_filas(
        [], CORTE, overrides=overrides)
    return pcorr.construir_parametros_corrida(vigentes, list(sucursales))


def test_the_legacy_snapshot_restores_the_legacy_preset():
    params = _snapshot()

    restaurados = pcorr.parametros_motor_desde_snapshot(
        params.snapshot, {"mes_en_curso": _bloque(None)})

    assert restaurados == params.motor


def test_a_snapshot_with_overrides_restores_the_same_engine_parameters():
    params = _snapshot({
        "consolidar_sustituidas": True,
        "incluir_demanda_perdida_en_ponderada": True,
        "factor_demanda_perdida": "2",
        "modo_redondeo_empaque": "ARRIBA",
        "corte_abc_a": "0.7",
        "umbral_f": 3,
    })

    restaurados = pcorr.parametros_motor_desde_snapshot(
        params.snapshot, {"mes_en_curso": _bloque(None)})

    assert restaurados == params.motor
    assert restaurados.consolidar_sustituidas is True
    assert restaurados.factor_demanda_perdida == Fraction(2)
    assert restaurados.modo_redondeo == "ARRIBA"


def test_the_effective_mes_en_curso_block_becomes_engine_parameters():
    params = _snapshot({"tope_proyeccion_mes_actual": "2.5"})

    restaurados = pcorr.parametros_motor_desde_snapshot(
        params.snapshot, {"mes_en_curso": _bloque(
            MesEnCurso("PONDERADO", 14, 30, Fraction(5, 2)))})

    assert restaurados.mes_en_curso == MesEnCurso(
        "PONDERADO", 14, 30, Fraction(5, 2))


def test_an_excluded_effective_mode_leaves_the_engine_without_m0():
    params = _snapshot({"modo_mes_en_curso": "PONDERADO"})

    restaurados = pcorr.parametros_motor_desde_snapshot(
        params.snapshot, {"mes_en_curso": _bloque(None)})

    assert restaurados.mes_en_curso is None


def test_the_days_between_orders_are_restored_per_sucursal():
    params = _snapshot({"dias_entre_pedidos": 15})

    dias = pcorr.dias_entre_pedidos_desde_snapshot(params.snapshot)

    assert dias == {SUC_1: 15, SUC_2: 15}
    assert dias == dict(params.dias_entre_pedidos)
