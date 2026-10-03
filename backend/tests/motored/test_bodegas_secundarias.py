"""
Sucursales upload: the "Bodegas secundarias" column.

A store can own several bodegas but the file only had "Bodega principal".
The new column lists the secondary codes (comma separated). On upload each
code is upserted as a `bodega` row linked to the sucursal
(`sucursal_id`) and pointing at the store's principal (`bodega_principal`),
the chain `resolucion._resolver_sucursal_de_bodega` follows.

Contract under test:
- Link: the bodega is created (or relinked) with `sucursal_id` and
  `bodega_principal`; codes are trimmed, empties ignored, duplicates dropped.
- Row errors (all-or-nothing): a code under two sucursales of the file; a code
  that is any sucursal's principal (file or DB); a code linked in the DB to a
  DIFFERENT sucursal; a code equal to its own store's principal.
- Unlink: column absent -> nothing touched; column present -> for every
  sucursal IN the file the listed codes are its secondaries, the previously
  linked ones that are no longer listed get both columns NULL (never deleted);
  a blank cell unlinks them all; sucursales absent from the file are untouched.
- The upload result reports links and unlinks.
- The bodegas bulk upload is disabled (410).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api.carga import _resolver_relaciones, _resolver_y_procesar_carga
from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.services.auth import MotoredUser
from app.motored.services.bodegas_secundarias import COLUMNA, FILA_CLAVE
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

USER_ID = uuid.uuid4()


def _fila(nombre, principal="", secundarias=None):
    fila = {"nombre": nombre, "bodega_principal": principal}
    if secundarias is not None:
        fila[COLUMNA] = secundarias
    return fila


def _suc_db(nombre, principal=None):
    return (uuid.uuid4(), nombre, principal)


def _motivos(errores):
    return [e["motivo"] for e in errores]


# ---------------------------------------------------------------------------
# resolver (validation shared by validar and carga)
# ---------------------------------------------------------------------------

class TestResolverFilas:
    async def test_column_absent_makes_no_query_and_leaves_rows_alone(self):
        db = FakeAsyncSession(execute_queue=[])
        filas = [_fila("CALI", "BA061")]

        resueltas, errores = await _resolver_relaciones(db, "sucursal", filas)

        assert errores == []
        assert FILA_CLAVE not in resueltas[0]

    async def test_column_present_without_codes_makes_no_query(self):
        db = FakeAsyncSession(execute_queue=[])

        resueltas, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", ""), _fila("PASTO", "BA070", None)]
        )

        assert errores == []
        assert [f[FILA_CLAVE] for f in resueltas] == [[], []]

    async def test_codes_are_trimmed_deduped_and_empties_dropped(self):
        db = FakeAsyncSession(execute_queue=[[], []])

        resueltas, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", " BA066 , ,BA067,BA066 ,")]
        )

        assert errores == []
        assert resueltas[0][FILA_CLAVE] == ["BA066", "BA067"]
        assert COLUMNA not in resueltas[0]

    async def test_code_listed_under_two_sucursales_is_a_row_error(self):
        db = FakeAsyncSession(execute_queue=[[], []])

        _, errores = await _resolver_relaciones(
            db, "sucursal",
            [_fila("CALI", "BA061", "BA066"), _fila("PASTO", "BA070", "BA066")],
        )

        assert [e["fila"] for e in errores] == [2]
        assert "BA066" in errores[0]["motivo"]
        assert "fila 1" in errores[0]["motivo"]

    async def test_secondary_that_is_another_sucursal_principal_in_the_file_is_an_error(self):
        db = FakeAsyncSession(execute_queue=[[], []])

        _, errores = await _resolver_relaciones(
            db, "sucursal",
            [_fila("CALI", "BA061", "BA070"), _fila("PASTO", "BA070")],
        )

        assert [e["fila"] for e in errores] == [1]
        assert "bodega principal" in errores[0]["motivo"].lower()
        assert "PASTO" in errores[0]["motivo"]

    async def test_secondary_that_is_a_db_sucursal_principal_is_an_error(self):
        otra = _suc_db("PASTO", "BA070")
        db = FakeAsyncSession(execute_queue=[[otra], []])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA070")]
        )

        assert len(errores) == 1
        assert "PASTO" in errores[0]["motivo"]

    async def test_principal_changed_in_the_file_frees_the_old_code(self):
        # PASTO moves its principal BA070 -> BA071 in this very file, so BA070
        # is no longer anyone's principal and CALI may list it.
        otra = _suc_db("PASTO", "BA070")
        db = FakeAsyncSession(execute_queue=[[otra], []])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA070"), _fila("PASTO", "BA071")]
        )

        assert errores == []

    async def test_secondary_equal_to_its_own_principal_is_an_error(self):
        db = FakeAsyncSession(execute_queue=[[], []])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA061, BA066")]
        )

        assert len(errores) == 1
        assert "BA061" in errores[0]["motivo"]
        assert "misma sucursal" in errores[0]["motivo"]

    async def test_own_principal_comes_from_the_db_when_the_cell_is_blank(self):
        cali = _suc_db("CALI", "BA061")
        db = FakeAsyncSession(execute_queue=[[cali], []])

        _, errores = await _resolver_relaciones(db, "sucursal", [_fila("CALI", "", "BA061")])

        assert len(errores) == 1

    async def test_secondary_linked_in_db_to_a_different_sucursal_is_rejected(self):
        pasto = _suc_db("PASTO", "BA070")
        db = FakeAsyncSession(execute_queue=[[pasto], [("BA066", pasto[0])]])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA066")]
        )

        assert len(errores) == 1
        assert "PASTO" in errores[0]["motivo"]
        assert "Quítela primero" in errores[0]["motivo"]

    async def test_secondary_linked_in_db_to_the_same_sucursal_is_fine(self):
        cali = _suc_db("CALI", "BA061")
        db = FakeAsyncSession(execute_queue=[[cali], [("BA066", cali[0])]])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA066")]
        )

        assert errores == []

    async def test_store_without_principal_cannot_list_secondaries(self):
        db = FakeAsyncSession(execute_queue=[[], []])

        _, errores = await _resolver_relaciones(db, "sucursal", [_fila("CALI", "", "BA066")])

        assert len(errores) == 1
        assert "Bodega principal" in errores[0]["motivo"]

    async def test_same_sucursal_twice_is_a_row_error_when_the_column_is_present(self):
        db = FakeAsyncSession(execute_queue=[[], []])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA066"), _fila("CALI", "BA061", "BA067")]
        )

        assert [e["fila"] for e in errores] == [2]


# ---------------------------------------------------------------------------
# apply (link / unlink) through the same path the router uses
# ---------------------------------------------------------------------------

def _bodega(codigo, sucursal_id=None, principal=None):
    return Bodega(
        id=uuid.uuid4(), codigo=codigo, sucursal_id=sucursal_id, bodega_principal=principal, activa=True
    )


def _sucursal(nombre, principal):
    return Sucursal(id=uuid.uuid4(), nombre=nombre, bodega_principal=principal, activa=True)


class TestAplicar:
    async def test_link_creates_the_bodega_with_sucursal_and_principal(self):
        # resolver: sucursales, bodegas | upsert: get_sucursal_by_nombre | apply: bodegas
        db = FakeAsyncSession(execute_queue=[[], [], [], []])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "BA066, BA067")], USER_ID
        )

        assert resultado.ok is True
        sucursal = db.added_of_type(Sucursal)[0]
        bodegas = {b.codigo: b for b in db.added_of_type(Bodega)}
        assert set(bodegas) == {"BA066", "BA067"}
        assert all(b.sucursal_id == sucursal.id for b in bodegas.values())
        assert all(b.bodega_principal == "BA061" for b in bodegas.values())
        assert db.committed is True
        assert sorted(v["bodega"] for v in resultado.bodegas_secundarias.vinculadas) == ["BA066", "BA067"]
        assert resultado.bodegas_secundarias.vinculadas[0]["sucursal"] == "CALI"
        assert resultado.bodegas_secundarias.desvinculadas == []

    async def test_existing_orphan_bodega_is_relinked_not_duplicated(self):
        cali = _sucursal("CALI", "BA061")
        huerfana = _bodega("BA066")
        # resolver: sucursales, bodegas | upsert: sucursal existente | apply: bodegas
        db = FakeAsyncSession(
            execute_queue=[[(cali.id, "CALI", "BA061")], [("BA066", None)], [cali], [huerfana]]
        )

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "BA066")], USER_ID
        )

        assert resultado.ok is True
        assert db.added_of_type(Bodega) == []
        assert huerfana.sucursal_id == cali.id
        assert huerfana.bodega_principal == "BA061"
        assert len(resultado.bodegas_secundarias.vinculadas) == 1

    async def test_already_linked_bodega_is_not_reported_again(self):
        cali = _sucursal("CALI", "BA061")
        vinculada = _bodega("BA066", cali.id, "BA061")
        db = FakeAsyncSession(
            execute_queue=[[(cali.id, "CALI", "BA061")], [("BA066", cali.id)], [cali], [vinculada]]
        )

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "BA066")], USER_ID
        )

        assert resultado.bodegas_secundarias.vinculadas == []
        assert resultado.bodegas_secundarias.desvinculadas == []

    async def test_listed_codes_replace_the_previous_secondaries(self):
        cali = _sucursal("CALI", "BA061")
        vieja = _bodega("BA066", cali.id, "BA061")
        queda = _bodega("BA067", cali.id, "BA061")
        db = FakeAsyncSession(
            execute_queue=[
                [(cali.id, "CALI", "BA061")], [("BA067", cali.id)], [cali], [vieja, queda],
            ]
        )

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "BA067")], USER_ID
        )

        assert resultado.ok is True
        assert vieja.sucursal_id is None and vieja.bodega_principal is None
        assert queda.sucursal_id == cali.id
        assert [v["bodega"] for v in resultado.bodegas_secundarias.desvinculadas] == ["BA066"]

    async def test_blank_cell_unlinks_every_secondary_of_that_store(self):
        cali = _sucursal("CALI", "BA061")
        a = _bodega("BA066", cali.id, "BA061")
        b = _bodega("BA067", cali.id, "BA061")
        # blank cell -> no codes at all -> the resolver makes no query
        db = FakeAsyncSession(execute_queue=[[cali], [a, b]])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "")], USER_ID
        )

        assert (a.sucursal_id, a.bodega_principal, b.sucursal_id, b.bodega_principal) == (None,) * 4
        assert sorted(v["bodega"] for v in resultado.bodegas_secundarias.desvinculadas) == ["BA066", "BA067"]

    async def test_the_principal_bodega_row_is_never_unlinked(self):
        cali = _sucursal("CALI", "BA061")
        principal = _bodega("BA061", cali.id, None)
        db = FakeAsyncSession(execute_queue=[[cali], [principal]])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "")], USER_ID
        )

        assert principal.sucursal_id == cali.id
        assert resultado.bodegas_secundarias.desvinculadas == []

    async def test_column_absent_touches_no_secondaries(self):
        cali = _sucursal("CALI", "BA061")
        # only the upsert query: any extra query would raise on the empty queue
        db = FakeAsyncSession(execute_queue=[[cali]])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [{"nombre": "CALI", "ciudad": "Cali"}], USER_ID
        )

        assert resultado.ok is True
        assert resultado.bodegas_secundarias is None
        assert db.added_of_type(Bodega) == []

    async def test_row_error_rejects_the_whole_file_and_writes_nothing(self):
        pasto = _suc_db("PASTO", "BA070")
        db = FakeAsyncSession(execute_queue=[[pasto], []])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [_fila("CALI", "BA061", "BA066"), _fila("BOGOTA", "BA080", "BA070")],
            USER_ID,
        )

        assert resultado.ok is False
        assert [e.fila for e in resultado.errores] == [2]
        assert db.added == []
        assert db.committed is False


# ---------------------------------------------------------------------------
# HTTP: the bodegas upload is disabled
# ---------------------------------------------------------------------------

@pytest.fixture
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "bodegas-sec-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "bodegas-sec-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "path", ["", "/validar", "/excel", "/excel/validar"]
)
def test_bodegas_bulk_upload_is_gone(_motored_ready, path):
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))
    url = f"/api/motored/maestros/bodega/carga{path}"

    with TestClient(app) as client:
        if "excel" in path:
            response = client.post(
                url, files={"file": ("b.xlsx", b"x", "application/octet-stream")}
            )
        else:
            response = client.post(url, json={"filas": [{"codigo": "BA066"}]})

    assert response.status_code == 410
    assert "Bodegas secundarias" in response.json()["detail"]


def test_sucursal_upload_still_works_over_http(_motored_ready):
    session = FakeAsyncSession(execute_queue=[[], [], []])  # probe, upsert, apply
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            "/api/motored/maestros/sucursal/carga",
            json={"filas": [{"nombre": "CALI", "bodega_principal": "BA061", "bodegas_secundarias": ""}]},
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["bodegas_secundarias"] == {"vinculadas": [], "desvinculadas": []}


# ---------------------------------------------------------------------------
# template / parsing / health
# ---------------------------------------------------------------------------

def test_sucursal_template_and_parser_know_the_new_column():
    import io

    import openpyxl

    from app.motored.services.carga_excel import column_labels, parse_excel_rows

    assert "Bodegas secundarias" in column_labels("sucursal")

    wb = openpyxl.Workbook()
    wb.active.append(["Nombre", "Bodega principal", "Bodegas secundarias"])
    wb.active.append(["CALI", "BA061", "BA066, BA067"])
    wb.active.append(["PASTO", "BA070", None])
    buffer = io.BytesIO()
    wb.save(buffer)

    filas = parse_excel_rows("sucursal", "s.xlsx", buffer.getvalue())

    assert filas[0][COLUMNA] == ["BA066", "BA067"]
    assert filas[1][COLUMNA] == ""  # present but blank -> unlink all


async def test_bodega_sin_sucursal_is_shown_under_the_sucursales_tab():
    from app.motored.services import salud

    bodega = Bodega(id=uuid.uuid4(), codigo="BA066", sucursal_id=None, activa=True)
    db = FakeAsyncSession(execute_queue=[[], [], [], [bodega]])

    resultado = await salud.evaluar_salud(db)

    hallazgo = [h for h in resultado.hallazgos if h.tipo == "bodega_sin_sucursal"][0]
    assert hallazgo.entidad == "sucursal"
    assert hallazgo.bloqueante is False
    assert hallazgo.mensaje == (
        "La bodega 'BA066' no está asociada a ninguna sucursal; "
        "agréguela en 'Bodegas secundarias' de su sucursal."
    )


async def test_concurrent_bodega_creation_is_a_409_not_a_500():
    from fastapi import HTTPException

    db = FakeAsyncSession(execute_queue=[[], [], [], []], raise_integrity_error=True)

    with pytest.raises(HTTPException) as exc:
        await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "BA066")], USER_ID
        )

    assert exc.value.status_code == 409
    assert db.rolled_back is True
