"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B3a, ADR-3, spec
ED-21, ED-22, ED-22b, CI-16, CI-23): las operaciones por tienda con sesiones
concurrentes sobre un Postgres real (opt-in).

Orden de bloqueos (`services/corridas/bloqueos.py`): cargas `FOR SHARE` ->
corrida `FOR SHARE` -> tienda (`FOR SHARE` al editar, `FOR UPDATE` al cerrar y
reabrir) -> línea `FOR UPDATE`. Acá se prueba, con VARIAS CONEXIONES, que ese
orden hace lo que el spec pide: tiendas distintas avanzan sin esperarse; un
cierre y una edición de la MISMA tienda se serializan (y el pedido cerrado
contiene la última edición, o la edición se rechaza con E-CORRIDA-052); dos
ediciones de la misma línea dejan un historial encadenado; y ningún cruce
termina en un `deadlock detected`.

Necesita sesiones distintas y filas confirmadas: siembra un proveedor, un
usuario, dos sucursales con una línea cada una y una corrida BORRADOR, y lo
borra todo al terminar. Una conexión por sesión que «sostiene» una operación
(sin confirmar) deja a la otra esperando, que es justo lo que se mide.
"""
import asyncio
import datetime
import os
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_linea_historial import CorridaLineaHistorial
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.pedido_evento import PedidoEvento
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services.corridas import (
    codigos,
    edicion,
    pedido_tienda,
    tope,
)

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

CORTE = datetime.date(2026, 9, 21)
ESPERA = 0.5
PLAZO = 10
D = Decimal


def _linea(corrida, sucursal, referencia, sugerido="50.00"):
    cero = D("0.00")
    return CorridaLinea(
        corrida_id=corrida.id, sucursal_id=sucursal.id,
        referencia_id=referencia.id, codigo_referencia=referencia.codigo,
        nombre_parte="PARTE", unidad_empaque=1, banderas=[],
        **{f"venta_m{m}": cero for m in range(1, 7)},
        **{f"perdida_m{m}": cero for m in range(1, 7)},
        inventario=cero, transito=cero, backorder=cero, ajuste=cero,
        pedido_sugerido=D(sugerido), pedido_final=D(sugerido),
        precio=D("100.00"), valor_pedido=D(sugerido) * 100, clase="AF",
        estado_quiebre="NORMAL")


def _objetos(sufijo):
    """Proveedor, usuario, dos sucursales, dos referencias y la corrida."""
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"CONC-{sufijo}", nombre="concurrencia",
        es_principal=False, dias_empaque_default=1, dias_transito_default=1,
        dias_seguridad_default=D("1"))
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Compras", role=MotoredRole.COMPRAS,
        email=f"c-{sufijo}@x.co", hashed_password="x")
    tiendas = [
        Sucursal(id=uuid.uuid4(), nombre=f"{n} {sufijo}",
                 sic=f"S-{n}-{sufijo}", dias_empaque=1, dias_transito=1)
        for n in ("A", "B")]
    referencias = [
        Referencia(
            id=uuid.uuid4(), codigo=f"R{n}-{sufijo}",
            proveedor_id=proveedor.id, unidad_empaque=1,
            precio_normal=D("100.00")) for n in (1, 2)]
    corrida = Corrida(
        id=uuid.uuid4(), codigo=f"TST-{sufijo}-01", proveedor_id=proveedor.id,
        fecha_corte=CORTE, estado="BORRADOR")
    return proveedor, usuario, tiendas, referencias, corrida


async def _sembrar(maker, proveedor, usuario, tiendas, referencias, corrida):
    """Todo CONFIRMADO: cada tienda OK en BORRADOR con una línea de 50."""
    async with maker() as db:
        db.add_all([proveedor, usuario, *tiendas])
        await db.flush()
        db.add_all([*referencias, corrida])
        await db.flush()
        db.add_all([
            CorridaSucursal(
                corrida_id=corrida.id, sucursal_id=t.id, orden=i,
                estado="OK", estado_pedido="BORRADOR")
            for i, t in enumerate(tiendas, start=1)])
        db.add_all([
            _linea(corrida, t, r) for t, r in zip(tiendas, referencias)])
        await db.commit()
    async with maker() as db:
        lineas = (await db.execute(
            select(CorridaLinea).where(CorridaLinea.corrida_id == corrida.id)
        )).scalars().all()
    return {linea.sucursal_id: linea.id for linea in lineas}


async def _borrar(maker, proveedor, usuario, tiendas, corrida):
    async with maker() as db:
        await db.execute(delete(Corrida).where(Corrida.id == corrida.id))
        await db.execute(delete(Referencia).where(
            Referencia.proveedor_id == proveedor.id))
        for tienda in tiendas:
            await db.execute(delete(Sucursal).where(Sucursal.id == tienda.id))
        await db.execute(delete(Usuario).where(Usuario.id == usuario.id))
        await db.execute(delete(Proveedor).where(
            Proveedor.id == proveedor.id))
        await db.commit()


@pytest.fixture
async def escenario():
    """Una corrida BORRADOR con dos tiendas OK (A y B) en BORRADOR, cada una
    con una línea de 50 unidades."""
    motor = create_async_engine(URL)
    maker = async_sessionmaker(motor, expire_on_commit=False, autoflush=False)
    proveedor, usuario, tiendas, referencias, corrida = _objetos(
        uuid.uuid4().hex[:6])
    por_tienda = await _sembrar(
        maker, proveedor, usuario, tiendas, referencias, corrida)
    a, b = tiendas
    yield SimpleNamespace(
        maker=maker, corrida_id=corrida.id, usuario_id=usuario.id,
        a=a.id, b=b.id, linea_a=por_tienda[a.id], linea_b=por_tienda[b.id])
    await _borrar(maker, proveedor, usuario, tiendas, corrida)
    await motor.dispose()


# --- Ayudas -----------------------------------------------------------------


async def _cerrar(db, esc, sucursal_id):
    return await pedido_tienda.cerrar_tienda(
        db, esc.corrida_id, sucursal_id, esc.usuario_id)


async def _editar(db, esc, linea_id, cantidad):
    return await edicion.editar_linea(
        db, esc.corrida_id, linea_id, cantidad, None, esc.usuario_id)


async def _esperar(tarea, mensaje):
    await asyncio.sleep(ESPERA)
    assert not tarea.done(), mensaje


async def _terminar(tarea):
    return await asyncio.wait_for(tarea, timeout=PLAZO)


async def _leer(esc, consulta):
    async with esc.maker() as db:
        return (await db.execute(
            consulta.execution_options(populate_existing=True))).all()


async def _estado_pedido(esc, sucursal_id):
    (fila,) = await _leer(esc, select(CorridaSucursal.estado_pedido).where(
        CorridaSucursal.corrida_id == esc.corrida_id,
        CorridaSucursal.sucursal_id == sucursal_id))
    return fila[0]


async def _valor(esc, linea_id):
    (fila,) = await _leer(esc, select(CorridaLinea.pedido_final).where(
        CorridaLinea.id == linea_id))
    return fila[0]


async def _historial(esc, linea_id):
    filas = await _leer(esc, select(
        CorridaLineaHistorial.valor_anterior,
        CorridaLineaHistorial.valor_nuevo)
        .where(CorridaLineaHistorial.linea_id == linea_id)
        .order_by(CorridaLineaHistorial.id))
    return [tuple(f) for f in filas]


# --- Tiendas distintas: no se esperan ---------------------------------------


async def test_two_tiendas_close_in_parallel_without_waiting(escenario):
    esc = escenario
    async with esc.maker() as sesion_a, esc.maker() as sesion_b:
        await _cerrar(sesion_a, esc, esc.a)

        await asyncio.wait_for(_cerrar(sesion_b, esc, esc.b), timeout=PLAZO)
        await sesion_b.commit()
        await sesion_a.commit()

    assert await _estado_pedido(esc, esc.a) == "CERRADO"
    assert await _estado_pedido(esc, esc.b) == "CERRADO"


async def test_closing_tienda_a_while_editing_tienda_b_both_succeed_ed_22b(
        escenario):
    esc = escenario
    async with esc.maker() as edita, esc.maker() as cierra:
        await _editar(edita, esc, esc.linea_b, 70)

        await asyncio.wait_for(_cerrar(cierra, esc, esc.a), timeout=PLAZO)
        await cierra.commit()
        await edita.commit()

    assert await _estado_pedido(esc, esc.a) == "CERRADO"
    assert await _estado_pedido(esc, esc.b) == "BORRADOR"
    assert await _valor(esc, esc.linea_b) == D("70.00")
    assert await _historial(esc, esc.linea_b) == [(D("50.00"), D("70.00"))]


# --- La misma tienda: cerrar y editar se serializan (ED-21) -----------------


async def test_a_close_waits_for_an_edit_in_flight_and_contains_it_ed_21(
        escenario):
    esc = escenario
    async with esc.maker() as edita, esc.maker() as cierra:
        await _editar(edita, esc, esc.linea_a, 60)
        tarea = asyncio.create_task(_cerrar(cierra, esc, esc.a))
        await _esperar(tarea, "el cierre debía esperar a la edición")

        await edita.commit()
        await _terminar(tarea)
        await cierra.commit()

    assert await _estado_pedido(esc, esc.a) == "CERRADO"
    assert await _valor(esc, esc.linea_a) == D("60.00")
    historial = await _historial(esc, esc.linea_a)
    assert historial[-1][1] == await _valor(esc, esc.linea_a)


async def test_an_edit_waits_for_a_close_in_flight_and_is_refused_052_ed_21(
        escenario):
    esc = escenario
    async with esc.maker() as cierra, esc.maker() as edita:
        await _cerrar(cierra, esc, esc.a)
        tarea = asyncio.create_task(_editar(edita, esc, esc.linea_a, 60))
        await _esperar(tarea, "la edición debía esperar al cierre")

        await cierra.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await _terminar(tarea)
        await edita.rollback()

    assert error.value.codigo == codigos.E_CORRIDA_PEDIDO_NO_BORRADOR
    assert await _estado_pedido(esc, esc.a) == "CERRADO"
    assert await _valor(esc, esc.linea_a) == D("50.00")
    assert await _historial(esc, esc.linea_a) == []


async def test_two_edits_of_one_line_keep_a_consistent_chain_ed_22(escenario):
    esc = escenario
    async with esc.maker() as primera, esc.maker() as segunda:
        await _editar(primera, esc, esc.linea_a, 60)
        tarea = asyncio.create_task(_editar(segunda, esc, esc.linea_a, 55))
        await _esperar(tarea, "la segunda edición debía esperar a la línea")

        await primera.commit()
        await _terminar(tarea)
        await segunda.commit()

    assert await _valor(esc, esc.linea_a) == D("55.00")
    assert await _historial(esc, esc.linea_a) == [
        (D("50.00"), D("60.00")), (D("60.00"), D("55.00"))]


async def test_two_edits_of_the_same_tienda_do_not_block_each_other(
        escenario):
    """Cada edición toma la tienda `FOR SHARE`: tiendas iguales, líneas
    distintas no se esperan."""
    esc = escenario
    async with esc.maker() as una, esc.maker() as otra:
        await _editar(una, esc, esc.linea_a, 60)

        await asyncio.wait_for(
            _editar(otra, esc, esc.linea_b, 70), timeout=PLAZO)
        await otra.commit()
        await una.commit()

    assert await _valor(esc, esc.linea_a) == D("60.00")
    assert await _valor(esc, esc.linea_b) == D("70.00")


# --- Reabrir y el lote ------------------------------------------------------


async def test_a_reopen_waits_for_a_close_in_flight_and_then_reopens_ci_23(
        escenario):
    esc = escenario
    async with esc.maker() as cierra, esc.maker() as reabre:
        await _cerrar(cierra, esc, esc.a)
        tarea = asyncio.create_task(pedido_tienda.reabrir_tienda(
            reabre, esc.corrida_id, esc.a, esc.usuario_id, "ajuste"))
        await _esperar(tarea, "el reabrir debía esperar al cierre")

        await cierra.commit()
        await _terminar(tarea)
        await reabre.commit()

    assert await _estado_pedido(esc, esc.a) == "BORRADOR"
    eventos = await _leer(esc, select(PedidoEvento.evento).where(
        PedidoEvento.corrida_id == esc.corrida_id).order_by(PedidoEvento.id))
    assert [e[0] for e in eventos] == ["CERRADO", "REABIERTO"]


async def test_a_batch_waits_for_a_single_close_and_counts_it_as_done(
        escenario):
    esc = escenario
    async with esc.maker() as sola, esc.maker() as lote:
        await _cerrar(sola, esc, esc.b)
        tarea = asyncio.create_task(pedido_tienda.cerrar_todas(
            lote, esc.corrida_id, esc.usuario_id))
        await _esperar(tarea, "el lote debía esperar a la tienda B")

        await sola.commit()
        resultado = await _terminar(tarea)
        await lote.commit()

    assert resultado.cerradas == [esc.a] and resultado.ya_cerradas == 1
    assert await _estado_pedido(esc, esc.a) == "CERRADO"
    assert await _estado_pedido(esc, esc.b) == "CERRADO"


async def test_two_batches_in_opposite_order_never_deadlock(escenario):
    """Las tiendas se bloquean siempre en orden de `sucursal_id`, así que dos
    lotes nombrados en orden contrario no se cruzan: uno gana y el otro ve el
    pedido ya cerrado (E-CORRIDA-064)."""
    esc = escenario

    async def lote(ids):
        async with esc.maker() as db:
            try:
                resultado = await pedido_tienda.cerrar_todas(
                    db, esc.corrida_id, esc.usuario_id, ids)
                await db.commit()
                return resultado
            except codigos.ErrorCorrida as error:
                await db.rollback()
                return error

    resultados = await asyncio.wait_for(asyncio.gather(
        lote([esc.a, esc.b]), lote([esc.b, esc.a])), timeout=20)

    cerrados = [r for r in resultados if not isinstance(r, Exception)]
    rechazados = [r for r in resultados if isinstance(r, Exception)]
    assert len(cerrados) == 1 and len(rechazados) == 1, resultados
    assert rechazados[0].codigo == codigos.E_CORRIDA_CERRAR_NO_BORRADOR
    assert await _estado_pedido(esc, esc.a) == "CERRADO"
    assert await _estado_pedido(esc, esc.b) == "CERRADO"


# --- Recorte al tope de presupuesto (B5b, TP-32, TP-33, TP-31) ---------------
#
# Orden de bloqueos del recorte: corrida SHARE -> tienda UPDATE -> líneas
# UPDATE por id. Una edición (tienda SHARE) y un cierre (tienda UPDATE) de la
# MISMA tienda lo esperan o lo hacen esperar; otra tienda no.

DESDE = datetime.date(2026, 1, 1)


@pytest.fixture
async def escenario_tope(escenario):
    """El escenario de dos tiendas con la línea de cada una como clase C
    (50 unidades, empaque 10, valor 5.000), el modo tope encendido y un tope
    de 3.000 en A: el recorte propone bajarla de 50 a 30."""
    esc = escenario
    parametros = [
        ParametroMetodologia(
            id=uuid.uuid4(), clave="modo_tope_presupuesto", valor=True,
            vigente_desde=DESDE),
        ParametroMetodologia(
            id=uuid.uuid4(), clave="presupuesto_maximo_pedido",
            valor="3000", vigente_desde=DESDE, sucursal_id=esc.a)]
    async with esc.maker() as db:
        await db.execute(
            update(CorridaLinea)
            .where(CorridaLinea.corrida_id == esc.corrida_id)
            .values(clase_abc="C", unidad_empaque=10,
                    inventario_final=D("0.00"),
                    demanda_ponderada=D("10.000000")))
        db.add_all(parametros)
        await db.commit()
    yield esc
    async with esc.maker() as db:
        await db.execute(delete(ParametroMetodologia).where(
            ParametroMetodologia.id.in_([p.id for p in parametros])))
        await db.commit()


async def _token(esc):
    async with esc.maker() as db:
        propuesta = await tope.previsualizar(db, esc.corrida_id, esc.a)
        await db.rollback()
    assert propuesta["activo"] and len(propuesta["recortes"]) == 1
    return propuesta["token"]


async def _recortar(db, esc, token, sucursal_id=None):
    return await tope.aplicar(
        db, esc.corrida_id, sucursal_id or esc.a, token, esc.usuario_id)


async def test_a_recorte_waits_for_an_edit_in_flight_and_is_stale_tp_32(
        escenario_tope):
    esc = escenario_tope
    token = await _token(esc)
    async with esc.maker() as edita, esc.maker() as recorta:
        await _editar(edita, esc, esc.linea_a, 60)
        tarea = asyncio.create_task(_recortar(recorta, esc, token))
        await _esperar(tarea, "el recorte debía esperar a la edición")

        await edita.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await _terminar(tarea)
        await recorta.rollback()

    assert error.value.codigo == codigos.E_CORRIDA_PROPUESTA_DESACTUALIZADA
    assert await _valor(esc, esc.linea_a) == D("60.00")
    assert await _historial(esc, esc.linea_a) == [(D("50.00"), D("60.00"))]


async def test_an_edit_waits_for_a_recorte_in_flight_and_chains_after_it(
        escenario_tope):
    esc = escenario_tope
    token = await _token(esc)
    async with esc.maker() as recorta, esc.maker() as edita:
        await _recortar(recorta, esc, token)
        tarea = asyncio.create_task(_editar(edita, esc, esc.linea_a, 45))
        await _esperar(tarea, "la edición debía esperar al recorte")

        await recorta.commit()
        await _terminar(tarea)
        await edita.commit()

    assert await _valor(esc, esc.linea_a) == D("45.00")
    assert await _historial(esc, esc.linea_a) == [
        (D("50.00"), D("30.00")), (D("30.00"), D("45.00"))]


async def test_a_close_waits_for_a_recorte_in_flight_and_closes_the_cut_one(
        escenario_tope):
    esc = escenario_tope
    token = await _token(esc)
    async with esc.maker() as recorta, esc.maker() as cierra:
        await _recortar(recorta, esc, token)
        tarea = asyncio.create_task(_cerrar(cierra, esc, esc.a))
        await _esperar(tarea, "el cierre debía esperar al recorte")

        await recorta.commit()
        await _terminar(tarea)
        await cierra.commit()

    assert await _estado_pedido(esc, esc.a) == "CERRADO"
    assert await _valor(esc, esc.linea_a) == D("30.00")
    (evento,) = await _leer(esc, select(PedidoEvento.detalle).where(
        PedidoEvento.corrida_id == esc.corrida_id,
        PedidoEvento.sucursal_id == esc.a))
    assert evento[0]["tope"] == "3000"


async def test_a_recorte_waits_for_a_close_in_flight_and_is_061_tp_32(
        escenario_tope):
    esc = escenario_tope
    token = await _token(esc)
    async with esc.maker() as cierra, esc.maker() as recorta:
        await _cerrar(cierra, esc, esc.a)
        tarea = asyncio.create_task(_recortar(recorta, esc, token))
        await _esperar(tarea, "el recorte debía esperar al cierre")

        await cierra.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await _terminar(tarea)
        await recorta.rollback()

    assert error.value.codigo == codigos.E_CORRIDA_RECORTE_NO_BORRADOR
    assert await _valor(esc, esc.linea_a) == D("50.00")
    assert await _historial(esc, esc.linea_a) == []


async def test_a_recorte_on_tienda_a_does_not_wait_for_closing_b_tp_33(
        escenario_tope):
    esc = escenario_tope
    token = await _token(esc)
    async with esc.maker() as cierra, esc.maker() as recorta:
        await _cerrar(cierra, esc, esc.b)

        await asyncio.wait_for(_recortar(recorta, esc, token), timeout=PLAZO)
        await recorta.commit()
        await cierra.commit()

    assert await _estado_pedido(esc, esc.b) == "CERRADO"
    assert await _valor(esc, esc.linea_a) == D("30.00")
    assert await _valor(esc, esc.linea_b) == D("50.00")


async def test_two_applies_with_the_same_token_apply_once_tp_31(
        escenario_tope):
    esc = escenario_tope
    token = await _token(esc)
    async with esc.maker() as primera, esc.maker() as segunda:
        await _recortar(primera, esc, token)
        tarea = asyncio.create_task(_recortar(segunda, esc, token))
        await _esperar(tarea, "el segundo recorte debía esperar al primero")

        await primera.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await _terminar(tarea)
        await segunda.rollback()

    assert error.value.codigo == codigos.E_CORRIDA_PROPUESTA_DESACTUALIZADA
    assert await _valor(esc, esc.linea_a) == D("30.00")
    assert await _historial(esc, esc.linea_a) == [(D("50.00"), D("30.00"))]
