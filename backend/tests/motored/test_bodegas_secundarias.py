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

Every row carries its store code (C.O.): the upload matches stores by it,
so `_db` queues the C.O. resolver's read of the saved stores first.
"""
import io
import uuid

import openpyxl
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.main import app
from app.motored.api.carga import _resolver_relaciones, _resolver_y_procesar_carga
from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.services import bodegas_secundarias, salud
from app.motored.services.auth import MotoredUser
from app.motored.services.bodegas_secundarias import COLUMNA, FILA_CLAVE
from app.motored.services.carga_excel import column_labels, parse_excel_rows
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

USER_ID = uuid.uuid4()
# Each store's code (C.O.), its key in the upload.
_CODIGOS = {"CALI": "E01", "PASTO": "E02", "BOGOTA": "E03"}


def _fila(nombre, principal="", secundarias=None):
    fila = {
        "nombre": nombre, "codigo_co": _CODIGOS[nombre],
        "bodega_principal": principal,
    }
    if secundarias is not None:
        fila[COLUMNA] = secundarias
    return fila


def _db(guardadas, *resto, **kwargs):
    """Session for the upload path: the C.O. resolver first reads the saved
    stores (`guardadas`: `(id, nombre, ...)`), then the queued `resto`."""
    claves = [(fila[0], fila[1], _CODIGOS[fila[1]]) for fila in guardadas]
    return FakeAsyncSession(execute_queue=[claves, *resto], **kwargs)


def _suc_db(nombre, principal=None):
    return (uuid.uuid4(), nombre, principal)


def _motivos(errores):
    return [e["motivo"] for e in errores]


# ---------------------------------------------------------------------------
# resolver (validation shared by validar and carga)
# ---------------------------------------------------------------------------

class TestResolverFilas:
    async def test_column_absent_makes_no_query_and_leaves_rows_alone(self):
        db = _db([])
        filas = [_fila("CALI", "BA061")]

        resueltas, errores = await _resolver_relaciones(db, "sucursal", filas)

        assert errores == []
        assert FILA_CLAVE not in resueltas[0]

    async def test_column_present_without_codes_makes_no_query(self):
        db = _db([])

        resueltas, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", ""), _fila("PASTO", "BA070", None)]
        )

        assert errores == []
        assert resueltas[0][FILA_CLAVE] == []
        assert FILA_CLAVE not in resueltas[1]  # omitted key -> untouched

    async def test_codes_are_trimmed_deduped_and_empties_dropped(self):
        db = _db([], [], [])

        resueltas, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", " BA066 , ,BA067,BA066 ,")]
        )

        assert errores == []
        assert resueltas[0][FILA_CLAVE] == ["BA066", "BA067"]
        assert COLUMNA not in resueltas[0]

    async def test_code_listed_under_two_sucursales_is_a_row_error(self):
        db = _db([], [], [])

        _, errores = await _resolver_relaciones(
            db, "sucursal",
            [
                _fila("CALI", "BA061", "BA066"),
                _fila("PASTO", "BA070", "BA066"),
            ],
        )

        assert [e["fila"] for e in errores] == [2]
        assert "BA066" in errores[0]["motivo"]
        assert "fila 1" in errores[0]["motivo"]

    async def test_secondary_that_is_another_sucursal_principal_in_the_file_is_an_error(self):
        db = _db([], [], [])

        _, errores = await _resolver_relaciones(
            db, "sucursal",
            [_fila("CALI", "BA061", "BA070"), _fila("PASTO", "BA070")],
        )

        assert [e["fila"] for e in errores] == [1]
        assert "bodega principal" in errores[0]["motivo"].lower()
        assert "PASTO" in errores[0]["motivo"]

    async def test_secondary_that_is_a_db_sucursal_principal_is_an_error(self):
        otra = _suc_db("PASTO", "BA070")
        db = _db([otra], [otra], [])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA070")]
        )

        assert len(errores) == 1
        assert "PASTO" in errores[0]["motivo"]

    async def test_principal_changed_in_the_file_frees_the_old_code(self):
        # PASTO moves its principal BA070 -> BA071 in this very file, so BA070
        # is no longer anyone's principal and CALI may list it.
        otra = _suc_db("PASTO", "BA070")
        db = _db([otra], [otra], [])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA070"), _fila("PASTO", "BA071")]
        )

        assert errores == []

    async def test_secondary_equal_to_its_own_principal_is_an_error(self):
        db = _db([], [], [])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA061, BA066")]
        )

        assert len(errores) == 1
        assert "BA061" in errores[0]["motivo"]
        assert "misma sucursal" in errores[0]["motivo"]

    async def test_own_principal_comes_from_the_db_when_the_cell_is_blank(self):
        cali = _suc_db("CALI", "BA061")
        db = _db([cali], [cali], [])

        _, errores = await _resolver_relaciones(db, "sucursal", [_fila("CALI", "", "BA061")])

        assert len(errores) == 1

    async def test_secondary_linked_in_db_to_a_different_sucursal_is_rejected(self):
        pasto = _suc_db("PASTO", "BA070")
        db = _db([pasto], [pasto], [("BA066", pasto[0])])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA066")]
        )

        assert len(errores) == 1
        assert "PASTO" in errores[0]["motivo"]
        assert "Quítela primero" in errores[0]["motivo"]

    async def test_code_released_by_its_owner_later_can_move(self):
        pasto = _suc_db("PASTO", "BA070")
        db = _db([pasto], [pasto], [("BA066", pasto[0])])

        _, errores = await _resolver_relaciones(
            db, "sucursal",
            [_fila("CALI", "BA061", "BA066"), _fila("PASTO", "BA070", "")],
        )

        assert errores == []

    async def test_code_released_by_its_owner_earlier_can_move(self):
        pasto = _suc_db("PASTO", "BA070")
        db = _db([pasto], [pasto], [("BA066", pasto[0])])

        _, errores = await _resolver_relaciones(
            db, "sucursal",
            [
                _fila("PASTO", "BA070", "BA067"),
                _fila("CALI", "BA061", "BA066"),
            ],
        )

        assert errores == []

    async def test_owner_row_without_the_column_does_not_release(self):
        pasto = _suc_db("PASTO", "BA070")
        db = _db([pasto], [pasto], [("BA066", pasto[0])])

        _, errores = await _resolver_relaciones(
            db, "sucursal",
            [_fila("CALI", "BA061", "BA066"), _fila("PASTO", "BA070")],
        )

        assert [e["fila"] for e in errores] == [1]
        assert "Quítela primero" in errores[0]["motivo"]

    async def test_owner_that_still_lists_the_code_keeps_it_a_row_error(self):
        pasto = _suc_db("PASTO", "BA070")
        db = _db([pasto], [pasto], [("BA066", pasto[0])])

        _, errores = await _resolver_relaciones(
            db, "sucursal",
            [
                _fila("CALI", "BA061", "BA066"),
                _fila("PASTO", "BA070", "BA066"),
            ],
        )

        assert errores != []
        assert all("BA066" in e["motivo"] for e in errores)

    async def test_owner_principal_still_in_effect_cannot_move(self):
        pasto = _suc_db("PASTO", "BA070")
        db = _db([pasto], [pasto], [("BA070", pasto[0])])

        _, errores = await _resolver_relaciones(
            db, "sucursal",
            [_fila("CALI", "BA061", "BA070"), _fila("PASTO", "BA070", "")],
        )

        assert [e["fila"] for e in errores] == [1]
        assert "bodega principal" in errores[0]["motivo"].lower()

    async def test_old_principal_replaced_and_released_can_move(self):
        pasto = _suc_db("PASTO", "BA070")
        db = _db([pasto], [pasto], [("BA070", pasto[0])])

        _, errores = await _resolver_relaciones(
            db, "sucursal",
            [_fila("CALI", "BA061", "BA070"), _fila("PASTO", "BA071", "")],
        )

        assert errores == []

    async def test_secondary_linked_in_db_to_the_same_sucursal_is_fine(self):
        cali = _suc_db("CALI", "BA061")
        db = _db([cali], [cali], [("BA066", cali[0])])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA066")]
        )

        assert errores == []

    async def test_store_without_principal_cannot_list_secondaries(self):
        db = _db([], [], [])

        _, errores = await _resolver_relaciones(db, "sucursal", [_fila("CALI", "", "BA066")])

        assert len(errores) == 1
        assert "Bodega principal" in errores[0]["motivo"]

    async def test_same_sucursal_twice_is_a_row_error_when_the_column_is_present(self):
        db = _db([], [], [])

        _, errores = await _resolver_relaciones(
            db, "sucursal", [_fila("CALI", "BA061", "BA066"), _fila("CALI", "BA061", "BA067")]
        )

        # One store twice: its C.O. repeats, an error on both rows.
        assert [e["fila"] for e in errores] == [1, 2]
        assert all("repetido" in e["motivo"] for e in errores)


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
        # C.O. | resolver: sucursales, bodegas | upsert | apply: bodegas
        db = _db([], [], [], [], [])

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
        # C.O. | resolver: sucursales, bodegas | upsert | apply: bodegas
        guardadas = [(cali.id, "CALI", "BA061")]
        db = _db(guardadas, guardadas, [("BA066", None)], [cali], [huerfana])

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
        guardadas = [(cali.id, "CALI", "BA061")]
        db = _db(
            guardadas, guardadas, [("BA066", cali.id)], [cali], [vinculada]
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
        guardadas = [(cali.id, "CALI", "BA061")]
        db = _db(
            guardadas, guardadas, [("BA067", cali.id)], [cali],
            [vieja, queda],
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
        db = _db([(cali.id, "CALI")], [cali], [a, b])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "")], USER_ID
        )

        assert (a.sucursal_id, a.bodega_principal, b.sucursal_id, b.bodega_principal) == (None,) * 4
        assert sorted(v["bodega"] for v in resultado.bodegas_secundarias.desvinculadas) == ["BA066", "BA067"]

    async def test_the_principal_bodega_row_is_never_unlinked(self):
        cali = _sucursal("CALI", "BA061")
        principal = _bodega("BA061", cali.id, None)
        db = _db([(cali.id, "CALI")], [cali], [principal])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "")], USER_ID
        )

        assert principal.sucursal_id == cali.id
        assert resultado.bodegas_secundarias.desvinculadas == []

    async def test_column_absent_touches_no_secondaries(self):
        cali = _sucursal("CALI", "BA061")
        # C.O. and upsert queries only: any extra query would raise
        db = _db([(cali.id, "CALI")], [cali])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "CALI", "codigo_co": "E01", "ciudad": "Cali"}],
            USER_ID,
        )

        assert resultado.ok is True
        assert resultado.bodegas_secundarias is None
        assert db.added_of_type(Bodega) == []

    @pytest.mark.parametrize("cali_first", [True, False])
    async def test_bodega_moves_between_stores_in_one_upload(self, cali_first):
        cali = _sucursal("CALI", "BA061")
        pasto = _sucursal("PASTO", "BA070")
        movida = _bodega("BA066", pasto.id, "BA070")
        filas = [_fila("CALI", "BA061", "BA066"), _fila("PASTO", "BA070", "")]
        upserts = [[cali], [pasto]]
        if not cali_first:
            filas.reverse()
            upserts.reverse()
        sucursales = [
            (cali.id, "CALI", "BA061"), (pasto.id, "PASTO", "BA070"),
        ]
        # C.O. | resolver: sucursales, bodegas | upserts | apply: bodegas
        db = _db(
            sucursales, sucursales, [("BA066", pasto.id)], *upserts,
            [movida],
        )

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", filas, USER_ID
        )

        assert resultado.ok is True
        assert movida.sucursal_id == cali.id
        assert movida.bodega_principal == "BA061"
        resumen = resultado.bodegas_secundarias
        assert resumen.vinculadas == [{"sucursal": "CALI", "bodega": "BA066"}]
        assert resumen.desvinculadas == []
        assert db.committed is True

    async def test_row_error_rejects_the_whole_file_and_writes_nothing(self):
        pasto = _suc_db("PASTO", "BA070")
        db = _db([pasto], [pasto], [])

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
    # probe, C.O. resolver, upsert, apply
    session = FakeAsyncSession(execute_queue=[[], [], [], []])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            "/api/motored/maestros/sucursal/carga",
            json={"filas": [{
                "nombre": "CALI", "codigo_co": "E01",
                "bodega_principal": "BA061", "bodegas_secundarias": "",
            }]},
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["bodegas_secundarias"] == {"vinculadas": [], "desvinculadas": []}


# ---------------------------------------------------------------------------
# template / parsing / health
# ---------------------------------------------------------------------------

def test_sucursal_template_and_parser_know_the_new_column():
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
    db = _db([], [], [], [], [], raise_integrity_error=True)

    with pytest.raises(HTTPException) as exc:
        await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "BA066")], USER_ID
        )

    assert exc.value.status_code == 409
    assert db.rolled_back is True


async def test_row_that_omits_the_column_keeps_its_secondaries_in_a_mixed_file():
    cali = _sucursal("CALI", "BA061")
    pasto = _sucursal("PASTO", "BA071")
    de_pasto = _bodega("BA070", pasto.id, "BA071")
    nueva = _bodega("BA066")
    # C.O. | resolver: sucursales, bodegas | upserts | apply: bodegas
    guardadas = [(cali.id, "CALI", "BA061"), (pasto.id, "PASTO", "BA071")]
    db = _db(
        guardadas, guardadas, [("BA066", None)], [cali], [pasto],
        [nueva, de_pasto],
    )
    # JSON row without the key
    omite = {
        "nombre": "PASTO", "codigo_co": "E02", "bodega_principal": "BA071",
    }

    resultado = await _resolver_y_procesar_carga(
        db, "sucursal", [_fila("CALI", "BA061", "BA066"), omite], USER_ID
    )

    assert resultado.ok is True
    assert de_pasto.sucursal_id == pasto.id and de_pasto.bodega_principal == "BA071"
    assert resultado.bodegas_secundarias.desvinculadas == []


async def test_row_with_empty_list_still_unlinks_all():
    cali = _sucursal("CALI", "BA061")
    a = _bodega("BA066", cali.id, "BA061")
    db = _db([(cali.id, "CALI")], [cali], [a])

    await _resolver_y_procesar_carga(db, "sucursal", [_fila("CALI", "BA061", [])], USER_ID)

    assert a.sucursal_id is None


async def test_integrity_error_inside_the_apply_step_is_a_409(monkeypatch):
    async def boom(db, entradas, usuario_id):
        raise IntegrityError("INSERT", {}, Exception("duplicate key value"))

    monkeypatch.setattr(bodegas_secundarias, "aplicar", boom)
    db = _db([], [], [], [])

    with pytest.raises(HTTPException) as exc:
        await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("CALI", "BA061", "BA066")], USER_ID
        )

    assert exc.value.status_code == 409
    assert db.rolled_back is True
    assert db.committed is False

