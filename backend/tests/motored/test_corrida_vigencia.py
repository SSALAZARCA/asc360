"""
Motored Pedidos F3 "Motor", S5a (sdd/motored-pedidos-motor, ADR-6/ADR-12,
decisiones #14/#16): preflight de la corrida -- vigencia por tipo de dato,
antigüedades reportadas y modo efectivo del mes en curso.

`evaluar_vigencia` es puro: recibe los hechos ya leídos (cargas vigentes y
dos banderas de existencia). `cargar_hechos` es la única lectura.
"""
import datetime
import uuid
from datetime import timezone
from fractions import Fraction

import pytest

from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros
from app.motored.services.corridas import codigos, vigencia
from app.motored.services.corridas import parametros_corrida as pcorr
from app.motored.services.corridas.vigencia import CargaVista, HechosVigencia
from tests.motored.conftest import FakeAsyncSession

CORTE = datetime.date(2026, 9, 21)
INICIO_VENTAS = datetime.date(2026, 3, 1)


def _fila(clave, valor):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor,
        vigente_desde=datetime.date(2026, 1, 1), sucursal_id=None,
    )


def _params(**filas):
    """Parámetros congelados; `filas` = clave -> valor de versión global."""
    versiones = [_fila(clave, valor) for clave, valor in filas.items()]
    vigentes = parametros.VigentesMotor.desde_filas(versiones, CORTE)
    return pcorr.construir_parametros_corrida(vigentes, [])


def _carga(tipo, desde=None, hasta=None, aplicado=None, fecha_max=None,
           estado="APLICADO"):
    return CargaVista(
        carga_id=uuid.uuid4(), tipo=tipo, estado=estado,
        periodo_desde=desde, periodo_hasta=hasta,
        aplicado_en=aplicado, fecha_max_detectada=fecha_max,
    )


def _subida(dia, hora=12):
    """Instante en UTC del día dado (12:00 UTC = 07:00 en Bogotá)."""
    return datetime.datetime(
        dia.year, dia.month, dia.day, hora, tzinfo=timezone.utc)


def _ventas(desde=INICIO_VENTAS, hasta=datetime.date(2026, 9, 14),
            fecha_max=datetime.date(2026, 9, 14), **kw):
    return _carga("VENTAS", desde, hasta, _subida(hasta), fecha_max, **kw)


def _inventario(dias_antes, **kw):
    fecha = CORTE - datetime.timedelta(days=dias_antes)
    return _carga("INVENTARIO", fecha, fecha, _subida(fecha), **kw)


def _backorder(dias_antes, **kw):
    fecha = CORTE - datetime.timedelta(days=dias_antes)
    return _carga("BACKORDER", fecha, fecha, _subida(fecha), **kw)


def _subido(tipo, dias_antes, **kw):
    fecha = CORTE - datetime.timedelta(days=dias_antes)
    return _carga(tipo, aplicado=_subida(fecha), **kw)


def _cargas_al_dia():
    return [
        _ventas(), _inventario(2), _backorder(3),
        _subido("FACTURAS_PEDIDOS", 1), _subido("INGRESOS_FACTURAS", 1),
    ]


def _hechos(cargas=None, referencias=True, perdida=True):
    lista = _cargas_al_dia() if cargas is None else cargas
    return HechosVigencia(
        cargas=tuple(lista), hay_referencias=referencias,
        hay_demanda_perdida=perdida,
    )


def _falla(hechos, params=None, corte=CORTE):
    with pytest.raises(vigencia.ErrorVigencia) as info:
        vigencia.evaluar_vigencia(hechos, corte, params or _params())
    return info.value


def _codigos(error):
    return [e["codigo"] for e in error.detalle["errores"]]


# --- Camino feliz y bloque de antigüedad ------------------------------------


def test_everything_fresh_returns_the_age_block_of_every_type():
    resultado = vigencia.evaluar_vigencia(_hechos(), CORTE, _params())

    assert set(resultado.antiguedad) == {
        "inventario", "backorder", "facturas", "ingresos"}
    inventario = resultado.antiguedad["inventario"]
    assert inventario["fecha_usada"] == "2026-09-19"
    assert inventario["antiguedad_dias"] == 2
    assert inventario["limite_dias"] == 7
    assert inventario["fuente_limite"] == "DEFAULT"
    assert resultado.antiguedad["backorder"]["antiguedad_dias"] == 3


def test_age_block_carries_the_carga_id_used():
    cargas = _cargas_al_dia()
    resultado = vigencia.evaluar_vigencia(_hechos(cargas), CORTE, _params())

    assert resultado.antiguedad["inventario"]["carga_id"] == str(
        cargas[1].carga_id)
    assert resultado.cargas_usadas["inventario"] == (cargas[1].carga_id,)


def test_seleccion_datos_embeds_the_age_block_and_the_cortes():
    resultado = vigencia.evaluar_vigencia(_hechos(), CORTE, _params())

    assert resultado.seleccion_datos["antiguedad"] == resultado.antiguedad
    assert resultado.seleccion_datos["cortes"] == {
        "inventario": "2026-09-19", "backorder": "2026-09-18"}
    assert resultado.seleccion_datos["meses_cerrados"] == [
        "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]


# --- Inventario y backorder: fecha de la foto vs corte ----------------------


def test_inventario_missing_is_e_002_and_lists_the_absent_type():
    hechos = _hechos([c for c in _cargas_al_dia() if c.tipo != "INVENTARIO"])

    error = _falla(hechos)

    assert error.codigo == codigos.E_CORRIDA_INVENTARIO_AUSENTE
    ausente = error.detalle["antiguedad"]["inventario"]
    assert ausente["carga_id"] is None and ausente["fecha_usada"] is None
    assert ausente["limite_dias"] == 7


def test_inventario_older_than_the_limit_is_e_003_naming_age_and_limit():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "INVENTARIO"]

    error = _falla(_hechos(cargas + [_inventario(8)]))

    assert error.codigo == codigos.E_CORRIDA_INVENTARIO_VIEJO
    assert "8" in error.mensaje and "7" in error.mensaje
    assert "inventario" in error.mensaje.lower()
    assert error.detalle["antiguedad"]["inventario"]["antiguedad_dias"] == 8


def test_inventario_exactly_at_the_limit_is_accepted():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "INVENTARIO"]

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas + [_inventario(7)]), CORTE, _params())

    assert resultado.antiguedad["inventario"]["antiguedad_dias"] == 7


def test_backorder_missing_is_e_004_and_stale_is_e_005():
    sin = [c for c in _cargas_al_dia() if c.tipo != "BACKORDER"]

    ausente = _falla(_hechos(sin))
    viejo = _falla(_hechos(sin + [_backorder(9)]))

    assert ausente.codigo == codigos.E_CORRIDA_BACKORDER_AUSENTE
    assert viejo.codigo == codigos.E_CORRIDA_BACKORDER_VIEJO
    assert "9" in viejo.mensaje


def test_as_of_selection_takes_the_latest_snapshot_not_after_the_corte():
    corte = datetime.date(2026, 9, 5)
    d1, d8 = datetime.date(2026, 9, 1), datetime.date(2026, 9, 8)
    cargas = [
        _carga("INVENTARIO", d1, d1, _subida(d1)),
        _carga("INVENTARIO", d8, d8, _subida(d8)),
        _ventas(fecha_max=None), _backorder(0),
        _subido("FACTURAS_PEDIDOS", 0), _subido("INGRESOS_FACTURAS", 0),
    ]
    cargas[3] = _carga("BACKORDER", corte, corte, _subida(corte))

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas), corte, _params())

    assert resultado.antiguedad["inventario"]["fecha_usada"] == "2026-09-01"
    assert resultado.antiguedad["inventario"]["antiguedad_dias"] == 4


def test_annulled_cargas_are_ignored():
    anulada = _inventario(0, estado="ANULADO")
    cargas = [c for c in _cargas_al_dia() if c.tipo != "INVENTARIO"]

    error = _falla(_hechos(cargas + [anulada]))

    assert error.codigo == codigos.E_CORRIDA_INVENTARIO_AUSENTE


# --- Facturas e ingresos: fecha de aplicación en Bogotá ---------------------


def test_facturas_missing_is_e_006_with_an_actionable_message():
    sin = [c for c in _cargas_al_dia() if c.tipo != "FACTURAS_PEDIDOS"]

    error = _falla(_hechos(sin))

    assert error.codigo == codigos.E_CORRIDA_FACTURAS_AUSENTE_O_VIEJA
    assert "facturas" in error.mensaje.lower()
    assert "None" not in error.mensaje


def test_facturas_stale_is_e_006_and_ingresos_stale_is_e_007():
    sin = [c for c in _cargas_al_dia()
           if c.tipo not in ("FACTURAS_PEDIDOS", "INGRESOS_FACTURAS")]
    cargas = sin + [
        _subido("FACTURAS_PEDIDOS", 10), _subido("INGRESOS_FACTURAS", 12)]

    error = _falla(_hechos(cargas))

    assert _codigos(error) == [
        codigos.E_CORRIDA_FACTURAS_AUSENTE_O_VIEJA,
        codigos.E_CORRIDA_INGRESOS_AUSENTE_O_VIEJO,
    ]
    assert "10" in error.detalle["errores"][0]["mensaje"]
    assert "12" in error.detalle["errores"][1]["mensaje"]


def test_ingresos_missing_is_e_007():
    sin = [c for c in _cargas_al_dia() if c.tipo != "INGRESOS_FACTURAS"]

    assert _falla(_hechos(sin)).codigo == (
        codigos.E_CORRIDA_INGRESOS_AUSENTE_O_VIEJO)


def test_facturas_age_uses_the_bogota_date_of_aplicado_en():
    # 03:00 UTC del 20 = 22:00 del 19 en Bogotá (UTC-5).
    tarde = datetime.datetime(2026, 9, 20, 3, tzinfo=timezone.utc)
    cargas = [c for c in _cargas_al_dia() if c.tipo != "FACTURAS_PEDIDOS"]
    cargas.append(_carga("FACTURAS_PEDIDOS", aplicado=tarde))

    resultado = vigencia.evaluar_vigencia(_hechos(cargas), CORTE, _params())

    assert resultado.antiguedad["facturas"]["fecha_usada"] == "2026-09-19"
    assert resultado.antiguedad["facturas"]["antiguedad_dias"] == 2


def test_facturas_uploaded_after_the_corte_are_valid_with_age_zero():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "FACTURAS_PEDIDOS"]
    cargas.append(_subido("FACTURAS_PEDIDOS", -3))

    resultado = vigencia.evaluar_vigencia(_hechos(cargas), CORTE, _params())

    assert resultado.antiguedad["facturas"]["antiguedad_dias"] == 0


def test_the_latest_facturas_carga_is_the_one_reported():
    viejo = _subido("FACTURAS_PEDIDOS", 6)
    nuevo = _subido("FACTURAS_PEDIDOS", 1)
    cargas = [c for c in _cargas_al_dia() if c.tipo != "FACTURAS_PEDIDOS"]

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas + [viejo, nuevo]), CORTE, _params())

    assert resultado.antiguedad["facturas"]["carga_id"] == str(
        nuevo.carga_id)


# --- Límites por tipo (decisión #16) ----------------------------------------


def test_raising_one_limit_accepts_older_data_of_that_type_only():
    params = _params(max_dias_antiguedad_facturas=15)
    sin = [c for c in _cargas_al_dia()
           if c.tipo not in ("FACTURAS_PEDIDOS", "INVENTARIO")]

    resultado = vigencia.evaluar_vigencia(
        _hechos(sin + [_subido("FACTURAS_PEDIDOS", 12), _inventario(2)]),
        CORTE, params)
    error = _falla(
        _hechos(sin + [_subido("FACTURAS_PEDIDOS", 12), _inventario(12)]),
        params)

    facturas = resultado.antiguedad["facturas"]
    assert facturas["antiguedad_dias"] == 12
    assert facturas["limite_dias"] == 15
    assert facturas["fuente_limite"] == "GLOBAL"
    assert _codigos(error) == [codigos.E_CORRIDA_INVENTARIO_VIEJO]


def test_a_failure_still_carries_the_age_block_of_every_type():
    error = _falla(_hechos([_ventas(), _inventario(9)]))

    assert set(error.detalle["antiguedad"]) == {
        "inventario", "backorder", "facturas", "ingresos"}
    assert error.detalle["antiguedad"]["inventario"]["antiguedad_dias"] == 9
    assert _codigos(error) == [
        codigos.E_CORRIDA_INVENTARIO_VIEJO,
        codigos.E_CORRIDA_BACKORDER_AUSENTE,
        codigos.E_CORRIDA_FACTURAS_AUSENTE_O_VIEJA,
        codigos.E_CORRIDA_INGRESOS_AUSENTE_O_VIEJO,
    ]


# --- Ventas de los seis meses cerrados y maestro de referencias -------------


def test_a_closed_month_without_ventas_is_e_001_naming_the_month():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(desde=datetime.date(2026, 4, 1)))

    error = _falla(_hechos(cargas))

    assert error.codigo == codigos.E_CORRIDA_VENTAS_SIN_CUBRIR
    assert "marzo de 2026" in error.mensaje


def test_ventas_split_across_two_cargas_cover_the_window_together():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(
        desde=datetime.date(2026, 3, 1), hasta=datetime.date(2026, 6, 30),
        fecha_max=None))
    cargas.append(_ventas(desde=datetime.date(2026, 7, 1)))

    resultado = vigencia.evaluar_vigencia(_hechos(cargas), CORTE, _params())

    assert len(resultado.cargas_usadas["ventas"]) == 2


def test_an_annulled_ventas_carga_does_not_cover():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(estado="ANULADO"))

    assert _falla(_hechos(cargas)).codigo == (
        codigos.E_CORRIDA_VENTAS_SIN_CUBRIR)


def test_missing_referencias_master_is_e_008():
    error = _falla(_hechos(referencias=False))

    assert error.codigo == codigos.E_CORRIDA_MAESTRO_REFERENCIAS_AUSENTE
    assert "referencias" in error.mensaje.lower()


def test_a_global_failure_reports_every_error_and_returns_no_result():
    error = _falla(_hechos([], referencias=False))

    assert _codigos(error)[0] == codigos.E_CORRIDA_VENTAS_SIN_CUBRIR
    assert codigos.E_CORRIDA_MAESTRO_REFERENCIAS_AUSENTE in _codigos(error)
    assert error.codigo == _codigos(error)[0]


# --- Demanda perdida: sólo un aviso -----------------------------------------


def test_missing_lost_demand_is_a_warning_and_never_blocks():
    resultado = vigencia.evaluar_vigencia(
        _hechos(perdida=False), CORTE, _params())

    assert [a.codigo for a in resultado.advertencias] == [
        codigos.A_CORRIDA_DEMANDA_PERDIDA_AUSENTE]


def test_present_lost_demand_adds_no_warning():
    resultado = vigencia.evaluar_vigencia(_hechos(), CORTE, _params())

    assert resultado.advertencias == ()


# --- Mes en curso: modo efectivo --------------------------------------------


def _ponderado(**extra):
    return _params(modo_mes_en_curso="PONDERADO", **extra)


def _mes(resultado):
    return resultado.seleccion_datos["mes_en_curso"]


def test_configured_excluido_is_effective_excluido_without_warning():
    resultado = vigencia.evaluar_vigencia(_hechos(), CORTE, _params())

    assert resultado.mes_en_curso.mes_en_curso is None
    assert resultado.advertencias == ()
    assert _mes(resultado)["modo_configurado"] == "EXCLUIDO"
    assert _mes(resultado)["modo_efectivo"] == "EXCLUIDO"
    assert _mes(resultado)["d"] is None


def test_weekly_corte_on_the_21st_with_last_sale_on_the_14th_gives_d_14():
    cargas = _cargas_al_dia()

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas), CORTE, _ponderado())

    efectivo = resultado.mes_en_curso.mes_en_curso
    assert (efectivo.modo, efectivo.dias_transcurridos,
            efectivo.dias_del_mes) == ("PONDERADO", 14, 30)
    assert efectivo.tope == Fraction(3)
    bloque = _mes(resultado)
    assert bloque["modo_efectivo"] == "PONDERADO"
    assert (bloque["d"], bloque["D"], bloque["w0"]) == (14, 30, "49/15")
    assert bloque["fecha_ultima_venta_m0"] == "2026-09-14"
    assert bloque["carga_ids"] == [str(cargas[0].carga_id)]


def test_last_sale_after_the_corte_is_capped_at_the_corte_day():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(fecha_max=datetime.date(2026, 9, 28)))

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas), CORTE, _ponderado())

    assert resultado.mes_en_curso.mes_en_curso.dias_transcurridos == 21


def test_without_a_carga_covering_m0_it_falls_back_with_a_105_warning():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(hasta=datetime.date(2026, 8, 31)))

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas), CORTE, _ponderado())

    assert resultado.mes_en_curso.mes_en_curso is None
    assert [a.codigo for a in resultado.advertencias] == [
        codigos.A_CORRIDA_MES_EN_CURSO_NO_DISPONIBLE]
    assert _mes(resultado)["modo_efectivo"] == "EXCLUIDO"
    assert _mes(resultado)["motivo"] == "A-CORRIDA-105"


def test_carga_without_fecha_max_detectada_falls_back_with_105():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(fecha_max=None))

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas), CORTE, _ponderado())

    assert resultado.mes_en_curso.mes_en_curso is None
    assert resultado.advertencias[0].codigo == (
        codigos.A_CORRIDA_MES_EN_CURSO_NO_DISPONIBLE)


def test_a_covering_carga_without_the_key_does_not_veto_one_with_it():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(fecha_max=None))
    cargas.append(_ventas(fecha_max=datetime.date(2026, 9, 14)))

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas), CORTE, _ponderado())

    assert resultado.mes_en_curso.mes_en_curso.dias_transcurridos == 14


def test_an_annulled_m0_carga_is_ignored():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(estado="ANULADO"))
    cargas.append(_ventas(hasta=datetime.date(2026, 8, 31), fecha_max=None))

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas), CORTE, _ponderado())

    assert resultado.mes_en_curso.mes_en_curso is None


def test_last_sale_before_the_month_starts_gives_d_below_one_and_105():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(fecha_max=datetime.date(2026, 8, 31)))

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas), CORTE, _ponderado())

    assert resultado.advertencias[0].codigo == (
        codigos.A_CORRIDA_MES_EN_CURSO_NO_DISPONIBLE)


@pytest.mark.parametrize("ultima, esperado", [
    (datetime.date(2026, 9, 4), codigos.A_CORRIDA_MES_EN_CURSO_CORTO),
    (datetime.date(2026, 9, 5), None),
])
def test_d_below_min_dias_is_106_and_d_equal_is_ponderado(ultima, esperado):
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(fecha_max=ultima))

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas), CORTE, _ponderado())

    if esperado is None:
        assert resultado.mes_en_curso.mes_en_curso.dias_transcurridos == 5
        assert resultado.advertencias == ()
    else:
        assert resultado.mes_en_curso.mes_en_curso is None
        assert [a.codigo for a in resultado.advertencias] == [esperado]
        assert "4 días" in resultado.advertencias[0].mensaje


def test_min_dias_is_read_from_the_frozen_parameters():
    cargas = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    cargas.append(_ventas(fecha_max=datetime.date(2026, 9, 7)))

    resultado = vigencia.evaluar_vigencia(
        _hechos(cargas), CORTE, _ponderado(min_dias_mes_actual=10))

    assert resultado.advertencias[0].codigo == (
        codigos.A_CORRIDA_MES_EN_CURSO_CORTO)


def test_m0_never_blocks_the_corrida_and_outputs_equal_excluido():
    sin_m0 = [c for c in _cargas_al_dia() if c.tipo != "VENTAS"]
    sin_m0.append(_ventas(hasta=datetime.date(2026, 8, 31)))

    resultado = vigencia.evaluar_vigencia(
        _hechos(sin_m0), CORTE, _ponderado())

    assert resultado.antiguedad["inventario"]["antiguedad_dias"] == 2


# --- Lectura: una sola consulta por hecho -----------------------------------


class _Fila:
    def __init__(self, **campos):
        self.__dict__.update(campos)


async def test_cargar_hechos_maps_rows_and_existence_flags():
    fila_id = uuid.uuid4()
    fila = _Fila(
        id=fila_id, tipo="VENTAS", estado="APLICADO",
        periodo_desde=INICIO_VENTAS, periodo_hasta=CORTE,
        aplicado_en=_subida(CORTE), fecha_max="2026-09-14",
    )
    db = FakeAsyncSession(execute_queue=[[fila], [1], [1]])

    hechos = await vigencia.cargar_hechos(db, CORTE)

    carga = hechos.cargas[0]
    assert carga.carga_id == fila_id
    assert carga.fecha_max_detectada == datetime.date(2026, 9, 14)
    assert hechos.hay_referencias and hechos.hay_demanda_perdida
    assert len(db.executed_statements) == 3


async def test_cargar_hechos_reports_absent_masters_and_lost_demand():
    db = FakeAsyncSession(execute_queue=[[], [], []])

    hechos = await vigencia.cargar_hechos(db, CORTE)

    assert hechos.cargas == ()
    assert not hechos.hay_referencias and not hechos.hay_demanda_perdida


async def test_the_cargas_query_never_loads_the_bot_lost_demand_headers():
    db = FakeAsyncSession(execute_queue=[[], [], []])

    await vigencia.cargar_hechos(db, CORTE)

    sql = str(db.executed_statements[0]).upper()
    assert "APLICADO" in sql or "ESTADO" in sql
    assert "TIPO IN" in sql


# --- API publica para el aviso anticipado de antiguedad -----------------


def test_tipos_antiguedad_expone_los_cuatro_tipos_del_preflight():
    assert set(vigencia.TIPOS_ANTIGUEDAD) == {
        "inventario", "backorder", "facturas", "ingresos"}
    assert vigencia.TIPOS_ANTIGUEDAD["inventario"][0] == "INVENTARIO"


def test_elegir_carga_vigente_usa_la_misma_regla_que_el_preflight():
    vieja = _carga("INVENTARIO", desde=datetime.date(2026, 9, 14))
    nueva = _carga("INVENTARIO", desde=datetime.date(2026, 9, 18))
    futura = _carga("INVENTARIO", desde=datetime.date(2026, 9, 25))

    carga, fecha = vigencia.elegir_carga_vigente(
        [vieja, nueva, futura], "inventario", CORTE)

    assert carga is nueva and fecha == datetime.date(2026, 9, 18)


def test_elegir_carga_vigente_sin_cargas_devuelve_none():
    assert vigencia.elegir_carga_vigente([], "backorder", CORTE) == (
        None, None)
