"""
Motored `motored-referencia-identidad` (R1): la carga masiva de referencias
identifica por CODIGO. Los codigos del archivo se recortan, un codigo repetido
en el archivo es error de fila (seria ambiguo a que proveedor pertenece) y una
referencia que cambia de proveedor se mueve y reporta los vinculos quitados.
"""
import uuid

from app.motored.api.carga import _resolve_referencia_relaciones
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.services import carga
from tests.motored.conftest import FakeAsyncSession

HMCL = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", es_principal=True)
OTRO = Proveedor(id=uuid.uuid4(), codigo="OTRO", nombre="Otro", es_principal=False)


async def test_los_codigos_del_archivo_se_recortan_antes_de_resolver():
    session = FakeAsyncSession(execute_queue=[[HMCL], []])  # proveedores; candidatas de sustituta
    filas = [{"codigo": " R-1 ", "proveedor_codigo": "HMCL", "sustituida_por_codigo": " R-2"},
             {"codigo": "R-2 ", "proveedor_codigo": "HMCL"}]

    resolved, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

    assert errores == []
    assert [f["codigo"] for f in resolved] == ["R-1", "R-2"]
    assert resolved[0]["_sustituta_codigo_en_archivo"] == "R-2"


async def test_un_codigo_repetido_en_el_archivo_es_error_de_fila_aunque_cambie_el_proveedor():
    session = FakeAsyncSession(execute_queue=[[HMCL, OTRO]])
    filas = [{"codigo": "R-1", "proveedor_codigo": "HMCL"},
             {"codigo": "OTRA", "proveedor_codigo": "HMCL"},
             {"codigo": "R-1 ", "proveedor_codigo": "OTRO"}]

    _, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

    assert [e["fila"] for e in errores] == [3]
    assert "R-1" in errores[0]["motivo"] and "fila 1" in errores[0]["motivo"]


async def test_cargar_una_referencia_con_otro_proveedor_la_mueve_y_avisa_los_vinculos_quitados():
    movida = Referencia(id=uuid.uuid4(), codigo="NUEVA", proveedor_id=HMCL.id,
                        unidad_empaque=1, activa=True, homologados=[])
    vieja = Referencia(id=uuid.uuid4(), codigo="VIEJA", proveedor_id=HMCL.id, unidad_empaque=1,
                       activa=False, homologados=[], sustituida_por=movida.id)
    session = FakeAsyncSession(execute_queue=[[movida, vieja], [HMCL, OTRO]])  # plan: referencias, proveedores
    filas = [{"codigo": "NUEVA", "proveedor_id": OTRO.id, "proveedor_codigo": "OTRO"}]

    resultado = await carga.procesar_carga(session, "referencia", filas, confirmar_reemplazo=True)

    assert resultado.ok and resultado.actualizados == 1 and resultado.insertados == 0
    assert movida.proveedor_id == OTRO.id and vieja.sustituida_por is None
    assert session.added_of_type(Referencia) == []
    assert resultado.resumen_reemplazo.vinculos_sustituta_limpiados.total == 1


async def test_un_codigo_repetido_ignorando_mayusculas_tambien_es_error_de_fila():
    session = FakeAsyncSession(execute_queue=[[HMCL]])
    filas = [{"codigo": "R-1", "proveedor_codigo": "HMCL"}, {"codigo": "r-1", "proveedor_codigo": "HMCL"}]

    _, errores = await _resolve_referencia_relaciones(session, "referencia", filas)

    assert [e["fila"] for e in errores] == [2]
