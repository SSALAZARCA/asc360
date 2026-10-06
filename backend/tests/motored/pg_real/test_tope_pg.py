"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B5b, ADR-6, spec
TP-08..TP-14b, TP-24..TP-33): el recorte al tope de presupuesto contra un
Postgres real (opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base migrada con `alembic -c alembic_motored.ini upgrade head`. Una única
conexión dentro de una transacción que se revierte al final (la `fabrica` de
`test_corridas_api_pg.py`) y las peticiones entran por la app real (ASGI,
`httpx`), con el usuario inyectado y la sesión real.

Siembra una corrida BORRADOR con dos tiendas: A (con tope de 9.000) tiene
una línea C de 50 y otra de 30, una B, una A, una D y una sin precio (más otra
sin precio y en 0, que no cuenta), con valor 12.000 y un exceso de 3.000 que
el recorte quita bajando la C-1 de 50 a 20; B vale 5.000 y no tiene tope.
Prueba lo que los dobles no pueden: el SQL
de la propuesta y de los totales, el UPDATE por lote, que el historial lleva
el tope y el token, la atomicidad y el tope congelado en el evento CERRADO.
La concurrencia (TP-32) está en `test_pedido_concurrencia_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_linea_historial import CorridaLineaHistorial
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.pedido_evento import PedidoEvento
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.database import get_motored_db
from app.main import app
from app.motored.services.corridas import tope
from tests.motored.pg_real.codigos_co import codigo_co_unico
from tests.motored.pg_real.test_corridas_api_pg import (  # noqa: F401
    BASE,
    URL,
    _app_lista,
    _cliente,
    _como,
    _sesion_de,
    fabrica,
)

pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

CORTE = datetime.date(2026, 9, 21)
DESDE = datetime.date(2026, 1, 1)
D = Decimal
CEROS = D("0.00")


def _linea(corrida, sucursal, referencia, pedido, clase_abc, *,
           precio="100.00", y="0.00", n="10.000000"):
    precio_d = None if precio is None else D(precio)
    return CorridaLinea(
        corrida_id=corrida.id, sucursal_id=sucursal.id,
        referencia_id=referencia.id, codigo_referencia=referencia.codigo,
        nombre_parte=f"PARTE {referencia.codigo}", unidad_empaque=10,
        banderas=[],
        **{f"venta_m{m}": CEROS for m in range(1, 7)},
        **{f"perdida_m{m}": CEROS for m in range(1, 7)},
        inventario=CEROS, transito=CEROS, backorder=CEROS, ajuste=CEROS,
        pedido_sugerido=D(pedido), pedido_final=D(pedido), precio=precio_d,
        valor_pedido=CEROS if precio_d is None else D(pedido) * precio_d,
        clase_abc=clase_abc, clase=f"{clase_abc}F", estado_quiebre="NORMAL",
        inventario_final=D(y), demanda_ponderada=D(n))


# Código, pedido, clase, precio: la tienda A vale 12.000.
LINEAS_A = (
    ("C-1", "50.00", "C", "100.00"), ("C-2", "30.00", "C", "100.00"),
    ("B-1", "20.00", "B", "100.00"), ("A-1", "10.00", "A", "100.00"),
    ("D-1", "10.00", "D", "100.00"), ("SP-1", "5.00", "C", None),
    ("SP-0", "0.00", "C", None))


async def _sembrar(db, *, modo=True, tope_a="9000"):
    """Proveedor, usuario COMPRAS, tiendas A y B, la corrida BORRADOR con
    sus líneas y el tope de A; todo confirmado dentro del savepoint."""
    sufijo = uuid.uuid4().hex[:6]
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"TOP-{sufijo}", nombre="tope",
        es_principal=False, dias_empaque_default=1, dias_transito_default=1,
        dias_seguridad_default=D("1"))
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Compras", role=MotoredRole.COMPRAS,
        email=f"t-{sufijo}@x.co", hashed_password="x")
    a, b = (
        Sucursal(id=uuid.uuid4(), nombre=f"{n} {sufijo}", sic=f"S-{n}",
                 codigo_co=codigo_co_unico(), dias_empaque=1,
                 dias_transito=1) for n in ("A", "B"))
    db.add_all([proveedor, usuario, a, b])
    await db.flush()
    corrida = Corrida(
        id=uuid.uuid4(), codigo=f"TOP-{sufijo}-01",
        proveedor_id=proveedor.id, fecha_corte=CORTE, estado="BORRADOR")
    referencias = {
        codigo: Referencia(
            id=uuid.uuid4(), codigo=f"{codigo}-{sufijo}",
            proveedor_id=proveedor.id, unidad_empaque=10,
            precio_normal=D("100.00"))
        for codigo, *_ in (*LINEAS_A, ("X-B", 0, 0, 0))}
    db.add_all([*referencias.values(), corrida])
    await db.flush()
    db.add_all([
        CorridaSucursal(
            corrida_id=corrida.id, sucursal_id=t.id, orden=i, estado="OK",
            estado_pedido="BORRADOR")
        for i, t in enumerate((a, b), start=1)])
    db.add_all([
        _linea(corrida, a, referencias[codigo], pedido, clase, precio=precio)
        for codigo, pedido, clase, precio in LINEAS_A])
    db.add(_linea(corrida, b, referencias["X-B"], "50.00", "C"))
    db.add(ParametroMetodologia(
        id=uuid.uuid4(), clave="modo_tope_presupuesto", valor=modo,
        vigente_desde=DESDE))
    if tope_a is not None:
        db.add(ParametroMetodologia(
            id=uuid.uuid4(), clave="presupuesto_maximo_pedido",
            valor=tope_a, vigente_desde=DESDE, sucursal_id=a.id))
    await db.commit()
    return SimpleNamespace(
        corrida=corrida, a=a, b=b, usuario=usuario, sufijo=sufijo)


@pytest.fixture
async def mundo(fabrica):  # noqa: F811
    async with fabrica() as db:
        datos = await _sembrar(db)
    app.dependency_overrides[get_motored_db] = _sesion_de(fabrica)
    _como("COMPRAS", datos.usuario.id)
    return SimpleNamespace(fabrica=fabrica, datos=datos)


# --- Ayudas -----------------------------------------------------------------


def _url(mundo, tienda="a", sufijo="recorte"):
    datos = mundo.datos
    sid = getattr(datos, tienda).id
    return f"{BASE}/{datos.corrida.id}/sucursales/{sid}/{sufijo}"


async def _ver(mundo, tienda="a"):
    async with _cliente() as cliente:
        return await cliente.get(_url(mundo, tienda))


async def _aplicar(mundo, token, tienda="a"):
    async with _cliente() as cliente:
        return await cliente.post(
            _url(mundo, tienda), json={"token": token})


async def _lineas(mundo, tienda="a"):
    sid = getattr(mundo.datos, tienda).id
    async with mundo.fabrica() as db:
        filas = (await db.execute(
            select(CorridaLinea.id, CorridaLinea.codigo_referencia,
                   CorridaLinea.pedido_final, CorridaLinea.valor_pedido,
                   CorridaLinea.pedido_sugerido)
            .where(CorridaLinea.corrida_id == mundo.datos.corrida.id,
                   CorridaLinea.sucursal_id == sid)
            .order_by(CorridaLinea.codigo_referencia))).all()
    sufijo = f"-{mundo.datos.sufijo}"
    return {
        f.codigo_referencia.removesuffix(sufijo): (
            f.pedido_final, f.valor_pedido, f.pedido_sugerido, f.id)
        for f in filas}


async def _historial(mundo):
    async with mundo.fabrica() as db:
        filas = (await db.execute(
            select(CorridaLineaHistorial)
            .where(CorridaLineaHistorial.corrida_id == mundo.datos.corrida.id)
            .order_by(CorridaLineaHistorial.id))).scalars().all()
    return filas


async def _eventos(mundo):
    async with mundo.fabrica() as db:
        return (await db.execute(
            select(PedidoEvento.sucursal_id, PedidoEvento.evento,
                   PedidoEvento.detalle)
            .where(PedidoEvento.corrida_id == mundo.datos.corrida.id)
            .order_by(PedidoEvento.id))).all()


async def _poner(mundo, **campos):
    async with mundo.fabrica() as db:
        corrida = await db.get(Corrida, mundo.datos.corrida.id)
        for nombre, valor in campos.items():
            setattr(corrida, nombre, valor)
        await db.commit()


async def _estado_tienda(mundo, estado, tienda="a"):
    sid = getattr(mundo.datos, tienda).id
    async with mundo.fabrica() as db:
        fila = await db.get(CorridaSucursal, (mundo.datos.corrida.id, sid))
        fila.estado_pedido = estado
        await db.commit()


# --- La propuesta (TP-08..TP-13) ---------------------------------------------


async def test_the_preview_proposes_the_cut_on_real_data_tp_09(mundo):
    respuesta = await _ver(mundo)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["activo"] is True and cuerpo["modo_activo"] is True
    assert cuerpo["tope"] == "9000"
    assert cuerpo["valor_actual"] == "12000.00"
    assert cuerpo["exceso"] == "3000.00"
    assert cuerpo["valor_final"] == "9000.00"
    assert cuerpo["exceso_residual"] == "0.00"
    assert cuerpo["lineas_sin_precio"] == 1
    assert [a["codigo"] for a in cuerpo["advertencias"]] == ["A-CORRIDA-121"]
    [corte] = cuerpo["recortes"]
    assert (corte["codigo"], corte["clase_abc"]) == (
        f"C-1-{mundo.datos.sufijo}", "C")
    assert (corte["pedido_actual"], corte["pedido_propuesto"]) == (
        "50.00", "20.00")
    assert corte["empaques_recortados"] == "3.00"
    assert corte["valor_recortado"] == "3000.00"
    assert len(cuerpo["token"]) == 64


async def test_repeated_previews_change_nothing_and_agree_tp_13_tp_23(mundo):
    antes = await _lineas(mundo)

    uno = (await _ver(mundo)).json()
    otro = (await _ver(mundo)).json()

    assert uno == otro
    assert await _lineas(mundo) == antes
    assert await _historial(mundo) == []


async def test_a_tienda_under_its_cap_has_an_empty_proposal_tp_08(mundo):
    await _poner_tope(mundo, "20000")

    cuerpo = (await _ver(mundo)).json()

    assert cuerpo["activo"] is True and cuerpo["exceso"] == "0.00"
    assert cuerpo["recortes"] == []


async def _poner_tope(mundo, valor):
    async with mundo.fabrica() as db:
        db.add(ParametroMetodologia(
            id=uuid.uuid4(), clave="presupuesto_maximo_pedido", valor=valor,
            vigente_desde=datetime.date(2026, 2, 1),
            sucursal_id=mundo.datos.a.id))
        await db.commit()


async def test_a_tienda_without_cap_has_no_proposal_tp_11(mundo):
    cuerpo = (await _ver(mundo, "b")).json()

    assert cuerpo["activo"] is False
    assert cuerpo["motivo_inactivo"] == "SIN_TOPE"
    assert cuerpo["recortes"] == [] and cuerpo["token"] is None


async def test_a_closed_tienda_has_no_proposal_tp_14b(mundo):
    await _estado_tienda(mundo, "CERRADO")

    cuerpo = (await _ver(mundo)).json()

    assert cuerpo["activo"] is False
    assert cuerpo["motivo_inactivo"] == "NO_BORRADOR"


async def test_a_scenario_has_no_proposal_and_042_on_apply(mundo):
    await _poner(mundo, es_escenario=True)

    ver = (await _ver(mundo)).json()
    aplicar = await _aplicar(mundo, "x")

    assert ver["activo"] is False and ver["motivo_inactivo"] == "ESCENARIO"
    assert aplicar.status_code == 409
    assert aplicar.json()["detail"]["code"] == "E-CORRIDA-042"
    assert "recortar" in aplicar.json()["detail"]["message"]


async def test_the_summary_reads_every_tienda_with_pedido_tp_09(mundo):
    async with _cliente() as cliente:
        respuesta = await cliente.get(
            f"{BASE}/{mundo.datos.corrida.id}/topes")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["activo"] is True
    filas = {f["sucursal_id"]: f for f in cuerpo["tiendas"]}
    a = filas[str(mundo.datos.a.id)]
    b = filas[str(mundo.datos.b.id)]
    assert (a["tope"], a["valor_a_pedir"], a["exceso"]) == (
        "9000", "12000.00", "3000.00")
    assert a["lineas_sin_precio"] == 1 and a["estado_pedido"] == "BORRADOR"
    assert (b["tope"], b["valor_a_pedir"], b["exceso"]) == (
        None, "5000.00", None)
    assert b["lineas_sin_precio"] == 0


async def test_the_summary_is_inactive_with_the_mode_off_tp_10(mundo):
    async with mundo.fabrica() as db:
        db.add(ParametroMetodologia(
            id=uuid.uuid4(), clave="modo_tope_presupuesto", valor=False,
            vigente_desde=datetime.date(2026, 2, 1)))
        await db.commit()

    async with _cliente() as cliente:
        cuerpo = (await cliente.get(
            f"{BASE}/{mundo.datos.corrida.id}/topes")).json()

    assert cuerpo["activo"] is False and cuerpo["tiendas"] == []
    modo = (await _ver(mundo)).json()
    assert modo["motivo_inactivo"] == "MODO_OFF"
    assert modo["modo_activo"] is False


async def test_the_summary_follows_a_manual_edit_tp_14(mundo):
    lineas = await _lineas(mundo)
    async with _cliente() as cliente:
        await cliente.patch(
            f"{BASE}/{mundo.datos.corrida.id}/lineas/{lineas['C-2'][3]}",
            json={"pedido_final": 60})
        cuerpo = (await cliente.get(
            f"{BASE}/{mundo.datos.corrida.id}/topes")).json()

    a = next(f for f in cuerpo["tiendas"]
             if f["sucursal_id"] == str(mundo.datos.a.id))
    assert (a["valor_a_pedir"], a["exceso"]) == ("15000.00", "6000.00")


# --- Aplicar (TP-24..TP-33) --------------------------------------------------


async def test_apply_cuts_only_the_proposed_line_and_logs_it_tp_24(mundo):
    token = (await _ver(mundo)).json()["token"]
    antes = await _lineas(mundo)

    respuesta = await _aplicar(mundo, token)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["lineas_recortadas"] == 1
    assert (cuerpo["valor_liberado"], cuerpo["valor_final"]) == (
        "3000.00", "9000.00")
    assert cuerpo["totales_tienda"]["valor_a_pedir"] == "9000.00"
    despues = await _lineas(mundo)
    assert despues["C-1"][:3] == (D("20.00"), D("2000.00"), D("50.00"))
    for codigo in ("C-2", "B-1", "A-1", "D-1", "SP-1", "SP-0"):
        assert despues[codigo] == antes[codigo], codigo
    [fila] = await _historial(mundo)
    assert (fila.linea_id, fila.motivo, fila.campo) == (
        despues["C-1"][3], "RECORTE_PRESUPUESTO", "pedido_final")
    assert (fila.valor_anterior, fila.valor_nuevo) == (D("50.00"), D("20.00"))
    assert fila.usuario_id == mundo.datos.usuario.id
    assert fila.sucursal_id == mundo.datos.a.id
    assert fila.detalle["tope"] == "9000" and fila.detalle["token"] == token
    assert uuid.UUID(fila.detalle["parametro_id"])


async def test_the_other_tienda_is_untouched_by_an_apply_tp_33(mundo):
    antes = await _lineas(mundo, "b")
    token = (await _ver(mundo)).json()["token"]

    await _aplicar(mundo, token)

    assert await _lineas(mundo, "b") == antes


async def test_the_edited_lines_show_the_recorte_motive_in_the_line_read(
        mundo):
    token = (await _ver(mundo)).json()["token"]
    await _aplicar(mundo, token)

    async with _cliente() as cliente:
        pagina = (await cliente.get(
            f"{BASE}/{mundo.datos.corrida.id}/lineas",
            params={"sucursal_id": str(mundo.datos.a.id),
                    "solo_editadas": "true"})).json()

    [linea] = pagina["items"]
    assert linea["motivo_edicion"] == "RECORTE_PRESUPUESTO"
    assert linea["editada"] is True and linea["editado_por"] == "Compras"


async def test_after_the_apply_the_proposal_is_empty_and_apply_is_060_tp_31(
        mundo):
    token = (await _ver(mundo)).json()["token"]
    await _aplicar(mundo, token)

    de_nuevo = await _aplicar(mundo, token)
    ver = (await _ver(mundo)).json()

    assert de_nuevo.status_code == 409
    assert de_nuevo.json()["detail"]["code"] == "E-CORRIDA-060"
    assert ver["activo"] is True and ver["recortes"] == []
    assert len(await _historial(mundo)) == 1


async def test_a_stale_token_after_a_manual_edit_is_060_with_the_fresh_one(
        mundo):
    token = (await _ver(mundo)).json()["token"]
    lineas = await _lineas(mundo)
    async with _cliente() as cliente:
        editada = await cliente.patch(
            f"{BASE}/{mundo.datos.corrida.id}/lineas/{lineas['C-2'][3]}",
            json={"pedido_final": 60})
    assert editada.status_code == 200, editada.text

    respuesta = await _aplicar(mundo, token)

    assert respuesta.status_code == 409
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "E-CORRIDA-060"
    fresca = detalle["detalle"]["propuesta"]
    assert fresca["token"] != token and fresca["exceso"] == "6000.00"
    assert (await _lineas(mundo))["C-1"][0] == D("50.00")
    assert [h.motivo for h in await _historial(mundo)] == ["MANUAL"]


async def test_the_fresh_proposal_of_a_060_can_be_applied_tp_25(mundo):
    token = (await _ver(mundo)).json()["token"]
    lineas = await _lineas(mundo)
    async with _cliente() as cliente:
        await cliente.patch(
            f"{BASE}/{mundo.datos.corrida.id}/lineas/{lineas['C-2'][3]}",
            json={"pedido_final": 60})
    rechazo = await _aplicar(mundo, token)
    fresca = rechazo.json()["detail"]["detalle"]["propuesta"]["token"]

    ok = await _aplicar(mundo, fresca)

    assert ok.status_code == 200, ok.text
    assert ok.json()["valor_final"] == "9000.00"


async def test_a_manual_edit_after_the_apply_still_works_tp_29(mundo):
    token = (await _ver(mundo)).json()["token"]
    await _aplicar(mundo, token)
    lineas = await _lineas(mundo)

    async with _cliente() as cliente:
        editada = await cliente.patch(
            f"{BASE}/{mundo.datos.corrida.id}/lineas/{lineas['C-1'][3]}",
            json={"pedido_final": 40})
    ver = (await _ver(mundo)).json()

    assert editada.status_code == 200, editada.text
    assert [h.motivo for h in await _historial(mundo)] == [
        "RECORTE_PRESUPUESTO", "MANUAL"]
    assert ver["activo"] is True and ver["exceso"] == "2000.00"
    assert len(ver["recortes"]) == 1


async def test_a_very_low_cap_cuts_c_then_b_never_a_or_d_tp_16_tp_17(mundo):
    await _poner_tope(mundo, "1000")
    ver = (await _ver(mundo)).json()

    respuesta = await _aplicar(mundo, ver["token"])

    assert respuesta.status_code == 200, respuesta.text
    despues = await _lineas(mundo)
    assert despues["C-1"][0] == D("0.00") and despues["C-2"][0] == D("0.00")
    assert despues["B-1"][0] == D("0.00")
    assert despues["A-1"][0] == D("10.00") and despues["D-1"][0] == D("10.00")
    cuerpo = respuesta.json()
    assert cuerpo["valor_final"] == "2000.00"
    assert cuerpo["exceso_residual"] == "1000.00"
    assert {h.linea_id for h in await _historial(mundo)} == {
        despues[c][3] for c in ("C-1", "C-2", "B-1")}


async def test_the_mode_off_and_a_missing_cap_are_058_and_059_tp_26(mundo):
    sin_tope = await _aplicar(mundo, "x", "b")
    async with mundo.fabrica() as db:
        db.add(ParametroMetodologia(
            id=uuid.uuid4(), clave="modo_tope_presupuesto", valor=False,
            vigente_desde=datetime.date(2026, 2, 1)))
        await db.commit()

    apagado = await _aplicar(mundo, "x")

    assert sin_tope.json()["detail"]["code"] == "E-CORRIDA-059"
    assert apagado.json()["detail"]["code"] == "E-CORRIDA-058"
    assert sin_tope.status_code == apagado.status_code == 409
    assert await _historial(mundo) == []


@pytest.mark.parametrize("estado", ["CERRADO", "ENVIADO"])
async def test_a_closed_or_sent_pedido_is_061_tp_27(mundo, estado):
    await _estado_tienda(mundo, estado)

    respuesta = await _aplicar(mundo, "x")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-061"
    assert await _historial(mundo) == []


async def test_a_corrida_not_calculated_is_040_and_an_unknown_tienda_404(
        mundo):
    await _poner(mundo, estado="PENDIENTE")

    pendiente = await _aplicar(mundo, "x")
    async with _cliente() as cliente:
        sin_tienda = await cliente.post(
            f"{BASE}/{mundo.datos.corrida.id}/sucursales/{uuid.uuid4()}"
            "/recorte", json={"token": "x"})

    assert pendiente.json()["detail"]["code"] == "E-CORRIDA-040"
    assert sin_tienda.status_code == 404


async def test_a_tienda_without_pedido_is_065(mundo):
    async with mundo.fabrica() as db:
        fila = await db.get(
            CorridaSucursal, (mundo.datos.corrida.id, mundo.datos.a.id))
        fila.estado, fila.estado_pedido = "FALLIDA", None
        await db.commit()

    respuesta = await _aplicar(mundo, "x")

    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-065"


async def test_an_apply_is_atomic_when_the_history_cannot_be_written_tp_30(
        mundo):
    token = (await _ver(mundo)).json()["token"]
    antes = await _lineas(mundo)

    async with mundo.fabrica() as db:
        with pytest.raises(Exception) as error:
            # Un usuario que no existe rompe la FK del historial DESPUÉS del
            # UPDATE de la línea: todo debe deshacerse.
            await tope.aplicar(
                db, mundo.datos.corrida.id, mundo.datos.a.id, token,
                uuid.uuid4())
        await db.rollback()

    assert "usuario" in str(error.value).lower()
    assert await _lineas(mundo) == antes
    assert await _historial(mundo) == []


# --- El tope congelado al cerrar (ADR-6) -------------------------------------


async def test_closing_freezes_the_cap_in_force_in_the_event(mundo):
    async with _cliente() as cliente:
        a = await cliente.post(_url(mundo, "a", "cerrar"))
        b = await cliente.post(_url(mundo, "b", "cerrar"))

    assert a.status_code == b.status_code == 200, (a.text, b.text)
    eventos = {sid: detalle for sid, _, detalle in await _eventos(mundo)}
    assert eventos[mundo.datos.a.id]["tope"] == "9000"
    assert uuid.UUID(eventos[mundo.datos.a.id]["parametro_id"])
    assert eventos[mundo.datos.b.id] is None


async def test_closing_with_the_mode_off_freezes_no_cap(mundo):
    async with mundo.fabrica() as db:
        db.add(ParametroMetodologia(
            id=uuid.uuid4(), clave="modo_tope_presupuesto", valor=False,
            vigente_desde=datetime.date(2026, 2, 1)))
        await db.commit()

    async with _cliente() as cliente:
        await cliente.post(_url(mundo, "a", "cerrar"))

    assert [d for _, _, d in await _eventos(mundo)] == [None]
    async with mundo.fabrica() as db:
        sin_detalle = (await db.execute(
            select(func.count()).select_from(PedidoEvento).where(
                PedidoEvento.corrida_id == mundo.datos.corrida.id,
                PedidoEvento.detalle.is_(None)))).scalar_one()
    assert sin_detalle == 1  # NULL de SQL, no el JSON null


async def test_the_frozen_cap_survives_a_later_cap_change(mundo):
    async with _cliente() as cliente:
        await cliente.post(_url(mundo, "a", "cerrar"))
    await _poner_tope(mundo, "1")

    [(_, _, detalle)] = await _eventos(mundo)

    assert detalle["tope"] == "9000"
