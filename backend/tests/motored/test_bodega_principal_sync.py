"""
Sucursales upload: the `bodega` record of each store's PRINCIPAL bodega.

A store keeps its principal bodega code only as text
(`sucursal.bodega_principal`). Ingest resolves a bodega code by following
`bodega.bodega_principal` up to the root record and taking that root's
`sucursal_id` (`resolucion._resolver_sucursal_de_bodega`). So after the
upload, for every store of the file with a principal code P:

- the record of P exists, belongs to the store and is the root
  (`bodega_principal` NULL), created when missing;
- every record of the store other than P chains to P;
- a record of ANOTHER store (or of none) that still chains to P has its
  chain cut (`bodega_principal` NULL): it resolves by its own
  `sucursal_id`, never through P to the wrong store.

The result does not depend on the order of the stores in the file.
"""
import uuid

import pytest

from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.services import bodegas_secundarias
from app.motored.services.ingesta.resolucion import (
    _resolver_sucursal_de_bodega,
)
from tests.motored.conftest import FakeAsyncSession

USER_ID = uuid.uuid4()


def _bodega(codigo, sucursal_id=None, principal=None):
    return Bodega(
        id=uuid.uuid4(), codigo=codigo, sucursal_id=sucursal_id,
        bodega_principal=principal, activa=True,
    )


def _sucursal(nombre, principal):
    return Sucursal(
        id=uuid.uuid4(), nombre=nombre, bodega_principal=principal,
        activa=True,
    )


def _mapa(db, bodegas):
    """codigo -> (sucursal_id, bodega_principal) of every record the test
    knows plus the ones the sync created: what `construir_cache` reads."""
    todas = list(bodegas) + db.added_of_type(Bodega)
    return {b.codigo: (b.sucursal_id, b.bodega_principal) for b in todas}


async def _sincronizar(sucursales, bodegas):
    db = FakeAsyncSession(execute_queue=[list(bodegas)])
    await bodegas_secundarias.sincronizar_principales(
        db, sucursales, USER_ID
    )
    return db


@pytest.mark.parametrize("orden", [1, -1])
async def test_principal_moved_to_a_new_store_resolves_to_it(orden):
    a16 = _sucursal("A16", "BA161")
    a07 = _sucursal("A07", "BA071")
    ba071 = _bodega("BA071", a16.id, None)  # stale: was A16's principal
    ba161 = _bodega("BA161", a16.id, "BA071")  # stale chain to BA071

    db = await _sincronizar([a16, a07][::orden], [ba071, ba161])

    mapa = _mapa(db, [ba071, ba161])
    assert _resolver_sucursal_de_bodega("BA071", mapa) == a07.id
    assert (ba071.sucursal_id, ba071.bodega_principal) == (a07.id, None)


@pytest.mark.parametrize("orden", [1, -1])
async def test_secondary_promoted_to_principal_loses_its_old_chain(orden):
    a16 = _sucursal("A16", "BA161")
    a07 = _sucursal("A07", "BA071")
    ba071 = _bodega("BA071", a16.id, None)
    ba161 = _bodega("BA161", a16.id, "BA071")

    db = await _sincronizar([a16, a07][::orden], [ba071, ba161])

    assert (ba161.sucursal_id, ba161.bodega_principal) == (a16.id, None)
    assert _resolver_sucursal_de_bodega("BA161", _mapa(db, [ba161])) == (
        a16.id
    )


@pytest.mark.parametrize("orden", [1, -1])
async def test_unlinked_secondary_promoted_to_principal_gets_its_store(
    orden,
):
    c11 = _sucursal("C11", "BC111")
    a11 = _sucursal("A11", "BA111")
    bc111 = _bodega("BC111")  # the unlink step left it NULL

    db = await _sincronizar([c11, a11][::orden], [bc111])

    assert (bc111.sucursal_id, bc111.bodega_principal) == (c11.id, None)
    assert _resolver_sucursal_de_bodega("BC111", _mapa(db, [bc111])) == (
        c11.id
    )


@pytest.mark.parametrize("orden", [1, -1])
async def test_secondary_of_a_new_store_chains_to_a_resolving_principal(
    orden,
):
    d01 = _sucursal("D01", "BD011")
    a01 = _sucursal("A01", "BA011")
    bd011 = _bodega("BD011")  # NULL principal record
    mcd01 = _bodega("MCD01", d01.id, "BD011")

    db = await _sincronizar([d01, a01][::orden], [bd011, mcd01])

    mapa = _mapa(db, [bd011, mcd01])
    assert _resolver_sucursal_de_bodega("MCD01", mapa) == d01.id


async def test_missing_principal_record_is_created_as_the_root():
    a07 = _sucursal("A07", "BA071")

    db = await _sincronizar([a07], [])

    creadas = db.added_of_type(Bodega)
    assert [(b.codigo, b.sucursal_id, b.bodega_principal)
            for b in creadas] == [("BA071", a07.id, None)]


async def test_every_secondary_of_the_store_points_to_its_principal():
    a16 = _sucursal("A16", "BA161")
    ba161 = _bodega("BA161", a16.id, None)
    vieja = _bodega("BA166", a16.id, "BA071")

    await _sincronizar([a16], [ba161, vieja])

    assert (vieja.sucursal_id, vieja.bodega_principal) == (a16.id, "BA161")


async def test_record_of_another_store_chaining_to_the_principal_is_cut():
    a07 = _sucursal("A07", "BA071")
    otra = uuid.uuid4()  # a store absent from the file
    ba071 = _bodega("BA071", a07.id, None)
    ajena = _bodega("BX001", otra, "BA071")
    huerfana = _bodega("BX002", None, "BA071")

    await _sincronizar([a07], [ba071, ajena, huerfana])

    assert (ajena.sucursal_id, ajena.bodega_principal) == (otra, None)
    assert (huerfana.sucursal_id, huerfana.bodega_principal) == (None, None)


async def test_records_already_in_sync_are_left_untouched():
    a16 = _sucursal("A16", "BA161")
    ba161 = _bodega("BA161", a16.id, None)
    sec = _bodega("BA166", a16.id, "BA161")

    db = await _sincronizar([a16], [ba161, sec])

    assert db.added == []


async def test_store_without_principal_makes_no_query():
    db = FakeAsyncSession(execute_queue=[])

    await bodegas_secundarias.sincronizar_principales(
        db, [_sucursal("A16", None), _sucursal("A07", "  ")], USER_ID
    )

    assert db.executed_statements == []


async def test_the_upload_syncs_the_principal_record():
    cali = _sucursal("CALI", "BA061")
    # C.O. | principal owner: sucursales, bodegas | upsert | principal
    # sync: bodegas
    db = FakeAsyncSession(execute_queue=[[(cali.id, "CALI", "E01")],
                                         [], [], [cali], []])

    resultado = await _resolver_y_procesar_carga(
        db, "sucursal",
        [{"nombre": "CALI", "codigo_co": "E01", "bodega_principal": "BA061"}],
        USER_ID,
    )

    assert resultado.ok is True
    creadas = db.added_of_type(Bodega)
    assert [(b.codigo, b.sucursal_id, b.bodega_principal)
            for b in creadas] == [("BA061", cali.id, None)]


async def test_a_blank_principal_cell_leaves_the_records_alone():
    cali = _sucursal("CALI", "BA061")
    # C.O. | upsert: any extra query would raise
    db = FakeAsyncSession(execute_queue=[[(cali.id, "CALI", "E01")],
                                         [cali]])

    resultado = await _resolver_y_procesar_carga(
        db, "sucursal",
        [{"nombre": "CALI", "codigo_co": "E01", "bodega_principal": ""}],
        USER_ID,
    )

    assert resultado.ok is True
    assert db.added_of_type(Bodega) == []
