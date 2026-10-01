"""
Motored Pedidos F3 "Motor", S6a (sdd/motored-pedidos-motor, ADR-3/ADR-4/
ADR-5/ADR-9, decisiones #14 y #16): servicio de la corrida.

`crear_corrida` valida, corre el preflight de forma SÍNCRONA y congela los
insumos; `calcular_corrida` recorre las sucursales (aislando las que
fallan) y `finalizar_corrida` decide BORRADOR o FALLIDA; `anular_corrida`
aplica la regla de anulación (desde F4 cerrar es por tienda y se prueba en
`test_pedido_tienda.py`). Los colaboradores con
su propia suite (parámetros, preflight, cargador, persistencia) se
reemplazan por dobles; el recorrido real corre en `pg_real`.
"""
import dataclasses
import datetime
import uuid
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.services import parametros
from app.motored.services.corridas import cargador as cg
from app.motored.services.corridas import codigos, estados
from app.motored.services.corridas import parametros_corrida as pcorr
from app.motored.services.corridas import persistencia as pe
from app.motored.services.corridas import servicio as sv
from app.motored.services.corridas import transito_corte as tc
from app.motored.services.corridas import vigencia as vg
from app.motored.services.corridas.cargador import (
    DatosSucursal, ErrorCargador)
from app.motored.services.motor.mes_en_curso import ResolucionMesEnCurso
from app.motored.services.motor.tipos import (
    Advertencia, MesEnCurso, NodoMaestro)
from tests.motored.conftest import FakeAsyncSession
from tests.motored.fixtures.motor.constructores import (
    atributos,
    fila_patron,
)

CORTE = datetime.date(2026, 9, 21)
SUC_A, SUC_B = uuid.UUID(int=101), uuid.UUID(int=102)
PROVEEDOR_ID = uuid.uuid4()
CARGA_VENTAS, CARGA_INV = uuid.uuid4(), uuid.uuid4()
USUARIO = uuid.uuid4()


class _Savepoint:
    """`begin_nested()` de juguete: deshace lo agregado si el bloque falla."""

    def __init__(self, sesion):
        self._sesion = sesion

    async def __aenter__(self):
        self._marca = len(self._sesion.added)
        self._sesion.savepoints += 1
        return self

    async def __aexit__(self, tipo, valor, traza):
        if tipo is not None:
            del self._sesion.added[self._marca:]
        return False


class Sesion(FakeAsyncSession):
    def __init__(self, *args, errores_flush=(), **kwargs):
        super().__init__(*args, **kwargs)
        self._errores_flush = list(errores_flush)
        self.savepoints = 0

    def begin_nested(self):
        return _Savepoint(self)

    async def flush(self):
        if self._errores_flush:
            raise self._errores_flush.pop(0)


def _sucursal(sucursal_id, nombre, activa=True):
    return SimpleNamespace(id=sucursal_id, nombre=nombre, activa=activa)


def _params(sucursales=(SUC_A, SUC_B), filas=(), overrides=None):
    vigentes = parametros.VigentesMotor.desde_filas(
        filas, CORTE, overrides=overrides)
    return pcorr.construir_parametros_corrida(vigentes, list(sucursales))


def _bloque_m0(modo="EXCLUIDO", d=None, D=None):
    return {
        "modo_configurado": "EXCLUIDO", "modo_efectivo": modo, "d": d,
        "D": D, "w0": None, "fecha_ultima_venta_m0": None,
        "carga_ids": [], "motivo": None}


def _antiguedad(dias=2, limite=7):
    return {
        tipo: {
            "carga_id": str(CARGA_INV), "fecha_usada": "2026-09-19",
            "antiguedad_dias": dias, "limite_dias": limite,
            "fuente_limite": "DEFAULT"}
        for tipo in ("inventario", "backorder", "facturas", "ingresos")}


def _vigencia(avisos=()):
    seleccion = {
        "antiguedad": _antiguedad(),
        "cortes": {"inventario": "2026-09-19", "backorder": "2026-09-18"},
        "meses_cerrados": ["2026-03", "2026-04", "2026-05", "2026-06",
                           "2026-07", "2026-08"],
        "mes_en_curso": _bloque_m0(),
        "cargas_usadas": {},
    }
    return vg.ResultadoVigencia(
        antiguedad=seleccion["antiguedad"],
        mes_en_curso=ResolucionMesEnCurso(None),
        seleccion_datos=seleccion,
        advertencias=tuple(avisos),
        cargas_usadas={
            "ventas": (CARGA_VENTAS,), "inventario": (CARGA_INV,)})


@pytest.fixture
def entorno(monkeypatch):
    """Dobles de los colaboradores que tienen su propia suite."""
    estado = SimpleNamespace(
        params=_params(), vigencia=_vigencia(), maestro=[],
        error_preflight=None, llamadas=[], cargas_perdida=())

    async def proveedor(db):
        return cg.FilaProveedor(PROVEEDOR_ID, 4, 5, Decimal("3"))

    async def maestro(db, proveedor_id):
        return {n.referencia_id: n for n in estado.maestro}

    async def cargar_params(db, en_fecha, sucursal_ids, overrides=None):
        estado.llamadas.append(("params", en_fecha, list(sucursal_ids)))
        return estado.params

    async def preflight(db, fecha_corte, params):
        estado.llamadas.append(("preflight", fecha_corte))
        if estado.error_preflight is not None:
            raise estado.error_preflight
        return estado.vigencia

    async def perdida(db, fecha_corte, con_m0):
        estado.llamadas.append(("perdida", fecha_corte, con_m0))
        return estado.cargas_perdida

    monkeypatch.setattr(sv.cargador, "cargar_proveedor_principal", proveedor)
    monkeypatch.setattr(sv.cargador, "cargar_maestro", maestro)
    monkeypatch.setattr(
        sv.parametros_corrida, "cargar_parametros_corrida", cargar_params)
    monkeypatch.setattr(sv.vigencia, "ejecutar_preflight", preflight)
    monkeypatch.setattr(
        sv.cargas_perdida, "cargas_demanda_perdida_excel", perdida)
    return estado


def _cola_crear(ultimo_codigo=None, sucursales=None):
    sucursales = sucursales if sucursales is not None else [
        _sucursal(SUC_B, "B SUCURSAL"), _sucursal(SUC_A, "A SUCURSAL")]
    return [sucursales, [] if ultimo_codigo is None else [ultimo_codigo]]


async def _crear(db, **kwargs):
    base = dict(fecha_corte=CORTE, hoy=CORTE, usuario_id=USUARIO)
    return await sv.crear_corrida(db, **{**base, **kwargs})


def _corrida_de(db):
    return db.added_of_type(Corrida)[-1]


# --- Código de la corrida ---------------------------------------------------


def test_the_codigo_uses_the_iso_year_and_week_of_the_corte():
    assert sv.formatear_codigo("PED", datetime.date(2026, 9, 21), 1) == (
        "PED-2026-S39-001")


def test_the_codigo_uses_the_iso_year_not_the_calendar_year():
    assert sv.formatear_codigo("PED", datetime.date(2027, 1, 1), 12) == (
        "PED-2026-S53-012")


def test_the_codigo_fits_the_column_even_with_a_four_digit_sequence():
    codigo = sv.formatear_codigo("ESC", datetime.date(2026, 9, 21), 1234)

    assert codigo == "ESC-2026-S39-1234" and len(codigo) <= 30


# --- crear_corrida ----------------------------------------------------------


async def test_creating_a_corrida_stores_it_pending_with_its_codigo(entorno):
    db = Sesion(execute_queue=_cola_crear())

    corrida = await _crear(db)

    assert corrida is _corrida_de(db)
    assert corrida.codigo == "PED-2026-S39-001"
    assert corrida.estado == "PENDIENTE"
    assert corrida.es_escenario is False
    assert corrida.proveedor_id == PROVEEDOR_ID
    assert corrida.fecha_corte == CORTE
    assert corrida.usuario_id == USUARIO


async def test_the_next_codigo_follows_the_last_one_of_the_week(entorno):
    db = Sesion(execute_queue=_cola_crear("PED-2026-S39-007"))

    corrida = await _crear(db)

    assert corrida.codigo == "PED-2026-S39-008"


async def test_a_unique_conflict_retries_with_the_next_number(entorno):
    conflicto = IntegrityError("INSERT", {}, Exception("duplicate key"))
    db = Sesion(
        execute_queue=_cola_crear("PED-2026-S39-002"),
        errores_flush=[conflicto])

    corrida = await _crear(db)

    assert corrida.codigo == "PED-2026-S39-004"
    assert len(db.added_of_type(Corrida)) == 1


async def test_persistent_unique_conflicts_give_up_after_five_attempts(
        entorno):
    conflicto = IntegrityError("INSERT", {}, Exception("duplicate key"))
    db = Sesion(
        execute_queue=_cola_crear(), errores_flush=[conflicto] * 5)

    with pytest.raises(IntegrityError):
        await _crear(db)

    assert db.added_of_type(Corrida) == []


async def test_a_scenario_corrida_has_the_esc_prefix_and_keeps_overrides(
        entorno):
    db = Sesion(execute_queue=_cola_crear())
    overrides = {"consolidar_sustituidas": True}

    corrida = await _crear(db, overrides=overrides)

    assert corrida.es_escenario is True
    assert corrida.codigo == "ESC-2026-S39-001"
    assert corrida.overrides == overrides


async def test_a_production_corrida_has_no_overrides(entorno):
    corrida = await _crear(Sesion(execute_queue=_cola_crear()))

    assert corrida.overrides is None


async def test_all_active_sucursales_is_the_todas_scope_in_name_order(
        entorno):
    db = Sesion(execute_queue=_cola_crear())

    corrida = await _crear(db)

    filas = db.added_of_type(CorridaSucursal)
    assert corrida.alcance == "TODAS" and corrida.sucursales_total == 2
    assert [(f.sucursal_id, f.orden, f.estado) for f in filas] == [
        (SUC_A, 1, "PENDIENTE"), (SUC_B, 2, "PENDIENTE")]
    assert all(f.corrida_id == corrida.id for f in filas)


async def test_a_selection_is_the_seleccion_scope(entorno):
    db = Sesion(execute_queue=_cola_crear(
        sucursales=[_sucursal(SUC_A, "A SUCURSAL")]))

    corrida = await _crear(db, sucursal_ids=[SUC_A])

    assert corrida.alcance == "SELECCION" and corrida.sucursales_total == 1
    assert [f.sucursal_id for f in db.added_of_type(CorridaSucursal)] == [
        SUC_A]


async def test_an_unknown_sucursal_is_rejected_with_its_id(entorno):
    db = Sesion(execute_queue=[[_sucursal(SUC_A, "A SUCURSAL")]])

    with pytest.raises(pe.ErrorCorrida) as error:
        await _crear(db, sucursal_ids=[SUC_A, SUC_B])

    assert error.value.codigo == codigos.E_CORRIDA_SUCURSAL_INVALIDA
    assert str(SUC_B) in error.value.mensaje
    assert db.added == []


async def test_an_inactive_sucursal_is_rejected_by_name(entorno):
    db = Sesion(execute_queue=[[_sucursal(SUC_A, "CERRADA S.A.", False)]])

    with pytest.raises(pe.ErrorCorrida) as error:
        await _crear(db, sucursal_ids=[SUC_A])

    assert error.value.codigo == codigos.E_CORRIDA_SUCURSAL_INVALIDA
    assert "CERRADA S.A." in error.value.mensaje


async def test_a_network_without_active_sucursales_is_rejected(entorno):
    db = Sesion(execute_queue=[[]])

    with pytest.raises(pe.ErrorCorrida) as error:
        await _crear(db)

    assert error.value.codigo == codigos.E_CORRIDA_SUCURSAL_INVALIDA


async def test_a_future_corte_is_rejected_before_any_query(entorno):
    db = Sesion()

    with pytest.raises(pe.ErrorCorrida) as error:
        await _crear(db, hoy=CORTE - datetime.timedelta(days=1))

    assert error.value.codigo == codigos.E_CORRIDA_CORTE_FUTURO
    assert db.executed_statements == []


async def test_a_corte_equal_to_today_is_accepted(entorno):
    corrida = await _crear(Sesion(execute_queue=_cola_crear()))

    assert corrida.fecha_corte == CORTE


async def test_an_invalid_override_is_rejected_before_any_query(entorno):
    db = Sesion()

    with pytest.raises(pe.ErrorCorrida) as error:
        await _crear(db, overrides={"clave_que_no_existe": 1})

    assert error.value.codigo == codigos.E_CORRIDA_OVERRIDE_INVALIDO
    assert db.executed_statements == []


async def test_a_bad_override_value_is_rejected(entorno):
    with pytest.raises(pe.ErrorCorrida) as error:
        await _crear(Sesion(), overrides={"dias_entre_pedidos": 0})

    assert error.value.codigo == codigos.E_CORRIDA_OVERRIDE_INVALIDO


async def test_the_parameters_are_resolved_at_the_corte(entorno):
    await _crear(Sesion(execute_queue=_cola_crear()))

    assert ("params", CORTE, [SUC_A, SUC_B]) in entorno.llamadas
    assert ("preflight", CORTE) in entorno.llamadas


async def test_a_late_creation_still_resolves_the_parameters_at_the_corte(
        entorno):
    db = Sesion(execute_queue=_cola_crear())

    corrida = await _crear(db, hoy=CORTE + datetime.timedelta(days=3))

    assert ("params", CORTE, [SUC_A, SUC_B]) in entorno.llamadas
    assert corrida.parametros_en_fecha == CORTE


async def test_a_failed_preflight_is_a_coded_error_with_the_age_detail(
        entorno):
    entorno.error_preflight = vg.ErrorVigencia(
        [{"codigo": "E-CORRIDA-003", "mensaje": "Los datos de inventario "
          "tienen 9 días y el máximo permitido es 7."}],
        {"inventario": {"antiguedad_dias": 9, "limite_dias": 7}})
    db = Sesion(execute_queue=_cola_crear())

    with pytest.raises(pe.ErrorCorrida) as error:
        await _crear(db)

    assert error.value.codigo == "E-CORRIDA-003"
    assert "9 días" in error.value.mensaje
    assert error.value.detalle["antiguedad"]["inventario"][
        "antiguedad_dias"] == 9
    assert error.value.detalle["errores"][0]["codigo"] == "E-CORRIDA-003"
    assert db.added == []


async def test_the_snapshot_and_the_input_ages_are_stored_on_the_corrida(
        entorno):
    corrida = await _crear(Sesion(execute_queue=_cola_crear()))

    assert corrida.parametros_snapshot == entorno.params.snapshot
    assert corrida.parametros_en_fecha == CORTE
    antiguedad = corrida.seleccion_datos["antiguedad"]
    assert set(antiguedad) == {
        "inventario", "backorder", "facturas", "ingresos"}
    assert antiguedad["inventario"] == {
        "carga_id": str(CARGA_INV), "fecha_usada": "2026-09-19",
        "antiguedad_dias": 2, "limite_dias": 7, "fuente_limite": "DEFAULT"}


async def test_the_mes_en_curso_block_and_the_cortes_are_stored(entorno):
    entorno.vigencia.seleccion_datos["mes_en_curso"] = _bloque_m0(
        "PONDERADO", 14, 30)

    corrida = await _crear(Sesion(execute_queue=_cola_crear()))

    assert corrida.seleccion_datos["mes_en_curso"]["d"] == 14
    assert corrida.seleccion_datos["cortes"] == {
        "inventario": "2026-09-19", "backorder": "2026-09-18"}


async def test_the_preflight_warnings_are_stored_as_plain_json(entorno):
    entorno.vigencia = _vigencia([
        Advertencia("A-CORRIDA-105", "Sin ventas del mes en curso")])

    corrida = await _crear(Sesion(execute_queue=_cola_crear()))

    assert corrida.seleccion_datos["advertencias"] == [
        {"codigo": "A-CORRIDA-105",
         "mensaje": "Sin ventas del mes en curso"}]


async def test_the_substitution_master_is_stored_as_json(entorno):
    a, b = uuid.UUID(int=7), uuid.UUID(int=8)
    entorno.maestro = [
        NodoMaestro(a, False, b), NodoMaestro(b, False, None)]

    corrida = await _crear(Sesion(execute_queue=_cola_crear()))

    assert corrida.maestro_sustitucion == [
        {"referencia_id": str(a), "activa": False,
         "sustituida_por": str(b)},
        {"referencia_id": str(b), "activa": False,
         "sustituida_por": None},
    ]


async def test_the_used_cargas_are_linked_to_the_new_corrida(entorno):
    db = Sesion(execute_queue=_cola_crear())

    corrida = await _crear(db)

    vinculos = {(v.carga_id, v.tipo) for v in db.added_of_type(CorridaCarga)}
    assert vinculos == {
        (CARGA_VENTAS, "VENTAS"), (CARGA_INV, "INVENTARIO")}
    assert all(
        v.corrida_id == corrida.id for v in db.added_of_type(CorridaCarga))


async def test_the_excel_lost_demand_cargas_are_linked_too(entorno):
    uno, dos = uuid.UUID(int=31), uuid.UUID(int=32)
    entorno.cargas_perdida = (uno, dos)
    db = Sesion(execute_queue=_cola_crear())

    await _crear(db)

    vinculos = {(v.carga_id, v.tipo) for v in db.added_of_type(CorridaCarga)}
    assert vinculos == {
        (CARGA_VENTAS, "VENTAS"), (CARGA_INV, "INVENTARIO"),
        (uno, "DEMANDA_PERDIDA"), (dos, "DEMANDA_PERDIDA")}


async def test_the_lost_demand_window_ignores_the_current_month_by_default(
        entorno):
    await _crear(Sesion(execute_queue=_cola_crear()))

    assert ("perdida", CORTE, False) in entorno.llamadas


async def test_the_lost_demand_window_takes_the_current_month_if_ponderado(
        entorno):
    entorno.vigencia.seleccion_datos["mes_en_curso"] = _bloque_m0(
        "PONDERADO", d=14, D=30)

    await _crear(Sesion(execute_queue=_cola_crear()))

    assert ("perdida", CORTE, True) in entorno.llamadas


async def test_the_nota_is_kept_in_the_creation_event(entorno):
    corrida = await _crear(
        Sesion(execute_queue=_cola_crear()), nota="Corrida de prueba")

    assert corrida.log[0]["nota"] == "Corrida de prueba"


async def test_no_nota_leaves_the_creation_event_without_the_key(entorno):
    corrida = await _crear(Sesion(execute_queue=_cola_crear()))

    assert "nota" not in corrida.log[0]


async def test_the_creation_event_opens_the_append_only_log(entorno):
    corrida = await _crear(Sesion(execute_queue=_cola_crear()))

    assert [e["evento"] for e in corrida.log] == ["CREADA"]
    assert corrida.log[0]["usuario_id"] == str(USUARIO)


# --- calcular_corrida -------------------------------------------------------


def _corrida_congelada(*, consolidar=False, m0=None, maestro=None):
    overrides = {"consolidar_sustituidas": True} if consolidar else None
    params = _params(overrides=overrides)
    seleccion = _vigencia().seleccion_datos
    if m0 is not None:
        seleccion["mes_en_curso"] = _bloque_m0(
            "PONDERADO", m0.dias_transcurridos, m0.dias_del_mes)
    return Corrida(
        id=uuid.UUID(int=555), codigo="PED-2026-S39-001",
        proveedor_id=PROVEEDOR_ID, fecha_corte=CORTE, estado="CALCULANDO",
        parametros_en_fecha=CORTE, parametros_snapshot=params.snapshot,
        seleccion_datos=seleccion, maestro_sustitucion=maestro or [],
        sucursales_total=2)


class Grabador:
    """Doble de la carga, el guardado y el tránsito de `calcular_corrida`:
    anota cada llamada y falla donde el test lo pida."""

    def __init__(self):
        self.guardadas = []
        self.fallidas = []
        self.contextos = []
        self.transito = []
        self.finalizadas = []
        self.fallos = {}
        self.guardar_falla = None

    async def cargar_sucursal(self, db, sucursal_id, ctx):
        self.contextos.append(ctx)
        if sucursal_id in self.fallos:
            raise self.fallos[sucursal_id]
        return DatosSucursal(
            dataclasses.replace(atributos(), sucursal_id=sucursal_id),
            (fila_patron(),))

    async def guardar(self, db, corrida_id, datos, resultado, *,
                      consolidar=False):
        if self.guardar_falla is not None:
            raise self.guardar_falla
        self.guardadas.append(
            (corrida_id, datos.atributos.sucursal_id, resultado.estado,
             consolidar))

    async def marcar(self, db, corrida_id, sucursal_id, codigo, mensaje):
        self.fallidas.append((sucursal_id, codigo, mensaje))

    async def proveedor(self, db):
        return cg.FilaProveedor(PROVEEDOR_ID, 4, 5, Decimal("3"))

    async def dias_ventana(self, db, en_fecha):
        return parametros.ResolverResultado(30, True)

    async def tolerancia(self, db, en_fecha):
        return parametros.ResolverResultado(2.0, True)

    async def cargar_transito(self, db, fecha_corte, **kwargs):
        self.transito.append((fecha_corte, kwargs))
        return tc.TransitoAlCorte({}, ())

    async def finalizar(self, db, corrida_id):
        self.finalizadas.append(corrida_id)
        return "BORRADOR"


@pytest.fixture
def calculo(monkeypatch):
    grabador = Grabador()
    reemplazos = [
        (sv.cargador, "cargar_sucursal", grabador.cargar_sucursal),
        (sv.cargador, "cargar_proveedor_principal", grabador.proveedor),
        (sv.persistencia, "guardar_sucursal", grabador.guardar),
        (sv.persistencia, "marcar_sucursal_fallida", grabador.marcar),
        (sv.parametros, "resolver_dias_ventana_ingresos",
         grabador.dias_ventana),
        (sv.parametros, "resolver_tolerancia_ingreso_pct",
         grabador.tolerancia),
        (sv.transito_corte, "cargar_transito_corte",
         grabador.cargar_transito),
        (sv, "finalizar_corrida", grabador.finalizar),
    ]
    for objetivo, nombre, doble in reemplazos:
        monkeypatch.setattr(objetivo, nombre, doble)
    return grabador


def _sesion_calculo(corrida, pendientes=(SUC_A, SUC_B), reclamada=True):
    return Sesion(
        execute_queue=[[corrida.id] if reclamada else [], list(pendientes)],
        get_queue=[corrida])


async def test_a_corrida_that_is_not_pending_cannot_be_started(calculo):
    corrida = _corrida_congelada()
    db = _sesion_calculo(corrida, reclamada=False)

    with pytest.raises(pe.ErrorCorrida) as error:
        await sv.calcular_corrida(db, corrida.id)

    assert error.value.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE
    assert calculo.guardadas == []


async def test_every_pending_sucursal_is_computed_and_saved_in_order(
        calculo):
    corrida = _corrida_congelada()

    estado = await sv.calcular_corrida(_sesion_calculo(corrida), corrida.id)

    assert estado == "BORRADOR"
    assert [g[1] for g in calculo.guardadas] == [SUC_A, SUC_B]
    assert all(g[0] == corrida.id and g[2] == "OK" for g in calculo.guardadas)
    assert calculo.finalizadas == [corrida.id]


async def test_the_claim_moves_the_corrida_to_calculando_only_if_pending(
        calculo):
    corrida = _corrida_congelada()
    db = _sesion_calculo(corrida)

    await sv.calcular_corrida(db, corrida.id)

    reclamo = str(db.executed_statements[0].compile(
        dialect=postgresql.dialect()))
    assert reclamo.startswith("UPDATE corrida SET")
    assert "estado = %(estado_1)s" in reclamo
    assert "RETURNING corrida.id" in reclamo


async def test_each_sucursal_runs_inside_its_own_savepoint(calculo):
    corrida = _corrida_congelada()
    db = _sesion_calculo(corrida)

    await sv.calcular_corrida(db, corrida.id)

    assert db.savepoints == 2


async def test_a_coded_loader_error_marks_that_sucursal_and_the_rest_go_on(
        calculo):
    calculo.fallos[SUC_A] = ErrorCargador("E-CORRIDA-021", "Sin SIC.")
    corrida = _corrida_congelada()

    estado = await sv.calcular_corrida(_sesion_calculo(corrida), corrida.id)

    assert calculo.fallidas == [(SUC_A, "E-CORRIDA-021", "Sin SIC.")]
    assert [g[1] for g in calculo.guardadas] == [SUC_B]
    assert estado == "BORRADOR"


async def test_an_unexpected_error_becomes_the_internal_code_and_isolates(
        calculo):
    calculo.fallos[SUC_A] = RuntimeError("boom")
    corrida = _corrida_congelada()

    await sv.calcular_corrida(_sesion_calculo(corrida), corrida.id)

    assert calculo.fallidas[0][:2] == (SUC_A, codigos.E_CORRIDA_INTERNO)
    assert calculo.fallidas[0][2] == codigos.mensaje(
        codigos.E_CORRIDA_INTERNO)
    assert [g[1] for g in calculo.guardadas] == [SUC_B]


async def test_a_missing_sucursal_is_a_failed_sucursal_not_a_crash(calculo):
    calculo.fallos[SUC_B] = LookupError("la sucursal no existe")
    corrida = _corrida_congelada()

    await sv.calcular_corrida(_sesion_calculo(corrida), corrida.id)

    assert [f[0] for f in calculo.fallidas] == [SUC_B]
    assert [g[1] for g in calculo.guardadas] == [SUC_A]


async def test_an_annulled_corrida_stops_the_run_cooperatively(calculo):
    calculo.guardar_falla = pe.ErrorCorrida(
        codigos.E_CORRIDA_ESTADO_NO_ADMITE, "anulada")
    corrida = _corrida_congelada()

    estado = await sv.calcular_corrida(_sesion_calculo(corrida), corrida.id)

    assert estado == "ANULADA"
    assert calculo.finalizadas == [] and calculo.fallidas == []
    assert len(calculo.contextos) == 1


async def test_an_omitted_sucursal_is_saved_with_its_omitted_result(
        calculo, monkeypatch):
    async def cargar(db, sucursal_id, ctx):
        nueva = dataclasses.replace(
            atributos(fecha_apertura=datetime.date(2026, 9, 5),
                      fecha_corte=CORTE), sucursal_id=sucursal_id)
        return DatosSucursal(nueva, ())

    monkeypatch.setattr(sv.cargador, "cargar_sucursal", cargar)
    corrida = _corrida_congelada()

    estado = await sv.calcular_corrida(
        _sesion_calculo(corrida, pendientes=(SUC_A,)), corrida.id)

    assert [g[2] for g in calculo.guardadas] == ["OMITIDA"]
    assert estado == "BORRADOR"


async def test_the_f2_transit_parameters_are_resolved_before_the_loader(
        calculo):
    corrida = _corrida_congelada()

    await sv.calcular_corrida(_sesion_calculo(corrida), corrida.id)

    fecha, kwargs = calculo.transito[0]
    assert fecha == CORTE
    assert kwargs["dias_ventana_ingresos"] == 30
    assert kwargs["tolerancia_ingreso_pct"] == 2.0
    assert kwargs["excluir_vencido"] is False


async def test_the_transit_is_computed_once_per_corrida_not_per_sucursal(
        calculo):
    corrida = _corrida_congelada()

    await sv.calcular_corrida(_sesion_calculo(corrida), corrida.id)

    assert len(calculo.transito) == 1
    assert len(calculo.contextos) == 2


async def test_the_context_uses_the_frozen_cortes_and_the_snapshot_days(
        calculo):
    corrida = _corrida_congelada()

    await sv.calcular_corrida(_sesion_calculo(corrida), corrida.id)

    ctx = calculo.contextos[0]
    assert ctx.corte_inventario == datetime.date(2026, 9, 19)
    assert ctx.corte_backorder == datetime.date(2026, 9, 18)
    assert ctx.fecha_corte == CORTE
    assert ctx.dias_entre_pedidos == {SUC_A: 30, SUC_B: 30}
    assert ctx.mes_en_curso is None and ctx.consolidar is False
    assert ctx.resoluciones == {}


async def test_the_frozen_mes_en_curso_reaches_the_loader_context(calculo):
    corrida = _corrida_congelada(m0=MesEnCurso("PONDERADO", 14, 30, 3))

    await sv.calcular_corrida(_sesion_calculo(corrida), corrida.id)

    assert calculo.contextos[0].mes_en_curso == MesEnCurso(
        "PONDERADO", 14, 30, Fraction(3))


async def test_the_frozen_master_is_resolved_only_when_consolidating(
        calculo):
    vieja, final = uuid.UUID(int=31), uuid.UUID(int=32)
    maestro = [{"referencia_id": str(vieja), "activa": False,
                "sustituida_por": str(final)}]
    corrida = _corrida_congelada(consolidar=True, maestro=maestro)

    await sv.calcular_corrida(_sesion_calculo(corrida), corrida.id)

    ctx = calculo.contextos[0]
    assert ctx.consolidar is True
    assert ctx.resoluciones[vieja].final_id == final
    assert all(g[3] is True for g in calculo.guardadas)


# --- finalizar_corrida (con el hook de anulación) ---------------------------


def _cargas(anuladas=()):
    """Filas `(id, estado)` de las cargas vinculadas: una viva y las dadas."""
    return [(uuid.uuid4(), "APLICADO")] + [
        (carga, "ANULADO") for carga in anuladas]


def _cola_finalizar(conteos, anuladas=(), actualizada=True):
    """Cargas, conteos por estado, el UPDATE de la corrida y, sólo si la
    corrida queda BORRADOR, el UPDATE que inicia los pedidos por tienda."""
    return [_cargas(anuladas), list(conteos),
            ["BORRADOR"] if actualizada else [], []]


async def test_some_ok_sucursales_leave_the_corrida_as_borrador():
    db = Sesion(execute_queue=_cola_finalizar([("OK", 2), ("FALLIDA", 1)]))

    estado = await sv.finalizar_corrida(db, uuid.uuid4())

    assert estado == "BORRADOR"


async def test_only_omitted_sucursales_still_leave_the_corrida_as_borrador():
    db = Sesion(execute_queue=_cola_finalizar([("OMITIDA", 3)]))

    assert await sv.finalizar_corrida(db, uuid.uuid4()) == "BORRADOR"


async def test_all_failed_sucursales_leave_the_corrida_failed():
    db = Sesion(execute_queue=_cola_finalizar([("FALLIDA", 3)]))

    assert await sv.finalizar_corrida(db, uuid.uuid4()) == "FALLIDA"


async def test_the_all_failed_outcome_records_the_030_code():
    db = Sesion(execute_queue=_cola_finalizar([("FALLIDA", 3)]))

    await sv.finalizar_corrida(db, uuid.uuid4())

    cierre = db.executed_statements[2].compile(dialect=postgresql.dialect())
    assert cierre.params["estado"] == "FALLIDA"
    assert codigos.E_CORRIDA_TODAS_FALLIDAS in str(cierre.params)


async def test_a_carga_annulled_during_the_run_invalidates_the_corrida():
    carga = uuid.uuid4()
    db = Sesion(execute_queue=_cola_finalizar([("OK", 2)], [carga]))

    await sv.finalizar_corrida(db, uuid.uuid4())

    cierre = db.executed_statements[2].compile(dialect=postgresql.dialect())
    assert cierre.params["invalidada"] is True
    assert cierre.params["motivo_invalidacion"] == {
        "tipo": "CARGA_ANULADA", "carga_ids": [str(carga)]}


async def test_without_annulled_cargas_the_corrida_is_not_invalidated():
    db = Sesion(execute_queue=_cola_finalizar([("OK", 2)]))

    await sv.finalizar_corrida(db, uuid.uuid4())

    cierre = db.executed_statements[2].compile(dialect=postgresql.dialect())
    assert "invalidada" not in cierre.params


async def test_the_linked_cargas_are_locked_for_share_before_deciding():
    db = Sesion(execute_queue=_cola_finalizar([("OK", 1)]))

    await sv.finalizar_corrida(db, uuid.uuid4())

    lectura = str(db.executed_statements[0].compile(
        dialect=postgresql.dialect()))
    assert "FOR SHARE" in lectura
    assert "corrida_carga" in lectura


async def test_finalizing_writes_only_if_the_corrida_is_still_calculating():
    db = Sesion(execute_queue=_cola_finalizar([("OK", 1)]))

    await sv.finalizar_corrida(db, uuid.uuid4())

    cierre = str(db.executed_statements[2].compile(
        dialect=postgresql.dialect()))
    assert "estado = %(estado_1)s" in cierre
    assert "RETURNING corrida.estado" in cierre


async def test_finalizing_an_annulled_corrida_reports_the_annulment():
    db = Sesion(execute_queue=_cola_finalizar(
        [("OK", 1)], actualizada=False))

    assert await sv.finalizar_corrida(db, uuid.uuid4()) == "ANULADA"


# --- finalizar_corrida inicia el pedido de cada tienda (F4, ADR-1) ----------


def _literal(sentencia):
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


async def test_a_borrador_corrida_starts_the_pedido_of_its_ok_tiendas():
    db = Sesion(execute_queue=_cola_finalizar([("OK", 2), ("FALLIDA", 1)]))

    await sv.finalizar_corrida(db, uuid.uuid4())

    assert len(db.executed_statements) == 4
    inicio = _literal(db.executed_statements[3])
    assert inicio.startswith("UPDATE corrida_sucursal SET estado_pedido")
    assert "estado_pedido='BORRADOR'" in inicio.replace(" ", "")
    assert "corrida_sucursal.estado = 'OK'" in inicio


async def test_the_pedido_start_skips_scenario_corridas():
    db = Sesion(execute_queue=_cola_finalizar([("OK", 2)]))

    await sv.finalizar_corrida(db, uuid.uuid4())

    inicio = _literal(db.executed_statements[3])
    assert "NOT (EXISTS" in inicio
    assert "corrida.es_escenario IS true" in inicio


async def test_the_pedido_start_is_scoped_to_the_finalized_corrida():
    corrida_id = uuid.uuid4()
    db = Sesion(execute_queue=_cola_finalizar([("OK", 1)]))

    await sv.finalizar_corrida(db, corrida_id)

    inicio = _literal(db.executed_statements[3])
    assert f"corrida_sucursal.corrida_id = '{corrida_id}'" in inicio


async def test_a_failed_corrida_starts_no_pedido():
    db = Sesion(execute_queue=_cola_finalizar([("FALLIDA", 3)]))

    assert await sv.finalizar_corrida(db, uuid.uuid4()) == "FALLIDA"

    assert len(db.executed_statements) == 3


async def test_an_annulled_corrida_starts_no_pedido():
    db = Sesion(execute_queue=_cola_finalizar(
        [("OK", 1)], actualizada=False))

    assert await sv.finalizar_corrida(db, uuid.uuid4()) == "ANULADA"

    assert len(db.executed_statements) == 3


def test_legacy_cerrada_counts_as_a_calculated_corrida():
    assert estados.CALCULADAS == frozenset({"BORRADOR", "CERRADA"})
    assert estados.BORRADOR in estados.CALCULADAS
    assert estados.CERRADA in estados.CALCULADAS
    assert estados.ANULADA not in estados.CALCULADAS


def test_the_per_tienda_pedido_states_are_defined():
    assert (estados.PEDIDO_BORRADOR, estados.PEDIDO_CERRADO,
            estados.PEDIDO_ENVIADO) == ("BORRADOR", "CERRADO", "ENVIADO")
    assert estados.PEDIDOS == frozenset({"BORRADOR", "CERRADO", "ENVIADO"})


# --- El cierre ya no es de la corrida (F4, B3a) ----------------------------


def _corrida_en(estado, **campos):
    valores = dict(
        id=uuid.uuid4(), codigo="PED-2026-S39-001", estado=estado,
        es_escenario=False, invalidada=False)
    valores.update(campos)
    return Corrida(**valores)


def test_closing_is_per_tienda_so_the_corrida_level_close_is_gone():
    """F3 cerraba la corrida entera (BORRADOR -> CERRADA) y se bloqueaba con
    una sucursal fallida (E-CORRIDA-043). Ahora cada tienda se cierra sola
    (`pedido_tienda`, probado en `test_pedido_tienda.py`) y la corrida sólo
    lleva el ciclo del cálculo."""
    assert not hasattr(sv, "cerrar_corrida")
    assert not hasattr(sv, "_validar_cierre")


# --- anular_corrida ---------------------------------------------------------


@pytest.mark.parametrize("estado", [
    "PENDIENTE", "CALCULANDO", "FALLIDA", "BORRADOR"])
async def test_a_live_corrida_can_be_annulled(estado):
    corrida = _corrida_en(estado)
    db = Sesion(execute_queue=[[corrida]])

    anulada = await sv.anular_corrida(
        db, corrida.id, USUARIO, "Datos equivocados")

    assert anulada.estado == "ANULADA"
    assert anulada.anulada_por == USUARIO
    assert anulada.anulada_en is not None
    assert anulada.motivo_anulacion == "Datos equivocados"


@pytest.mark.parametrize("estado", ["CERRADA", "ANULADA"])
async def test_a_closed_or_annulled_corrida_cannot_be_annulled(estado):
    corrida = _corrida_en(estado)
    db = Sesion(execute_queue=[[corrida]])

    with pytest.raises(pe.ErrorCorrida) as error:
        await sv.anular_corrida(db, corrida.id, USUARIO, "x")

    assert error.value.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE
    assert corrida.estado == estado
