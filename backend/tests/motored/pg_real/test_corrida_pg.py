"""
Motored Pedidos F3 "Motor", S6a (sdd/motored-pedidos-motor): el servicio de
la corrida contra un Postgres real (opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base ya migrada con `alembic -c alembic_motored.ini upgrade head`. Cada
test trabaja dentro de una transacción que se revierte al final. Recorre el
camino completo: preflight real, cargador real, motor puro, persistencia
real, reproducción y guarda de anulación.
"""
import dataclasses
import datetime
import os
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_resumen import CorridaResumen
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services.corridas import codigos, guardas
from app.motored.services.corridas import persistencia as pe
from app.motored.services.corridas import reproduccion as rp
from app.motored.services.corridas import servicio as sv
from app.motored.services.corridas.cargador import DatosSucursal
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.tipos import ParametrosMotor
from tests.motored.fixtures.motor.constructores import atributos

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

CORTE = datetime.date(2026, 9, 21)
UTC = datetime.timezone.utc
PATRON = (102, 112, 108, 105, 74, 59)


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


async def _guardar(db, *objetos):
    db.add_all(objetos)
    await db.flush()


def _carga(tipo, desde=None, hasta=None, aplicado=None, log=None):
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen="EXCEL", estado="APLICADO",
        nombre_archivo="f.xlsx", hash_sha256="h" * 64, ruta_objeto="r",
        bytes=1, periodo_desde=desde, periodo_hasta=hasta,
        aplicado_en=aplicado, log=log)


def _sucursal(nombre, **campos):
    valores = dict(
        id=uuid.uuid4(), nombre=f"{nombre} {uuid.uuid4().hex[:6]}",
        sic=f"SIC-{uuid.uuid4().hex[:6]}", dias_empaque=3, dias_transito=2)
    return Sucursal(**{**valores, **campos})


def _referencia(codigo, proveedor, **campos):
    return Referencia(
        id=uuid.uuid4(), codigo=codigo, proveedor_id=proveedor.id,
        unidad_empaque=1, precio_normal=Decimal("460.75"), **campos)


def _ventas(sucursal, ref, unidades, carga):
    """Seis meses cerrados de ventas MOSTRADOR: marzo (M6) .. agosto (M1)."""
    return [
        VentaMensual(
            id=uuid.uuid4(), sucursal_id=sucursal.id, referencia_id=ref.id,
            anio=2026, mes=mes, origen="MOSTRADOR", unidades=Decimal(u),
            carga_id=carga.id)
        for mes, u in zip(range(3, 9), unidades)
    ]


def _inventario(sucursal, ref, existencias, carga):
    return InventarioSnapshot(
        id=uuid.uuid4(), fecha_corte=datetime.date(2026, 9, 19),
        sucursal_id=sucursal.id, referencia_id=ref.id,
        existencias=Decimal(existencias), carga_id=carga.id)


async def _sembrar(db):
    """Tres sucursales (la tercera abrió hace días), datos sintéticos y las
    cargas que el preflight exige, todas frescas al corte."""
    hmcl = Proveedor(
        id=uuid.uuid4(), codigo=f"HMCL-{uuid.uuid4().hex[:6]}",
        nombre="HMCL", es_principal=True, dias_empaque_default=4,
        dias_transito_default=5, dias_seguridad_default=Decimal("3"))
    uno, dos = _sucursal("UNO"), _sucursal("DOS")
    tres = _sucursal("TRES", fecha_apertura=datetime.date(2026, 9, 10))
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Compras", role=MotoredRole.COMPRAS,
        email=f"c-{uuid.uuid4().hex[:6]}@x.co", hashed_password="x")
    await _guardar(db, hmcl, uno, dos, tres, usuario)
    patron = _referencia("94109-12000S", hmcl)
    otra = _referencia("55555-00001", hmcl)
    await _guardar(db, patron, otra)
    cargas = SimpleNamespace(
        ventas=_carga(
            "VENTAS", datetime.date(2026, 3, 1), datetime.date(2026, 9, 14),
            log={"fecha_max_detectada": "2026-09-14"}),
        inventario=_carga("INVENTARIO", datetime.date(2026, 9, 19)),
        backorder=_carga("BACKORDER", datetime.date(2026, 9, 18)),
        facturas=_carga(
            "FACTURAS_PEDIDOS",
            aplicado=datetime.datetime(2026, 9, 19, 15, tzinfo=UTC)),
        ingresos=_carga(
            "INGRESOS_FACTURAS",
            aplicado=datetime.datetime(2026, 9, 19, 15, tzinfo=UTC)),
        perdida=_carga("DEMANDA_PERDIDA"))
    await _guardar(db, *vars(cargas).values())
    await _guardar(
        db,
        *_ventas(uno, patron, PATRON, cargas.ventas),
        *_ventas(dos, patron, (9, 8, 7, 6, 5, 4), cargas.ventas),
        *_ventas(dos, otra, (0, 3, 0, 3, 0, 3), cargas.ventas),
        _inventario(uno, patron, 27, cargas.inventario),
        _inventario(dos, otra, 4, cargas.inventario),
        FacturaProveedorLinea(
            id=uuid.uuid4(), prefijo_rh="RH", numero_rh=1,
            fecha_factura=datetime.date(2026, 9, 10), sucursal_id=uno.id,
            referencia_id=patron.id, cantidad=Decimal(70),
            valor_total=Decimal(1000), carga_id=cargas.facturas.id))
    return SimpleNamespace(
        hmcl=hmcl, uno=uno, dos=dos, tres=tres, patron=patron, otra=otra,
        usuario=usuario, cargas=cargas)


async def _correr(db, **kwargs):
    corrida = await sv.crear_corrida(
        db, fecha_corte=CORTE, hoy=CORTE, **kwargs)
    estado = await sv.calcular_corrida(db, corrida.id)
    await db.refresh(corrida)
    return corrida, estado


async def _lineas(db, corrida_id, sucursal_id):
    resultado = await db.execute(
        select(CorridaLinea)
        .where(CorridaLinea.corrida_id == corrida_id,
               CorridaLinea.sucursal_id == sucursal_id)
        .execution_options(populate_existing=True)
        .order_by(CorridaLinea.codigo_referencia))
    return resultado.scalars().all()


# --- Recorrido completo -----------------------------------------------------


async def test_a_three_sucursal_corrida_runs_end_to_end(sesion):
    datos = await _sembrar(sesion)

    corrida, estado = await _correr(sesion)

    assert estado == "BORRADOR" and corrida.estado == "BORRADOR"
    assert corrida.codigo == "PED-2026-S39-001"
    assert corrida.sucursales_total == 3 and corrida.sucursales_procesadas == 3
    assert corrida.terminado_en is not None
    assert [e["evento"] for e in corrida.log] == ["CREADA", "FINALIZADA"]


async def test_the_pattern_row_persists_with_z_zero(sesion):
    datos = await _sembrar(sesion)

    corrida, _ = await _correr(sesion)

    (linea,) = await _lineas(sesion, corrida.id, datos.uno.id)
    assert linea.codigo_referencia == "94109-12000S"
    assert linea.demanda_ponderada == Decimal("85.428571")
    assert linea.stock_objetivo == Decimal("149.500000")
    assert (linea.inventario, linea.transito) == (Decimal(27), Decimal(70))
    assert linea.inventario_final == Decimal("97.00")
    assert linea.pedido_sugerido == Decimal("53.00")
    assert linea.pedido_final == Decimal("53.00")
    assert linea.valor_pedido == Decimal("24419.75")
    assert linea.clase == "CF" and linea.estado_quiebre == "NORMAL"


async def test_a_sucursal_opened_days_ago_is_skipped_with_the_warning(sesion):
    datos = await _sembrar(sesion)

    corrida, _ = await _correr(sesion)

    fila = (await sesion.execute(
        select(CorridaSucursal)
        .where(CorridaSucursal.corrida_id == corrida.id,
               CorridaSucursal.sucursal_id == datos.tres.id)
        .execution_options(populate_existing=True))).scalar_one()
    assert fila.estado == "OMITIDA"
    assert fila.codigo == "A-CORRIDA-102"
    assert "abrió hace menos de un mes" in fila.mensaje
    assert await _lineas(sesion, corrida.id, datos.tres.id) == []


async def test_the_resumen_and_the_sucursal_totals_are_persisted(sesion):
    datos = await _sembrar(sesion)

    corrida, _ = await _correr(sesion)

    resumen = (await sesion.execute(
        select(CorridaResumen).where(
            CorridaResumen.corrida_id == corrida.id,
            CorridaResumen.sucursal_id == datos.uno.id))).scalars().all()
    assert len(resumen) == 11
    total = next(r for r in resumen if r.clase == "TOTAL")
    assert (total.unidades, total.referencias, total.valor) == (
        Decimal("53.00"), 1, Decimal("24419.75"))
    tres = (await sesion.execute(
        select(CorridaResumen).where(
            CorridaResumen.corrida_id == corrida.id,
            CorridaResumen.sucursal_id == datos.tres.id))).scalars().all()
    assert tres == []


async def test_the_input_ages_are_readable_from_the_corrida(sesion):
    await _sembrar(sesion)

    corrida, _ = await _correr(sesion)

    antiguedad = corrida.seleccion_datos["antiguedad"]
    assert antiguedad["inventario"]["antiguedad_dias"] == 2
    assert antiguedad["backorder"]["antiguedad_dias"] == 3
    assert antiguedad["inventario"]["limite_dias"] == 7
    assert antiguedad["inventario"]["fuente_limite"] == "DEFAULT"
    assert corrida.seleccion_datos["mes_en_curso"]["modo_efectivo"] == (
        "EXCLUIDO")


async def test_the_used_cargas_are_linked(sesion):
    datos = await _sembrar(sesion)

    corrida, _ = await _correr(sesion)

    vinculos = (await sesion.execute(
        select(CorridaCarga).where(
            CorridaCarga.corrida_id == corrida.id))).scalars().all()
    assert {(v.carga_id, v.tipo) for v in vinculos} == {
        (datos.cargas.ventas.id, "VENTAS"),
        (datos.cargas.inventario.id, "INVENTARIO"),
        (datos.cargas.backorder.id, "BACKORDER"),
        (datos.cargas.facturas.id, "FACTURAS_PEDIDOS"),
        (datos.cargas.ingresos.id, "INGRESOS_FACTURAS"),
    }


async def test_the_second_corrida_of_the_week_gets_the_next_codigo(sesion):
    await _sembrar(sesion)

    primera, _ = await _correr(sesion)
    segunda, _ = await _correr(sesion)

    assert (primera.codigo, segunda.codigo) == (
        "PED-2026-S39-001", "PED-2026-S39-002")


async def test_a_selection_of_sucursales_computes_only_those(sesion):
    datos = await _sembrar(sesion)

    corrida, _ = await _correr(sesion, sucursal_ids=[datos.dos.id])

    assert corrida.alcance == "SELECCION" and corrida.sucursales_total == 1
    assert len(await _lineas(sesion, corrida.id, datos.dos.id)) == 2
    assert await _lineas(sesion, corrida.id, datos.uno.id) == []


async def test_a_stale_inventory_is_rejected_with_the_age_detail(sesion):
    datos = await _sembrar(sesion)
    datos.cargas.inventario.periodo_desde = datetime.date(2026, 9, 10)
    await sesion.flush()

    with pytest.raises(codigos.ErrorCorrida) as error:
        await sv.crear_corrida(sesion, fecha_corte=CORTE, hoy=CORTE)

    assert error.value.codigo == "E-CORRIDA-003"
    assert error.value.detalle["antiguedad"]["inventario"][
        "antiguedad_dias"] == 11


async def test_a_raised_staleness_limit_lets_the_old_data_run(sesion):
    datos = await _sembrar(sesion)
    datos.cargas.inventario.periodo_desde = datetime.date(2026, 9, 10)
    await _guardar(sesion, ParametroMetodologia(
        id=uuid.uuid4(), clave="max_dias_antiguedad_inventario", valor=15,
        vigente_desde=datetime.date(2026, 9, 1)))

    corrida = await sv.crear_corrida(sesion, fecha_corte=CORTE, hoy=CORTE)

    limite = corrida.seleccion_datos["antiguedad"]["inventario"]
    assert limite["limite_dias"] == 15
    assert limite["fuente_limite"] == "GLOBAL"


# --- Falla parcial ----------------------------------------------------------


async def test_a_sucursal_without_sic_fails_alone_and_blocks_the_close(
        sesion):
    datos = await _sembrar(sesion)
    datos.dos.sic = None
    await sesion.flush()

    corrida, estado = await _correr(sesion)

    assert estado == "BORRADOR"
    fila = (await sesion.execute(
        select(CorridaSucursal)
        .where(CorridaSucursal.corrida_id == corrida.id,
               CorridaSucursal.sucursal_id == datos.dos.id)
        .execution_options(populate_existing=True))).scalar_one()
    assert (fila.estado, fila.codigo) == ("FALLIDA", "E-CORRIDA-021")
    assert len(await _lineas(sesion, corrida.id, datos.uno.id)) == 1
    with pytest.raises(codigos.ErrorCorrida) as error:
        await sv.cerrar_corrida(sesion, corrida.id, datos.usuario.id)
    assert error.value.codigo == codigos.E_CORRIDA_SUCURSAL_FALLIDA


async def test_when_every_sucursal_fails_the_corrida_is_failed(sesion):
    datos = await _sembrar(sesion)
    for sucursal in (datos.uno, datos.dos, datos.tres):
        sucursal.sic = None
    await sesion.flush()

    corrida, estado = await _correr(sesion)

    assert estado == "FALLIDA" and corrida.estado == "FALLIDA"
    assert corrida.log[-1]["codigo"] == codigos.E_CORRIDA_TODAS_FALLIDAS


# --- Reproducción -----------------------------------------------------------


async def test_the_replay_is_identical(sesion):
    await _sembrar(sesion)
    corrida, _ = await _correr(sesion)

    reporte = await rp.reproducir(sesion, corrida.id)

    assert reporte.identico is True and reporte.diferencias == ()


async def test_the_replay_survives_purged_sources_and_a_changed_master(
        sesion):
    datos = await _sembrar(sesion)
    corrida, _ = await _correr(sesion)
    await sesion.execute(text("delete from inventario_snapshot"))
    await sesion.execute(text("delete from venta_mensual"))
    await sesion.execute(text("delete from factura_proveedor_linea"))
    await sesion.execute(text(
        "update referencia set precio_normal = 1, unidad_empaque = 9,"
        " activa = false"))
    await sesion.execute(text("update sucursal set dias_empaque = 30"))
    await _guardar(sesion, ParametroMetodologia(
        id=uuid.uuid4(), clave="dias_entre_pedidos", valor=7,
        vigente_desde=datetime.date(2026, 9, 1)))

    reporte = await rp.reproducir(sesion, corrida.id)

    assert reporte.identico is True


async def test_a_line_edited_by_hand_is_reported_by_the_replay(sesion):
    datos = await _sembrar(sesion)
    corrida, _ = await _correr(sesion)
    await sesion.execute(
        update(CorridaLinea)
        .where(CorridaLinea.corrida_id == corrida.id,
               CorridaLinea.sucursal_id == datos.uno.id)
        .values(pedido_sugerido=Decimal("999")))

    reporte = await rp.reproducir(sesion, corrida.id)

    assert reporte.identico is False
    diferencia = next(
        d for d in reporte.diferencias if d.columna == "pedido_sugerido")
    assert diferencia.esperado == Decimal("53.00")
    assert diferencia.almacenado == Decimal("999.00")


async def test_the_same_data_gives_identical_lines_twice_t17(sesion):
    datos = await _sembrar(sesion)

    primera, _ = await _correr(sesion)
    segunda, _ = await _correr(sesion)

    async def _valores(corrida):
        filas = await _lineas(sesion, corrida.id, datos.dos.id)
        return [
            {c.key: getattr(f, c.key) for c in CorridaLinea.__table__.columns
             if c.key not in ("id", "corrida_id")} for f in filas]

    assert len(await _valores(primera)) == 2
    assert await _valores(primera) == await _valores(segunda)


async def _sembrar_sustitucion(db, datos):
    """OLD (inactiva, con ventas y stock) y LOST (sólo demanda perdida) se
    consolidan en NEW; los tres viven en la sucursal UNO."""
    nueva = _referencia("NEW-1", datos.hmcl)
    await _guardar(db, nueva)
    vieja = _referencia(
        "OLD-1", datos.hmcl, activa=False, sustituida_por=nueva.id)
    perdedora = _referencia(
        "LOST-1", datos.hmcl, activa=False, sustituida_por=nueva.id)
    await _guardar(db, vieja, perdedora)
    await _guardar(
        db,
        *_ventas(datos.uno, vieja, (5, 0, 3, 0, 2, 4), datos.cargas.ventas),
        *_ventas(datos.uno, nueva, (1, 1, 1, 1, 1, 1), datos.cargas.ventas),
        _inventario(datos.uno, vieja, 30, datos.cargas.inventario),
        DemandaPerdida(
            id=uuid.uuid4(), fecha=datetime.date(2026, 8, 10),
            sucursal_id=datos.uno.id, referencia_id=perdedora.id,
            cantidad_solicitada=Decimal(8), origen="EXCEL",
            carga_id=datos.cargas.perdida.id))
    return nueva


async def test_a_consolidated_scenario_replays_identical(sesion):
    datos = await _sembrar(sesion)
    nueva = await _sembrar_sustitucion(sesion, datos)
    overrides = {
        "consolidar_sustituidas": True,
        "incluir_demanda_perdida_en_ponderada": True}

    corrida, _ = await _correr(
        sesion, sucursal_ids=[datos.uno.id], overrides=overrides)

    assert corrida.es_escenario is True
    assert corrida.codigo == "ESC-2026-S39-001"
    lineas = {
        f.codigo_referencia: f
        for f in await _lineas(sesion, corrida.id, datos.uno.id)}
    assert lineas["OLD-1"].motivo_exclusion == "SUSTITUIDA"
    assert lineas["OLD-1"].sustituta_final_id == nueva.id
    assert lineas["NEW-1"].y_recibido == Decimal("30.00")
    assert "LOST-1" not in lineas
    fila = (await sesion.execute(
        select(CorridaSucursal)
        .where(CorridaSucursal.corrida_id == corrida.id)
        .execution_options(populate_existing=True))).scalar_one()
    assert [a["codigo"] for a in fila.parametros["entradas_auxiliares"]] == [
        "LOST-1"]
    reporte = await rp.reproducir(sesion, corrida.id)
    assert reporte.identico is True


async def test_a_scenario_cannot_be_closed_and_leaves_production_alone(
        sesion):
    datos = await _sembrar(sesion)
    corrida, _ = await _correr(
        sesion, overrides={"modo_redondeo_empaque": "ARRIBA"})

    with pytest.raises(codigos.ErrorCorrida) as error:
        await sv.cerrar_corrida(sesion, corrida.id, datos.usuario.id)

    assert error.value.codigo == codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA
    parametros = (await sesion.execute(
        select(ParametroMetodologia))).scalars().all()
    assert parametros == []


# --- Ciclo de vida y guarda de anulación ------------------------------------


async def test_the_annulment_guard_invalidates_a_draft_and_blocks_a_closed(
        sesion):
    datos = await _sembrar(sesion)
    borrador, _ = await _correr(sesion)

    invalidadas = await guardas.aplicar_guard_anulacion(
        sesion, datos.cargas.inventario)

    assert invalidadas == [borrador.codigo]
    await sesion.refresh(borrador)
    assert borrador.invalidada is True
    assert borrador.motivo_invalidacion == {
        "tipo": "CARGA_ANULADA", "carga_id": str(datos.cargas.inventario.id)}
    with pytest.raises(codigos.ErrorCorrida) as error:
        await sv.cerrar_corrida(sesion, borrador.id, datos.usuario.id)
    assert error.value.codigo == codigos.E_CORRIDA_INVALIDADA

    cerrable, _ = await _correr(sesion)
    cerrada = await sv.cerrar_corrida(sesion, cerrable.id, datos.usuario.id)
    assert cerrada.estado == "CERRADA" and cerrada.cerrada_en is not None
    with pytest.raises(codigos.ErrorCorrida) as bloqueo:
        await guardas.aplicar_guard_anulacion(
            sesion, datos.cargas.inventario)
    assert bloqueo.value.codigo == codigos.E_CARGA_ANULACION_BLOQUEADA
    assert cerrable.codigo in bloqueo.value.mensaje


async def test_an_unused_carga_annuls_freely(sesion):
    datos = await _sembrar(sesion)
    libre = _carga("INVENTARIO", datetime.date(2026, 9, 1))
    await _guardar(sesion, libre)
    await _correr(sesion)

    assert await guardas.aplicar_guard_anulacion(sesion, libre) == []


async def test_a_closed_corrida_rejects_every_write_t18(sesion):
    datos = await _sembrar(sesion)
    corrida, _ = await _correr(sesion)
    await sv.cerrar_corrida(sesion, corrida.id, datos.usuario.id)
    antes = await _lineas(sesion, corrida.id, datos.uno.id)
    sucursal = dataclasses.replace(atributos(), sucursal_id=datos.uno.id)
    resultado = calcular_sucursal((), sucursal, ParametrosMotor())

    with pytest.raises(codigos.ErrorCorrida) as error:
        await pe.guardar_sucursal(
            sesion, corrida.id, DatosSucursal(sucursal, ()), resultado)

    assert error.value.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE
    despues = await _lineas(sesion, corrida.id, datos.uno.id)
    assert len(antes) == 1
    assert [f.id for f in despues] == [f.id for f in antes]


async def test_an_annulled_corrida_stops_and_keeps_its_lines_readable(
        sesion):
    datos = await _sembrar(sesion)
    corrida = await sv.crear_corrida(sesion, fecha_corte=CORTE, hoy=CORTE)
    await sv.anular_corrida(
        sesion, corrida.id, datos.usuario.id, "prueba")

    with pytest.raises(codigos.ErrorCorrida) as error:
        await sv.calcular_corrida(sesion, corrida.id)

    assert error.value.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE
    assert corrida.estado == "ANULADA"
    assert corrida.motivo_anulacion == "prueba"


async def test_finalizing_flags_a_carga_annulled_while_the_corrida_ran(
        sesion):
    datos = await _sembrar(sesion)
    corrida = await sv.crear_corrida(sesion, fecha_corte=CORTE, hoy=CORTE)
    await sesion.execute(
        update(Corrida).where(Corrida.id == corrida.id)
        .values(estado="CALCULANDO"))
    await sesion.execute(
        update(CorridaSucursal)
        .where(CorridaSucursal.corrida_id == corrida.id)
        .values(estado="OK"))
    datos.cargas.backorder.estado = "ANULADO"
    await sesion.flush()

    estado = await sv.finalizar_corrida(sesion, corrida.id)

    assert estado == "BORRADOR"
    await sesion.refresh(corrida)
    assert corrida.invalidada is True
    assert corrida.motivo_invalidacion["carga_ids"] == [
        str(datos.cargas.backorder.id)]


# --- Volumen ----------------------------------------------------------------


async def test_a_3000_line_sucursal_persists_in_chunks_and_replays(sesion):
    datos = await _sembrar(sesion)
    await sesion.execute(text(
        "insert into referencia(id, codigo, proveedor_id, unidad_empaque,"
        " unidad_empaque_advertencia, activa, precio_normal)"
        " select gen_random_uuid(), 'V-' || lpad(n::text, 5, '0'), :prov,"
        " 1 + n % 4, false, true, 10 + n % 50"
        " from generate_series(1, 3000) as n"), {"prov": datos.hmcl.id})
    await sesion.execute(text(
        "insert into venta_mensual(id, sucursal_id, referencia_id, anio,"
        " mes, origen, unidades, es_mes_parcial, carga_id)"
        " select gen_random_uuid(), :suc, r.id, 2026, m, 'MOSTRADOR',"
        " 1 + (row_number() over (order by r.codigo) + m) % 9, false, :carga"
        " from referencia r cross join generate_series(4, 8) as m"
        " where r.codigo like 'V-%'"),
        {"suc": datos.uno.id, "carga": datos.cargas.ventas.id})

    corrida, estado = await _correr(sesion, sucursal_ids=[datos.uno.id])

    lineas = await _lineas(sesion, corrida.id, datos.uno.id)
    assert estado == "BORRADOR" and len(lineas) == 3001
    assert pe.TAMANO_BLOQUE < len(lineas)
    reporte = await rp.reproducir(sesion, corrida.id)
    assert reporte.identico is True
