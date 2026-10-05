"""
Tablero de asesores (feature motored-tablero-asesores, T4) contra un Postgres
real (opt-in).

Corre solo con `MOTORED_TEST_PG_URL` apuntando a una base migrada. Cada test
arma un mundo pequeno dentro de una transaccion que se revierte. Las fechas son
del anio 2098 y el inventario de fines de 2099 para no cruzarse con otros datos.

El mundo (todo calculado a mano, ver comentarios) incluye: una carga ANULADA
(no cuenta), un cliente HMCL (tambien escrito como `900883086.0`), un cliente
Tecnired (escrito `800111222.`), una factura con 2 lineas, la misma factura en
otra sucursal (cuenta aparte), una linea sin costo, lineas de referencias con
linea comercial no reconocida (NULL y NO APLICA), un vendedor inactivo y uno que
no esta en el maestro, y un inventario con costos negativos, nulos, de una carga
ANULADA y de un corte anterior.
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.schemas.cliente_tecnired import normalizar_nit
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services.ingesta.ventas import normalizar_vendedor

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

D = Decimal
CORTE = datetime.date(2099, 12, 28)


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


def _carga(tipo, estado):
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen="EXCEL", estado=estado,
        nombre_archivo="x.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)


async def _mundo(db):
    """Crea el mundo descrito arriba y devuelve un objeto con lo necesario."""
    sfx = uuid.uuid4().hex[:8].upper()
    nit_tecnired = "7" + str(uuid.uuid4().int)[:8]
    prov = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
        dias_empaque_default=4, dias_transito_default=5, dias_seguridad_default=D("3"))
    s1 = Sucursal(id=uuid.uuid4(), nombre=f"Cali Norte {sfx}", sic=f"S1-{sfx}")
    s2 = Sucursal(id=uuid.uuid4(), nombre=f"Bogota {sfx}", sic=f"S2-{sfx}")
    db.add_all([prov, s1, s2])
    await db.flush()

    lineas = {
        "R1": " repuestos ", "R2": "ACCESORIOS", "R3": "Llantas", "R4": "NO APLICA",
        "R5": "BATERÍAS", "R6": None,
    }
    refs = {}
    for clave, linea in lineas.items():
        refs[clave] = Referencia(
            id=uuid.uuid4(), codigo=f"{clave}-{sfx}", proveedor_id=prov.id, unidad_empaque=1,
            precio_normal=None, linea_comercial=linea)
    db.add_all(refs.values())
    c_venta, c_anulada_v = _carga("VENTAS", "APLICADO"), _carga("VENTAS", "ANULADO")
    c_inv, c_anulada_i = _carga("INVENTARIO", "APLICADO"), _carga("INVENTARIO", "ANULADO")
    db.add_all([c_venta, c_anulada_v, c_inv, c_anulada_i])
    await db.flush()

    def inv(carga, ref, corte, costo, bodega):
        return InventarioDetalle(
            id=uuid.uuid4(), carga_id=carga.id, fecha_corte=corte, sucursal_id=s1.id,
            referencia_id=refs[ref].id, bodega=bodega, existencia=D("1"), costo_unitario=costo)

    db.add_all([
        # R1: positivos 100 y 300 (mediana 200); negativo y nulo se ignoran; el
        # corte viejo y la carga anulada (con un corte aun mas nuevo) no cuentan.
        inv(c_inv, "R1", CORTE, D("100"), "B1"), inv(c_inv, "R1", CORTE, D("300"), "B2"),
        inv(c_inv, "R1", CORTE, D("-50"), "B3"), inv(c_inv, "R1", CORTE, None, "B4"),
        inv(c_inv, "R1", datetime.date(2099, 12, 1), D("5000"), "B1"),
        inv(c_anulada_i, "R1", datetime.date(2099, 12, 30), D("7777"), "B1"),
        inv(c_inv, "R2", CORTE, D("50"), "B1"),
        inv(c_anulada_i, "R5", CORTE, D("999"), "B1"),  # R5 solo tiene costo en carga anulada
    ])
    db.add(ClienteTecnired(id=uuid.uuid4(), nit=nit_tecnired))

    def persona(nombre, cargo, activo=True, suc=None):
        return Vendedor(
            id=uuid.uuid4(), nombre=f"{nombre} {sfx}", nombre_norm=normalizar_vendedor(f"{nombre} {sfx}"),
            cargo=cargo, sucursal_id=suc.id if suc else None, activo=activo)

    ana = persona("Ana", "ASESOR DE REPUESTOS", suc=s1)
    luis = persona("Luis", "ASESOR DE REPUESTOS SUPERNUMERARIO", suc=s2)
    beto = persona("Beto", "ASESOR COMERCIAL DE SERVICIO POSVENTA")
    fabio = persona("Fabio", "ASESOR COMERCIAL DE SERVICIO POSVENTA")
    carla = persona("Carla", "JEFE DE TALLER")
    dora = persona("Dora", "ASESOR DE REPUESTOS", activo=False)  # inactiva: va a RESTO
    db.add_all([ana, luis, beto, fabio, carla, dora])

    def linea(vend, nro, ref, mes, dia, cant, bruto, desc, cliente, origen="MOSTRADOR", suc=s1, carga=c_venta, anio=2098):
        nombre = f"{vend} {sfx}"
        db.add(VentaDetalle(
            id=uuid.uuid4(), carga_id=carga.id, fecha=datetime.date(anio, mes, dia), anio=anio, mes=mes,
            sucursal_id=suc.id, referencia_id=refs[ref].id, origen=origen, cantidad=D(cant),
            vendedor=nombre, vendedor_norm=normalizar_vendedor(nombre), valor_bruto=D(bruto),
            valor_descuentos=D(desc), cliente_factura=cliente, nro_documento=f"{nro}-{sfx}"))

    # Ana: factura A1 con 2 lineas (REPUESTOS + ACCESORIOS), A2 HMCL, A3 Tecnired,
    # la misma A1 en otra sucursal (otra factura), A4 con linea no reconocida.
    linea("Ana", "A1", "R1", 1, 5, 2, 1000, 100, "Taller X")
    linea("Ana", "A1", "R2", 1, 5, 1, 500, 0, "Taller X")
    linea("Ana", "A2", "R1", 2, 5, 1, 400, 40, "900723988", origen="CRM")
    linea("Ana", "A3", "R3", 6, 5, 3, 900, 90, f"{nit_tecnired}.", origen=" mostrador ")
    linea("Ana", "A4", "R4", 2, 6, 1, 1000, 200, "Taller X")
    linea("Ana", "A1", "R1", 5, 5, 1, 300, 0, "Taller X", suc=s2)
    linea("Ana", "A9", "R1", 7, 5, 1, 99999, 0, "Taller X")  # fuera del rango (mes 7)
    linea("Beto", "B1", "R1", 3, 5, 1, 700, 0, "Cliente Y", origen="VENTA")
    linea("Fabio", "F1", "R2", 3, 6, 4, 400, 0, "Cliente Y", origen="VENTA")
    linea("Carla", "C1", "R5", 4, 5, 2, 600, 60, "Cliente Z", origen="VENTA")
    linea("Luis", "U1", "R1", 2, 7, 1, 200, 0, "Cliente Y")
    linea("Luis", "U2", "R2", 6, 7, 1, 100, 0, "Cliente Y")
    linea("Dora", "D1", "R1", 1, 7, 1, 1000, 100, "900883086.0", origen="VENTA")
    linea("Eva", "E1", "R6", 1, 8, 1, 5000, 0, "Taller X")  # sin linea comercial
    linea("Eva", "E2", "R2", 2, 8, 1, 250, 0, "Taller X", origen="VENTA")
    linea("Fantasma", "X1", "R1", 1, 9, 1, 99999, 0, "Taller X", carga=c_anulada_v)
    await db.flush()
    return sfx, {"ana": ana, "luis": luis}


def _fila(tablero, nombre_empieza=None, clave=None):
    for f in tablero["filas"]:
        if (clave and f["clave"] == clave) or (nombre_empieza and f["nombre"].startswith(nombre_empieza)):
            return f
    raise AssertionError(f"fila no encontrada: {nombre_empieza or clave}")


async def _tablero(db, modo="incluir", desde="2098-01", hasta="2098-06"):
    return await q.calcular_tablero(db, desde, hasta, modo)


async def test_fila_de_una_persona_con_todos_los_indicadores(sesion):
    sfx, _ = await _mundo(sesion)

    tablero = await _tablero(sesion)

    ana = _fila(tablero, "Ana")
    assert (ana["tipo"], ana["cargo"]) == ("PERSONA", "ASESOR DE REPUESTOS")
    assert ana["punto_venta"] == f"Cali Norte {sfx}"
    v = ana["venta"]
    assert v["total"] == 2870.0  # 900 + 500 + 360 + 810 + 300 (A4 y el mes 7 no cuentan)
    assert (v["hmcl"], v["sin_hmcl"]) == (360.0, 2510.0)
    assert v["pct_hmcl"] == pytest.approx(360 / 2870)
    assert v["por_mes"] == {
        "2098-01": 1400.0, "2098-02": 360.0, "2098-03": 0.0, "2098-04": 0.0,
        "2098-05": 300.0, "2098-06": 810.0}
    assert v["por_linea"] == {
        "REPUESTOS": 1560.0, "ACCESORIOS": 500.0, "LLANTAS": 810.0, "LUBRICANTES": 0.0,
        "BATERIAS": 0.0, "GPS": 0.0, "CASCOS": 0.0}
    assert v["mix"]["REPUESTOS"] == pytest.approx(1560 / 2870)
    c = ana["costo"]
    # Mediana REPUESTOS = 200, ACCESORIOS = 50: 2*200 + 1*50 + 1*200 + 1*200; LLANTAS sin costo.
    assert (c["costo_venta"], c["venta_con_costo"], c["utilidad_bruta"]) == (850.0, 2060.0, 1210.0)
    assert c["pct_margen"] == pytest.approx(1210 / 2060)
    assert c["pct_venta_con_costo"] == pytest.approx(2060 / 2870)
    tend = ana["tendencia"]
    assert (tend["ultimos_3m"], tend["previos_3m"], tend["diferencia"]) == (1110.0, 1760.0, -650.0)
    assert tend["pct"] == pytest.approx(1110 / 1760 - 1)
    f = ana["facturas"]
    # (A1, S1), A2, A3 y (A1, S2): 4 facturas; solo la primera tiene 2 lineas.
    assert f["facturas"] == 4 and f["ticket_promedio"] == 717.5
    assert f["unidades"] == 8.0 and f["items_por_factura"] == 1.25
    assert f["pct_con_linea"]["REPUESTOS"] == 0.75
    assert f["pct_con_linea"]["ACCESORIOS"] == 0.25 and f["pct_con_linea"]["LLANTAS"] == 0.25
    assert f["pct_con_linea"]["GPS"] == 0.0 and f["pct_multilinea"] == 0.25
    assert f["facturas_con_linea"]["REPUESTOS"] == 3 and f["facturas_con_linea"]["GPS"] == 0
    assert f["ticket_por_linea"]["GPS"] is None
    assert f["ticket_por_linea"]["REPUESTOS"] == pytest.approx(1560 / 3)
    assert f["ticket_por_linea"]["ACCESORIOS"] == 500.0 and f["ticket_por_linea"]["LLANTAS"] == 810.0
    d = ana["descuentos"]
    assert d["total"] == 230.0 and d["mes_mayor"] == "2098-01"
    assert d["pct_en_mes_mayor"] == pytest.approx(100 / 230)
    assert d["pct_descuento"] == pytest.approx(230 / 3100)
    cl = ana["clientes"]
    assert cl["pct_mostrador"] == pytest.approx(2510 / 2870)  # " mostrador " tambien cuenta
    assert cl["venta_tecnired"] == 810.0 and cl["pct_tecnired"] == pytest.approx(810 / 2870)
    assert cl["clientes_unicos"] == 3 and cl["pct_top5"] == 1.0


async def test_grupos_consolidados_y_resto(sesion):
    await _mundo(sesion)

    tablero = await _tablero(sesion)

    comerciales = _fila(tablero, clave=t.GRUPO_COMERCIALES)
    assert comerciales["nombre"] == "ASESORES COMERCIALES DE SERVICIO POSVENTA (2 personas)"
    assert comerciales["venta"]["total"] == 1100.0
    assert comerciales["facturas"]["facturas"] == 2 and comerciales["clientes"]["clientes_unicos"] == 1
    assert comerciales["costo"]["costo_venta"] == 400.0  # 1*200 + 4*50
    otros = _fila(tablero, clave=t.GRUPO_OTROS)
    assert otros["nombre"] == "OTROS ROLES POSVENTA (1 persona)"
    assert otros["venta"]["total"] == 540.0
    # BATERIAS (con tilde en la referencia) cuenta; su unico costo es de una carga ANULADA.
    assert otros["venta"]["por_linea"]["BATERIAS"] == 540.0
    assert otros["costo"]["venta_con_costo"] == 0.0 and otros["costo"]["pct_margen"] is None
    resto = _fila(tablero, clave=t.GRUPO_RESTO)
    assert resto["nombre"] == "RESTO COMPAÑÍA (2 vendedores)"  # Dora (inactiva) y Eva (no esta)
    assert resto["venta"]["total"] == 1150.0 and resto["venta"]["hmcl"] == 900.0  # "900883086.0"
    assert [f["tipo"] for f in tablero["filas"]] == ["PERSONA", "PERSONA", "GRUPO", "GRUPO", "GRUPO"]


async def test_ranking_entre_personas_e_indice_contra_el_promedio(sesion):
    await _mundo(sesion)

    tablero = await _tablero(sesion)

    ana, luis = _fila(tablero, "Ana")["ranking"], _fila(tablero, "Luis")["ranking"]
    assert ana["indice_vs_promedio"] == pytest.approx(2870 / 1585)
    assert luis["indice_vs_promedio"] == pytest.approx(300 / 1585)
    assert (ana["rank_total"], luis["rank_total"]) == (1, 2)
    assert (ana["rank_repuestos"], luis["rank_repuestos"]) == (1, 2)
    assert (ana["rank_accesorios"], luis["rank_accesorios"]) == (1, 2)
    assert (ana["rank_lubricantes"], luis["rank_lubricantes"]) == (1, 1)
    assert _fila(tablero, clave=t.GRUPO_RESTO)["ranking"] is None


async def test_total_y_venta_sin_linea_reconocida(sesion):
    await _mundo(sesion)

    tablero = await _tablero(sesion)

    total = tablero["total"]
    assert total["venta"]["total"] == 5960.0 and total["venta"]["hmcl"] == 1260.0
    assert total["facturas"]["facturas"] == 11
    assert total["clientes"]["clientes_unicos"] == 6
    # Mayores clientes: 1950, 1400, 900, 810, 540 (el sexto, 360, queda fuera).
    assert total["clientes"]["pct_top5"] == pytest.approx(5600 / 5960)
    assert total["costo"]["costo_venta"] == 1750.0 and total["costo"]["venta_con_costo"] == 4610.0
    # E1 (5000, linea NULL) + A4 (1000 - 200, NO APLICA); la carga ANULADA no cuenta.
    assert tablero["venta_sin_linea"] == 5800.0
    assert tablero["pct_venta_sin_linea"] == pytest.approx(5800 / 11760)


async def test_metadatos_meses_y_fecha_de_costos(sesion):
    await _mundo(sesion)

    tablero = await _tablero(sesion)

    assert tablero["meses"] == ["2098-01", "2098-02", "2098-03", "2098-04", "2098-05", "2098-06"]
    assert {"2098-01", "2098-07"} <= set(tablero["meses_disponibles"])
    # El corte mas nuevo (2099-12-30) es de una carga ANULADA: se usa el 28.
    assert tablero["fecha_corte_costos"] == "2099-12-28"


async def test_filtro_hmcl_solo_y_excluir(sesion):
    await _mundo(sesion)

    solo = await _tablero(sesion, "solo")
    excluir = await _tablero(sesion, "excluir")

    assert solo["total"]["venta"]["total"] == 1260.0
    assert _fila(solo, "Ana")["venta"]["total"] == 360.0
    assert _fila(solo, clave=t.GRUPO_RESTO)["venta"]["total"] == 900.0
    assert solo["total"]["facturas"]["facturas"] == 2
    assert excluir["total"]["venta"]["total"] == 4700.0 and excluir["total"]["venta"]["hmcl"] == 0.0
    assert _fila(excluir, "Ana")["venta"]["total"] == 2510.0


async def test_un_rango_corto_no_tiene_tendencia_y_filtra_por_mes(sesion):
    await _mundo(sesion)

    tablero = await _tablero(sesion, desde="2098-02", hasta="2098-02")

    ana = _fila(tablero, "Ana")
    assert ana["venta"]["total"] == 360.0 and ana["tendencia"]["pct"] is None


async def test_un_rango_sin_ventas_devuelve_un_tablero_vacio(sesion):
    tablero = await _tablero(sesion, desde="2097-01", hasta="2097-02")

    assert tablero["filas"] == [] and tablero["total"]["venta"]["total"] == 0.0
    assert tablero["total"]["facturas"]["facturas"] == 0 and tablero["total"]["clientes"]["pct_top5"] is None
    assert tablero["pct_venta_sin_linea"] is None


async def test_el_sql_normaliza_el_nit_igual_que_python(sesion):
    from sqlalchemy import literal, select
    crudos = ["900123456", " 900123456. ", "900 123 456", "900123456.0", "123.0.", "123.", " 1 23.0 ",
              "900.123.456-7", "1.0.0", "12.00.", "Taller El Rayo"]
    for crudo in crudos:
        original = q.VentaDetalle.cliente_factura
        try:
            q.VentaDetalle.cliente_factura = literal(crudo)
            en_sql = (await sesion.execute(select(q._expr_cliente_norm()))).scalar()
        finally:
            q.VentaDetalle.cliente_factura = original
        assert en_sql == normalizar_nit(crudo), crudo


async def test_un_cliente_nulo_cuenta_como_no_hmcl(sesion):
    """`cliente_factura` es NOT NULL hoy; la regla es defensiva. Un NULL en el
    NOT IN daria NULL y la linea saldria de `hmcl=excluir` (y de `solo`)."""
    from sqlalchemy import null, select, cast as sa_cast, String

    nulo = sa_cast(null(), String)
    es_hmcl = (await sesion.execute(select(q._expr_es_hmcl(nulo, t.REGLAS_POR_DEFECTO)))).scalar_one()
    no_es_hmcl = (await sesion.execute(select(~q._expr_es_hmcl(nulo, t.REGLAS_POR_DEFECTO)))).scalar_one()

    assert es_hmcl is False
    assert no_es_hmcl is True
