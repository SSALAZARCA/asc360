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
