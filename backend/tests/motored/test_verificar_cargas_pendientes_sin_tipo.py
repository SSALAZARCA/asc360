"""
Motored Pedidos — Fase 3 "Cargas: Tipo Declarado", Phase 1 "Pre-Deploy Data
Check" (sdd/motored-cargas-tipo-declarado; design D2, task 1.1/1.2).

`scripts/verificar_cargas_pendientes_sin_tipo.py` no se puede probar contra
producción desde este entorno (no hay conexión viva a la base real) --
estos tests prueban su LÓGICA de query/reporte contra el mismo
`FakeAsyncSession` que el resto de la suite Motored usa, en vez de contra
datos reales: prueban que identifica correctamente los DOS casos de fila
huérfana --

  A. `estado='PENDIENTE' AND tipo IS NULL` (nunca se detectó el tipo).
  B. `estado='PENDIENTE' AND tipo IS NOT NULL AND periodo_desde IS NULL`,
     para un tipo que declara período (el tipo sí se detectó, pero el
     Paso 2 viejo -- completar período -- nunca se terminó).

-- y que deja en paz cualquier otra combinación de estado/tipo/período.
"""
import uuid
from datetime import datetime

from app.motored.models.carga_archivo import CargaArchivo
from scripts.verificar_cargas_pendientes_sin_tipo import (
    UPDATE_SQL,
    UPDATE_SQL_SIN_PERIODO,
    buscar_cargas_pendientes_sin_periodo,
    buscar_cargas_pendientes_sin_tipo,
    formatear_reporte,
)
from tests.motored.conftest import FakeAsyncSession


def _carga(estado: str, tipo, periodo_desde=None, nombre_archivo="archivo.xlsx") -> CargaArchivo:
    return CargaArchivo(
        id=uuid.uuid4(),
        tipo=tipo,
        nombre_archivo=nombre_archivo,
        hash_sha256="a" * 64,
        ruta_objeto=f"{tipo or 'SIN_TIPO'}/2026/09/x.xlsx",
        bytes=100,
        estado=estado,
        filas_leidas=0,
        filas_validas=0,
        filas_rechazadas=0,
        periodo_desde=periodo_desde,
        periodo_hasta=None,
        lotes_staged=0,
        ultimo_lote_aplicado=0,
        latido_en=None,
        log=None,
        subido_por=uuid.uuid4(),
        aplicado_en=None,
        created_at=datetime(2026, 8, 1, 12, 0, 0),
    )


# ---------------------------------------------------------------------------
# Caso A -- tipo IS NULL
# ---------------------------------------------------------------------------

async def test_encuentra_filas_pendiente_con_tipo_null():
    huerfana = _carga(estado="PENDIENTE", tipo=None)
    session = FakeAsyncSession(execute_queue=[[huerfana]])

    resultado = await buscar_cargas_pendientes_sin_tipo(session)

    assert resultado == [huerfana]


async def test_no_reporta_nada_cuando_la_query_no_devuelve_filas():
    session = FakeAsyncSession(execute_queue=[[]])

    resultado = await buscar_cargas_pendientes_sin_tipo(session)

    assert resultado == []


async def test_query_sin_tipo_filtra_por_estado_pendiente_y_tipo_null():
    """`FakeAsyncSession` no evalúa el `WHERE` -- devuelve lo que se le
    encola, sin importar el filtro. La garantía de que una fila `PENDIENTE`
    CON `tipo` (nuevo flujo) o una fila `ANULADO` con `tipo IS NULL` (vieja
    fila ya cerrada) nunca se reporta como huérfana vive en el `SELECT`
    real que arma la función, no en `FakeAsyncSession`: esta prueba
    inspecciona el statement REALMENTE ejecutado y confirma que ambas
    condiciones (`estado = 'PENDIENTE'` Y `tipo IS NULL`) están presentes,
    combinadas con AND -- nunca OR, que reportaría de más."""
    session = FakeAsyncSession(execute_queue=[[]])

    await buscar_cargas_pendientes_sin_tipo(session)

    assert len(session.executed_statements) == 1
    sql_compilado = str(
        session.executed_statements[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "carga_archivo.estado = 'PENDIENTE'" in sql_compilado
    assert "carga_archivo.tipo IS NULL" in sql_compilado
    assert " AND " in sql_compilado


# ---------------------------------------------------------------------------
# Caso B -- tipo conocido, período sin declarar (para un tipo que lo exige)
# ---------------------------------------------------------------------------

async def test_encuentra_filas_pendiente_con_tipo_pero_sin_periodo():
    huerfana = _carga(estado="PENDIENTE", tipo="VENTAS", periodo_desde=None)
    session = FakeAsyncSession(execute_queue=[[huerfana]])

    resultado = await buscar_cargas_pendientes_sin_periodo(session)

    assert resultado == [huerfana]


async def test_query_sin_periodo_filtra_tipo_no_null_periodo_null_y_tipo_en_lista():
    """Misma lógica que el test análogo del caso A: `FakeAsyncSession` no
    evalúa el `WHERE`, así que esta prueba inspecciona el SQL compilado
    para confirmar las 3 condiciones reales (tipo no nulo, período nulo,
    tipo en la lista de los que declaran período), combinadas con AND."""
    session = FakeAsyncSession(execute_queue=[[]])

    await buscar_cargas_pendientes_sin_periodo(session)

    assert len(session.executed_statements) == 1
    sql_compilado = str(
        session.executed_statements[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "carga_archivo.estado = 'PENDIENTE'" in sql_compilado
    assert "carga_archivo.tipo IS NOT NULL" in sql_compilado
    assert "carga_archivo.periodo_desde IS NULL" in sql_compilado
    assert "carga_archivo.tipo IN" in sql_compilado


# ---------------------------------------------------------------------------
# Reporte combinado
# ---------------------------------------------------------------------------

def test_formatear_reporte_ok_cuando_no_hay_huerfanas_de_ningun_caso():
    reporte = formatear_reporte([], [])

    assert "OK" in reporte
    assert "UPDATE" not in reporte


def test_formatear_reporte_ok_con_solo_el_primer_argumento_sin_tipo_vacio():
    """`sin_periodo` tiene default `()` -- un caller que solo conoce el
    caso A (como el test viejo, previo a este cambio) no debe romperse."""
    reporte = formatear_reporte([])

    assert "OK" in reporte


def test_formatear_reporte_incluye_grupo_sin_tipo_con_su_update():
    huerfana = _carga(estado="PENDIENTE", tipo=None, nombre_archivo="ventas_agosto.xlsx")

    reporte = formatear_reporte([huerfana], [])

    assert str(huerfana.id) in reporte
    assert "ventas_agosto.xlsx" in reporte
    assert "2026-08-01 12:00:00" in reporte
    assert UPDATE_SQL in reporte
    assert "estado = 'ANULADO'" in UPDATE_SQL
    assert "cutover_tipo_declarado_sin_tipo" in UPDATE_SQL
    assert "WHERE estado = 'PENDIENTE' AND tipo IS NULL" in UPDATE_SQL


def test_formatear_reporte_incluye_grupo_sin_periodo_con_su_update():
    huerfana = _carga(estado="PENDIENTE", tipo="VENTAS", periodo_desde=None, nombre_archivo="ventas_sep.xlsx")

    reporte = formatear_reporte([], [huerfana])

    assert str(huerfana.id) in reporte
    assert "ventas_sep.xlsx" in reporte
    assert UPDATE_SQL_SIN_PERIODO in reporte
    assert "estado = 'ANULADO'" in UPDATE_SQL_SIN_PERIODO
    assert "cutover_tipo_declarado_sin_periodo" in UPDATE_SQL_SIN_PERIODO
    assert "tipo IS NOT NULL AND periodo_desde IS NULL" in UPDATE_SQL_SIN_PERIODO


def test_formatear_reporte_incluye_ambos_grupos_cuando_hay_de_los_dos():
    sin_tipo = _carga(estado="PENDIENTE", tipo=None)
    sin_periodo = _carga(estado="PENDIENTE", tipo="INVENTARIO", periodo_desde=None)

    reporte = formatear_reporte([sin_tipo], [sin_periodo])

    assert str(sin_tipo.id) in reporte
    assert str(sin_periodo.id) in reporte
    assert UPDATE_SQL in reporte
    assert UPDATE_SQL_SIN_PERIODO in reporte


def test_formatear_reporte_cuenta_multiples_filas_por_grupo():
    huerfanas = [_carga(estado="PENDIENTE", tipo=None) for _ in range(3)]

    reporte = formatear_reporte(huerfanas, [])

    assert "(3)" in reporte
    for huerfana in huerfanas:
        assert str(huerfana.id) in reporte
