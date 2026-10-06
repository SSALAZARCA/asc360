"""
Associated stores (`sucursal.principal_id`): the group helpers and the
depth-1 rules the CRUD enforces.

A store either is its own principal (NULL) or points at a principal that
is itself a principal. It can never point at itself, at an associated
store, and a store that already has associated stores cannot be
associated. Setting NULL dissociates. The change is audited as a field
change.
"""
import uuid

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.sucursal import (
    SucursalCreate,
    SucursalRead,
    SucursalUpdate,
)
from app.motored.services import maestros, sucursal_grupo
from tests.motored.conftest import FakeAsyncSession

USER_ID = uuid.uuid4()
A, B, C, D = (uuid.uuid4() for _ in range(4))


def _sucursal(nombre="EXPO 2", principal_id=None):
    return Sucursal(
        id=uuid.uuid4(), nombre=nombre, principal_id=principal_id,
        activa=True,
    )


def _auditorias(db):
    return [
        (a.campo, a.valor_anterior, a.valor_nuevo)
        for a in db.added_of_type(AuditoriaMaestro)
    ]


class TestPrincipalDe:
    async def test_maps_every_store_to_its_effective_principal(self):
        db = FakeAsyncSession(
            execute_queue=[[(A, None), (B, A), (C, None), (D, A)]]
        )

        mapa = await sucursal_grupo.principal_de(db)

        assert mapa == {A: A, B: A, C: C, D: A}

    def test_group_lists_the_principal_first(self):
        mapa = {A: A, B: A, C: C, D: A}

        grupo = sucursal_grupo.grupo_de(mapa, A)

        assert grupo[0] == A
        assert sorted(grupo[1:], key=str) == sorted([B, D], key=str)
        assert sucursal_grupo.grupo_de(mapa, C) == [C]

    def test_group_of_an_unknown_principal_is_just_itself(self):
        assert sucursal_grupo.grupo_de({}, A) == [A]

    def test_sql_expression_coalesces_principal_and_id(self):
        sql = str(
            sucursal_grupo.principal_efectivo_expr().compile(
                dialect=postgresql.dialect()
            )
        )

        assert "coalesce(sucursal.principal_id, sucursal.id)" in sql


class TestMotivoAsociacion:
    def test_valid_association_has_no_reason(self):
        assert sucursal_grupo.motivo_asociacion(
            "EXPO 2", "LA 33", misma=False, principal_asociada_a=None,
            asociadas=[],
        ) is None

    def test_self_reference(self):
        motivo = sucursal_grupo.motivo_asociacion(
            "LA 33", "LA 33", misma=True, principal_asociada_a=None,
            asociadas=[],
        )

        assert "su propia tienda principal" in motivo

    def test_target_that_is_itself_associated(self):
        motivo = sucursal_grupo.motivo_asociacion(
            "EXPO 2", "EXPO 1", misma=False, principal_asociada_a="LA 33",
            asociadas=[],
        )

        assert "'EXPO 1'" in motivo
        assert "'LA 33'" in motivo

    def test_store_that_already_has_associated_stores(self):
        motivo = sucursal_grupo.motivo_asociacion(
            "LA 33", "CENTRO", misma=False, principal_asociada_a=None,
            asociadas=["EXPO 2", "EXPO 1"],
        )

        assert "'LA 33'" in motivo
        assert "EXPO 1, EXPO 2" in motivo


class TestValidarPrincipal:
    async def test_none_never_queries(self):
        db = FakeAsyncSession(execute_queue=[])

        await sucursal_grupo.validar_principal(db, _sucursal(), None)

    async def test_self_is_rejected_without_queries(self):
        sucursal = _sucursal()
        db = FakeAsyncSession(execute_queue=[])

        with pytest.raises(sucursal_grupo.PrincipalInvalidaError):
            await sucursal_grupo.validar_principal(
                db, sucursal, sucursal.id
            )

    async def test_nonexistent_target(self):
        db = FakeAsyncSession(execute_queue=[[]])

        with pytest.raises(
            sucursal_grupo.PrincipalInvalidaError, match="no existe"
        ):
            await sucursal_grupo.validar_principal(db, None, A)

    async def test_target_already_associated(self):
        db = FakeAsyncSession(execute_queue=[[(A, "EXPO 1", "LA 33")]])

        with pytest.raises(
            sucursal_grupo.PrincipalInvalidaError, match="LA 33"
        ):
            await sucursal_grupo.validar_principal(db, None, A)

    async def test_store_with_associated_stores(self):
        db = FakeAsyncSession(
            execute_queue=[[(A, "CENTRO", None)], [("EXPO 2",)]]
        )

        with pytest.raises(
            sucursal_grupo.PrincipalInvalidaError, match="EXPO 2"
        ):
            await sucursal_grupo.validar_principal(
                db, _sucursal("LA 33"), A
            )

    async def test_valid_target(self):
        db = FakeAsyncSession(execute_queue=[[(A, "LA 33", None)], []])

        await sucursal_grupo.validar_principal(db, _sucursal(), A)


class TestCrud:
    async def test_create_with_a_principal_validates_and_stores_it(self):
        # principal, then the C.O. is free
        db = FakeAsyncSession(execute_queue=[[(A, "LA 33", None)], []])

        creada = await maestros.create_sucursal(
            db, SucursalCreate(nombre="EXPO 2", codigo_co="E12",
                               principal_id=A),
            USER_ID,
        )

        assert creada.principal_id == A

    async def test_create_with_an_associated_target_is_rejected(self):
        db = FakeAsyncSession(execute_queue=[[(A, "EXPO 1", "LA 33")]])

        with pytest.raises(sucursal_grupo.PrincipalInvalidaError):
            await maestros.create_sucursal(
                db, SucursalCreate(nombre="EXPO 2", codigo_co="E12",
                                   principal_id=A),
                USER_ID,
            )
        assert db.added_of_type(Sucursal) == []

    async def test_update_associates_and_audits_the_field(self):
        sucursal = _sucursal()
        db = FakeAsyncSession(execute_queue=[[(A, "LA 33", None)], []])

        await maestros.update_sucursal(
            db, sucursal, SucursalUpdate(principal_id=A), USER_ID
        )

        assert sucursal.principal_id == A
        assert _auditorias(db) == [("principal_id", None, str(A))]

    async def test_update_to_none_dissociates_without_queries(self):
        sucursal = _sucursal(principal_id=A)
        db = FakeAsyncSession(execute_queue=[])

        await maestros.update_sucursal(
            db, sucursal, SucursalUpdate(principal_id=None), USER_ID
        )

        assert sucursal.principal_id is None
        assert _auditorias(db) == [("principal_id", str(A), None)]

    async def test_update_with_the_same_principal_skips_validation(self):
        sucursal = _sucursal(principal_id=A)
        db = FakeAsyncSession(execute_queue=[])

        await maestros.update_sucursal(
            db, sucursal, SucursalUpdate(principal_id=A), USER_ID
        )

        assert sucursal.principal_id == A

    async def test_update_rejects_a_principal_with_associated_stores(self):
        sucursal = _sucursal("LA 33")
        db = FakeAsyncSession(
            execute_queue=[[(B, "CENTRO", None)], [("EXPO 2",)]]
        )

        with pytest.raises(sucursal_grupo.PrincipalInvalidaError):
            await maestros.update_sucursal(
                db, sucursal, SucursalUpdate(principal_id=B), USER_ID
            )
        assert sucursal.principal_id is None

    def test_read_schema_exposes_the_principal(self):
        leida = SucursalRead.model_validate(
            Sucursal(
                id=B, nombre="EXPO 2", codigo_co="E02", principal_id=A,
                activa=True, dias_seguridad=2.5,
            )
        )

        assert leida.principal_id == A
