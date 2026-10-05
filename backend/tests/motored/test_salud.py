"""
Phase 3 "Models/Schemas/Services" — task 3.5 (sdd/motored-pedidos-cimientos).

`services/salud.py`: tablero de salud de maestros. `sucursal` sin `sic` es
el ÚNICO defecto BLOQUEANTE; todo lo demás (referencia activa sin precio,
`unidad_empaque` corregido, bodega sin sucursal) es ADVERTENCIA, nunca
bloqueante (spec "Masters health board").
"""
import uuid

from app.motored.models.bodega import Bodega
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.services import salud
from tests.motored.conftest import FakeAsyncSession


class TestSucursalSinSicIsBlocking:
    async def test_sucursal_without_sic_is_a_blocking_finding(self):
        sucursal = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE", sic=None, activa=True)
        db = FakeAsyncSession(execute_queue=[[sucursal], [], [], []])

        resultado = await salud.evaluar_salud(db)

        assert resultado.estado == "bloqueado"
        bloqueantes = [h for h in resultado.hallazgos if h.bloqueante]
        assert len(bloqueantes) == 1
        assert bloqueantes[0].entidad == "sucursal"


class TestWarningsNeverBlock:
    async def test_referencia_without_price_is_warning_not_blocking(self):
        referencia = Referencia(
            id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(),
            unidad_empaque=1, precio_normal=None, activa=True,
        )
        db = FakeAsyncSession(execute_queue=[[], [referencia], [], []])

        resultado = await salud.evaluar_salud(db)

        assert resultado.estado == "advertencia"
        assert all(not h.bloqueante for h in resultado.hallazgos)

    async def test_bodega_without_sucursal_is_warning_not_blocking(self):
        bodega = Bodega(id=uuid.uuid4(), codigo="BA061", sucursal_id=None, activa=True)
        db = FakeAsyncSession(execute_queue=[[], [], [], [bodega]])

        resultado = await salud.evaluar_salud(db)

        assert resultado.estado == "advertencia"
        assert all(not h.bloqueante for h in resultado.hallazgos)

    async def test_unidad_empaque_coerced_reference_is_warning_not_blocking(self):
        referencia = Referencia(
            id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(),
            unidad_empaque=1, unidad_empaque_advertencia=True, precio_normal=100, activa=True,
        )
        db = FakeAsyncSession(execute_queue=[[], [], [referencia], []])

        resultado = await salud.evaluar_salud(db)

        assert resultado.estado == "advertencia"
        assert all(not h.bloqueante for h in resultado.hallazgos)


class TestGreenBoard:
    async def test_no_findings_is_green(self):
        db = FakeAsyncSession(execute_queue=[[], [], [], []])

        resultado = await salud.evaluar_salud(db)

        assert resultado.estado == "verde"
        assert resultado.hallazgos == []


def _tienda(nombre, activa=True, principal_id=None, sic="S1"):
    return Sucursal(
        id=uuid.uuid4(), nombre=nombre, sic=sic, activa=activa,
        principal_id=principal_id,
    )


def _por_tipo(resultado, tipo):
    return [h for h in resultado.hallazgos if h.tipo == tipo]


class TestAssociatedStores:
    async def test_associated_store_does_not_need_a_sic(self):
        principal = _tienda("LA 33")
        asociada = _tienda(
            "EXPO 2", activa=False, principal_id=principal.id, sic=None
        )
        db = FakeAsyncSession(
            execute_queue=[[principal, asociada], [], [], []]
        )

        resultado = await salud.evaluar_salud(db)

        assert _por_tipo(resultado, "sucursal_sin_sic") == []
        assert resultado.estado == "verde"

    async def test_inactive_store_without_sic_is_not_reported(self):
        db = FakeAsyncSession(
            execute_queue=[[_tienda("CERRADA", activa=False, sic=None)],
                           [], [], []]
        )

        resultado = await salud.evaluar_salud(db)

        assert resultado.estado == "verde"

    async def test_inactive_principal_is_a_warning(self):
        principal = _tienda("LA 33", activa=False)
        asociada = _tienda(
            "EXPO 2", activa=False, principal_id=principal.id
        )
        db = FakeAsyncSession(
            execute_queue=[[principal, asociada], [], [], []]
        )

        resultado = await salud.evaluar_salud(db)

        avisos = _por_tipo(resultado, "asociada_principal_inactiva")
        assert len(avisos) == 1
        assert avisos[0].entidad_id == asociada.id
        assert avisos[0].bloqueante is False
        assert "'EXPO 2'" in avisos[0].mensaje
        assert "LA 33" in avisos[0].mensaje
        assert resultado.estado == "advertencia"

    async def test_active_associated_store_is_a_warning(self):
        principal = _tienda("LA 33")
        asociada = _tienda("EXPO 2", principal_id=principal.id)
        db = FakeAsyncSession(
            execute_queue=[[principal, asociada], [], [], []]
        )

        resultado = await salud.evaluar_salud(db)

        avisos = _por_tipo(resultado, "asociada_activa")
        assert [h.entidad_id for h in avisos] == [asociada.id]
        assert avisos[0].bloqueante is False
        assert "pedido" in avisos[0].mensaje
        assert resultado.estado == "advertencia"
