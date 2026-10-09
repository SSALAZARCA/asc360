"""
Responsible + ERP template against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`, database migrated to head; odd/tasks/motored-ingresos-
responsable-plantilla.md, T2) and the unit-price upsert (T1).

Same hermetic style as `test_ingresos_pendientes_pg.py`: one outer
transaction rolled back, an ingreso window starting in 1900, invoices dated
2097 with fresh numbers and stores, assertions only on those rows.
"""
import datetime
import io
import os
import uuid
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services import ingresos_pendientes as ip
from app.motored.services import ingresos_plantilla as pl
from app.motored.services.ingesta import facturas
from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

D = Decimal
HOY = datetime.date(2097, 10, 8)
DESDE = datetime.date(1900, 1, 1)


@pytest.fixture
async def fabrica():
    motor = create_async_engine(URL)
    async with motor.connect() as conexion:
        transaccion = await conexion.begin()
        yield async_sessionmaker(
            bind=conexion, class_=AsyncSession, expire_on_commit=False,
            autoflush=False, join_transaction_mode="create_savepoint")
        await transaccion.rollback()
    await motor.dispose()


def _carga(tipo, estado="APLICADO"):
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen="EXCEL", estado=estado,
        nombre_archivo="x.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)


@pytest.fixture
async def mundo(fabrica):
    sfx = uuid.uuid4().hex[:6]
    async with fabrica() as db:
        cali = Sucursal(id=uuid.uuid4(), nombre=f"Cali {sfx}", sic=f"S1-{sfx}",
                        codigo_co=codigo_co_unico(), bodega_principal="BF021")
        sin_bodega = Sucursal(id=uuid.uuid4(), nombre=f"Sin {sfx}", sic=f"S2-{sfx}",
                              codigo_co=codigo_co_unico())
        db.add_all([cali, sin_bodega])
        await db.flush()
        sur = Sucursal(id=uuid.uuid4(), nombre=f"Cali Sur {sfx}", sic=f"S3-{sfx}",
                       codigo_co=codigo_co_unico(), principal_id=cali.id)
        prov = Proveedor(
            id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
            dias_empaque_default=4, dias_transito_default=5,
            dias_seguridad_default=D("3"))
        db.add_all([sur, prov])
        await db.flush()
        refs = [Referencia(id=uuid.uuid4(), codigo=f"R{i:02d}-{sfx}",
                           proveedor_id=prov.id, unidad_empaque=1,
                           precio_normal=None, linea_comercial="X")
                for i in range(13)]
        db.add_all(refs)
        fact, ingr = _carga("FACTURAS_PEDIDOS"), _carga("INGRESOS_FACTURAS")
        db.add_all([fact, ingr])
        await db.flush()

        def linea(numero, ref, cant, valor, suc, unitario=None):
            db.add(FacturaProveedorLinea(
                id=uuid.uuid4(), prefijo_rh="RH", numero_rh=numero,
                fecha_factura=datetime.date(2097, 10, 3), sucursal_id=suc.id,
                referencia_id=ref.id, cantidad=D(cant), valor_total=D(valor),
                valor_unitario=None if unitario is None else D(unitario),
                carga_id=fact.id))

        base = 900000000 + int(sfx, 16) % 1000000 * 10
        n = {"grande": base, "chica": base + 1, "limite": base + 2,
             "sin_bodega": base + 3}
        # 12 references: 11 with quantity, one credited to zero, plus one
        # reference loaded on the associated store too (counted once).
        for i, ref in enumerate(refs[:10]):
            linea(n["grande"], ref, 2, 200, cali, unitario=100)
        linea(n["grande"], refs[10], 3, 10, cali)             # no unit price
        linea(n["grande"], refs[0], 1, 100, sur, unitario=100)  # same ref, sur
        linea(n["grande"], refs[11], 0, 0, cali)              # net zero: out
        linea(n["grande"], refs[12], 1, 7, sur, unitario=7)   # 12th real ref
        for ref in refs[:3]:
            linea(n["chica"], ref, 1, 5, cali, unitario=5)
        for ref in refs[:10]:
            linea(n["limite"], ref, 1, 5, cali, unitario=5)
        for ref in refs[:11]:
            linea(n["sin_bodega"], ref, 1, 5, sin_bodega, unitario=5)
        db.add(IngresoFactura(
            id=uuid.uuid4(), prefijo_rh="RH", numero_rh=1,
            fecha_ingreso=DESDE, valor_neto=D(1), carga_id=ingr.id))
        coord = Usuario(
            id=uuid.uuid4(), nombre=f"Coord {sfx}", role=MotoredRole.COMPRAS,
            activo=True, status="approved", email=f"c{sfx}@x.co", hashed_password="x")
        db.add(coord)
        await db.commit()

    class M:
        pass
    m = M()
    m.fabrica, m.cali, m.sur, m.sin_bodega, m.n, m.coord = (
        fabrica, cali, sur, sin_bodega, n, coord)
    m.refs = refs
    return m


async def _llego(mundo, db, clave, tienda):
    await ip.confirmar(
        db, f"RH {mundo.n[clave]}", tienda.id, "LLEGO",
        ip.Actor(nombre="Coord", usuario_id=mundo.coord.id), "web")


async def test_responsable_and_reference_count_on_real_data(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        items = {i["numero_rh"]: i for i in await ip.pendientes(db, hoy=HOY)}

    assert items[n["grande"]]["num_referencias"] == 12
    assert items[n["grande"]]["responsable"] == "ANALISTA"
    assert items[n["chica"]]["num_referencias"] == 3
    assert items[n["chica"]]["responsable"] == "ASESOR"
    assert items[n["limite"]]["num_referencias"] == 10
    assert items[n["limite"]]["responsable"] == "ASESOR"  # inclusive
    assert items[n["sin_bodega"]]["responsable"] == "ANALISTA"
    assert items[n["grande"]]["puede_descargar_plantilla"] is False


async def test_the_template_of_a_confirmed_analista_invoice(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        await _llego(mundo, db, "grande", mundo.sur)  # via associated store
    async with mundo.fabrica() as db:
        items = {i["numero_rh"]: i for i in await ip.pendientes(db, hoy=HOY)}
        assert items[n["grande"]]["puede_descargar_plantilla"] is True
        datos = await pl.preparar(db, ("RH", n["grande"]), mundo.cali.id, HOY)

    assert datos.codigo_co == mundo.cali.codigo_co and datos.bodega == "BF021"
    assert datos.ajustes["unidad_negocio"] == "003"
    por_ref = {l.referencia: l for l in datos.lineas}
    assert len(por_ref) == 12  # the netted-to-zero reference is out
    assert [l.referencia for l in datos.lineas] == sorted(por_ref)
    primera = por_ref[mundo.refs[0].codigo]
    assert (primera.cantidad, primera.valor_unitario) == (D(3), D(100))
    assert por_ref[mundo.refs[10].codigo].valor_unitario is None  # fallback

    ws = load_workbook(io.BytesIO(pl.construir_libro(datos)))["Entrada Compra"]
    assert ws["B5"].value == f"ENTRADA POR COMPRA RH{n['grande']}"
    assert ws["D1"].value.date() == HOY
    assert ws.max_row == 7 + 12
    fila = {ws.cell(r, 2).value: r for r in range(8, ws.max_row + 1)}
    sin_precio = fila[mundo.refs[10].codigo]
    assert ws.cell(sin_precio, 4).value == pytest.approx(3.33)  # 10 / 3


async def test_errors_on_real_data(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        with pytest.raises(pl.PlantillaError) as e:
            await pl.preparar(db, ("RH", n["chica"]), mundo.cali.id, HOY)
        assert e.value.status_code == 409 and "asesor" in e.value.detail
        with pytest.raises(pl.PlantillaError) as e:
            await pl.preparar(db, ("RH", n["grande"]), mundo.cali.id, HOY)
        assert e.value.status_code == 409 and "llegó" in e.value.detail
        with pytest.raises(pl.PlantillaError) as e:
            await pl.preparar(db, ("RH", 7), mundo.cali.id, HOY)
        assert e.value.status_code == 404
        await _llego(mundo, db, "sin_bodega", mundo.sin_bodega)
        with pytest.raises(pl.PlantillaError) as e:
            await pl.preparar(
                db, ("RH", n["sin_bodega"]), mundo.sin_bodega.id, HOY)
        assert e.value.status_code == 409 and "Tiendas" in e.value.detail


async def test_the_unit_price_survives_a_load_without_that_column(mundo):
    ref = mundo.refs[0]
    clave = (mundo.cali.id, ref.id, "RH", mundo.n["chica"])

    async with mundo.fabrica() as db:
        carga = _carga("FACTURAS_PEDIDOS")
        db.add(carga)
        await db.flush()
        base = {"cantidad": D(1), "valor_total": D(5),
                "fecha_factura": datetime.date(2097, 10, 3)}
        await db.execute(facturas.construir_statement_upsert(
            {clave: {**base, "valor_unitario": None}}, carga.id))
        precio = (await db.execute(select(FacturaProveedorLinea.valor_unitario)
                  .where(FacturaProveedorLinea.sucursal_id == clave[0],
                         FacturaProveedorLinea.referencia_id == clave[1],
                         FacturaProveedorLinea.numero_rh == clave[3]))
                  ).scalar_one()
        assert precio == D(5)  # the earlier price was kept

        await db.execute(facturas.construir_statement_upsert(
            {clave: {**base, "valor_unitario": D("6.5")}}, carga.id))
        precio = (await db.execute(select(FacturaProveedorLinea.valor_unitario)
                  .where(FacturaProveedorLinea.sucursal_id == clave[0],
                         FacturaProveedorLinea.referencia_id == clave[1],
                         FacturaProveedorLinea.numero_rh == clave[3]))
                  ).scalar_one()
        assert precio == D("6.50")
