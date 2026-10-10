"""
Inventory counts, pair readings against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`, database migrated to head;
odd/motored-conteos-inventario, WU8; design §6.2, §7, ADR-5).

Same savepoint-mode harness as `test_publico_conteos_pg.py`: each route's
`commit()` is visible to the next request and nothing survives the test.
Proves the parts a fake session cannot: `ON CONFLICT (id) DO NOTHING`
across batches, the case-insensitive code lookup, the per-location
summary and voiding, and a pair-made location seen by the leader.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from app.motored.models.conteo_lectura import ConteoLectura
from app.motored.models.referencia import Referencia
from app.motored.models.ubicacion_inventario import UbicacionInventario
from app.motored.services.conteos import catalogo
from tests.motored.pg_real import test_publico_conteos_pg as publico
from tests.motored.pg_real.test_conteos_api_pg import (  # noqa: F401
    BASE, llamar, pytestmark,
)

UTC = datetime.timezone.utc

# The shared harness and the running conteo, as fixtures here.
fabrica = publico.fabrica
_app_lista = publico._app_lista
abierto = publico.abierto


@pytest.fixture(autouse=True)
def _sin_cache():
    catalogo.limpiar_cache()
    yield
    catalogo.limpiar_cache()


@pytest.fixture
async def pareja(abierto, fabrica):
    """A joined pair standing in location A3, plus two referencias."""
    r = await publico._unirse(abierto)
    assert r.status_code == 201, r.text
    abierto.token = r.json()["sesion_token"]
    abierto.sesion_id = uuid.UUID(r.json()["sesion_id"])
    async with fabrica() as db:
        abierto.ref_a = Referencia(
            id=uuid.uuid4(), codigo=f"Pk-{uuid.uuid4().hex[:8]}",
            nombre="Pastilla", proveedor_id=abierto.proveedor.id,
            unidad_empaque=1)
        abierto.ref_b = Referencia(
            id=uuid.uuid4(), codigo=f"FT-{uuid.uuid4().hex[:8].upper()}",
            nombre="Filtro", proveedor_id=abierto.proveedor.id,
            unidad_empaque=1)
        db.add_all([abierto.ref_a, abierto.ref_b])
        await db.commit()
    assert (await _ubicar(abierto, "UBI-A3")).status_code == 200
    return abierto


async def _pedir(mundo, metodo, ruta, **kwargs):
    return await llamar(
        metodo, f"{publico.PUBLICO}/{mundo.conteo.enlace_slug}{ruta}",
        headers={"Authorization": f"Bearer {mundo.token}",
                 **kwargs.pop("headers", {})}, **kwargs)


async def _ubicar(mundo, codigo, nombre=None):
    return await _pedir(
        mundo, "PUT", "/ubicacion",
        json={"codigo": codigo, "nombre": nombre})


def _item(codigo, cantidad="1", **extra):
    item = {"id": str(uuid.uuid4()), "codigo_leido": codigo,
            "cantidad": cantidad, "metodo": "ESCANER",
            "leida_en": datetime.datetime.now(UTC).isoformat()}
    item.update(extra)
    return item


async def _enviar(mundo, items):
    r = await _pedir(mundo, "POST", "/lecturas", json={"lecturas": items})
    assert r.status_code == 200, r.text
    return r.json()


async def _filas(fabrica, mundo):
    async with fabrica() as db:
        return (await db.scalars(select(ConteoLectura).where(
            ConteoLectura.conteo_id == mundo.conteo.id).order_by(
            ConteoLectura.seq))).all()


async def _resumen(mundo):
    r = await _pedir(mundo, "GET", "/lecturas/recientes")
    assert r.status_code == 200, r.text
    return {f["codigo"]: Decimal(f["cantidad"])
            for f in r.json()["resumen_ubicacion"]}


async def test_duplicate_ids_across_batches_are_stored_once(
        pareja, fabrica):
    a, b, c = (_item(pareja.ref_a.codigo) for _ in range(3))

    primera = await _enviar(pareja, [a, b])
    segunda = await _enviar(pareja, [b, c])

    assert primera["aceptadas"] == [a["id"], b["id"]]
    assert segunda["aceptadas"] == [c["id"]]
    assert segunda["duplicadas"] == [b["id"]]
    assert len(await _filas(fabrica, pareja)) == 3


async def test_a_resend_after_a_network_failure_counts_once(
        pareja, fabrica):
    lote = [_item(pareja.ref_a.codigo, "2"), _item(pareja.ref_b.codigo)]

    await _enviar(pareja, lote)
    reenvio = await _enviar(pareja, lote)

    assert reenvio["aceptadas"] == []
    assert reenvio["duplicadas"] == [i["id"] for i in lote]
    filas = await _filas(fabrica, pareja)
    assert sum(f.cantidad for f in filas) == Decimal("3")
    assert await _resumen(pareja) == {
        pareja.ref_a.codigo.upper(): Decimal("2"),
        pareja.ref_b.codigo: Decimal("1")}


async def test_codes_match_ignoring_case_and_spaces(pareja, fabrica):
    mixto = pareja.ref_a.codigo
    resultado = await _enviar(pareja, [
        _item(f"  {mixto.lower()} "), _item(pareja.ref_b.codigo.lower())])

    assert len(resultado["aceptadas"]) == 2
    assert resultado["referencias"] == {
        mixto.upper(): "Pastilla", pareja.ref_b.codigo: "Filtro"}
    filas = await _filas(fabrica, pareja)
    assert [(f.referencia_id, f.codigo_leido, f.ronda, f.reconteo_id)
            for f in filas] == [
        (pareja.ref_a.id, mixto.upper(), 1, None),
        (pareja.ref_b.id, pareja.ref_b.codigo, 1, None)]
    assert {f.ubicacion_id for f in filas} == {pareja.ubicacion.id}


async def test_unknown_codes_are_reported_and_stored_only_if_forced(
        pareja, fabrica):
    suelta = _item("NO-EXISTE-1")

    resultado = await _enviar(pareja, [suelta])

    assert resultado["desconocidos"] == [
        {"id": suelta["id"], "codigo": "NO-EXISTE-1"}]
    assert await _filas(fabrica, pareja) == []
    forzada = dict(suelta, forzar_desconocido=True)
    assert (await _enviar(pareja, [forzada]))["aceptadas"] == [
        suelta["id"]]
    filas = await _filas(fabrica, pareja)
    assert [(f.codigo_leido, f.referencia_id) for f in filas] == [
        ("NO-EXISTE-1", None)]


async def test_the_location_summary_sums_per_location(pareja):
    ref_a = pareja.ref_a.codigo
    await _enviar(pareja, [
        _item(ref_a), _item(ref_a, "3"), _item(pareja.ref_b.codigo)])
    assert (await _ubicar(pareja, "b2", "Bodega 2")).json()["creada"]
    await _enviar(pareja, [_item(ref_a)])

    assert await _resumen(pareja) == {ref_a.upper(): Decimal("1")}
    await _ubicar(pareja, "A3")
    assert await _resumen(pareja) == {
        ref_a.upper(): Decimal("4"), pareja.ref_b.codigo: Decimal("1")}


async def test_voided_readings_leave_the_summary(pareja, fabrica):
    uno, dos = _item(pareja.ref_a.codigo, "5"), _item(pareja.ref_a.codigo)
    await _enviar(pareja, [uno, dos])

    r = await _pedir(pareja, "POST", f"/lecturas/{uno['id']}/anular")

    assert r.status_code == 200, r.text
    assert await _resumen(pareja) == {
        pareja.ref_a.codigo.upper(): Decimal("1")}
    recientes = await _pedir(pareja, "GET", "/lecturas/recientes")
    anuladas = {f["id"]: f["anulada_en"] is not None
                for f in recientes.json()["lecturas"]}
    assert anuladas == {uno["id"]: True, dos["id"]: False}
    assert recientes.json()["lecturas"][0]["id"] == dos["id"]


async def test_a_pair_cannot_void_another_pairs_reading(pareja, fabrica):
    lectura = _item(pareja.ref_a.codigo)
    await _enviar(pareja, [lectura])
    otra = await publico._unirse(pareja)
    pareja.token = otra.json()["sesion_token"]

    r = await _pedir(pareja, "POST", f"/lecturas/{lectura['id']}/anular")

    assert r.status_code == 404, r.text
    assert (await _filas(fabrica, pareja))[0].anulada_en is None


async def test_a_reading_needs_a_location_first(abierto, fabrica):
    abierto.token = (await publico._unirse(abierto)).json()["sesion_token"]

    r = await _pedir(abierto, "POST", "/lecturas",
                     json={"lecturas": [_item("X")]})

    assert r.status_code == 409
    assert r.json()["detail"]["mensaje"] == "Primero indique la ubicación."


async def test_a_location_made_by_a_pair_is_visible_to_the_leader(
        pareja, fabrica):
    r = await _ubicar(pareja, " pasillo  9 ")

    assert r.status_code == 200, r.text
    lider = ("LIDER_INVENTARIOS", pareja.lider.id)
    r = await llamar(
        "GET", f"{BASE}/{pareja.conteo.id}/ubicaciones", lider)
    assert r.status_code == 200, r.text
    assert {(u["codigo"], u["origen"]) for u in r.json()} == {
        ("A3", "LIDER"), ("PASILLO 9", "PAREJA")}
    pareja_ve = await _pedir(pareja, "GET", "/ubicaciones")
    assert "PASILLO 9" in {u["codigo"] for u in pareja_ve.json()}


async def test_the_leader_prepares_renames_and_deactivates(
        pareja, fabrica):
    lider = ("LIDER_INVENTARIOS", pareja.lider.id)
    ruta = f"{BASE}/{pareja.conteo.id}/ubicaciones"

    creada = await llamar("POST", ruta, lider,
                          json={"codigo": "UBI-v1", "nombre": "Vitrina"})
    assert creada.status_code == 201, creada.text
    repetida = await llamar("POST", ruta, lider, json={"codigo": "v1"})
    assert repetida.status_code == 409
    r = await llamar(
        "PATCH", f"{ruta}/{creada.json()['id']}", lider,
        json={"nombre": "Vitrina 1", "activa": False})
    assert r.json()["nombre"] == "Vitrina 1" and not r.json()["activa"]

    assert (await _ubicar(pareja, "V1")).status_code == 409
    async with fabrica() as db:
        fila = await db.get(UbicacionInventario, uuid.UUID(
            creada.json()["id"]))
    assert (fila.origen, fila.created_by) == ("LIDER", pareja.lider.id)


async def test_a_location_label_cannot_shadow_a_referencia(
        pareja, fabrica):
    async with fabrica() as db:
        db.add(Referencia(
            id=uuid.uuid4(), codigo="ubi-zona7", nombre="raro",
            proveedor_id=pareja.proveedor.id, unidad_empaque=1))
        await db.commit()

    r = await _ubicar(pareja, "zona7")

    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UBICACION_CHOCA_REFERENCIA"
    async with fabrica() as db:
        creadas = await db.scalar(select(func.count()).where(
            UbicacionInventario.codigo == "ZONA7"))
    assert creadas == 0


async def test_the_catalogue_has_every_referencia_and_a_304(
        pareja, fabrica):
    r = await _pedir(pareja, "GET", "/catalogo")

    assert r.status_code == 200, r.text
    codigos = dict(map(tuple, r.json()["referencias"]))
    assert codigos[pareja.ref_a.codigo.upper()] == "Pastilla"
    assert codigos[pareja.ref_b.codigo] == "Filtro"
    async with fabrica() as db:
        total = await db.scalar(select(func.count(func.distinct(
            func.upper(func.btrim(Referencia.codigo))))))
    assert len(codigos) == total
    r2 = await _pedir(pareja, "GET", "/catalogo",
                      headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304
    assert r2.content == b""


async def _referencias(fabrica, mundo, *codigos):
    async with fabrica() as db:
        refs = [Referencia(
            id=uuid.uuid4(), codigo=c, nombre=f"Ref {c}",
            proveedor_id=mundo.proveedor.id, unidad_empaque=1)
            for c in codigos]
        db.add_all(refs)
        await db.commit()
    return refs


async def test_a_hyphen_less_scan_counts_under_the_master_code(
        pareja, fabrica):
    raiz = uuid.uuid4().hex[:8].upper()
    (maestra,) = await _referencias(fabrica, pareja, f"{raiz}-12000S")

    resultado = await _enviar(pareja, [
        _item(f"{raiz}12000s"), _item(f" {raiz} 12000S ")])

    assert len(resultado["aceptadas"]) == 2
    assert resultado["desconocidos"] == []
    filas = await _filas(fabrica, pareja)
    assert {(f.referencia_id, f.codigo_leido) for f in filas} == {
        (maestra.id, f"{raiz}-12000S")}
    assert await _resumen(pareja) == {f"{raiz}-12000S": Decimal("2")}


async def test_an_ambiguous_key_is_unknown_but_an_exact_code_counts(
        pareja, fabrica):
    raiz = uuid.uuid4().hex[:8].upper()
    _, punto = await _referencias(
        fabrica, pareja, f"{raiz}-7", f"{raiz}.7")
    ambigua = _item(f"{raiz}7")

    resultado = await _enviar(pareja, [ambigua, _item(f"{raiz}.7")])

    assert resultado["desconocidos"] == [
        {"id": ambigua["id"], "codigo": f"{raiz}7"}]
    filas = await _filas(fabrica, pareja)
    assert [(f.referencia_id, f.codigo_leido) for f in filas] == [
        (punto.id, f"{raiz}.7")]


async def test_the_key_lookup_uses_the_functional_index(fabrica):
    async with fabrica() as db:
        indices = (await db.execute(text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'ix_referencia_codigo_clave'"))).scalars()
        (definicion,) = list(indices)
    assert "regexp_replace(upper((codigo)::text)" in definicion
