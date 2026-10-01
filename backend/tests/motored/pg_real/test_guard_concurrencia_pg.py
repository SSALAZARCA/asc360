"""
Motored Pedidos F3 "Motor", S7 (sdd/motored-pedidos-motor, ADR-11, tasks
S7-3): la guarda de anulación contra `cerrar` con sesiones concurrentes sobre
un Postgres real (opt-in).

`pedido_tienda.cerrar_tienda` (F4, B3a) toma la carga `FOR SHARE`; la guarda
la toma `FOR UPDATE`. Acá se prueba el orden que imponen esos bloqueos: quien
llega segundo espera al primero y luego ve su resultado (un cierre ve la
corrida invalidada y se rechaza con E-CORRIDA-041), y que ningún orden de
llegada termina en un deadlock.

Hasta B3b la guarda sigue mirando el estado de la CORRIDA: una anulación que
espera a un cierre de tienda termina sin bloquearse (B3b la llevará a las
tiendas y devolverá el E-CARGA-050 que F3 daba al cerrar la corrida entera).

Necesita sesiones distintas y filas confirmadas: siembra un proveedor, un
usuario, una sucursal, una carga y una corrida BORRADOR vinculada con esa
tienda en BORRADOR, y los borra al terminar.
"""
import asyncio
import datetime
import os
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.proveedor import Proveedor
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services.corridas import codigos, guardas, pedido_tienda
from tests.motored.pg_real.test_corrida_pg import CORTE, _carga

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

ESPERA = 0.5


@pytest.fixture
async def escenario():
    """Una corrida BORRADOR vinculada a una carga EXCEL, CONFIRMADA."""
    motor = create_async_engine(URL)
    maker = async_sessionmaker(motor, expire_on_commit=False, autoflush=False)
    sufijo = uuid.uuid4().hex[:6]
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"GUARDA-{sufijo}", nombre="guarda",
        es_principal=False, dias_empaque_default=1, dias_transito_default=1,
        dias_seguridad_default=Decimal("1"))
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Compras", role=MotoredRole.COMPRAS,
        email=f"g-{sufijo}@x.co", hashed_password="x")
    tienda = Sucursal(
        id=uuid.uuid4(), nombre=f"GUARDA {sufijo}", sic=f"G-{sufijo}",
        dias_empaque=1, dias_transito=1)
    carga = _carga(
        "VENTAS", datetime.date(2026, 3, 1), datetime.date(2026, 9, 14))
    corrida = Corrida(
        id=uuid.uuid4(), codigo=f"TST-{sufijo}-01", proveedor_id=proveedor.id,
        fecha_corte=CORTE, estado="BORRADOR")
    async with maker() as db:
        db.add_all([proveedor, usuario, carga, tienda])
        await db.flush()
        db.add(corrida)
        await db.flush()
        db.add_all([
            CorridaCarga(
                corrida_id=corrida.id, carga_id=carga.id, tipo="VENTAS"),
            CorridaSucursal(
                corrida_id=corrida.id, sucursal_id=tienda.id, orden=1,
                estado="OK", estado_pedido="BORRADOR")])
        await db.commit()
    yield SimpleNamespace(
        maker=maker, carga_id=carga.id, corrida_id=corrida.id,
        usuario_id=usuario.id, codigo=corrida.codigo,
        sucursal_id=tienda.id, tienda=tienda.nombre)
    async with maker() as db:
        await db.execute(delete(CorridaCarga).where(
            CorridaCarga.corrida_id == corrida.id))
        await db.execute(delete(Corrida).where(Corrida.id == corrida.id))
        await db.execute(delete(CargaArchivo).where(
            CargaArchivo.id == carga.id))
        await db.execute(delete(Sucursal).where(Sucursal.id == tienda.id))
        await db.execute(delete(Usuario).where(Usuario.id == usuario.id))
        await db.execute(delete(Proveedor).where(
            Proveedor.id == proveedor.id))
        await db.commit()
    await motor.dispose()


async def _estado_de(maker, modelo, clave):
    async with maker() as db:
        return (await db.execute(
            select(modelo).where(modelo.id == clave)
            .execution_options(populate_existing=True))).scalars().one()


async def _anular(db, carga_id):
    """Lo que hace el endpoint: guarda, marcar la carga y confirmar."""
    carga = await db.get(CargaArchivo, carga_id)
    invalidadas = await guardas.aplicar_guard_anulacion(db, carga)
    carga.estado = "ANULADO"
    await db.commit()
    return invalidadas


async def _cerrar(db, escenario):
    tienda = await pedido_tienda.cerrar_tienda(
        db, escenario.corrida_id, escenario.sucursal_id,
        escenario.usuario_id)
    await db.commit()
    return tienda


async def test_an_annulment_waits_for_a_close_in_flight_and_is_then_blocked(
        escenario):
    async with escenario.maker() as cierre, escenario.maker() as anulacion:
        await pedido_tienda.cerrar_tienda(
            cierre, escenario.corrida_id, escenario.sucursal_id,
            escenario.usuario_id)
        tarea = asyncio.create_task(
            _anular(anulacion, escenario.carga_id))
        await asyncio.sleep(ESPERA)
        assert not tarea.done(), "la anulación debía esperar al cierre"

        await cierre.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await asyncio.wait_for(tarea, timeout=10)

    assert error.value.codigo == codigos.E_CARGA_ANULACION_BLOQUEADA
    assert escenario.tienda in error.value.mensaje
    assert escenario.codigo in error.value.mensaje
    carga = await _estado_de(escenario.maker, CargaArchivo, escenario.carga_id)
    corrida = await _estado_de(escenario.maker, Corrida, escenario.corrida_id)
    assert carga.estado != "ANULADO"
    assert corrida.invalidada is False
    async with escenario.maker() as db:
        estado = (await db.execute(
            select(CorridaSucursal.estado_pedido).where(
                CorridaSucursal.corrida_id == escenario.corrida_id)
        )).scalar_one()
    assert estado == "CERRADO"


async def test_a_close_waits_for_an_annulment_in_flight_and_is_refused(
        escenario):
    async with escenario.maker() as cierre, escenario.maker() as anulacion:
        carga = await anulacion.get(CargaArchivo, escenario.carga_id)
        invalidadas = await guardas.aplicar_guard_anulacion(anulacion, carga)
        carga.estado = "ANULADO"
        await anulacion.flush()
        tarea = asyncio.create_task(_cerrar(cierre, escenario))
        await asyncio.sleep(ESPERA)
        assert not tarea.done(), "el cierre debía esperar a la anulación"

        await anulacion.commit()
        with pytest.raises(codigos.ErrorCorrida) as error:
            await asyncio.wait_for(tarea, timeout=10)

    assert invalidadas == [escenario.codigo]
    assert error.value.codigo == codigos.E_CORRIDA_INVALIDADA
    corrida = await _estado_de(escenario.maker, Corrida, escenario.corrida_id)
    assert corrida.estado == "BORRADOR" and corrida.invalidada is True


async def test_a_close_and_an_annulment_in_flight_never_deadlock(escenario):
    """La anulación toma la carga y queda detenida justo después; el cierre
    llega y se pone a esperar; la anulación sigue. Con un orden de bloqueos
    distinto en cada lado (corrida y luego carga en el cierre; carga y luego
    corrida en la anulación) Postgres aborta a uno con `deadlock detected`."""
    llegada, seguir = asyncio.Event(), asyncio.Event()
    async with escenario.maker() as cierre, escenario.maker() as anulacion:
        original = anulacion.execute
        cuenta = []

        async def execute(sentencia, *args, **kwargs):
            resultado = await original(sentencia, *args, **kwargs)
            cuenta.append(1)
            if len(cuenta) == 1:  # ya tiene el FOR UPDATE de la carga
                llegada.set()
                await seguir.wait()
            return resultado

        anulacion.execute = execute
        t_anular = asyncio.create_task(_anular(anulacion, escenario.carga_id))
        await asyncio.wait_for(llegada.wait(), timeout=10)
        t_cerrar = asyncio.create_task(_cerrar(cierre, escenario))
        await asyncio.sleep(ESPERA)
        seguir.set()
        resultados = await asyncio.wait_for(
            asyncio.gather(t_anular, t_cerrar, return_exceptions=True),
            timeout=20)

    anulada, cierre_resultado = resultados
    assert anulada == [escenario.codigo], resultados
    assert isinstance(cierre_resultado, codigos.ErrorCorrida), resultados
    assert cierre_resultado.codigo == codigos.E_CORRIDA_INVALIDADA
    carga = await _estado_de(escenario.maker, CargaArchivo, escenario.carga_id)
    corrida = await _estado_de(escenario.maker, Corrida, escenario.corrida_id)
    assert carga.estado == "ANULADO"
    assert corrida.estado == "BORRADOR" and corrida.invalidada is True
