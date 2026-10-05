"""
KPI tabs on a large synthetic dataset: live queries vs precomputed summaries (R8).

Opt-in on top of `pg_real`: it only runs with `MOTORED_KPI_PERF=1` (it seeds ~1M `venta_detalle`
rows with set-based `generate_series` inserts, so it takes minutes). The size is tunable with
`MOTORED_KPI_PERF_LINEAS` (lines per store per month, default 2800: 40 stores x 9 months ~ 1M rows).
Everything happens inside one transaction that is rolled back, so run it against a throwaway
database. It prints the timings ("año corrido", best of two runs per tab) and asserts the summary
answers no slower than the live queries, with identical results.
"""
import datetime
import os
import time
import uuid
from decimal import Decimal as D

import pytest
from sqlalchemy import text

from app.config import settings
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.services import kpi_resumen as k
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as kpis
from tests.motored.pg_real.test_kpi_resumen_pg import URL, sesion  # noqa: F401

pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
    pytest.mark.skipif(os.environ.get("MOTORED_KPI_PERF") != "1", reason="MOTORED_KPI_PERF=1 no definida"),
]

TIENDAS = 40
MESES = [f"2097-{m:02d}" for m in range(1, 10)]
LINEAS_POR_TIENDA_MES = int(os.environ.get("MOTORED_KPI_PERF_LINEAS", "2800"))
REFERENCIAS = 300
CORTE = datetime.date(2097, 9, 28)

_VENTAS = text("""
INSERT INTO venta_detalle (id, carga_id, fecha, anio, mes, sucursal_id, referencia_id, origen, cantidad,
                           vendedor, vendedor_norm, valor_bruto, valor_descuentos, cliente_factura,
                           nro_documento, created_at)
SELECT gen_random_uuid(), :carga, make_date(2097, m, 1 + (g % 27)), 2097, m, s.id, r.id,
       CASE WHEN g % 3 = 0 THEN 'MOSTRADOR' ELSE 'VENTA' END, 1 + (g % 5),
       'V' || s.rn || '-' || (g % 6), 'V' || s.rn || '-' || (g % 6),
       (1000 + (g * 37) % 90000)::numeric, (((g % 10) * (1000 + (g * 37) % 90000)) / 100)::numeric(16, 2),
       CASE WHEN g % 50 = 0 THEN '900723988' WHEN g % 70 = 0 THEN :tec
            ELSE '9' || lpad(((g * 31 + s.rn) % 4000)::text, 8, '0') END,
       (s.rn * 1000000 + m * 100000 + g / 4)::text, now()
FROM generate_series(1, 9) AS m
CROSS JOIN (SELECT id, row_number() OVER (ORDER BY nombre) AS rn FROM sucursal WHERE nombre LIKE :prefijo) AS s
CROSS JOIN generate_series(1, :n) AS g
JOIN (SELECT id, row_number() OVER (ORDER BY codigo) AS rn FROM referencia WHERE codigo LIKE :prefijo) AS r
  ON r.rn = 1 + (g * 7 + s.rn) % :refs
""")
_INVENTARIO = text("""
INSERT INTO inventario_detalle (id, carga_id, fecha_corte, sucursal_id, referencia_id, bodega, existencia,
                                costo_unitario)
SELECT gen_random_uuid(), :carga, :corte, s.id, r.id, 'B1', 1 + (r.rn % 9),
       CASE WHEN r.rn % 7 = 0 THEN NULL ELSE (500 + r.rn * 13)::numeric END
FROM (SELECT id FROM sucursal WHERE nombre LIKE :prefijo) AS s
CROSS JOIN (SELECT id, row_number() OVER (ORDER BY codigo) AS rn FROM referencia WHERE codigo LIKE :prefijo) AS r
""")


async def _sembrar(db):
    sfx = uuid.uuid4().hex[:8].upper()
    prefijo = f"PERF{sfx}%"
    proveedor = Proveedor(id=uuid.uuid4(), codigo=f"PERF{sfx}-P", nombre="P", es_principal=True,
                          dias_empaque_default=4, dias_transito_default=5, dias_seguridad_default=D("3"))
    db.add(proveedor)
    cargas = {tipo: CargaArchivo(id=uuid.uuid4(), tipo=tipo, origen="EXCEL", estado="APLICADO",
                                 nombre_archivo="x.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)
              for tipo in ("VENTAS", "INVENTARIO")}
    db.add_all(cargas.values())
    sucursales = [Sucursal(id=uuid.uuid4(), nombre=f"PERF{sfx} {n:02d}", sic=f"P{sfx}{n}") for n in range(TIENDAS)]
    db.add_all(sucursales)
    lineas = list(t.LINEAS) + ["NO APLICA", None]
    db.add_all([
        Referencia(id=uuid.uuid4(), codigo=f"PERF{sfx}-{n:04d}", proveedor_id=proveedor.id, unidad_empaque=1,
                   precio_normal=D(800 + n) if n % 5 == 0 else None, linea_comercial=lineas[n % len(lineas)])
        for n in range(REFERENCIAS)])
    cargo = "ASESOR DE REPUESTOS"
    db.add_all([
        Vendedor(id=uuid.uuid4(), nombre=f"V{n + 1}-{i}", nombre_norm=f"V{n + 1}-{i}", cargo=cargo,
                 cedula=str(uuid.uuid4().int)[:10], sucursal_id=s.id, activo=True)
        for n, s in enumerate(sorted(sucursales, key=lambda s: s.nombre)) for i in range(6)])
    await db.flush()
    params = dict(prefijo=prefijo, refs=REFERENCIAS)
    inicio = time.perf_counter()
    await db.execute(_VENTAS, dict(params, carga=cargas["VENTAS"].id, n=LINEAS_POR_TIENDA_MES, tec="7" + sfx))
    await db.execute(_INVENTARIO, dict(params, carga=cargas["INVENTARIO"].id, corte=CORTE))
    for tabla in ("venta_detalle", "inventario_detalle", "referencia", "sucursal"):
        await db.execute(text(f"ANALYZE {tabla}"))
    return time.perf_counter() - inicio


async def _medir(llamar):
    """Best of two runs (the first one warms the caches), in seconds, and the answer."""
    mejor, respuesta = None, None
    for _ in range(2):
        inicio = time.perf_counter()
        respuesta = await llamar()
        duracion = time.perf_counter() - inicio
        mejor = duracion if mejor is None else min(mejor, duracion)
    return mejor, respuesta


def _sin_frescura(respuesta):
    return {c: v for c, v in respuesta.items() if c not in ("usando_resumen", "datos_actualizados_en")}


async def test_the_summaries_answer_the_tabs_faster_than_the_live_queries(sesion, monkeypatch):
    segundos_siembra = await _sembrar(sesion)
    filas = (await sesion.execute(text("SELECT count(*) FROM venta_detalle"))).scalar_one()
    filtro = await q.cargar_filtro(sesion, MESES, t.HMCL_INCLUIR, None)
    tabs = {"ventas": kpis.calcular_kpis_ventas, "tiendas": kpis.calcular_kpis_tiendas,
            "asesores": kpis.calcular_kpis_asesores}

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    vivo = {nombre: await _medir(lambda f=f: f(sesion, filtro)) for nombre, f in tabs.items()}

    inicio = time.perf_counter()
    await k.reconstruir_todo(sesion)
    segundos_reconstruccion = time.perf_counter() - inicio
    for tabla in ("kpi_venta_mes", "kpi_factura_firma", "kpi_cliente_mes", "kpi_costo_referencia",
                  "kpi_inventario_corte"):
        await sesion.execute(text(f"ANALYZE {tabla}"))
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.usar_resumen(sesion)
    resumen = {nombre: await _medir(lambda f=f: f(sesion, filtro)) for nombre, f in tabs.items()}

    lineas = [f"KPI PERF: {filas} venta_detalle rows, {TIENDAS} stores, {len(MESES)} months "
              f"(seed {segundos_siembra:.1f} s, full summary rebuild {segundos_reconstruccion:.1f} s)"]
    for nombre in tabs:
        lineas.append(f"KPI PERF {nombre}: live {vivo[nombre][0]:.2f} s -> summary {resumen[nombre][0]:.2f} s "
                      f"(x{vivo[nombre][0] / max(resumen[nombre][0], 1e-9):.1f})")
    print("\n" + "\n".join(lineas))

    for nombre in tabs:
        assert _sin_frescura(resumen[nombre][1]) == _sin_frescura(vivo[nombre][1]), nombre
        assert resumen[nombre][0] <= vivo[nombre][0], (nombre, lineas)
