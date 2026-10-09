"""
Invoices of an excluded order type (GARANTIA25) never enter the ingreso
process, against a real Postgres (opt-in, `MOTORED_TEST_PG_URL`, database
migrated to head; odd/tasks/motored-ingresos-pendientes.md).

Same isolation as `test_ingresos_pendientes_pg.py`: one rolled-back outer
transaction, window from 1900, invoices dated 2097 with fresh numbers.
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.vendedor import Vendedor
from app.motored.services import informe_publico as publico
from app.motored.services import ingresos_pendientes as ip
from app.motored.services import ingresos_plantilla as pl
from app.motored.services.ingesta import facturas as ing
from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

D = Decimal
HOY = datetime.date(2097, 10, 8)
DESDE = datetime.date(1900, 1, 1)
HMCL_NIT = "900723988"


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


def _carga(tipo):
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen="EXCEL", estado="APLICADO",
        nombre_archivo="x.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)


@pytest.fixture
async def mundo(fabrica):
    sfx = uuid.uuid4().hex[:6]
    async with fabrica() as db:
        cali = Sucursal(id=uuid.uuid4(), nombre=f"Cali {sfx}", sic=f"S1-{sfx}",
                        codigo_co=codigo_co_unico(), bodega_principal="BF021")
        db.add(cali)
        prov = Proveedor(
            id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
            dias_empaque_default=4, dias_transito_default=5,
            dias_seguridad_default=D("3"))
        db.add(prov)
        await db.flush()
        refs = [Referencia(id=uuid.uuid4(), codigo=f"R{i:02d}-{sfx}",
                           proveedor_id=prov.id, unidad_empaque=1,
                           precio_normal=None, linea_comercial="X")
                for i in range(12)]
        db.add_all(refs)
        fact, ingr = _carga("FACTURAS_PEDIDOS"), _carga("INGRESOS_FACTURAS")
        db.add_all([fact, ingr])
        await db.flush()

        def linea(numero, ref, tipo, nit=None):
            db.add(FacturaProveedorLinea(
                id=uuid.uuid4(), prefijo_rh="RH", numero_rh=numero,
                fecha_factura=datetime.date(2097, 10, 3), sucursal_id=cali.id,
                referencia_id=ref.id, cantidad=D(1), valor_total=D(10),
                tipo_pedido=tipo, cliente_nit=nit, carga_id=fact.id))

        base = 900000000 + int(sfx, 16) % 1000000 * 10
        n = {k: base + i for i, k in enumerate(
            ("garantia", "normal", "viejo", "otro", "mixta", "grande"))}
        linea(n["garantia"], refs[0], "GARANTIA25", HMCL_NIT)
        linea(n["normal"], refs[0], "NORMAL", HMCL_NIT)       # HMCL NIT, kept
        linea(n["viejo"], refs[0], None)                       # old load, kept
        linea(n["otro"], refs[0], "OTRO")
        linea(n["mixta"], refs[0], "GARANTIA25")
        linea(n["mixta"], refs[1], "NORMAL")
        for ref in refs:                                       # analyst invoice
            linea(n["grande"], ref, "GARANTIA25")
            linea(n["grande"] + 1000, ref, "NORMAL")
        n["grande_normal"] = n["grande"] + 1000
        db.add(IngresoFactura(
            id=uuid.uuid4(), prefijo_rh="RH", numero_rh=1,
            fecha_ingreso=DESDE, valor_neto=D(1), carga_id=ingr.id))
        cedula = f"7{int(sfx, 16) % 10**8:08d}"
        usuario = Usuario(
            id=uuid.uuid4(), nombre=f"Ana {sfx}", role=MotoredRole.ASESOR_MOSTRADOR,
            activo=True, status="approved", cedula=cedula, cedula_aprobada=True,
            telegram_id=int(str(uuid.uuid4().int)[:9]))
        db.add(usuario)
        await db.flush()
        db.add(Vendedor(
            id=uuid.uuid4(), nombre=f"Ana {sfx}", nombre_norm=f"ANA {sfx}".upper(),
            cargo="ASESOR DE REPUESTOS", sucursal_id=cali.id, cedula=cedula,
            usuario_id=usuario.id))
        db.add(ReporteAsesorLink(
            id=uuid.uuid4(), usuario_id=usuario.id, cedula=cedula,
            token=uuid.uuid4().hex + uuid.uuid4().hex))
        await db.commit()

    class M:
        pass
    m = M()
    m.fabrica, m.cali, m.n, m.cedula = fabrica, cali, n, cedula
    m.refs = refs
    return m


def _nuestras(items, n):
    return {i["numero_rh"]: i for i in items if i["numero_rh"] in set(n.values())}


async def test_panel_excludes_the_type_keeps_null_and_ignores_the_nit(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        items = _nuestras(await ip.pendientes(db, hoy=HOY), n)
        por_tienda = _nuestras(await ip.pendientes(db, [mundo.cali.id], HOY), n)
    assert n["garantia"] not in items and n["grande"] not in items
    assert {n["normal"], n["viejo"], n["otro"], n["mixta"], n["grande_normal"]} \
        <= set(items)
    assert set(por_tienda) == set(items)
    # the mixed invoice keeps only its non-excluded line
    assert items[n["mixta"]]["unidades"] == 1 and items[n["mixta"]]["num_referencias"] == 1


async def test_asesor_card_and_public_link_leave_the_type_out(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        bloque = await ip.para_asesor(db, [mundo.cali.id])
        tiendas = await ip.tiendas_de_asesor(db, None, mundo.cedula)
        enlace = await ip.para_asesor(db, tiendas)
    for b in (bloque, enlace):
        numeros = set(_nuestras(b["items"], n))
        assert n["garantia"] not in numeros and n["normal"] in numeros


async def test_confirming_an_excluded_invoice_is_a_409(mundo):
    async with mundo.fabrica() as db:
        with pytest.raises(ip.PendienteError) as exc:
            await ip.confirmar(db, f"RH {mundo.n['garantia']}", mundo.cali.id,
                               "LLEGO", ip.Actor(nombre="Coord"), "web")
    assert exc.value.status_code == 409


async def test_template_of_an_excluded_invoice_is_a_404_and_lines_skip_the_type(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        with pytest.raises(pl.PlantillaError) as exc:
            await pl.preparar(db, ("RH", n["grande"]), mundo.cali.id, HOY)
        assert exc.value.status_code == 404
        await ip.confirmar(db, f"RH {n['grande_normal']}", mundo.cali.id,
                           "LLEGO", ip.Actor(nombre="Coord"), "web")
        datos = await pl.preparar(db, ("RH", n["grande_normal"]), mundo.cali.id, HOY)
        assert len(datos.lineas) == 12
        # mixed invoice: the template carries only the non-excluded line
        lineas = await pl._lineas(db, ("RH", n["mixta"]), mundo.cali.id, ("GARANTIA25",))
        assert [l.referencia for l in lineas] == [mundo.refs[1].codigo]


async def test_config_change_is_respected(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        db.add(ParametroMetodologia(
            id=uuid.uuid4(), clave=ip.CLAVE_TIPOS_EXCLUIDOS,
            valor=["NORMAL"], vigente_desde=datetime.date(2097, 10, 1)))
        await db.flush()
        items = _nuestras(await ip.pendientes(db, hoy=HOY), n)
    assert n["normal"] not in items and n["grande_normal"] not in items
    assert n["garantia"] in items and n["otro"] in items and n["viejo"] in items


def _upsert(carga_id, suc, ref, nit, tipo, numero):
    consolidado = {(suc, ref, "RH", numero): {
        "cantidad": D(1), "valor_total": D(10), "valor_unitario": None,
        "cliente_nit": nit, "tipo_pedido": tipo,
        "fecha_factura": datetime.date(2097, 10, 3)}}
    return ing.construir_statement_upsert(consolidado, carga_id)


async def test_reload_overwrites_with_a_value_and_keeps_on_null(mundo):
    numero = mundo.n["otro"]            # stored with NULL nit and type "OTRO"
    ref_id = mundo.refs[0].id
    async with mundo.fabrica() as db:
        carga = _carga("FACTURAS_PEDIDOS")
        db.add(carga)
        await db.flush()

        async def leer():
            fila = (await db.execute(select(
                FacturaProveedorLinea.cliente_nit,
                FacturaProveedorLinea.tipo_pedido).where(
                FacturaProveedorLinea.numero_rh == numero))).one()
            return tuple(fila)

        await db.execute(_upsert(carga.id, mundo.cali.id, ref_id, HMCL_NIT, "GARANTIA25", numero))
        assert await leer() == (HMCL_NIT, "GARANTIA25")
        await db.execute(_upsert(carga.id, mundo.cali.id, ref_id, None, None, numero))
        assert await leer() == (HMCL_NIT, "GARANTIA25")
        await db.execute(_upsert(carga.id, mundo.cali.id, ref_id, "800", "NORMAL", numero))
        assert await leer() == ("800", "NORMAL")
