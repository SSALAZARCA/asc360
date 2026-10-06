"""
Maestro de vendedores contra un Postgres real (opt-in).

Corre solo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base ya migrada con `alembic -c alembic_motored.ini upgrade head`. Cada
test trabaja dentro de una transaccion que se revierte al final (los
`commit()` del codigo bajo prueba se degradan a `flush()`).

Cubre lo que los dobles no pueden: el upsert por `nombre_norm` contra el
indice unico real (la misma persona escrita distinto no se duplica), que la
carga nunca desactiva ni desenlaza a nadie, la resolucion de sucursal contra la
tabla real (nombre, prefijo `MR `, alias) y el listado de "sin registrar"
(excluye cargas ANULADAS y a quienes ya estan en el maestro).
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.api.carga import _resolver_relaciones
from app.motored.api.vendedores import vendedores_sin_registrar
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import carga
from app.motored.services.ingesta.ventas import normalizar_vendedor

from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        monkeypatch.setattr(db, "commit", db.flush)
        yield db
        await db.rollback()
    await motor.dispose()


def _sufijo():
    return uuid.uuid4().hex[:8].upper()


async def _vendedores_de(db, *nombres_norm):
    consulta = select(Vendedor).where(Vendedor.nombre_norm.in_(nombres_norm))
    return (await db.execute(consulta)).scalars().all()


async def test_el_upsert_por_nombre_norm_no_duplica_a_la_misma_persona(sesion):
    sfx = _sufijo()
    primera = await carga.procesar_carga(
        sesion, "vendedor", [{"nombre": f"Ana  Pérez {sfx}", "cargo": "asesor de repuestos", "cedula": "111"}])
    segunda = await carga.procesar_carga(
        sesion, "vendedor", [{"nombre": f"ANA PEREZ {sfx}", "cargo": "jefe de taller", "cedula": "222"}])

    assert primera.insertados == 1 and segunda.actualizados == 1 and segunda.insertados == 0
    [ana] = await _vendedores_de(sesion, normalizar_vendedor(f"Ana Pérez {sfx}"))
    assert ana.nombre == f"Ana Pérez {sfx}"  # el nombre guardado no se reescribe
    assert ana.cargo == "JEFE DE TALLER"
    assert ana.cedula == "222"  # la cedula del archivo reemplaza la guardada


async def test_la_carga_no_desactiva_ni_desenlaza_a_nadie(sesion):
    sfx = _sufijo()
    await carga.procesar_carga(sesion, "vendedor", [{"nombre": f"Luis {sfx}", "cargo": "OTRO", "cedula": "5"}])
    [luis] = await _vendedores_de(sesion, f"LUIS {sfx}")
    luis.activo = False
    await sesion.flush()

    # Un archivo sin Luis, y otro con Luis: ninguno lo borra ni lo reactiva.
    await carga.procesar_carga(sesion, "vendedor", [{"nombre": f"Otra {sfx}", "cargo": "OTRO", "cedula": "6"}])
    await carga.procesar_carga(sesion, "vendedor", [{"nombre": f"Luis {sfx}", "cargo": "CAJERO POSVENTA", "cedula": "5"}])

    [luis] = await _vendedores_de(sesion, f"LUIS {sfx}")
    assert luis.activo is False and luis.cargo == "CAJERO POSVENTA"


async def test_el_indice_unico_impide_dos_vendedores_con_el_mismo_nombre_norm(sesion):
    sfx = _sufijo()
    for _ in range(2):
        sesion.add(Vendedor(
            id=uuid.uuid4(), nombre=f"Ana {sfx}", nombre_norm=f"ANA {sfx}", cargo="OTRO", activo=True))

    with pytest.raises(IntegrityError):
        await sesion.flush()


async def test_la_sucursal_se_resuelve_por_nombre_prefijo_mr_y_alias(sesion):
    sfx = _sufijo()
    suc = Sucursal(
        id=uuid.uuid4(), nombre=f"Cali Norte {sfx}", sic=f"S-{sfx}",
        codigo_co=codigo_co_unico())
    sesion.add(suc)
    await sesion.flush()
    sesion.add(SucursalAlias(id=uuid.uuid4(), texto_normalizado=f"SEDE VIEJA {sfx}", sucursal_id=suc.id))
    await sesion.flush()
    filas = [
        {"nombre": f"A {sfx}", "cargo": "OTRO", "cedula": "65", "sucursal_nombre": f"MR cali  norte {sfx}"},
        {"nombre": f"B {sfx}", "cargo": "OTRO", "cedula": "66", "sucursal_nombre": f"sede vieja {sfx}"},
        {"nombre": f"C {sfx}", "cargo": "OTRO", "cedula": "67", "sucursal_nombre": f"No Existe {sfx}"},
    ]

    resueltas, errores = await _resolver_relaciones(sesion, "vendedor", filas)

    assert resueltas[0]["sucursal_id"] == suc.id and resueltas[1]["sucursal_id"] == suc.id
    assert [e["fila"] for e in errores] == [3]


async def test_la_sucursal_se_resuelve_por_codigo_co_sin_importar_mayusculas(sesion):
    sfx = _sufijo()
    co = "Y" + str(int(sfx, 16) % 100).zfill(2)
    suc = Sucursal(
        id=uuid.uuid4(), nombre=f"Cali Sur {sfx}", sic=f"S-{sfx}",
        codigo_co=co)
    sesion.add(suc)
    await sesion.flush()
    filas = [
        {"nombre": f"A {sfx}", "cargo": "OTRO", "cedula": "75", "sucursal_nombre": co},
        {"nombre": f"B {sfx}", "cargo": "OTRO", "cedula": "76", "sucursal_nombre": f" {co.lower()} "},
        {"nombre": f"C {sfx}", "cargo": "OTRO", "cedula": "77", "sucursal_nombre": "Z99"},
    ]

    resueltas, errores = await _resolver_relaciones(sesion, "vendedor", filas)

    assert resueltas[0]["sucursal_id"] == suc.id and resueltas[1]["sucursal_id"] == suc.id
    assert [e["fila"] for e in errores] == [3]


async def _mundo_ventas(db, sfx):
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
        dias_empaque_default=4, dias_transito_default=5, dias_seguridad_default=Decimal("3"))
    sucursal = Sucursal(
        id=uuid.uuid4(), nombre=f"S {sfx}", sic=f"SIC-{sfx}",
        codigo_co=codigo_co_unico())
    db.add_all([proveedor, sucursal])
    await db.flush()
    referencia = Referencia(
        id=uuid.uuid4(), codigo=f"R-{sfx}", proveedor_id=proveedor.id,
        unidad_empaque=1, precio_normal=Decimal("100"))
    cargas = {
        estado: CargaArchivo(
            id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado=estado,
            nombre_archivo="v.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)
        for estado in ("APLICADO", "ANULADO")
    }
    db.add_all([referencia, *cargas.values()])
    await db.flush()
    return sucursal, referencia, cargas


def _linea(carga, sucursal, referencia, vendedor, fecha, nro):
    return VentaDetalle(
        id=uuid.uuid4(), carga_id=carga.id, fecha=fecha, anio=fecha.year, mes=fecha.month,
        sucursal_id=sucursal.id, referencia_id=referencia.id, origen="MOSTRADOR",
        cantidad=Decimal("1"), vendedor=vendedor, vendedor_norm=normalizar_vendedor(vendedor),
        valor_bruto=Decimal("1000"), valor_descuentos=Decimal("0"),
        cliente_factura="X", nro_documento=nro)


async def test_sin_registrar_excluye_anuladas_y_a_los_ya_registrados(sesion):
    sfx = _sufijo()
    suc, ref, cargas = await _mundo_ventas(sesion, sfx)
    aplicada, anulada = cargas["APLICADO"], cargas["ANULADO"]
    sesion.add_all([
        # Falta registrar: dos escrituras de la misma persona en cargas validas.
        _linea(aplicada, suc, ref, f"Juan  Gómez {sfx}", datetime.date(2099, 9, 1), "1"),
        _linea(aplicada, suc, ref, f"JUAN GOMEZ {sfx}", datetime.date(2099, 9, 5), "2"),
        # Ya registrado (aunque este inactivo): no debe salir.
        _linea(aplicada, suc, ref, f"Ana Pérez {sfx}", datetime.date(2099, 9, 1), "3"),
        # Solo en una carga ANULADA: no debe salir.
        _linea(anulada, suc, ref, f"Fantasma {sfx}", datetime.date(2099, 9, 1), "4"),
        Vendedor(
            id=uuid.uuid4(), nombre=f"Ana Perez {sfx}", nombre_norm=f"ANA PEREZ {sfx}",
            cargo="OTRO", activo=False),
    ])
    await sesion.flush()

    filas = await vendedores_sin_registrar(db=sesion, user=None)

    propios = [f for f in filas if f["vendedor_norm"].endswith(sfx)]
    assert [f["vendedor_norm"] for f in propios] == [f"JUAN GOMEZ {sfx}"]
    assert propios[0]["lineas"] == 2
    assert propios[0]["ultima_venta"] == "2099-09-05"
    assert propios[0]["vendedor_ejemplo"].upper().startswith("JUAN")


async def test_sin_registrar_cuenta_las_lineas_de_cada_vendedor(sesion):
    sfx = _sufijo()
    suc, ref, cargas = await _mundo_ventas(sesion, sfx)
    c = cargas["APLICADO"]
    sesion.add_all(
        [_linea(c, suc, ref, f"Pocas {sfx}", datetime.date(2099, 9, 1), f"a{i}") for i in range(1)]
        + [_linea(c, suc, ref, f"Muchas {sfx}", datetime.date(2099, 9, 1), f"b{i}") for i in range(3)])
    await sesion.flush()

    filas = [f for f in await vendedores_sin_registrar(db=sesion, user=None) if f["vendedor_norm"].endswith(sfx)]

    assert [(f["vendedor_norm"], f["lineas"]) for f in filas] == [(f"MUCHAS {sfx}", 3), (f"POCAS {sfx}", 1)]


async def test_sin_registrar_excluye_el_vendedor_norm_vacio(sesion):
    sfx = _sufijo()
    suc, ref, cargas = await _mundo_ventas(sesion, sfx)
    c = cargas["APLICADO"]
    vacia = _linea(c, suc, ref, f"x {sfx}", datetime.date(2099, 9, 1), "v1")
    vacia.vendedor_norm = ""
    sesion.add_all([vacia, _linea(c, suc, ref, f"Real {sfx}", datetime.date(2099, 9, 1), "v2")])
    await sesion.flush()

    filas = await vendedores_sin_registrar(db=sesion, user=None)

    assert "" not in [f["vendedor_norm"] for f in filas]
    assert f"REAL {sfx}" in [f["vendedor_norm"] for f in filas]
