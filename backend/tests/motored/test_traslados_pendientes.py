"""Pending transfers: the pure grouping/estado rules and the atomic confirm
(odd/tasks/motored-traslados-pendientes.md, T2)."""
import uuid
from datetime import date, datetime
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.models.traslado import (
    TrasladoConfirmacion, TrasladoConfirmacionHistorial)
from app.motored.services import traslados_pendientes as tp

HOY = date(2026, 10, 9)
CALI, SUR, BOGOTA, ORIGEN = (uuid.uuid4() for _ in range(4))
NOMBRES = {CALI: "Cali", SUR: "Cali Sur", BOGOTA: "Bogotá", ORIGEN: "Medellín"}
PRINCIPAL = {SUR: CALI}


def _l(doc="79-1", bod="BA1", fecha=date(2026, 10, 1), destino=CALI,
       origen=ORIGEN, ref="R1", cant=1, desc="Pieza", desc_bod=None):
    return NS(
        nro_documento=doc, bodega_salida=bod, fecha=fecha,
        descripcion_bodega_salida=desc_bod, sucursal_salida_id=origen,
        sucursal_entrada_id=destino, referencia_codigo=ref,
        descripcion=desc, cantidad=cant)


def _calc(lineas, confs=None):
    return tp.calcular_traslados(lineas, HOY, PRINCIPAL, NOMBRES, confs or {})


def test_agrupa_por_documento_y_bodega_de_salida():
    items = _calc([_l("79-1", "BA1"), _l("79-1", "BB2"), _l("79-2", "BA1")])

    assert [(i["documento"], i["bodega_salida"]) for i in items] == [
        ("79-1", "BA1"), ("79-1", "BB2"), ("79-2", "BA1")]


def test_un_traslado_suma_unidades_refs_distintas_y_lineas():
    items = _calc([
        _l(ref="R1", cant=2, fecha=date(2026, 10, 5)),
        _l(ref="R2", cant=3, fecha=date(2026, 10, 3)),
        _l(ref="R1", cant=1, fecha=date(2026, 10, 4)),
    ])

    (item,) = items
    assert item["fecha"] == date(2026, 10, 3)
    assert item["dias"] == 6
    assert item["refs"] == 2 and item["unidades"] == 6 and item["num_lineas"] == 3
    assert item["lineas"] == [
        {"referencia": "R1", "descripcion": "Pieza", "cantidad": 3.0},
        {"referencia": "R2", "descripcion": "Pieza", "cantidad": 3.0}]


def test_sale_y_llega_usan_la_tienda_principal_de_cada_extremo():
    (item,) = _calc([_l(destino=SUR)])

    assert item["sucursal_id"] == CALI
    assert item["llega"] == "Cali" and item["tienda"] == "Cali"
    assert item["sale"] == "Medellín"


def test_origen_sin_tienda_usa_la_descripcion_o_el_codigo_de_la_bodega():
    (con_desc,) = _calc([_l(origen=None, desc_bod="BODEGA CENTRAL")])
    (sin_desc,) = _calc([_l(origen=None, desc_bod=None)])

    assert con_desc["sale"] == "BODEGA CENTRAL"
    assert sin_desc["sale"] == "BA1"


def test_estados_y_aviso_erp_vienen_de_la_confirmacion():
    ahora = datetime(2026, 10, 8, 9, 0)
    confs = {
        ("79-1", "BA1"): NS(estado="RECIBIDO", actualizado_por_nombre="Ana",
                            actualizado_en=ahora),
        ("79-2", "BA1"): NS(estado="NO_HA_LLEGADO", actualizado_por_nombre="Luis",
                            actualizado_en=ahora),
    }
    items = {i["documento"]: i for i in _calc(
        [_l("79-1"), _l("79-2"), _l("79-3")], confs)}

    assert items["79-1"]["estado"] == "RECIBIDO" and items["79-1"]["aviso_erp"]
    assert items["79-1"]["confirmado_por"] == "Ana"
    assert items["79-1"]["confirmado_en"] == ahora
    assert items["79-2"]["estado"] == "NO_HA_LLEGADO"
    assert not items["79-2"]["aviso_erp"]
    assert items["79-3"]["estado"] == "SIN_CONFIRMAR"
    assert items["79-3"]["confirmado_por"] is None


def test_la_confirmacion_de_otra_bodega_del_mismo_documento_no_aplica():
    confs = {("79-1", "BA1"): NS(
        estado="RECIBIDO", actualizado_por_nombre="Ana", actualizado_en=None)}
    items = {i["bodega_salida"]: i for i in _calc(
        [_l("79-1", "BA1"), _l("79-1", "BB2")], confs)}

    assert items["BA1"]["estado"] == "RECIBIDO"
    assert items["BB2"]["estado"] == "SIN_CONFIRMAR"


def test_resumen_cuenta_estados_masantiguo_y_lineas():
    confs = {
        ("79-1", "BA1"): NS(estado="RECIBIDO", actualizado_por_nombre="A",
                            actualizado_en=None),
        ("79-2", "BA1"): NS(estado="NO_HA_LLEGADO", actualizado_por_nombre="A",
                            actualizado_en=None),
    }
    items = _calc([
        _l("79-1", fecha=date(2026, 10, 8)),
        _l("79-2", fecha=date(2026, 9, 1), destino=BOGOTA),
        _l("79-3", fecha=date(2026, 10, 9)), _l("79-3", ref="R2"),
    ], confs)

    assert tp.resumen(items) == {
        "pendientes": 3, "recibidos_sin_erp": 1, "sin_confirmar": 1,
        "aun_no_llegan": 1,
        "mas_antiguo": {"documento": "79-2", "tienda": "Bogotá", "dias": 38},
        "lineas": 4}


def test_resumen_vacio():
    assert tp.resumen([]) == {
        "pendientes": 0, "recibidos_sin_erp": 0, "sin_confirmar": 0,
        "aun_no_llegan": 0, "mas_antiguo": None, "lineas": 0}


def test_por_tienda_ordena_por_recibidos_y_resume_cada_tienda():
    confs = {("79-3", "BA1"): NS(
        estado="RECIBIDO", actualizado_por_nombre="A", actualizado_en=None)}
    items = _calc([
        _l("79-1", destino=BOGOTA, cant=2, fecha=date(2026, 9, 29)),
        _l("79-2", destino=CALI, cant=4), _l("79-3", destino=SUR, cant=1),
    ], confs)

    filas = tp.por_tienda(items)

    assert [f["tienda"] for f in filas] == ["Cali", "Bogotá"]
    assert filas[0] == {
        "sucursal_id": CALI, "tienda": "Cali", "pendientes": 2, "recibidos": 1,
        "sin_confirmar": 1, "no": 0, "mas_antiguo_dias": 8, "unidades": 5.0}
    assert filas[1]["mas_antiguo_dias"] == 10


# ---------------------------------------------------------------------------
# confirmar
# ---------------------------------------------------------------------------

def _db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _pendientes(monkeypatch, items):
    mock = AsyncMock(return_value=items)
    monkeypatch.setattr(tp, "pendientes", mock)
    return mock


async def test_confirmar_hace_upsert_atomico_e_historial(monkeypatch):
    item = {"documento": "79-1", "bodega_salida": "BA1", "estado": "SIN_CONFIRMAR",
            "sucursal_id": CALI}
    _pendientes(monkeypatch, [item])
    db = _db()

    out = await tp.confirmar(
        db, " 79-1 ", "BA1", "RECIBIDO", tp.Actor(nombre="Ana"), "link")

    assert out["estado"] == "RECIBIDO" and out["aviso_erp"] is True
    assert out["confirmado_por"] == "Ana"
    [(stmt,), _] = db.execute.await_args
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert sql.startswith("INSERT INTO traslado_confirmacion")
    assert "ON CONFLICT (nro_documento, bodega_salida) DO UPDATE" in sql
    agregados = [type(c.args[0]) for c in db.add.call_args_list]
    assert agregados == [TrasladoConfirmacionHistorial]
    assert TrasladoConfirmacion not in agregados
    assert db.add.call_args.args[0].canal == "link"
    db.commit.assert_awaited_once()


async def test_confirmar_fuera_del_snapshot_es_404(monkeypatch):
    _pendientes(monkeypatch, [])
    db = _db()

    with pytest.raises(tp.PendienteError) as exc:
        await tp.confirmar(db, "79-9", "BA1", "RECIBIDO", tp.Actor(nombre="A"), "web")

    assert (exc.value.status_code, exc.value.detail) == (404, tp.MSG_NO_PENDIENTE)
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("doc,bod,estado,detalle", [
    ("", "BA1", "RECIBIDO", tp.MSG_TRASLADO),
    ("79-1", None, "RECIBIDO", tp.MSG_TRASLADO),
    ("79-1", "BA1", "LLEGO", tp.MSG_ESTADO),
    ("79-1", "BA1", None, tp.MSG_ESTADO),
])
async def test_confirmar_valida_el_cuerpo_con_422(monkeypatch, doc, bod, estado, detalle):
    _pendientes(monkeypatch, [])

    with pytest.raises(tp.PendienteError) as exc:
        await tp.confirmar(_db(), doc, bod, estado, tp.Actor(nombre="A"), "web")

    assert (exc.value.status_code, exc.value.detail) == (422, detalle)


async def test_confirmar_con_tiendas_solo_busca_en_ellas(monkeypatch):
    mock = _pendientes(monkeypatch, [])

    with pytest.raises(tp.PendienteError):
        await tp.confirmar(
            _db(), "79-1", "BA1", "RECIBIDO", tp.Actor(nombre="A"), "link",
            tiendas=[CALI])

    assert mock.await_args.args[1] == [CALI]
