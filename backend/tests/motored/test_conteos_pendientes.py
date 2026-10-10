"""
Inventory counts, "Pendientes por sanear" (odd/motored-conteos-inventario,
WU15): invoices still waiting for an ingreso and transfers still waiting
for reception in the count's store. Iniciar only WARNS: a 409 with the
counts until the leader confirms; the confirmation is recorded in
`conteo.snapshot_advertencias`. Combined with the stale-inventory 409,
either confirmation may come first.

The orchestration of `iniciar_conteo` runs here on stubbed seams; the SQL
side runs in `pg_real/test_conteos_pendientes_pg.py`.
"""
import datetime
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.motored.models.conteo import Conteo
from app.motored.services import ingresos_pendientes as ingresos
from app.motored.services import traslados_pendientes as traslados
from app.motored.services.conteos import (
    acceso, errores, pendientes, snapshot,
)

UTC = datetime.timezone.utc
AHORA = datetime.datetime(2026, 10, 10, 15, 0, tzinfo=UTC)
HOY = AHORA.date()
USUARIO = uuid.uuid4()
TIENDA = uuid.uuid4()


# --- the pure verdict --------------------------------------------------------


def test_no_pending_items_give_no_warning():
    assert pendientes.revisar(0, 0, False, USUARIO) is None
    assert pendientes.revisar(0, 0, True, USUARIO) is None


@pytest.mark.parametrize("facturas, traslados_", [(2, 1), (1, 0), (0, 3)])
def test_pending_items_are_a_409_with_the_counts(facturas, traslados_):
    with pytest.raises(errores.PendientesPorSanear) as error:
        pendientes.revisar(facturas, traslados_, False, USUARIO)

    assert error.value.codigo == "PENDIENTES_POR_SANEAR"
    assert error.value.datos == {
        "facturas": facturas, "traslados": traslados_}


def test_the_message_names_both_counts_in_spanish():
    with pytest.raises(errores.PendientesPorSanear) as error:
        pendientes.revisar(1, 2, False, USUARIO)

    assert "1 factura por ingresar" in error.value.mensaje
    assert "2 traslados por recibir" in error.value.mensaje


def test_a_confirmed_start_records_who_and_the_counts():
    registro = pendientes.revisar(2, 1, True, USUARIO)

    assert registro == {
        "facturas": 2, "traslados": 1, "confirmada_por": str(USUARIO)}


# --- the store's lists, shaped from the services -----------------------------


def _factura(**extra):
    item = {
        "prefijo_rh": "RH", "numero_rh": 482915, "factura": "RH 482915",
        "sucursal_id": TIENDA, "tienda": "Quilichao",
        "fecha": datetime.date(2026, 10, 3), "dias": 7, "unidades": 4.0,
        "valor": 125000.0, "num_referencias": 3, "responsable": "ASESOR",
        "puede_descargar_plantilla": False, "estado": ingresos.LLEGO,
        "confirmado_por": "Ana", "confirmado_en": AHORA}
    item.update(extra)
    return item


def _traslado(**extra):
    item = {
        "documento": "79-00000067", "bodega_salida": "B07",
        "bodega_entrada": "B01", "sale": "Popayán", "sucursal_id": TIENDA,
        "llega": "Quilichao", "tienda": "Quilichao",
        "fecha": datetime.date(2026, 10, 5), "dias": 5, "refs": 2,
        "unidades": 6.0, "num_lineas": 3, "lineas": [],
        "estado": traslados.SIN_CONFIRMAR, "aviso_erp": False,
        "confirmado_por": None, "confirmado_en": None}
    item.update(extra)
    return item


def _sembrar_lecturas(monkeypatch, facturas, lista_traslados, cargas=None):
    leer_facturas = AsyncMock(return_value=facturas)
    leer_traslados = AsyncMock(return_value=lista_traslados)
    monkeypatch.setattr(ingresos, "pendientes", leer_facturas)
    monkeypatch.setattr(traslados, "pendientes", leer_traslados)
    monkeypatch.setattr(
        ingresos, "verificable_desde",
        AsyncMock(return_value=datetime.date(2026, 9, 1)))
    monkeypatch.setattr(
        pendientes, "ultima_carga",
        AsyncMock(side_effect=lambda db, tipo: (cargas or {}).get(tipo)))
    return leer_facturas, leer_traslados


async def test_the_lists_are_read_per_store_with_the_services(monkeypatch):
    leer_facturas, leer_traslados = _sembrar_lecturas(
        monkeypatch, [_factura()], [_traslado()])

    salida = await pendientes.leer(object(), TIENDA, HOY)

    assert leer_facturas.await_args.args[1] == [TIENDA]
    assert leer_traslados.await_args.args[1] == [TIENDA]
    assert salida["facturas"] == [{
        "factura": "RH 482915", "fecha": datetime.date(2026, 10, 3),
        "dias": 7, "unidades": 4.0, "valor": 125000.0,
        "num_referencias": 3, "estado_confirmacion": "LLEGO",
        "confirmado_por": "Ana", "clave": "RH 482915",
        "verificado": None}]
    assert salida["traslados"] == [{
        "documento": "79-00000067", "fecha": datetime.date(2026, 10, 5),
        "dias": 5, "bodega_salida": "B07", "bodega_entrada": "B01",
        "sale": "Popayán", "llega": "Quilichao", "refs": 2,
        "unidades": 6.0, "num_lineas": 3,
        "estado_confirmacion": "SIN_CONFIRMAR", "confirmado_por": None,
        "clave": "79-00000067|B07|B01", "verificado": None}]
    assert salida["verificable_desde"] == datetime.date(2026, 9, 1)
    assert salida["por_sanear"] == {"facturas": 1, "traslados": 1}


async def test_the_load_dates_come_per_type(monkeypatch):
    carga = {"fecha_carga": AHORA, "periodo_hasta": None}
    _sembrar_lecturas(
        monkeypatch, [], [], {"FACTURAS_PEDIDOS": carga})

    salida = await pendientes.leer(object(), TIENDA, HOY)

    assert salida["cargas"] == {
        "facturas_pedidos": carga, "ingresos_facturas": None,
        "traslados": None}
    assert salida["facturas"] == [] and salida["traslados"] == []


async def test_counting_uses_the_same_readers(monkeypatch):
    _sembrar_lecturas(
        monkeypatch, [_factura(), _factura(numero_rh=1)], [_traslado()])

    assert await pendientes.contar(object(), TIENDA, HOY) == (2, 1)


# --- Iniciar: warn, never block ----------------------------------------------


class _Db:
    """Just what `iniciar_conteo` touches once its seams are stubbed."""

    def __init__(self):
        self.flush = AsyncMock()

    @asynccontextmanager
    async def begin_nested(self):
        yield


@pytest.fixture
def inicio(monkeypatch):
    """Stubs the seams of `iniciar_conteo`. `estado["antiguo"]` makes the
    inventory 30 hours old (limit 6); `estado["pendientes"]` sets the
    store's (facturas, traslados)."""
    conteo = Conteo(
        id=uuid.uuid4(), tipo="TOTAL", estado="PROGRAMADO",
        origen="MANUAL", sucursal_id=TIENDA, lider_id=USUARIO,
        fecha_programada=HOY)
    estado = {"antiguo": False, "pendientes": (0, 0)}

    def fuente(*_):
        horas = 30 if estado["antiguo"] else 1
        return snapshot.FuenteSnapshot(
            uuid.uuid4(), HOY, AHORA - datetime.timedelta(hours=horas), 5)

    monkeypatch.setattr(
        acceso, "bloquear_conteo", AsyncMock(return_value=conteo))
    monkeypatch.setattr(snapshot, "_exigir_sin_total_abierto", AsyncMock())
    monkeypatch.setattr(snapshot, "leer_umbrales", AsyncMock(
        return_value=snapshot.Umbrales(
            Decimal("100000"), Decimal("500000"), 6)))
    monkeypatch.setattr(
        snapshot, "copiar_snapshot", AsyncMock(side_effect=fuente))
    monkeypatch.setattr(pendientes, "contar", AsyncMock(
        side_effect=lambda *_: estado["pendientes"]))
    return conteo, estado


async def _iniciar(**banderas):
    return await snapshot.iniciar_conteo(
        _Db(), uuid.uuid4(), USUARIO, ahora=AHORA, **banderas)


async def test_pending_items_refuse_an_unconfirmed_start(inicio):
    conteo, estado = inicio
    estado["pendientes"] = (2, 1)

    with pytest.raises(errores.PendientesPorSanear) as error:
        await _iniciar()

    assert error.value.datos == {"facturas": 2, "traslados": 1}
    assert conteo.estado == "PROGRAMADO"


async def test_a_confirmed_start_records_the_pending_items(inicio):
    conteo, estado = inicio
    estado["pendientes"] = (2, 1)

    salida = await _iniciar(confirmar_pendientes=True)

    registro = {
        "pendientes": {
            "facturas": 2, "traslados": 1, "confirmada_por": str(USUARIO)}}
    assert conteo.estado == "EN_CONTEO"
    assert conteo.snapshot_advertencias == registro
    assert salida.advertencia == registro


async def test_no_pending_items_start_without_a_record(inicio):
    conteo, _ = inicio

    salida = await _iniciar(confirmar_pendientes=True)

    assert conteo.estado == "EN_CONTEO"
    assert conteo.snapshot_advertencias is None
    assert salida.advertencia is None


async def test_the_counts_are_read_for_the_conteo_store(inicio):
    _, _ = inicio

    await _iniciar()

    assert pendientes.contar.await_args.args[1:3] == (TIENDA, HOY)


@pytest.mark.parametrize("primera, segunda", [
    ({"confirmar_antiguedad": True}, {"confirmar_pendientes": True}),
    ({"confirmar_pendientes": True}, {"confirmar_antiguedad": True}),
])
async def test_stale_and_pending_need_both_confirmations_in_any_order(
        inicio, primera, segunda):
    conteo, estado = inicio
    estado.update(antiguo=True, pendientes=(1, 2))
    nombres = {
        "confirmar_antiguedad": "confirmar_inventario_viejo",
        "confirmar_pendientes": "confirmar_pendientes"}

    def banderas(*confirmadas):
        return {nombres[k]: True for c in confirmadas for k in c}

    with pytest.raises((errores.PendientesPorSanear,
                        errores.InventarioAntiguo)):
        await _iniciar()
    with pytest.raises((errores.PendientesPorSanear,
                        errores.InventarioAntiguo)):
        await _iniciar(**banderas(primera))
    assert conteo.estado == "PROGRAMADO"

    await _iniciar(**banderas(primera, segunda))

    assert conteo.estado == "EN_CONTEO"
    assert conteo.snapshot_advertencias == {
        "antiguedad_horas": "30.0", "vigencia_horas": 6,
        "confirmada_por": str(USUARIO),
        "pendientes": {
            "facturas": 1, "traslados": 2, "confirmada_por": str(USUARIO)}}


async def test_only_the_stale_inventory_keeps_its_flat_record(inicio):
    conteo, estado = inicio
    estado["antiguo"] = True

    await _iniciar(confirmar_inventario_viejo=True)

    assert conteo.snapshot_advertencias == {
        "antiguedad_horas": "30.0", "vigencia_horas": 6,
        "confirmada_por": str(USUARIO)}


# --- "Verificado en el ERP": scoped to this conteo ---------------------------


def _marca(tipo="FACTURA", clave="RH 482915"):
    return {
        "tipo": tipo, "clave": clave, "usuario_id": str(USUARIO),
        "nombre": "Lina Líder", "en": AHORA.isoformat()}


def test_marking_adds_one_entry_per_item_and_keeps_the_rest():
    previas = {"verificados_erp": [_marca("TRASLADO", "D|B07|B01")]}

    nuevas = pendientes.marcar_en(
        previas, "FACTURA", "RH 482915", USUARIO, "Lina Líder", AHORA)
    otra_vez = pendientes.marcar_en(
        nuevas, "FACTURA", "RH 482915", USUARIO, "Lina Líder", AHORA)

    assert nuevas == {"verificados_erp": [
        _marca("TRASLADO", "D|B07|B01"), _marca()]}
    assert otra_vez == nuevas
    assert previas == {"verificados_erp": [_marca("TRASLADO", "D|B07|B01")]}


def test_undoing_removes_only_that_item_and_clears_an_empty_record():
    previas = {"verificados_erp": [_marca(), _marca("TRASLADO", "D|X|Y")]}

    quedan = pendientes.desmarcar_en(previas, "FACTURA", "RH 482915")

    assert quedan == {"verificados_erp": [_marca("TRASLADO", "D|X|Y")]}
    assert pendientes.desmarcar_en(quedan, "TRASLADO", "D|X|Y") is None
    assert pendientes.desmarcar_en(None, "FACTURA", "RH 1") is None


async def test_verified_items_carry_who_and_when_and_stop_counting(
        monkeypatch):
    _sembrar_lecturas(
        monkeypatch, [_factura(), _factura(numero_rh=1, factura="RH 1")],
        [_traslado()])
    marcas = [_marca(), _marca("TRASLADO", "79-00000067|B07|B01")]

    salida = await pendientes.leer(object(), TIENDA, HOY, marcas)
    cuenta = await pendientes.contar(object(), TIENDA, HOY, marcas)

    assert salida["facturas"][0]["verificado"] == {
        "por": "Lina Líder", "en": AHORA.isoformat()}
    assert salida["facturas"][1]["verificado"] is None
    assert salida["traslados"][0]["verificado"]["por"] == "Lina Líder"
    assert salida["por_sanear"] == {"facturas": 1, "traslados": 0}
    assert cuenta == (1, 0)


class _DbMarca:
    """A locked conteo, the store's lists and the leader's name."""

    def __init__(self, conteo):
        self.conteo = conteo
        self.flush = AsyncMock()

    async def get(self, modelo, ident):
        return type("U", (), {"nombre": "Lina Líder"})()


@pytest.fixture
def marcable(monkeypatch):
    conteo = Conteo(
        id=uuid.uuid4(), tipo="TOTAL", estado="PROGRAMADO",
        origen="MANUAL", sucursal_id=TIENDA, lider_id=USUARIO,
        fecha_programada=HOY)
    monkeypatch.setattr(
        acceso, "bloquear_conteo", AsyncMock(return_value=conteo))
    _sembrar_lecturas(monkeypatch, [_factura()], [_traslado()])
    return conteo


async def test_marking_a_pending_item_stores_it_on_the_conteo(marcable):
    db = _DbMarca(marcable)

    await pendientes.marcar(
        db, marcable.id, "TRASLADO", "79-00000067|B07|B01", USUARIO,
        AHORA)

    assert marcable.snapshot_advertencias == {"verificados_erp": [
        _marca("TRASLADO", "79-00000067|B07|B01")]}
    assert acceso.bloquear_conteo.await_count == 1
    db.flush.assert_awaited()

    await pendientes.desmarcar(
        db, marcable.id, "TRASLADO", "79-00000067|B07|B01")

    assert marcable.snapshot_advertencias is None


async def test_an_item_not_pending_in_the_store_is_a_404(marcable):
    with pytest.raises(errores.PendienteNoEncontrado):
        await pendientes.marcar(
            _DbMarca(marcable), marcable.id, "FACTURA", "RH 9", USUARIO,
            AHORA)


async def test_an_unknown_type_is_refused(marcable):
    with pytest.raises(errores.PendienteInvalido):
        await pendientes.marcar(
            _DbMarca(marcable), marcable.id, "OTRO", "RH 482915", USUARIO,
            AHORA)


@pytest.mark.parametrize("estado", ["EN_CONTEO", "CERRADO", "ANULADO"])
async def test_marks_are_frozen_once_the_count_started(marcable, estado):
    marcable.estado = estado

    with pytest.raises(errores.EstadoInvalido):
        await pendientes.marcar(
            _DbMarca(marcable), marcable.id, "FACTURA", "RH 482915",
            USUARIO, AHORA)
    with pytest.raises(errores.EstadoInvalido):
        await pendientes.desmarcar(
            _DbMarca(marcable), marcable.id, "FACTURA", "RH 482915")


async def test_iniciar_counts_only_unverified_and_keeps_the_marks(inicio):
    conteo, estado = inicio
    conteo.snapshot_advertencias = {"verificados_erp": [_marca()]}
    estado["pendientes"] = (0, 0)

    await _iniciar()

    assert pendientes.contar.await_args.args[3] == [_marca()]
    assert conteo.snapshot_advertencias == {"verificados_erp": [_marca()]}
