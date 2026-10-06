"""
Sucursales form (CRUD): a store's bodegas.

The form edits "Bodega principal" (text) and the list of secondary bodegas
of a store in ONE save. The secondaries follow the same rules as the
Sucursales upload (`bodegas_secundarias`): codes are trimmed and
upper-cased, a code belongs to one store only, a secondary is never
another store's principal, a code dropped from the list is released, and
every write goes through the audited `create_bodega`/`update_bodega`.
Unlike the upload, the form never moves a code owned by another store: it
is rejected naming that store.

After any save that sets the principal or the secondaries, the principal's
own record is synced (`sincronizar_principales`, bug T9), so ingest
resolves every code of the store to it.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.services import bodegas_secundarias
from app.motored.services.auth import MotoredUser
from app.motored.services.ingesta.resolucion import (
    _resolver_sucursal_de_bodega,
)
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

USER_ID = uuid.uuid4()
SUCURSALES_URL = "/api/motored/maestros/sucursales"


def _bodega(codigo, sucursal_id=None, principal=None):
    return Bodega(
        id=uuid.uuid4(), codigo=codigo, sucursal_id=sucursal_id,
        bodega_principal=principal, activa=True,
    )


def _sucursal(nombre="QUILICHAO", principal="BA071", codigo_co="A16"):
    return Sucursal(
        id=uuid.uuid4(), nombre=nombre, bodega_principal=principal,
        codigo_co=codigo_co, activa=True, dias_seguridad=2.5,
    )


def _estado(bodega):
    return bodega.sucursal_id, bodega.bodega_principal


def _creada(db, codigo):
    creadas = [b for b in db.added_of_type(Bodega) if b.codigo == codigo]
    assert len(creadas) == 1, creadas
    return creadas[0]


async def _guardar(sucursal, codigos, queue):
    db = FakeAsyncSession(execute_queue=queue)
    await bodegas_secundarias.guardar_de_sucursal(
        db, sucursal, codigos, USER_ID
    )
    return db


class TestNormalization:
    def test_codes_are_trimmed_upper_cased_and_deduplicated(self):
        assert bodegas_secundarias.normalizar_codigos(
            [" mc001 ", "BA161", "ba161", "", None, "x1, x2"]
        ) == ["MC001", "BA161", "X1", "X2"]

    def test_none_is_an_empty_list(self):
        assert bodegas_secundarias.normalizar_codigos(None) == []

    async def test_the_upload_uses_the_same_normalization(self):
        resueltas, _ = await bodegas_secundarias.resolver_filas(
            FakeAsyncSession(execute_queue=[[], []]),
            [{"nombre": "X", "bodegas_secundarias": " mc001 ,Mc001"}],
        )
        assert resueltas[0][bodegas_secundarias.FILA_CLAVE] == ["MC001"]


class TestAddAndRemove:
    async def test_adds_an_existing_and_a_new_secondary(self):
        tienda = _sucursal()
        ba071 = _bodega("BA071", tienda.id)
        ba161 = _bodega("BA161")
        bodegas = [ba071, ba161]

        db = await _guardar(tienda, [" ba161", "mc001 "], [
            [], [("BA161", None, None)], bodegas, bodegas,
        ])

        assert _estado(ba161) == (tienda.id, "BA071")
        assert _estado(_creada(db, "MC001")) == (tienda.id, "BA071")
        assert _estado(ba071) == (tienda.id, None)

    async def test_a_code_left_out_of_the_list_is_released(self):
        tienda = _sucursal()
        ba071 = _bodega("BA071", tienda.id)
        ba161 = _bodega("BA161", tienda.id, "BA071")
        bodegas = [ba071, ba161]

        # principal owner: sucursales, bodegas | apply | principal sync
        await _guardar(tienda, [], [[], [], bodegas, bodegas])

        assert _estado(ba161) == (None, None)
        assert _estado(ba071) == (tienda.id, None)

    async def test_without_the_list_only_the_principal_is_synced(self):
        tienda = _sucursal(principal="BA161")
        ba071 = _bodega("BA071", tienda.id)
        ba161 = _bodega("BA161", tienda.id, "BA071")

        # principal owner: sucursales, bodegas | principal sync
        await _guardar(tienda, None, [[], [], [ba071, ba161]])

        assert _estado(ba161) == (tienda.id, None)
        assert _estado(ba071) == (tienda.id, "BA161")


class TestSwap:
    async def test_principal_and_secondary_swap_in_one_save(self):
        # The store had principal BA071 and secondary BA161; the form
        # already set principal BA161 and now lists BA071.
        tienda = _sucursal(principal="BA161")
        ba071 = _bodega("BA071", tienda.id)
        ba161 = _bodega("BA161", tienda.id, "BA071")
        bodegas = [ba071, ba161]

        await _guardar(tienda, ["BA071"], [
            [], [("BA071", tienda.id, tienda.nombre)], bodegas, bodegas,
        ])

        assert _estado(ba161) == (tienda.id, None)
        assert _estado(ba071) == (tienda.id, "BA161")
        mapa = {b.codigo: _estado(b) for b in bodegas}
        assert _resolver_sucursal_de_bodega("BA071", mapa) == tienda.id
        assert _resolver_sucursal_de_bodega("BA161", mapa) == tienda.id


class TestRejections:
    async def test_a_code_of_another_store_is_rejected_naming_it(self):
        tienda = _sucursal()
        pasto = uuid.uuid4()

        with pytest.raises(
            bodegas_secundarias.BodegasSecundariasInvalidasError
        ) as exc:
            await _guardar(tienda, ["MC002"], [
                [], [("MC002", pasto, "PASTO")],
            ])

        assert "'MC002'" in str(exc.value)
        assert "'PASTO'" in str(exc.value)
        assert "carga masiva" in str(exc.value)

    async def test_another_stores_principal_is_rejected(self):
        tienda = _sucursal()

        with pytest.raises(
            bodegas_secundarias.BodegasSecundariasInvalidasError
        ) as exc:
            await _guardar(tienda, ["BP001"], [
                [("PASTO", "BP001")], [],
            ])

        assert "'BP001'" in str(exc.value)
        assert "principal de la sucursal 'PASTO'" in str(exc.value)

    async def test_its_own_principal_cannot_be_a_secondary(self):
        tienda = _sucursal()

        with pytest.raises(
            bodegas_secundarias.BodegasSecundariasInvalidasError,
            match="misma sucursal",
        ):
            await _guardar(tienda, ["ba071"], [[], []])

    async def test_secondaries_need_a_principal(self):
        tienda = _sucursal(principal=None)

        with pytest.raises(
            bodegas_secundarias.BodegasSecundariasInvalidasError,
            match="no tiene 'Bodega principal'",
        ):
            await _guardar(tienda, ["MC001"], [])

    async def test_a_rejection_writes_nothing(self):
        tienda = _sucursal()
        db = FakeAsyncSession(execute_queue=[
            [], [("MC002", uuid.uuid4(), "PASTO")],
        ])

        with pytest.raises(
            bodegas_secundarias.BodegasSecundariasInvalidasError
        ):
            await bodegas_secundarias.guardar_de_sucursal(
                db, tienda, ["MC002"], USER_ID
            )

        assert db.added == []


class TestSecundariasPorSucursal:
    async def test_groups_codes_without_the_principal_in_one_query(self):
        quilichao = _sucursal()
        pasto = _sucursal("PASTO", "BP001", "C06")
        db = FakeAsyncSession(execute_queue=[[
            (quilichao.id, "BA071"), (quilichao.id, "BA161"),
            (quilichao.id, "MC001"), (pasto.id, "BP001"),
        ]])

        resultado = await bodegas_secundarias.secundarias_por_sucursal(
            db, [quilichao, pasto]
        )

        assert resultado == {quilichao.id: ["BA161", "MC001"]}
        assert len(db.executed_statements) == 1

    async def test_no_store_means_no_query(self):
        db = FakeAsyncSession()

        assert await bodegas_secundarias.secundarias_por_sucursal(
            db, []
        ) == {}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "t4-test-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "t4-test-asc360")
    override_motored_user(
        MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN")
    )
    yield
    app.dependency_overrides.clear()


def _cliente(queue):
    session = FakeAsyncSession(execute_queue=queue)
    override_motored_db(session)
    return session


class TestCrudApi:
    def test_update_swaps_principal_and_secondary_in_one_save(self, api):
        tienda = _sucursal()
        ba071 = _bodega("BA071", tienda.id)
        ba161 = _bodega("BA161", tienda.id, "BA071")
        bodegas = [ba071, ba161]
        session = _cliente([
            [], [tienda], [], [("BA071", tienda.id, tienda.nombre)],
            bodegas, bodegas,
        ])

        with TestClient(app) as client:
            response = client.patch(
                f"{SUCURSALES_URL}/{tienda.id}",
                json={"bodega_principal": "BA161",
                      "bodegas_secundarias": ["ba071"]},
            )

        assert response.status_code == 200, response.json()
        assert response.json()["bodegas_secundarias"] == ["BA071"]
        assert session.committed is True
        assert _estado(ba161) == (tienda.id, None)
        assert _estado(ba071) == (tienda.id, "BA161")

    def test_update_rejects_a_code_of_another_store(self, api):
        tienda = _sucursal()
        session = _cliente([
            [], [tienda], [], [("MC002", uuid.uuid4(), "PASTO")],
        ])

        with TestClient(app) as client:
            response = client.patch(
                f"{SUCURSALES_URL}/{tienda.id}",
                json={"bodegas_secundarias": ["MC002"]},
            )

        assert response.status_code == 422
        assert "'PASTO'" in response.json()["detail"]
        assert session.committed is False

    def test_update_of_the_principal_syncs_its_record(self, api):
        tienda = _sucursal()
        ba071 = _bodega("BA071", tienda.id)
        _cliente([[], [tienda], [], [], [ba071]])

        with TestClient(app) as client:
            response = client.patch(
                f"{SUCURSALES_URL}/{tienda.id}",
                json={"bodega_principal": "BA161"},
            )

        assert response.status_code == 200, response.json()
        assert response.json()["bodegas_secundarias"] is None
        assert _estado(ba071) == (tienda.id, "BA161")

    def test_update_without_bodegas_does_not_sync(self, api):
        tienda = _sucursal()
        session = _cliente([[], [tienda]])

        with TestClient(app) as client:
            response = client.patch(
                f"{SUCURSALES_URL}/{tienda.id}", json={"ciudad": "CALI"},
            )

        assert response.status_code == 200, response.json()
        assert session.committed is True

    def test_create_with_a_principal_creates_its_record(self, api):
        # Ready check, C.O. check, 2 validation reads, aplicar, sync.
        session = _cliente([[], [], [], [], [], []])

        with TestClient(app) as client:
            response = client.post(SUCURSALES_URL, json={
                "nombre": "NUEVA", "codigo_co": "A07",
                "bodega_principal": "BA071",
                "bodegas_secundarias": ["mc071"],
            })

        assert response.status_code == 201, response.json()
        nueva = response.json()["id"]
        assert response.json()["bodegas_secundarias"] == ["MC071"]
        assert _estado(_creada(session, "BA071")) == (
            uuid.UUID(nueva), None
        )
        assert _estado(_creada(session, "MC071")) == (
            uuid.UUID(nueva), "BA071"
        )

    def test_list_returns_each_stores_secondaries(self, api):
        quilichao = _sucursal()
        pasto = _sucursal("PASTO", "BP001", "C06")
        _cliente([[], [quilichao, pasto], [
            (quilichao.id, "BA071"), (quilichao.id, "BA161"),
        ]])

        with TestClient(app) as client:
            response = client.get(SUCURSALES_URL)

        assert response.status_code == 200
        por_nombre = {
            s["nombre"]: s["bodegas_secundarias"] for s in response.json()
        }
        assert por_nombre == {"QUILICHAO": ["BA161"], "PASTO": []}
