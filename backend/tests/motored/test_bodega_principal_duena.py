"""
A store's principal bodega must not belong to another store (upload and
form), unless the same file or save releases it; and a raw
`principal_id` in a JSON upload row never associates stores. The real
database flows live in `pg_real/test_bodega_principal_duena_pg.py`.
"""
import uuid

import pytest

from app.motored.models.sucursal import Sucursal
from app.motored.services import bodegas_secundarias, sucursal_grupo
from app.motored.services.sucursal_grupo import FILA_SUCURSAL_ID
from tests.motored.conftest import FakeAsyncSession

USER_ID = uuid.uuid4()
CALI, PASTO = uuid.uuid4(), uuid.uuid4()
GUARDADAS = [(CALI, "CALI", "BA061"), (PASTO, "PASTO", "BP001")]


def _motivo(codigo, nombre):
    return (
        f"La bodega {codigo} ya es de la sucursal {nombre}. Quítela de "
        "esa sucursal primero o muévala con la carga masiva."
    )


def _fila(nombre, principal, sucursal_id=None, **extra):
    return {
        "nombre": nombre, "bodega_principal": principal,
        FILA_SUCURSAL_ID: sucursal_id, **extra,
    }


def _errores(filas, bodegas_db):
    return bodegas_secundarias.errores_de_principales_en(
        filas, GUARDADAS, bodegas_db
    )


class TestUpload:
    def test_another_stores_principal(self):
        errores = _errores([_fila("NEIVA", "BA061")], {"BA061": CALI})

        assert errores == [{"fila": 1, "motivo": _motivo("BA061", "CALI")}]

    def test_another_stores_secondary_record(self):
        errores = _errores([_fila("NEIVA", "MC001")], {"MC001": PASTO})

        assert errores == [{"fila": 1, "motivo": _motivo("MC001", "PASTO")}]

    def test_its_own_record_is_fine(self):
        assert _errores(
            [_fila("CALI", "MC001", CALI)], {"MC001": CALI}
        ) == []

    def test_a_record_without_a_store_is_free(self):
        assert _errores([_fila("NEIVA", "MC001")], {"MC001": None}) == []

    def test_released_when_its_store_changes_principal_in_the_file(self):
        filas = [_fila("CALI", "BA099", CALI), _fila("NEIVA", "BA061")]

        assert _errores(filas, {"BA061": CALI}) == []

    def test_released_when_its_store_stops_listing_it(self):
        filas = [
            _fila("PASTO", "BP001", PASTO, **{
                bodegas_secundarias.FILA_CLAVE: [],
            }),
            _fila("NEIVA", "MC001"),
        ]

        assert _errores(filas, {"MC001": PASTO}) == []

    def test_still_listed_as_secondary_is_not_released(self):
        filas = [
            _fila("PASTO", "BP001", PASTO, **{
                bodegas_secundarias.FILA_CLAVE: ["MC001"],
            }),
            _fila("NEIVA", "MC001"),
        ]

        assert _errores(filas, {"MC001": PASTO}) == [
            {"fila": 2, "motivo": _motivo("MC001", "PASTO")},
        ]

    def test_two_stores_swap_principals(self):
        filas = [_fila("CALI", "BP001", CALI), _fila("PASTO", "BA061", PASTO)]

        assert _errores(filas, {"BA061": CALI, "BP001": PASTO}) == []

    async def test_no_principal_means_no_query(self):
        db = FakeAsyncSession(execute_queue=[])

        _, errores = await bodegas_secundarias.resolver_filas(
            db, [{"nombre": "CALI", "bodega_principal": " "}]
        )

        assert errores == []

    async def test_the_resolver_checks_the_principal(self):
        db = FakeAsyncSession(execute_queue=[GUARDADAS, [("BA061", CALI)]])

        _, errores = await bodegas_secundarias.resolver_filas(
            db, [_fila("NEIVA", "BA061")]
        )

        assert errores == [{"fila": 1, "motivo": _motivo("BA061", "CALI")}]


class TestForm:
    async def test_another_stores_principal_is_rejected(self):
        tienda = Sucursal(
            id=uuid.uuid4(), nombre="NEIVA", codigo_co="E07",
            bodega_principal="BA061",
        )
        db = FakeAsyncSession(execute_queue=[
            [("CALI", "BA061")], [("BA061", CALI, "CALI")],
        ])

        with pytest.raises(
            bodegas_secundarias.BodegasSecundariasInvalidasError
        ) as error:
            await bodegas_secundarias.guardar_de_sucursal(
                db, tienda, None, USER_ID
            )

        assert str(error.value) == _motivo("BA061", "CALI")


class TestRawPrincipalId:
    async def test_is_dropped_without_the_named_column(self):
        db = FakeAsyncSession(execute_queue=[])

        filas, errores = await sucursal_grupo.resolver_filas(
            db, [{"nombre": "CALI", "principal_id": str(PASTO)}]
        )

        assert errores == []
        assert "principal_id" not in filas[0]
