"""Pending invoice ingresos: the pure rule (odd/tasks/motored-ingresos-pendientes.md)."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal as D
from types import SimpleNamespace

from app.motored.services import ingresos_pendientes as ip

TIENDA = uuid.uuid4()
OTRA = uuid.uuid4()
ASOCIADA = uuid.uuid4()
HOY = date(2026, 10, 8)
DESDE = date(2026, 9, 1)
PRINCIPAL = {TIENDA: TIENDA, OTRA: OTRA, ASOCIADA: TIENDA}
NOMBRES = {TIENDA: "Cali", OTRA: "Pasto"}


def _l(numero, fecha, cant, valor, suc=TIENDA, prefijo="RH"):
    return SimpleNamespace(
        prefijo_rh=prefijo, numero_rh=numero, sucursal_id=suc,
        fecha_factura=fecha, cantidad=D(cant), valor_total=D(valor))


def _calc(lineas, ingresos=(), desde=DESDE, conf=None):
    return ip.calcular_pendientes(
        lineas, set(ingresos), desde, HOY, PRINCIPAL, NOMBRES, conf or {})


def test_pending_document_has_the_expected_shape():
    [item] = _calc([_l(482915, date(2026, 10, 3), 2, 100),
                    _l(482915, date(2026, 10, 3), 3, 50)])
    assert item["factura"] == "RH 482915"
    assert item["prefijo_rh"] == "RH" and item["numero_rh"] == 482915
    assert item["sucursal_id"] == TIENDA and item["tienda"] == "Cali"
    assert item["fecha"] == date(2026, 10, 3) and item["dias"] == 5
    assert item["unidades"] == D(5) and item["valor"] == D(150)
    assert item["estado"] == "SIN_CONFIRMAR"
    assert item["confirmado_por"] is None and item["confirmado_en"] is None


def test_documents_before_verificable_desde_are_not_verifiable():
    assert _calc([_l(1, date(2026, 8, 31), 1, 1)]) == []
    assert len(_calc([_l(1, date(2026, 9, 1), 1, 1)])) == 1


def test_nothing_verifiable_returns_empty():
    assert _calc([_l(1, date(2026, 10, 1), 1, 1)], desde=None) == []


def test_real_ingreso_removes_the_document():
    lineas = [_l(1, date(2026, 10, 1), 1, 1), _l(2, date(2026, 10, 1), 1, 1)]
    out = _calc(lineas, ingresos=[("RH", 1)])
    assert [i["numero_rh"] for i in out] == [2]


def test_prefix_is_part_of_the_identity():
    out = _calc([_l(1, date(2026, 10, 1), 1, 1, prefijo="NR")],
                ingresos=[("RH", 1)])
    assert len(out) == 1


def test_credit_notes_net_and_fully_credited_is_dropped():
    parcial = [_l(5, date(2026, 10, 1), 4, 400), _l(5, date(2026, 10, 2), -1, -100)]
    [item] = _calc(parcial)
    assert item["unidades"] == D(3) and item["valor"] == D(300)
    total = [_l(6, date(2026, 10, 1), 4, 400), _l(6, date(2026, 10, 2), -4, -400)]
    assert _calc(total) == []


def test_multi_date_document_takes_the_min_date():
    [item] = _calc([_l(7, date(2026, 10, 5), 1, 1), _l(7, date(2026, 10, 2), 1, 1)])
    assert item["fecha"] == date(2026, 10, 2) and item["dias"] == 6


def test_associated_store_rolls_up_into_principal():
    [item] = _calc([_l(8, date(2026, 10, 1), 1, 1, suc=ASOCIADA)])
    assert item["sucursal_id"] == TIENDA and item["tienda"] == "Cali"


def test_sorted_oldest_first_and_confirmation_applied():
    ahora = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
    conf = {("RH", 10, TIENDA): SimpleNamespace(
        estado="LLEGO", actualizado_por_nombre="Ana", actualizado_en=ahora)}
    out = _calc([_l(11, date(2026, 10, 6), 1, 1), _l(10, date(2026, 10, 1), 1, 1)],
                conf=conf)
    assert [i["numero_rh"] for i in out] == [10, 11]
    assert out[0]["estado"] == "LLEGO"
    assert out[0]["confirmado_por"] == "Ana" and out[0]["confirmado_en"] == ahora
    assert out[1]["estado"] == "SIN_CONFIRMAR"


def test_parse_factura():
    assert ip.parsear_factura("rh 482915") == ("RH", 482915)
    assert ip.parsear_factura("RH482915") == ("RH", 482915)
    for malo in ("", "482915", "RH", None, "R1 5"):
        assert ip.parsear_factura(malo) is None


def test_resumen_counts_by_state():
    items = [
        {"estado": "SIN_CONFIRMAR", "dias": 3, "valor": D(10), "sucursal_id": TIENDA},
        {"estado": "LLEGO", "dias": 9, "valor": D(20), "sucursal_id": TIENDA},
        {"estado": "NO_HA_LLEGADO", "dias": 1, "valor": D(5), "sucursal_id": OTRA},
    ]
    r = ip.resumen(items)
    assert r == {"pendientes": 3, "llegaron_sin_ingresar": 1, "sin_confirmar": 1,
                 "aun_no_llegan": 1, "mas_antigua": 9, "valor_pendiente": D(35)}
    assert ip.resumen([])["mas_antigua"] is None


def test_por_tienda_groups_and_orders_by_pendientes_desc():
    items = [
        {"estado": "SIN_CONFIRMAR", "dias": 3, "valor": D(10), "sucursal_id": TIENDA, "tienda": "Cali"},
        {"estado": "LLEGO", "dias": 9, "valor": D(20), "sucursal_id": TIENDA, "tienda": "Cali"},
        {"estado": "NO_HA_LLEGADO", "dias": 1, "valor": D(5), "sucursal_id": OTRA, "tienda": "Pasto"},
    ]
    filas = ip.por_tienda(items)
    assert [f["tienda"] for f in filas] == ["Cali", "Pasto"]
    assert filas[0]["pendientes"] == 2 and filas[0]["llegaron_sin_ingresar"] == 1
    assert filas[0]["mas_antigua"] == 9 and filas[0]["valor_pendiente"] == D(30)
