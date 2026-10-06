"""
Tablero de asesores: una persona con varios nombres del ERP (misma cedula) contra
un Postgres real (opt-in, `MOTORED_TEST_PG_URL`).

El maestro guarda una fila por nombre del ERP, pero la persona es una sola: el
tablero agrupa por cedula. Cada indicador se calcula sobre la UNION de las lineas
de la persona (nunca sumando razones por nombre). Las fechas son del anio 2097.

Mundo (todo calculado a mano):
- DIANA, cedula C1, dos nombres: "MORA DIANA ..." (REPUESTOS, sucursal A) con 1.400 de
  venta y "MORA BUSTOS DIANA ..." (SUPERNUMERARIO, sucursal B) con 2.800, mas una
  linea NO APLICA de 5.000 en el primer nombre (no cuenta y no debe decidir el nombre).
  Comparten la factura D1 de la sucursal A.
- PEDRO: sin cedula (legado), una sola fila.
- Comerciales: BETO y BETO ALIAS (misma cedula, misma factura B1), FABIO y GINA
  (GINA sin cedula) = 3 personas con 4 nombres.
- Otros roles: CARLA y CARLA ALIAS (misma cedula) = 1 persona.
- Resto: EVA, que no esta en el maestro.
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services.ingesta.ventas import normalizar_vendedor

from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

D = Decimal
REPUESTOS_CARGO = "ASESOR DE REPUESTOS"
SUPER_CARGO = "ASESOR DE REPUESTOS SUPERNUMERARIO"
COMERCIAL = "ASESOR COMERCIAL DE SERVICIO POSVENTA"


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


async def _mundo(db):
    sfx = uuid.uuid4().hex[:8].upper()
    ced = {k: str(uuid.uuid4().int)[:10] for k in ("diana", "beto", "carla", "fabio")}
    prov = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
        dias_empaque_default=4, dias_transito_default=5, dias_seguridad_default=D("3"))
    suc_a = Sucursal(
        id=uuid.uuid4(), nombre=f"Cali Norte {sfx}", sic=f"S1-{sfx}",
        codigo_co=codigo_co_unico())
    suc_b = Sucursal(
        id=uuid.uuid4(), nombre=f"Bogota {sfx}", sic=f"S2-{sfx}",
        codigo_co=codigo_co_unico())
    db.add_all([prov, suc_a, suc_b])
    await db.flush()
    lineas = {"R1": "REPUESTOS", "R2": "ACCESORIOS", "R4": "NO APLICA"}
    refs = {
        k: Referencia(
            id=uuid.uuid4(), codigo=f"{k}-{sfx}", proveedor_id=prov.id, unidad_empaque=1,
            precio_normal=None, linea_comercial=v)
        for k, v in lineas.items()
    }
    carga = CargaArchivo(
        id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado="APLICADO",
        nombre_archivo="x.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)
    db.add_all([*refs.values(), carga])
    await db.flush()

    def vend(nombre, cargo, cedula, suc):
        return Vendedor(
            id=uuid.uuid4(), nombre=f"{nombre} {sfx}", nombre_norm=normalizar_vendedor(f"{nombre} {sfx}"),
            cargo=cargo, cedula=cedula, sucursal_id=suc.id if suc else None, activo=True)

    db.add_all([
        vend("MORA DIANA PATRICIA", REPUESTOS_CARGO, ced["diana"], suc_a),
        vend("MORA BUSTOS DIANA PATRICIA", SUPER_CARGO, ced["diana"], suc_b),
        vend("PEDRO", REPUESTOS_CARGO, None, suc_a),
        vend("BETO", COMERCIAL, ced["beto"], None),
        vend("BETO ALIAS", COMERCIAL, ced["beto"], None),
        vend("FABIO", COMERCIAL, ced["fabio"], None),
        vend("GINA", COMERCIAL, None, None),
        vend("CARLA", "JEFE DE TALLER", ced["carla"], None),
        vend("CARLA ALIAS", "JEFE DE TALLER", ced["carla"], None),
    ])

    def linea(vend_nombre, nro, ref, mes, cant, bruto, desc, cliente, suc=suc_a, origen="VENTA"):
        nombre = f"{vend_nombre} {sfx}"
        db.add(VentaDetalle(
            id=uuid.uuid4(), carga_id=carga.id, fecha=datetime.date(2097, mes, 5), anio=2097, mes=mes,
            sucursal_id=suc.id, referencia_id=refs[ref].id, origen=origen, cantidad=D(cant),
            vendedor=nombre, vendedor_norm=normalizar_vendedor(nombre), valor_bruto=D(bruto),
            valor_descuentos=D(desc), cliente_factura=cliente, nro_documento=f"{nro}-{sfx}"))

    # Diana, primer nombre: 900 + 500 = 1.400 (la linea NO APLICA no cuenta).
    linea("MORA DIANA PATRICIA", "D1", "R1", 1, 2, 1000, 100, "Taller X")
    linea("MORA DIANA PATRICIA", "D1", "R2", 1, 1, 500, 0, "Taller X")
    linea("MORA DIANA PATRICIA", "D4", "R4", 1, 1, 5000, 0, "Taller X")
    # Diana, segundo nombre: 300 (misma factura D1) + 1.800 + 700 = 2.800.
    linea("MORA BUSTOS DIANA PATRICIA", "D1", "R1", 1, 1, 300, 0, "Taller X", origen="MOSTRADOR")
    linea("MORA BUSTOS DIANA PATRICIA", "D2", "R1", 5, 3, 2000, 200, "Cliente Y", suc=suc_b)
    linea("MORA BUSTOS DIANA PATRICIA", "D3", "R2", 6, 1, 700, 0, "900883086", suc=suc_b)
    linea("PEDRO", "P1", "R1", 2, 1, 1000, 0, "Cliente Q")
    linea("BETO", "B1", "R1", 3, 1, 400, 0, "Cliente Q")
    linea("BETO ALIAS", "B1", "R2", 3, 2, 600, 0, "Cliente Q")
    linea("FABIO", "F1", "R1", 4, 1, 200, 0, "Cliente Q")
    linea("GINA", "G1", "R2", 4, 1, 100, 0, "Cliente Q")
    linea("CARLA", "C1", "R1", 2, 1, 500, 0, "Cliente Q", suc=suc_b)
    linea("CARLA ALIAS", "C2", "R2", 2, 1, 250, 0, "Cliente Q", suc=suc_b)
    linea("EVA", "E1", "R1", 1, 1, 100, 0, "Cliente Q")
    await db.flush()
    return sfx, suc_b


def _fila(tablero, nombre_empieza=None, clave=None):
    for f in tablero["filas"]:
        if (clave and f["clave"] == clave) or (nombre_empieza and f["nombre"].startswith(nombre_empieza)):
            return f
    raise AssertionError(f"fila no encontrada: {nombre_empieza or clave}")


async def _tablero(db):
    return await q.calcular_tablero(db, "2097-01", "2097-06", "incluir")


async def test_dos_nombres_del_erp_con_la_misma_cedula_son_una_sola_fila(sesion):
    sfx, suc_b = await _mundo(sesion)

    tablero = await _tablero(sesion)

    personas = [f for f in tablero["filas"] if f["tipo"] == "PERSONA"]
    assert len(personas) == 2  # Diana (2 nombres) y Pedro
    diana = _fila(tablero, "MORA BUSTOS")
    assert diana["clave"].startswith("P:") and diana["personas"] == 1
    # Nombre, cargo y sucursal de la fila con mas ventas (2.800 contra 1.400).
    assert diana["nombre"] == f"MORA BUSTOS DIANA PATRICIA {sfx}"
    assert (diana["cargo"], diana["punto_venta"]) == (SUPER_CARGO, suc_b.nombre)
    assert diana["cargos"] == [REPUESTOS_CARGO, SUPER_CARGO] and diana["cargo_conflicto"] is True


async def test_los_indicadores_son_sobre_la_union_de_las_lineas_de_la_persona(sesion):
    await _mundo(sesion)

    diana = _fila(await _tablero(sesion), "MORA BUSTOS")

    v = diana["venta"]
    assert v["total"] == 4200.0  # 900 + 500 + 300 + 1800 + 700
    assert (v["hmcl"], v["sin_hmcl"]) == (700.0, 3500.0)
    assert v["pct_hmcl"] == pytest.approx(700 / 4200)
    assert v["por_mes"] == {
        "2097-01": 1700.0, "2097-02": 0.0, "2097-03": 0.0, "2097-04": 0.0, "2097-05": 1800.0, "2097-06": 700.0}
    assert v["por_linea"]["REPUESTOS"] == 3000.0 and v["por_linea"]["ACCESORIOS"] == 1200.0
    assert v["mix"]["REPUESTOS"] == pytest.approx(3000 / 4200)
    assert v["mix"]["ACCESORIOS"] == pytest.approx(1200 / 4200)
    tend = diana["tendencia"]
    assert (tend["ultimos_3m"], tend["previos_3m"], tend["diferencia"]) == (2500.0, 1700.0, 800.0)
    assert tend["pct"] == pytest.approx(2500 / 1700 - 1)
    c = diana["costo"]  # sin inventario: ninguna linea tiene costo
    assert (c["costo_venta"], c["venta_con_costo"], c["pct_margen"]) == (0.0, 0.0, None)
    f = diana["facturas"]
    # (D1, A) la comparten los dos nombres y cuenta UNA vez; mas (D2, B) y (D3, B).
    assert f["facturas"] == 3 and f["ticket_promedio"] == 1400.0
    assert f["unidades"] == 8.0 and f["items_por_factura"] == pytest.approx(5 / 3)
    assert f["pct_con_linea"]["REPUESTOS"] == pytest.approx(2 / 3)
    assert f["pct_con_linea"]["ACCESORIOS"] == pytest.approx(2 / 3)
    assert f["pct_multilinea"] == pytest.approx(1 / 3)
    d = diana["descuentos"]
    assert d["total"] == 300.0 and d["mes_mayor"] == "2097-05"
    assert d["pct_en_mes_mayor"] == pytest.approx(200 / 300)
    assert d["pct_descuento"] == pytest.approx(300 / 4500)
    cl = diana["clientes"]
    # Taller X (la comparten los dos nombres) cuenta una vez: 3 clientes, no 4.
    assert cl["clientes_unicos"] == 3 and cl["pct_top5"] == 1.0
    assert cl["pct_mostrador"] == pytest.approx(300 / 4200)


async def test_los_grupos_cuentan_personas_distintas_por_cedula(sesion):
    await _mundo(sesion)

    tablero = await _tablero(sesion)

    comerciales = _fila(tablero, clave=t.GRUPO_COMERCIALES)
    # BETO + BETO ALIAS (misma cedula), FABIO y GINA (sin cedula): 3 personas, 4 nombres.
    assert comerciales["nombre"] == "ASESORES COMERCIALES DE SERVICIO POSVENTA (3 personas)"
    assert comerciales["personas"] == 3 and comerciales["venta"]["total"] == 1300.0
    assert comerciales["facturas"]["facturas"] == 3  # B1 (de los dos nombres), F1 y G1
    otros = _fila(tablero, clave=t.GRUPO_OTROS)
    assert otros["nombre"] == "OTROS ROLES POSVENTA (1 persona)"
    assert otros["venta"]["total"] == 750.0
    resto = _fila(tablero, clave=t.GRUPO_RESTO)
    assert resto["nombre"] == "RESTO COMPAÑÍA (1 vendedor)"
    assert tablero["total"]["personas"] == 2 + 3 + 1 + 1
    assert tablero["total"]["venta"]["total"] == 7350.0


async def test_el_ranking_y_el_promedio_corren_sobre_personas(sesion):
    await _mundo(sesion)

    tablero = await _tablero(sesion)

    diana, pedro = _fila(tablero, "MORA BUSTOS")["ranking"], _fila(tablero, "PEDRO")["ranking"]
    # Dos personas (no tres nombres): promedio (4200 + 1000) / 2.
    assert diana["indice_vs_promedio"] == pytest.approx(4200 / 2600)
    assert pedro["indice_vs_promedio"] == pytest.approx(1000 / 2600)
    assert (diana["rank_total"], pedro["rank_total"]) == (1, 2)
    assert (diana["rank_repuestos"], pedro["rank_repuestos"]) == (1, 2)
    assert (diana["rank_accesorios"], pedro["rank_accesorios"]) == (1, 2)
    assert (diana["rank_lubricantes"], pedro["rank_lubricantes"]) == (1, 1)


async def test_una_fila_sin_cedula_sigue_agrupada_por_nombre(sesion):
    sfx, _ = await _mundo(sesion)

    pedro = _fila(await _tablero(sesion), "PEDRO")

    assert pedro["nombre"] == f"PEDRO {sfx}" and pedro["cargo"] == REPUESTOS_CARGO
    assert pedro["cargos"] == [REPUESTOS_CARGO] and pedro["cargo_conflicto"] is False
    assert pedro["venta"]["total"] == 1000.0 and pedro["facturas"]["facturas"] == 1
