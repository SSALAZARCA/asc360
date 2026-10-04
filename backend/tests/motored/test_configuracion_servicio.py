"""
Motored "Configuración" admin page, T1 (odd/motored-configuracion-admin):
the point-in-time read `vigente_en`, the history query and the page read
model (`leer_configuracion`), with the fake session. The real SQL is proven
in `pg_real/test_configuracion_pg.py`.
"""
import datetime
import uuid

from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros
from app.motored.services import parametros_claves as pc
from tests.motored.conftest import FakeAsyncSession

CLAVE = "dias_ventana_ingresos"
SUC = uuid.uuid4()


def _fila(valor, desde, sucursal=None, clave=CLAVE):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor,
        vigente_desde=desde, sucursal_id=sucursal)


def _parametros_de(db):
    return db.executed_statements[0].compile().params.values()


async def test_vigente_en_queries_up_to_the_first_day_of_the_month():
    db = FakeAsyncSession(execute_queue=[[]])

    await parametros.vigente_en(db, CLAVE, datetime.date(2026, 10, 27))

    assert datetime.date(2026, 10, 1) in _parametros_de(db)
    assert datetime.date(2026, 10, 27) not in _parametros_de(db)


async def test_vigente_en_falls_back_to_the_registry_default():
    db = FakeAsyncSession(execute_queue=[[]])

    res = await parametros.vigente_en(db, CLAVE, datetime.date(2026, 10, 1))

    assert (res.valor, res.fuente) == (45, parametros.FUENTE_DEFAULT)
    assert res.parametro_id is None and res.vigente_desde is None


async def test_vigente_en_returns_the_global_row_when_no_sucursal_asked():
    glob = _fila(60, datetime.date(2026, 9, 1))
    suc = _fila(10, datetime.date(2026, 9, 1), SUC)
    db = FakeAsyncSession(execute_queue=[[glob, suc]])

    res = await parametros.vigente_en(db, CLAVE, datetime.date(2026, 10, 5))

    assert (res.valor, res.fuente) == (60, parametros.FUENTE_GLOBAL)
    assert res.vigente_desde == datetime.date(2026, 9, 1)


async def test_vigente_en_prefers_the_sucursal_row_over_the_global():
    glob = _fila(60, datetime.date(2026, 9, 1))
    suc = _fila(10, datetime.date(2026, 9, 1), SUC)
    db = FakeAsyncSession(execute_queue=[[glob, suc]])

    res = await parametros.vigente_en(
        db, CLAVE, datetime.date(2026, 10, 5), SUC)

    assert (res.valor, res.fuente) == (10, parametros.FUENTE_SUCURSAL)


async def test_vigente_en_uses_global_for_a_sucursal_without_override():
    glob = _fila(60, datetime.date(2026, 9, 1))
    db = FakeAsyncSession(execute_queue=[[glob]])

    res = await parametros.vigente_en(
        db, CLAVE, datetime.date(2026, 10, 5), uuid.uuid4())

    assert (res.valor, res.fuente) == (60, parametros.FUENTE_GLOBAL)


async def test_history_is_newest_first_and_joins_the_author_name():
    db = FakeAsyncSession(execute_queue=[[]])

    await parametros.listar_historial(db, CLAVE)

    sql = str(db.executed_statements[0].compile())
    assert "ORDER BY parametro_metodologia.vigente_desde DESC" in sql
    assert "usuario.nombre" in sql
    assert "LEFT OUTER JOIN usuario" in sql


async def test_history_rows_carry_the_author_name_or_none():
    uno = _fila(60, datetime.date(2026, 9, 1))
    dos = _fila(45, datetime.date(2026, 1, 1))
    db = FakeAsyncSession(execute_queue=[[(uno, "Ana"), (dos, None)]])

    filas = await parametros.listar_historial(db, CLAVE)

    assert [(f.valor, f.autor) for f in filas] == [(60, "Ana"), (45, None)]
    assert filas[0].fila is uno


async def test_configuracion_lists_every_registered_key_in_every_section():
    db = FakeAsyncSession(execute_queue=[[], []])

    cfg = await parametros.leer_configuracion(
        db, datetime.date(2026, 10, 4))

    assert [s["seccion"] for s in cfg] == list(pc.SECCIONES)
    claves = {c["clave"] for s in cfg for g in s["grupos"]
              for c in g["claves"]}
    assert claves == set(pc.REGISTRO)


async def test_configuracion_groups_by_registry_group_inside_a_section():
    db = FakeAsyncSession(execute_queue=[[], []])

    cfg = await parametros.leer_configuracion(
        db, datetime.date(2026, 10, 4))

    pedido = next(s for s in cfg if s["seccion"] == "pedido")
    assert [g["grupo"] for g in pedido["grupos"]] == [pc.GRUPO_MOTOR]
    avisos = next(s for s in cfg if s["seccion"] == "avisos")
    assert avisos["grupos"] == []


async def test_configuracion_shows_default_global_override_and_scheduled():
    glob = _fila(60, datetime.date(2026, 9, 1), clave="dias_entre_pedidos")
    suc = _fila(7, datetime.date(2026, 9, 1), SUC, "dias_entre_pedidos")
    futura = _fila(20, datetime.date(2026, 11, 1), None, "dias_entre_pedidos")
    db = FakeAsyncSession(execute_queue=[[glob, suc], [futura]])

    cfg = await parametros.leer_configuracion(
        db, datetime.date(2026, 10, 4))
    por_clave = {c["clave"]: c for s in cfg for g in s["grupos"]
                 for c in g["claves"]}

    dias = por_clave["dias_entre_pedidos"]
    assert dias["efectivo_global"]["valor"] == 60
    assert dias["efectivo_global"]["fuente"] == "GLOBAL"
    assert dias["por_sucursal"] == [{
        "sucursal_id": SUC, "valor": 7,
        "vigente_desde": datetime.date(2026, 9, 1),
        "parametro_id": suc.id}]
    assert [p["valor"] for p in dias["programados"]] == [20]
    otra = por_clave["umbral_f"]
    assert otra["efectivo_global"]["fuente"] == "DEFAULT"
    assert otra["efectivo_global"]["valor"] == 2
    assert otra["por_sucursal"] == [] and otra["programados"] == []


async def test_configuracion_reads_as_of_the_first_day_of_the_month():
    db = FakeAsyncSession(execute_queue=[[], []])

    await parametros.leer_configuracion(db, datetime.date(2026, 10, 27))

    assert datetime.date(2026, 10, 1) in _parametros_de(db)
