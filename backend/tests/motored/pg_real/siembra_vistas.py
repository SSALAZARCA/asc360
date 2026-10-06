"""
Siembra compartida de los tests `pg_real` de las vistas de la red (Fase 4,
sdd/motored-pedidos-ui, B6): `test_consolidado_pg.py` y
`test_comparacion_pg.py`.

Dos tamaños de datos:

- A mano (`linea`): unas pocas líneas con cantidades y valores escogidos
  para que cada regla tenga una respuesta que se pueda verificar a ojo.
- En bloque (`lineas_en_bloque`): un `INSERT ... SELECT` que cruza tiendas y
  referencias en el servidor, para el volumen real (47 tiendas por 3.000
  referencias son 141.000 líneas por corrida). Las cantidades son una
  función determinista del código y la tienda (0 a 7), así que el esperado
  se calcula con SQL propio sin repetir la consulta que se prueba.

Todo se crea dentro de la transacción que revierte la fixture `fabrica`: la
base queda limpia.
"""
import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import insert, text

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario

from tests.motored.pg_real.codigos_co import codigo_co_unico

CORTE = datetime.date(2026, 9, 21)
D = Decimal
CEROS = D("0.00")

_LINEAS_EN_BLOQUE = text("""
INSERT INTO corrida_linea (
    corrida_id, sucursal_id, referencia_id, codigo_referencia, nombre_parte,
    unidad_empaque, venta_m6, venta_m5, venta_m4, venta_m3, venta_m2,
    venta_m1, perdida_m6, perdida_m5, perdida_m4, perdida_m3, perdida_m2,
    perdida_m1, inventario, transito, backorder, ajuste, precio,
    pedido_sugerido, pedido_final, valor_pedido, clase_abc, clase)
SELECT CAST(:corrida AS uuid), s.id, r.id, r.codigo, 'PARTE ' || r.codigo, 10,
       0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 100.00,
       q.cantidad + q.mas + CAST(:aparte AS integer), q.cantidad + q.mas,
       (q.cantidad + q.mas) * 100.00, 'A', 'AF'
FROM sucursal s
CROSS JOIN referencia r
CROSS JOIN LATERAL (
    SELECT (hashtext(r.codigo || s.nombre)::bigint & 2147483647) % 8
               AS cantidad,
           CASE WHEN (hashtext(s.nombre || r.codigo)::bigint & 2147483647)
                     % 5 = 0 THEN CAST(:plus AS integer) ELSE 0 END AS mas) q
WHERE s.nombre LIKE '%-' || CAST(:sufijo AS text)
  AND r.codigo LIKE '%-' || CAST(:sufijo AS text)
""")


def sufijo_nuevo() -> str:
    return uuid.uuid4().hex[:6]


async def base(db, sufijo: str):
    """Un proveedor y un usuario COMPRAS."""
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"VIS-{sufijo}", nombre="vistas",
        es_principal=False, dias_empaque_default=1, dias_transito_default=1,
        dias_seguridad_default=D("1"))
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Compras", role=MotoredRole.COMPRAS,
        email=f"v-{sufijo}@x.co", hashed_password="x")
    db.add_all([proveedor, usuario])
    await db.flush()
    return SimpleNamespace(proveedor=proveedor, usuario=usuario)


async def tiendas(db, sufijo: str, cantidad: int, desde: int = 0) -> list:
    """`cantidad` tiendas `T00-<sufijo>`... (el orden por nombre es el
    orden de creación)."""
    filas = [
        Sucursal(id=uuid.uuid4(), nombre=f"T{i:02d}-{sufijo}",
                 sic=f"S{i:02d}-{sufijo}", codigo_co=codigo_co_unico(),
                 dias_empaque=1, dias_transito=1)
        for i in range(desde, desde + cantidad)]
    db.add_all(filas)
    await db.flush()
    return filas


async def referencias(db, proveedor, sufijo: str, cantidad: int) -> list:
    """`cantidad` referencias `R0000-<sufijo>`... como `(id, codigo)`."""
    filas = [
        {"id": uuid.uuid4(), "codigo": f"R{i:04d}-{sufijo}",
         "proveedor_id": proveedor.id, "unidad_empaque": 10,
         "precio_normal": D("100.00"), "nombre": f"Parte {i}",
         "unidad_empaque_advertencia": False, "activa": True,
         "homologados": []}
        for i in range(cantidad)]
    await db.execute(insert(Referencia.__table__), filas)
    return [(f["id"], f["codigo"]) for f in filas]


async def corrida(
    db, datos, sufijo: str, orden: int, *, estado="BORRADOR",
    escenario=False, corte=CORTE, proveedor=None,
):
    fila = Corrida(
        id=uuid.uuid4(),
        codigo=f"{'ESC' if escenario else 'PED'}-{sufijo}-{orden:02d}",
        proveedor_id=(proveedor or datos.proveedor).id, fecha_corte=corte,
        estado=estado, es_escenario=escenario)
    db.add(fila)
    await db.flush()
    return fila


async def estados_de_tiendas(db, corrida_fila, estados) -> None:
    """`corrida_sucursal` por `(tienda, estado de cálculo, estado del
    pedido)`; las fallidas y las omitidas llevan código y mensaje."""
    db.add_all([
        CorridaSucursal(
            corrida_id=corrida_fila.id, sucursal_id=tienda.id, orden=i,
            estado=estado, estado_pedido=pedido,
            codigo=None if estado == "OK" else "E-CORRIDA-020",
            mensaje=None if estado == "OK" else "sin empaque")
        for i, (tienda, estado, pedido) in enumerate(estados, start=1)])
    await db.flush()


def linea(
    corrida_fila, tienda, codigo: str, referencia_id, final, *,
    sugerido=None, precio="100.00", exclusion=None, nombre=None,
    clase="AF",
):
    """Una línea a mano. `sugerido` es lo del motor (por defecto igual a
    `final`); `exclusion` la marca excluida."""
    final = D(str(final))
    sugerido = final if sugerido is None else D(str(sugerido))
    precio_d = None if precio is None else D(precio)
    return CorridaLinea(
        corrida_id=corrida_fila.id, sucursal_id=tienda.id,
        referencia_id=referencia_id, codigo_referencia=codigo,
        nombre_parte=nombre, unidad_empaque=10, banderas=[],
        **{f"venta_m{m}": CEROS for m in range(1, 7)},
        **{f"perdida_m{m}": CEROS for m in range(1, 7)},
        inventario=CEROS, transito=CEROS, backorder=CEROS, ajuste=CEROS,
        pedido_sugerido=sugerido, pedido_final=final, precio=precio_d,
        valor_pedido=CEROS if precio_d is None else final * precio_d,
        clase=clase, clase_abc=clase[0], estado_quiebre="NORMAL",
        motivo_exclusion=exclusion)


async def referencia_a_mano(db, datos, codigo: str, nombre=None):
    fila = Referencia(
        id=uuid.uuid4(), codigo=codigo, proveedor_id=datos.proveedor.id,
        unidad_empaque=10, precio_normal=D("100.00"), nombre=nombre)
    db.add(fila)
    await db.flush()
    return fila


async def lineas_en_bloque(
    db, corrida_fila, sufijo: str, *, plus: int = 0, aparte: int = 0,
) -> None:
    """Cruza las tiendas y las referencias del sufijo en el servidor:
    `pedido_final` = 0 a 7 (+ `plus` en una de cada cinco líneas) y
    `pedido_sugerido` = `pedido_final` + `aparte`."""
    await db.execute(_LINEAS_EN_BLOQUE, {
        "corrida": corrida_fila.id, "sufijo": sufijo, "plus": plus,
        "aparte": aparte})
    # Con estadísticas frescas, como en producción tras el autovacuum: sin
    # ellas el planner no ve cuántas líneas hay y elige planes que no son
    # los reales.
    await db.execute(text("ANALYZE corrida_linea"))
