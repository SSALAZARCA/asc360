"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B3b, ADR-1, ADR-3,
ADR-5, spec CI-23..CI-41, DM-09..DM-12, decisiones F4-13 y F4-15): enviar el
pedido de una tienda, el envío duplicado entre corridas, la corrección del
número de orden, anular una corrida y la guarda de cargas, contra un
Postgres real (opt-in).

Primero las reglas con sesiones sucesivas (la UNIQUE y los CHECK de
`corrida_envio` son los de verdad) y después las carreras con VARIAS
CONEXIONES: dos corridas que envían la misma tienda y corte a la vez
(exactamente un éxito), enviar contra reabrir, anular la corrida contra
cerrar y la guarda de cargas contra reabrir. Una sesión que «sostiene» una
operación sin confirmar deja a la otra esperando, que es lo que se mide.

Siembra, CONFIRMADO: un proveedor, un usuario, dos tiendas OK con una línea
de 50 en cada una de tres corridas BORRADOR (C1 y C2 con el mismo corte, C3
con otro) y una carga EXCEL vinculada a C1; lo borra todo al terminar.
"""
import asyncio
import datetime
import os
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_envio import CorridaEnvio
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.pedido_evento import PedidoEvento
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services.corridas import (
    codigos,
    envio,
    guardas,
    pedido_tienda,
    servicio,
)
from tests.motored.pg_real.test_corrida_pg import CORTE, _carga

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

OTRO_CORTE = CORTE + datetime.timedelta(days=7)
FECHA = datetime.date(2026, 9, 22)
ESPERA = 0.5
PLAZO = 10
D = Decimal


def _linea(corrida, sucursal, referencia):
    cero = D("0.00")
    return CorridaLinea(
        corrida_id=corrida.id, sucursal_id=sucursal.id,
        referencia_id=referencia.id, codigo_referencia=referencia.codigo,
        nombre_parte="PARTE", unidad_empaque=1, banderas=[],
        **{f"venta_m{m}": cero for m in range(1, 7)},
        **{f"perdida_m{m}": cero for m in range(1, 7)},
        inventario=cero, transito=cero, backorder=cero, ajuste=cero,
        pedido_sugerido=D("50.00"), pedido_final=D("50.00"),
        precio=D("100.00"), valor_pedido=D("5000.00"), clase="AF",
        estado_quiebre="NORMAL")


def _objetos(sufijo):
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"ENV-{sufijo}", nombre="envio",
        es_principal=False, dias_empaque_default=1, dias_transito_default=1,
        dias_seguridad_default=D("1"))
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Compras", role=MotoredRole.COMPRAS,
        email=f"e-{sufijo}@x.co", hashed_password="x")
    tiendas = [
        Sucursal(id=uuid.uuid4(), nombre=f"{n} {sufijo}",
                 sic=f"S-{n}-{sufijo}", dias_empaque=1, dias_transito=1)
        for n in ("A", "B")]
    referencia = Referencia(
        id=uuid.uuid4(), codigo=f"R1-{sufijo}", proveedor_id=proveedor.id,
        unidad_empaque=1, precio_normal=D("100.00"))
    corridas = [
        Corrida(
            id=uuid.uuid4(), codigo=f"TST-{sufijo}-0{n}",
            proveedor_id=proveedor.id, fecha_corte=corte, estado="BORRADOR")
        for n, corte in ((1, CORTE), (2, CORTE), (3, OTRO_CORTE))]
    return proveedor, usuario, tiendas, referencia, corridas


async def _sembrar(maker, proveedor, usuario, tiendas, referencia, corridas,
                   carga):
    async with maker() as db:
        db.add_all([proveedor, usuario, carga, *tiendas])
        await db.flush()
        db.add_all([referencia, *corridas])
        await db.flush()
        for corrida in corridas:
            db.add_all([
                CorridaSucursal(
                    corrida_id=corrida.id, sucursal_id=t.id, orden=i,
                    estado="OK", estado_pedido="BORRADOR")
                for i, t in enumerate(tiendas, start=1)])
            db.add_all([_linea(corrida, t, referencia) for t in tiendas])
        db.add(CorridaCarga(
            corrida_id=corridas[0].id, carga_id=carga.id, tipo="VENTAS"))
        await db.commit()


async def _borrar(maker, proveedor, usuario, tiendas, referencia, corridas,
                  carga):
    ids = [c.id for c in corridas]
    async with maker() as db:
        await db.execute(delete(CorridaEnvio).where(
            CorridaEnvio.corrida_id.in_(ids)))
        await db.execute(delete(CorridaCarga).where(
            CorridaCarga.corrida_id.in_(ids)))
        await db.execute(delete(Corrida).where(Corrida.id.in_(ids)))
        await db.execute(delete(CargaArchivo).where(
            CargaArchivo.id == carga.id))
        await db.execute(delete(Referencia).where(
            Referencia.id == referencia.id))
        for tienda in tiendas:
            await db.execute(delete(Sucursal).where(Sucursal.id == tienda.id))
        await db.execute(delete(Usuario).where(Usuario.id == usuario.id))
        await db.execute(delete(Proveedor).where(
            Proveedor.id == proveedor.id))
        await db.commit()


@pytest.fixture
async def escenario():
    motor = create_async_engine(URL)
    maker = async_sessionmaker(motor, expire_on_commit=False, autoflush=False)
    proveedor, usuario, tiendas, referencia, corridas = _objetos(
        uuid.uuid4().hex[:6])
    carga = _carga(
        "VENTAS", datetime.date(2026, 3, 1), datetime.date(2026, 9, 14))
    await _sembrar(
        maker, proveedor, usuario, tiendas, referencia, corridas, carga)
    yield SimpleNamespace(
        maker=maker, usuario_id=usuario.id, carga_id=carga.id,
        a=tiendas[0].id, b=tiendas[1].id, nombre_a=tiendas[0].nombre,
        nombre_b=tiendas[1].nombre,
        c1=corridas[0].id, c2=corridas[1].id, c3=corridas[2].id,
        codigo1=corridas[0].codigo, codigo2=corridas[1].codigo)
    await _borrar(
        maker, proveedor, usuario, tiendas, referencia, corridas, carga)
    await motor.dispose()


# --- Ayudas -----------------------------------------------------------------


async def _hacer(esc, operacion):
    """Corre `operacion(db)` en su propia sesión y confirma (o deshace)."""
    async with esc.maker() as db:
        try:
            resultado = await operacion(db)
        except BaseException:
            await db.rollback()
            raise
        await db.commit()
        return resultado


async def _cerrar(esc, corrida, tienda):
    return await _hacer(esc, lambda db: pedido_tienda.cerrar_tienda(
        db, corrida, tienda, esc.usuario_id))


async def _enviar(esc, corrida, tienda, numero="12345", fecha=FECHA):
    return await _hacer(esc, lambda db: envio.enviar_tienda(
        db, corrida, tienda, numero, fecha, esc.usuario_id))


async def _reabrir(esc, corrida, tienda):
    return await _hacer(esc, lambda db: pedido_tienda.reabrir_tienda(
        db, corrida, tienda, esc.usuario_id, "ajuste"))


async def _anular_corrida(esc, corrida):
    return await _hacer(esc, lambda db: servicio.anular_corrida(
        db, corrida, esc.usuario_id, "datos malos"))


async def _anular_carga(esc):
    """Lo que hace el endpoint de cargas: la guarda, marcar y confirmar."""
    async def operacion(sesion):
        carga = await sesion.get(CargaArchivo, esc.carga_id)
        invalidadas = await guardas.aplicar_guard_anulacion(sesion, carga)
        carga.estado = "ANULADO"
        return invalidadas

    return await _hacer(esc, operacion)


async def _error(coro):
    with pytest.raises(codigos.ErrorCorrida) as error:
        await coro
    return error.value


async def _leer(esc, consulta):
    async with esc.maker() as db:
        return (await db.execute(
            consulta.execution_options(populate_existing=True))).all()


async def _estado_pedido(esc, corrida, tienda):
    (fila,) = await _leer(esc, select(CorridaSucursal.estado_pedido).where(
        CorridaSucursal.corrida_id == corrida,
        CorridaSucursal.sucursal_id == tienda))
    return fila[0]


async def _envios(esc, corrida):
    filas = await _leer(esc, select(
        CorridaEnvio.sucursal_id, CorridaEnvio.numero_pedido_proveedor,
        CorridaEnvio.fecha_envio).where(CorridaEnvio.corrida_id == corrida))
    return [tuple(f) for f in filas]


async def _eventos(esc, corrida, tienda):
    filas = await _leer(esc, select(
        PedidoEvento.evento, PedidoEvento.detalle).where(
        PedidoEvento.corrida_id == corrida,
        PedidoEvento.sucursal_id == tienda).order_by(PedidoEvento.id))
    return [tuple(f) for f in filas]


async def _corrida(esc, corrida):
    (fila,) = await _leer(esc, select(
        Corrida.estado, Corrida.invalidada).where(Corrida.id == corrida))
    return tuple(fila)


async def _carga_estado(esc):
    (fila,) = await _leer(esc, select(CargaArchivo.estado).where(
        CargaArchivo.id == esc.carga_id))
    return fila[0]


async def _esperar(tarea, mensaje):
    await asyncio.sleep(ESPERA)
    assert not tarea.done(), mensaje


async def _terminar(tarea):
    return await asyncio.wait_for(tarea, timeout=PLAZO)


# --- Enviar -----------------------------------------------------------------


async def test_sending_writes_the_envio_the_event_and_keeps_the_invariant(
        escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)

    resultado = await _enviar(esc, esc.c1, esc.a, "  12345 ")

    assert resultado.envios[0].numero_pedido_proveedor == "12345"
    assert await _estado_pedido(esc, esc.c1, esc.a) == "ENVIADO"
    assert await _envios(esc, esc.c1) == [(esc.a, "12345", FECHA)]
    assert await _eventos(esc, esc.c1, esc.a) == [
        ("CERRADO", None),
        ("ENVIADO", {"numero": "12345", "fecha_envio": "2026-09-22"})]
    assert await _estado_pedido(esc, esc.c1, esc.b) == "BORRADOR"


async def test_a_tienda_not_closed_is_047_and_writes_nothing(escenario):
    esc = escenario

    error = await _error(_enviar(esc, esc.c1, esc.a))

    assert error.codigo == codigos.E_CORRIDA_ENVIAR_NO_CERRADO
    assert await _envios(esc, esc.c1) == []
    assert await _estado_pedido(esc, esc.c1, esc.a) == "BORRADOR"


async def test_sending_twice_is_049_and_keeps_the_stored_number(escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _enviar(esc, esc.c1, esc.a, "11111")

    error = await _error(_enviar(esc, esc.c1, esc.a, "22222"))

    assert error.codigo == codigos.E_CORRIDA_ENVIAR_YA_ENVIADO
    assert "11111" in error.mensaje
    assert await _envios(esc, esc.c1) == [(esc.a, "11111", FECHA)]


@pytest.mark.parametrize("numero,fecha", [
    ("", FECHA), ("x" * 51, FECHA), ("1", CORTE - datetime.timedelta(days=1)),
    ("1", datetime.date(2999, 1, 1))])
async def test_an_invalid_number_or_date_is_048_and_changes_nothing(
        escenario, numero, fecha):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)

    error = await _error(_enviar(esc, esc.c1, esc.a, numero, fecha))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_INVALIDO
    assert await _estado_pedido(esc, esc.c1, esc.a) == "CERRADO"
    assert await _envios(esc, esc.c1) == []


async def test_a_pedido_with_nothing_to_order_closes_but_cannot_send_056(
        escenario):
    esc = escenario
    async with esc.maker() as db:
        await db.execute(update(CorridaLinea).where(
            CorridaLinea.corrida_id == esc.c1,
            CorridaLinea.sucursal_id == esc.b).values(
            pedido_final=D("0.00"), valor_pedido=D("0.00")))
        await db.commit()
    await _cerrar(esc, esc.c1, esc.b)

    error = await _error(_enviar(esc, esc.c1, esc.b))

    assert error.codigo == codigos.E_CORRIDA_NADA_QUE_ENVIAR
    assert await _estado_pedido(esc, esc.c1, esc.b) == "CERRADO"
    assert await _envios(esc, esc.c1) == []


async def test_a_batch_is_all_or_nothing_in_the_database_ci_32(escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    pedidos = [
        envio.PedidoEnviar(esc.a, "1", FECHA),
        envio.PedidoEnviar(esc.b, "2", FECHA)]

    error = await _error(_hacer(
        esc, lambda db: envio.enviar_lote(
            db, esc.c1, pedidos, esc.usuario_id)))

    assert error.codigo == codigos.E_CORRIDA_ENVIAR_NO_CERRADO
    assert await _estado_pedido(esc, esc.c1, esc.a) == "CERRADO"
    assert await _envios(esc, esc.c1) == []


async def test_a_batch_stores_independent_numbers_ci_26(escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _cerrar(esc, esc.c1, esc.b)

    await _hacer(esc, lambda db: envio.enviar_lote(
        db, esc.c1, [envio.PedidoEnviar(esc.b, "B-2", FECHA),
                     envio.PedidoEnviar(esc.a, "A-1", FECHA)],
        esc.usuario_id))

    assert sorted(await _envios(esc, esc.c1)) == sorted([
        (esc.a, "A-1", FECHA), (esc.b, "B-2", FECHA)])
    assert await _estado_pedido(esc, esc.c1, esc.b) == "ENVIADO"


async def test_a_sent_tienda_cannot_be_reopened_or_edited_ci_18(escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _enviar(esc, esc.c1, esc.a, "777")

    error = await _error(_reabrir(esc, esc.c1, esc.a))

    assert error.codigo == codigos.E_CORRIDA_REABRIR_ENVIADO
    assert "777" in error.mensaje
    assert await _estado_pedido(esc, esc.c1, esc.a) == "ENVIADO"


# --- F4-13: un envío por semana ----------------------------------------------


async def test_the_same_tienda_and_corte_in_another_corrida_is_050_ci_34(
        escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _enviar(esc, esc.c1, esc.a, "12345")
    await _cerrar(esc, esc.c2, esc.a)

    error = await _error(_enviar(esc, esc.c2, esc.a, "99999"))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_DUPLICADO
    assert esc.codigo1 in error.mensaje and "12345" in error.mensaje
    assert error.detalle["corrida"] == esc.codigo1
    assert await _estado_pedido(esc, esc.c2, esc.a) == "CERRADO"
    assert await _envios(esc, esc.c2) == []


async def test_another_tienda_or_another_corte_is_allowed_ci_35_ci_36(
        escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _enviar(esc, esc.c1, esc.a, "12345")
    await _cerrar(esc, esc.c2, esc.b)
    await _cerrar(esc, esc.c3, esc.a)

    await _enviar(esc, esc.c2, esc.b, "55")
    await _enviar(esc, esc.c3, esc.a, "66", OTRO_CORTE)

    assert await _estado_pedido(esc, esc.c2, esc.b) == "ENVIADO"
    assert await _estado_pedido(esc, esc.c3, esc.a) == "ENVIADO"


async def test_the_unique_index_backs_the_rule_with_no_precheck(escenario):
    """Aunque la consulta previa no encuentre al rival, la UNIQUE de la base
    rechaza la segunda fila."""
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _enviar(esc, esc.c1, esc.a, "12345")
    async with esc.maker() as db:
        proveedor = (await db.execute(select(Corrida.proveedor_id).where(
            Corrida.id == esc.c2))).scalar_one()
        db.add(CorridaEnvio(
            corrida_id=esc.c2, sucursal_id=esc.a, proveedor_id=proveedor,
            fecha_corte=CORTE, numero_pedido_proveedor="X",
            fecha_envio=FECHA, enviada_por=esc.usuario_id))
        with pytest.raises(IntegrityError) as error:
            await db.flush()
        await db.rollback()

    assert "uq_corrida_envio_corte_sucursal" in str(error.value)


# --- Corregir el número (F4-15) ----------------------------------------------


async def test_correcting_the_number_audits_before_and_after(escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _enviar(esc, esc.c1, esc.a, "12345")

    resultado = await _hacer(esc, lambda db: envio.corregir_numero(
        db, esc.c1, esc.a, " 99999 ", esc.usuario_id))

    assert resultado.cambio is True
    assert await _envios(esc, esc.c1) == [(esc.a, "99999", FECHA)]
    assert await _estado_pedido(esc, esc.c1, esc.a) == "ENVIADO"
    eventos = await _eventos(esc, esc.c1, esc.a)
    assert eventos[-1] == (
        "ENVIO_CORREGIDO", {"antes": "12345", "despues": "99999"})


async def test_the_same_number_is_a_no_op_with_no_event(escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _enviar(esc, esc.c1, esc.a, "12345")

    resultado = await _hacer(esc, lambda db: envio.corregir_numero(
        db, esc.c1, esc.a, "12345", esc.usuario_id))

    assert resultado.cambio is False
    assert [e[0] for e in await _eventos(esc, esc.c1, esc.a)] == [
        "CERRADO", "ENVIADO"]


@pytest.mark.parametrize("cerrar", [False, True])
async def test_correcting_a_pedido_not_sent_is_067(escenario, cerrar):
    esc = escenario
    if cerrar:
        await _cerrar(esc, esc.c1, esc.a)

    error = await _error(_hacer(esc, lambda db: envio.corregir_numero(
        db, esc.c1, esc.a, "1", esc.usuario_id)))

    assert error.codigo == codigos.E_CORRIDA_CORREGIR_NO_ENVIADO


async def test_a_blank_corrected_number_is_048_and_keeps_the_stored_one(
        escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _enviar(esc, esc.c1, esc.a, "12345")

    error = await _error(_hacer(esc, lambda db: envio.corregir_numero(
        db, esc.c1, esc.a, "   ", esc.usuario_id)))

    assert error.codigo == codigos.E_CORRIDA_ENVIO_INVALIDO
    assert await _envios(esc, esc.c1) == [(esc.a, "12345", FECHA)]


async def test_the_number_check_constraint_rejects_a_blank_number(escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _enviar(esc, esc.c1, esc.a, "12345")
    async with esc.maker() as db:
        with pytest.raises(IntegrityError) as error:
            await db.execute(update(CorridaEnvio).where(
                CorridaEnvio.corrida_id == esc.c1).values(
                numero_pedido_proveedor="   "))
        await db.rollback()

    assert "ck_corrida_envio_numero" in str(error.value)


# --- Anular la corrida (051) -------------------------------------------------


@pytest.mark.parametrize("enviar", [False, True])
async def test_annulling_with_a_closed_or_sent_tienda_is_051_ci_37(
        escenario, enviar):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    if enviar:
        await _enviar(esc, esc.c1, esc.a)

    error = await _error(_anular_corrida(esc, esc.c1))

    assert error.codigo == codigos.E_CORRIDA_ANULAR_CON_PEDIDOS
    assert esc.nombre_a in error.mensaje
    assert await _corrida(esc, esc.c1) == ("BORRADOR", False)
    assert await _estado_pedido(esc, esc.c1, esc.b) == "BORRADOR"


async def test_annulling_with_every_tienda_in_borrador_works_ci_39(escenario):
    esc = escenario

    anulada = await _anular_corrida(esc, esc.c1)

    assert anulada.estado == "ANULADA"
    assert await _corrida(esc, esc.c1) == ("ANULADA", False)


async def test_annulling_after_reopening_the_last_closed_tienda_works(
        escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _reabrir(esc, esc.c1, esc.a)

    await _anular_corrida(esc, esc.c1)

    assert await _corrida(esc, esc.c1) == ("ANULADA", False)


# --- La guarda de cargas (DM-09..DM-12) --------------------------------------


@pytest.mark.parametrize("enviar,palabra", [
    (False, "cerrado"), (True, "enviado")])
async def test_a_closed_or_sent_tienda_blocks_the_carga_dm_09_dm_10(
        escenario, enviar, palabra):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    if enviar:
        await _enviar(esc, esc.c1, esc.a)

    error = await _error(_anular_carga(esc))

    assert error.codigo == codigos.E_CARGA_ANULACION_BLOQUEADA
    assert error.mensaje == (
        f"La carga la usa el pedido {palabra} de {esc.nombre_a} (corrida "
        f"{esc.codigo1}) y no se puede anular.")
    assert await _carga_estado(esc) != "ANULADO"
    assert await _corrida(esc, esc.c1) == ("BORRADOR", False)


async def test_one_closed_tienda_among_borrador_ones_blocks_dm_10(escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.b)

    error = await _error(_anular_carga(esc))

    assert error.detalle == {
        "corrida": esc.codigo1, "tienda": esc.nombre_b,
        "estado_pedido": "CERRADO"}
    assert esc.nombre_a not in error.mensaje


async def test_reopening_the_last_closed_tienda_lets_the_carga_go_dm_11(
        escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _reabrir(esc, esc.c1, esc.a)

    invalidadas = await _anular_carga(esc)

    assert invalidadas == [esc.codigo1]
    assert await _carga_estado(esc) == "ANULADO"
    assert await _corrida(esc, esc.c1) == ("BORRADOR", True)
    error = await _error(_cerrar(esc, esc.c1, esc.b))
    assert error.codigo == codigos.E_CORRIDA_INVALIDADA


async def test_reopening_one_tienda_while_another_stays_closed_keeps_blocking(
        escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _cerrar(esc, esc.c1, esc.b)
    await _reabrir(esc, esc.c1, esc.a)

    error = await _error(_anular_carga(esc))

    assert error.codigo == codigos.E_CARGA_ANULACION_BLOQUEADA


async def test_a_legacy_cerrada_corrida_blocks_even_with_no_closed_tienda(
        escenario):
    """Una corrida que F3 dejó CERRADA (sin tiendas cerradas) bloquea con el
    texto de F3, que nombra sólo la corrida."""
    esc = escenario
    async with esc.maker() as db:
        await db.execute(update(Corrida).where(
            Corrida.id == esc.c1).values(estado="CERRADA"))
        await db.commit()

    error = await _error(_anular_carga(esc))

    assert error.codigo == codigos.E_CARGA_ANULACION_BLOQUEADA
    assert error.mensaje == (
        f"La carga la usa la corrida cerrada {esc.codigo1} y no se puede "
        "anular.")
    assert error.detalle["tienda"] is None


async def test_an_unused_carga_and_all_borrador_corridas_annul_as_in_f2(
        escenario):
    esc = escenario

    invalidadas = await _anular_carga(esc)

    assert invalidadas == [esc.codigo1]
    assert await _carga_estado(esc) == "ANULADO"


# --- Carreras (CI-23, CI-36c) ------------------------------------------------


async def test_two_corridas_sending_the_same_tienda_and_corte_one_wins_ci_36c(
        escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    await _cerrar(esc, esc.c2, esc.a)
    async with esc.maker() as primera, esc.maker() as segunda:
        await envio.enviar_tienda(
            primera, esc.c1, esc.a, "11111", FECHA, esc.usuario_id)
        tarea = asyncio.create_task(envio.enviar_tienda(
            segunda, esc.c2, esc.a, "22222", FECHA, esc.usuario_id))
        await _esperar(tarea, "la segunda debía esperar a la UNIQUE")

        await primera.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await _terminar(tarea)
        await segunda.rollback()

    assert error.value.codigo == codigos.E_CORRIDA_ENVIO_DUPLICADO
    assert esc.codigo1 in error.value.mensaje
    assert "11111" in error.value.mensaje
    assert await _envios(esc, esc.c1) == [(esc.a, "11111", FECHA)]
    assert await _envios(esc, esc.c2) == []
    assert await _estado_pedido(esc, esc.c2, esc.a) == "CERRADO"


async def test_a_send_waits_for_a_reopen_in_flight_and_is_refused_047_ci_23(
        escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    async with esc.maker() as reabre, esc.maker() as envia:
        await pedido_tienda.reabrir_tienda(
            reabre, esc.c1, esc.a, esc.usuario_id, "ajuste")
        tarea = asyncio.create_task(envio.enviar_tienda(
            envia, esc.c1, esc.a, "1", FECHA, esc.usuario_id))
        await _esperar(tarea, "el envío debía esperar al reabrir")

        await reabre.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await _terminar(tarea)
        await envia.rollback()

    assert error.value.codigo == codigos.E_CORRIDA_ENVIAR_NO_CERRADO
    assert await _estado_pedido(esc, esc.c1, esc.a) == "BORRADOR"
    assert await _envios(esc, esc.c1) == []


async def test_a_reopen_waits_for_a_send_in_flight_and_is_refused_045_ci_23(
        escenario):
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    async with esc.maker() as envia, esc.maker() as reabre:
        await envio.enviar_tienda(
            envia, esc.c1, esc.a, "4321", FECHA, esc.usuario_id)
        tarea = asyncio.create_task(pedido_tienda.reabrir_tienda(
            reabre, esc.c1, esc.a, esc.usuario_id, "ajuste"))
        await _esperar(tarea, "el reabrir debía esperar al envío")

        await envia.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await _terminar(tarea)
        await reabre.rollback()

    assert error.value.codigo == codigos.E_CORRIDA_REABRIR_ENVIADO
    assert "4321" in error.value.mensaje
    assert await _estado_pedido(esc, esc.c1, esc.a) == "ENVIADO"


async def test_an_annulment_waits_for_a_close_in_flight_and_is_refused_051(
        escenario):
    esc = escenario
    async with esc.maker() as cierra, esc.maker() as anula:
        await pedido_tienda.cerrar_tienda(
            cierra, esc.c1, esc.a, esc.usuario_id)
        tarea = asyncio.create_task(servicio.anular_corrida(
            anula, esc.c1, esc.usuario_id, "datos malos"))
        await _esperar(tarea, "la anulación debía esperar al cierre")

        await cierra.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await _terminar(tarea)
        await anula.rollback()

    assert error.value.codigo == codigos.E_CORRIDA_ANULAR_CON_PEDIDOS
    assert await _corrida(esc, esc.c1) == ("BORRADOR", False)
    assert await _estado_pedido(esc, esc.c1, esc.a) == "CERRADO"


async def test_a_close_waits_for_an_annulment_in_flight_and_is_refused_040(
        escenario):
    esc = escenario
    async with esc.maker() as anula, esc.maker() as cierra:
        await servicio.anular_corrida(
            anula, esc.c1, esc.usuario_id, "datos malos")
        tarea = asyncio.create_task(pedido_tienda.cerrar_tienda(
            cierra, esc.c1, esc.a, esc.usuario_id))
        await _esperar(tarea, "el cierre debía esperar a la anulación")

        await anula.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await _terminar(tarea)
        await cierra.rollback()

    assert error.value.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE
    assert await _corrida(esc, esc.c1) == ("ANULADA", False)
    assert await _estado_pedido(esc, esc.c1, esc.a) == "BORRADOR"


async def test_the_carga_guard_sees_a_reopen_only_once_it_commits(escenario):
    """Con el reabrir en vuelo, la tienda sigue CERRADO para los demás: la
    guarda bloquea (lo seguro); confirmado el reabrir, la misma anulación
    invalida la corrida y sigue."""
    esc = escenario
    await _cerrar(esc, esc.c1, esc.a)
    async with esc.maker() as reabre:
        await pedido_tienda.reabrir_tienda(
            reabre, esc.c1, esc.a, esc.usuario_id, "ajuste")

        error = await _error(_anular_carga(esc))
        await reabre.commit()

    assert error.codigo == codigos.E_CARGA_ANULACION_BLOQUEADA
    assert await _carga_estado(esc) != "ANULADO"

    invalidadas = await _anular_carga(esc)

    assert invalidadas == [esc.codigo1]
    assert await _carga_estado(esc) == "ANULADO"
