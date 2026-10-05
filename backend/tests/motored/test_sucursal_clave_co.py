"""
The store code "C.O." is the business key of a sucursal.

The C.O. identifies the store; the name is a mutable attribute. The
Sucursales upload matches a saved store by its C.O. and renames it when the
name differs. On the first upload of codes (a store without a C.O. yet) the
row matches by name and fills the code in. Every per-row resolver of the
upload ("Bodegas secundarias", "Sucursal principal") keys on the resolved
store, so a rename, a bodega move and an association work in one file. The
"Sucursal principal" column accepts a C.O. or a name. The CRUD requires the
C.O. on create and refuses to clear it.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.services import maestros
from app.motored.services.auth import MotoredUser
from app.motored.services.sucursal_grupo import FILA_SUCURSAL_ID
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

USER_ID = uuid.uuid4()
SUCURSALES_URL = "/api/motored/maestros/sucursales"
OBLIGATORIO = "El Código C.O. es obligatorio: identifica a la sucursal."


def _sucursal(nombre, codigo_co=None, bodega_principal=None):
    return Sucursal(
        id=uuid.uuid4(), nombre=nombre, codigo_co=codigo_co, activa=True,
        sic="S1", bodega_principal=bodega_principal,
    )


def _guardada(sucursal):
    """A row of the resolver's query: (id, nombre, codigo_co)."""
    return (sucursal.id, sucursal.nombre, sucursal.codigo_co)


def _motivos(errores):
    return [(e["fila"], e["motivo"]) for e in errores]


class TestResolver:
    async def test_a_missing_code_is_a_row_error(self):
        db = FakeAsyncSession(execute_queue=[])

        _, errores = await maestros.resolver_sucursales_carga(
            db, [{"nombre": "CALI"}, {"nombre": "PASTO", "codigo_co": " "}]
        )

        assert _motivos(errores) == [(1, OBLIGATORIO), (2, OBLIGATORIO)]

    async def test_the_code_matches_the_store_even_with_a_new_name(self):
        cali = _sucursal("CALI", "E05")
        db = FakeAsyncSession(execute_queue=[[_guardada(cali)]])

        filas, errores = await maestros.resolver_sucursales_carga(
            db, [{"nombre": "CALI CENTRO", "codigo_co": "E05"}]
        )

        assert errores == []
        assert filas[0][FILA_SUCURSAL_ID] == cali.id

    async def test_a_rename_onto_another_store_name_names_both(self):
        cali = _sucursal("CALI", "E05")
        pasto = _sucursal("PASTO", "C06")
        db = FakeAsyncSession(
            execute_queue=[[_guardada(cali), _guardada(pasto)]]
        )

        _, errores = await maestros.resolver_sucursales_carga(
            db, [{"nombre": "PASTO", "codigo_co": "E05"}]
        )

        assert _motivos(errores) == [(1, (
            "Columna 'Nombre': la sucursal con C.O. 'E05' no puede "
            "llamarse 'PASTO': ese nombre es de la sucursal con C.O. "
            "'C06'. Cada sucursal necesita un nombre distinto."
        ))]

    async def test_first_upload_matches_a_store_without_code_by_name(self):
        cali = _sucursal("CALI")
        db = FakeAsyncSession(execute_queue=[[_guardada(cali)]])

        filas, errores = await maestros.resolver_sucursales_carga(
            db, [{"nombre": " CALI ", "codigo_co": "e05"}]
        )

        assert errores == []
        assert filas[0][FILA_SUCURSAL_ID] == cali.id

    async def test_code_and_name_of_different_stores_is_a_row_error(self):
        cali = _sucursal("CALI", "E05")
        db = FakeAsyncSession(execute_queue=[[_guardada(cali)]])

        _, errores = await maestros.resolver_sucursales_carga(
            db, [{"nombre": "CALI", "codigo_co": "C09"}]
        )

        assert _motivos(errores) == [(1, (
            "Columna 'Código C.O.': el código 'C09' no es de ninguna "
            "sucursal, pero el nombre 'CALI' es de la sucursal con C.O. "
            "'E05'. El C.O. y el nombre apuntan a tiendas distintas: "
            "corrija uno de los dos."
        ))]

    async def test_two_stores_may_swap_names_and_codes_in_one_file(self):
        a = _sucursal("A", "E05")
        b = _sucursal("B", "C06")
        db = FakeAsyncSession(execute_queue=[[_guardada(a), _guardada(b)]])

        filas, errores = await maestros.resolver_sucursales_carga(
            db,
            [{"nombre": "B", "codigo_co": "E05"},
             {"nombre": "A", "codigo_co": "C06"}],
        )

        assert errores == []
        assert [f[FILA_SUCURSAL_ID] for f in filas] == [a.id, b.id]

    async def test_two_rows_filling_in_the_same_store_are_an_error(self):
        cali = _sucursal("CALI")
        db = FakeAsyncSession(execute_queue=[[_guardada(cali)]])

        _, errores = await maestros.resolver_sucursales_carga(
            db,
            [{"nombre": "CALI", "codigo_co": "E05"},
             {"nombre": "CALI", "codigo_co": "C06"}],
        )

        assert [e["fila"] for e in errores] == [1, 2]
        assert all("filas 1 y 2" in e["motivo"] for e in errores)

    async def test_an_unknown_code_and_name_is_a_new_store(self):
        db = FakeAsyncSession(execute_queue=[[]])

        filas, errores = await maestros.resolver_sucursales_carga(
            db, [{"nombre": "NEIVA", "codigo_co": "E07"}]
        )

        assert errores == []
        assert filas[0][FILA_SUCURSAL_ID] is None

    async def test_a_new_store_may_take_a_name_another_store_leaves(self):
        cali = _sucursal("CALI", "E05")
        db = FakeAsyncSession(execute_queue=[[_guardada(cali)]])

        filas, errores = await maestros.resolver_sucursales_carga(
            db,
            [{"nombre": "CALI SUR", "codigo_co": "E05"},
             {"nombre": "CALI", "codigo_co": "E08"}],
        )

        assert errores == []
        assert [f[FILA_SUCURSAL_ID] for f in filas] == [cali.id, None]


class TestUpload:
    async def test_a_rename_updates_the_store_instead_of_creating(self):
        cali = _sucursal("CALI", "E05")
        db = FakeAsyncSession(execute_queue=[[_guardada(cali)], [cali]])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "CALI CENTRO", "codigo_co": "E05"}], USER_ID,
        )

        assert resultado.ok is True
        assert (resultado.insertados, resultado.actualizados) == (0, 1)
        assert cali.nombre == "CALI CENTRO"
        assert not [o for o in db.added if isinstance(o, Sucursal)]

    async def test_a_missing_code_rejects_the_file(self):
        db = FakeAsyncSession(execute_queue=[])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [{"nombre": "CALI"}], USER_ID,
        )

        assert resultado.ok is False
        assert resultado.errores[0].motivo == OBLIGATORIO
        assert db.committed is False

    async def test_first_upload_fills_in_the_code_by_name(self):
        cali = _sucursal("CALI")
        db = FakeAsyncSession(execute_queue=[[_guardada(cali)], [cali]])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [{"nombre": "CALI", "codigo_co": "E05"}],
            USER_ID,
        )

        assert resultado.ok is True
        assert cali.codigo_co == "E05"

    async def test_two_stores_swap_names_in_one_file(self):
        a = _sucursal("A", "E05")
        b = _sucursal("B", "C06")
        db = FakeAsyncSession(
            execute_queue=[[_guardada(a), _guardada(b)], [a], [b]]
        )

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "B", "codigo_co": "E05"},
             {"nombre": "A", "codigo_co": "C06"}],
            USER_ID,
        )

        assert resultado.ok is True
        assert (a.nombre, b.nombre) == ("B", "A")
        assert (a.codigo_co, b.codigo_co) == ("E05", "C06")

    async def test_a_rename_with_an_inactive_flag_hits_the_coded_store(self):
        cali = _sucursal("CALI", "E05")
        db = FakeAsyncSession(execute_queue=[[_guardada(cali)], [cali]])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "CALI VIEJA", "codigo_co": "E05", "activa": "No"}],
            USER_ID,
        )

        assert resultado.ok is True
        assert (cali.nombre, cali.activa) == ("CALI VIEJA", False)

    async def test_rename_bodega_move_and_association_in_one_file(self):
        a = _sucursal("A", "E05", bodega_principal="BA061")
        b = _sucursal("B", "C06", bodega_principal="BA075")
        ba066 = Bodega(
            id=uuid.uuid4(), codigo="BA066", sucursal_id=a.id,
            bodega_principal="BA061",
        )
        sucursales = [(s.id, s.nombre, s.bodega_principal) for s in (a, b)]
        contexto = [(s.id, s.nombre, None, s.codigo_co) for s in (a, b)]
        db = FakeAsyncSession(execute_queue=[
            [_guardada(a), _guardada(b)],  # C.O. resolver
            sucursales, [("BA066", a.id)],  # bodegas resolver
            contexto,  # "Sucursal principal" resolver
            [a], [b],  # one upsert per row
            [ba066],  # bodegas aplicar
        ])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "A NUEVA", "codigo_co": "E05",
              "bodega_principal": "BA061", "bodegas_secundarias": ""},
             {"nombre": "B", "codigo_co": "C06",
              "bodega_principal": "BA075", "bodegas_secundarias": "BA066",
              "sucursal_principal": "E05"}],
            USER_ID,
        )

        assert resultado.ok is True, resultado.errores
        assert a.nombre == "A NUEVA"
        assert (ba066.sucursal_id, ba066.bodega_principal) == (
            b.id, "BA075"
        )
        assert b.principal_id == a.id


class TestPrincipalByCode:
    async def test_the_principal_column_takes_a_saved_store_code(self):
        a = _sucursal("A", "E05")
        b = _sucursal("B", "C06")
        contexto = [(s.id, s.nombre, None, s.codigo_co) for s in (a, b)]
        db = FakeAsyncSession(execute_queue=[
            [_guardada(a), _guardada(b)], contexto, [b],
        ])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "B", "codigo_co": "C06",
              "sucursal_principal": "e05"}],
            USER_ID,
        )

        assert resultado.ok is True, resultado.errores
        assert b.principal_id == a.id

    async def test_the_principal_column_takes_a_code_of_the_same_file(self):
        b = _sucursal("B", "C06")
        contexto = [(b.id, b.nombre, None, b.codigo_co)]
        db = FakeAsyncSession(execute_queue=[
            [_guardada(b)], contexto, [], [b],
        ])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "NUEVA", "codigo_co": "E09"},
             {"nombre": "B", "codigo_co": "C06",
              "sucursal_principal": "E09"}],
            USER_ID,
        )

        assert resultado.ok is True, resultado.errores
        nueva = [o for o in db.added if isinstance(o, Sucursal)][0]
        assert b.principal_id == nueva.id

    async def test_the_principal_column_still_takes_a_name(self):
        a = _sucursal("A", "E05")
        b = _sucursal("B", "C06")
        contexto = [(s.id, s.nombre, None, s.codigo_co) for s in (a, b)]
        db = FakeAsyncSession(execute_queue=[
            [_guardada(a), _guardada(b)], contexto, [b],
        ])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "B", "codigo_co": "C06", "sucursal_principal": "a"}],
            USER_ID,
        )

        assert resultado.ok is True, resultado.errores
        assert b.principal_id == a.id

    async def test_an_unknown_code_or_name_is_a_row_error(self):
        b = _sucursal("B", "C06")
        contexto = [(b.id, b.nombre, None, b.codigo_co)]
        db = FakeAsyncSession(execute_queue=[[_guardada(b)], contexto])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "B", "codigo_co": "C06",
              "sucursal_principal": "Z99"}],
            USER_ID,
        )

        assert resultado.ok is False
        assert resultado.errores[0].motivo == (
            "'Sucursal principal' 'Z99' no corresponde a ningún Código "
            "C.O. ni nombre de sucursal existente ni del archivo."
        )


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "clave-co-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "clave-co-asc360")
    override_motored_user(MotoredUser(user_id=str(USER_ID), role="ADMIN"))
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


class TestCrud:
    async def test_create_without_a_code_is_rejected(self):
        db = FakeAsyncSession(execute_queue=[])

        with pytest.raises(maestros.CodigoCoRequeridoError) as exc:
            await maestros.create_sucursal(
                db, maestros.SucursalCreate(nombre="CALI")
            )

        assert str(exc.value) == OBLIGATORIO

    async def test_clearing_the_code_is_rejected(self):
        cali = _sucursal("CALI", "E05")
        db = FakeAsyncSession(execute_queue=[])

        with pytest.raises(maestros.CodigoCoRequeridoError):
            await maestros.update_sucursal(
                db, cali, maestros.SucursalUpdate(codigo_co=None)
            )

        assert cali.codigo_co == "E05"

    async def test_a_store_without_code_still_edits_without_one(self):
        cali = _sucursal("CALI")
        db = FakeAsyncSession(execute_queue=[])

        await maestros.update_sucursal(
            db, cali,
            maestros.SucursalUpdate(codigo_co=None, ciudad="Cali"),
        )

        assert (cali.codigo_co, cali.ciudad) == (None, "Cali")

    async def test_the_form_may_rename_freely(self):
        cali = _sucursal("CALI", "E05")
        db = FakeAsyncSession(execute_queue=[])

        await maestros.update_sucursal(
            db, cali, maestros.SucursalUpdate(nombre=" CALI SUR ")
        )

        assert cali.nombre == "CALI SUR"


class TestCrudApi:
    def test_create_without_a_code_is_a_422(self, api):
        override_motored_db(FakeAsyncSession(execute_queue=[[]]))

        respuesta = api.post(SUCURSALES_URL, json={"nombre": "CALI"})

        assert respuesta.status_code == 422
        assert respuesta.json()["detail"] == OBLIGATORIO

    def test_clearing_the_code_is_a_422(self, api):
        cali = _sucursal("CALI", "E05")
        override_motored_db(FakeAsyncSession(execute_queue=[[], [cali]]))

        respuesta = api.patch(
            f"{SUCURSALES_URL}/{cali.id}", json={"codigo_co": None}
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["detail"] == (
            "El Código C.O. no se puede borrar: identifica a la sucursal."
        )
