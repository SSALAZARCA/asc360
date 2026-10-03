"""
Motored `motored-referencia-identidad` (R2): superficie HTTP del reemplazo
completo de referencias. `/validar` y `/excel/validar` devuelven
`resumen_reemplazo`; aplicar (`""` y `/excel`) exige `confirmar_reemplazo` y,
si el resumen lo pide, `confirmar_inactivacion_masiva` (409 si falta).
R3: las ausentes se listan completas y solo se desactivan las de
`codigos_inactivar` (JSON; en `/excel`, campo de formulario con una lista JSON).
"""
import io
import uuid

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

BASE = "/api/motored/maestros/referencia/carga"
HMCL = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", es_principal=True)


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "reemplazo-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "reemplazo-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    yield
    app.dependency_overrides.clear()


def _ref(codigo, activa=True):
    return Referencia(id=uuid.uuid4(), codigo=codigo, proveedor_id=HMCL.id, unidad_empaque=1,
                      activa=activa, homologados=[])


def _session(referencias, con_actividad=False):
    # probe, proveedor (codigos), plan: referencias, proveedores [+ ventas, ultimo corte]
    cola = [[], [HMCL], list(referencias), [HMCL]]
    if con_actividad:
        cola += [[], [None]]
    return FakeAsyncSession(execute_queue=cola)


def _xlsx(filas):
    wb = openpyxl.Workbook()
    wb.active.append(["Código", "Código del proveedor"])
    for fila in filas:
        wb.active.append(fila)
    buffer = io.BytesIO()
    wb.save(buffer)
    return {"file": ("r.xlsx", buffer.getvalue(),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


FILAS = [{"codigo": "A", "proveedor_codigo": "HMCL"}]


def test_validar_devuelve_el_resumen_del_reemplazo_y_no_escribe():
    session = _session([_ref("A"), _ref("B")], con_actividad=True)
    override_motored_db(session)

    with TestClient(app) as client:
        body = client.post(BASE + "/validar", json={"filas": FILAS}).json()

    resumen = body["resumen_reemplazo"]
    assert body["ok"] is True
    assert resumen["ausentes"]["total"] == 1 and resumen["ausentes"]["items"][0]["codigo"] == "B"
    assert resumen["ausentes"]["items"][0]["proveedor"] == "HMCL"
    assert resumen["requiere_doble_confirmacion"] is False and resumen["pct_inactivar"] == 0
    assert resumen["pct_inactivar_si_todas"] == 0.5 and resumen["activas_actuales"] == 2
    assert session.committed is False and session.added_of_type(Referencia) == []


def test_validar_con_demasiadas_ausentes_es_422_con_mensaje(monkeypatch):
    from app.motored.services import reemplazo_referencias
    monkeypatch.setattr(reemplazo_referencias, "AUSENTES_MAX", 1)
    override_motored_db(_session([_ref("A"), _ref("B"), _ref("C")], con_actividad=True))

    with TestClient(app) as client:
        response = client.post(BASE + "/validar", json={"filas": FILAS})

    assert response.status_code == 422 and "ausentes" in response.json()["detail"].lower()


def test_validar_excel_devuelve_el_resumen_del_reemplazo():
    session = _session([_ref("A")])
    override_motored_db(session)

    with TestClient(app) as client:
        body = client.post(BASE + "/excel/validar", files=_xlsx([["A", "HMCL"], ["NUEVA", "HMCL"]])).json()

    assert body["ok"] is True
    assert body["resumen_reemplazo"]["crear"]["total"] == 1
    assert body["resumen_reemplazo"]["requiere_doble_confirmacion"] is False


def test_validar_con_error_de_fila_no_devuelve_resumen():
    session = _session([_ref("AB-1")])
    override_motored_db(session)
    filas = [{"codigo": "ab-1", "proveedor_codigo": "HMCL"}]

    with TestClient(app) as client:
        body = client.post(BASE + "/validar", json={"filas": filas}).json()

    assert body["ok"] is False and body["resumen_reemplazo"] is None and body["errores"][0]["fila"] == 1


def test_aplicar_sin_confirmar_el_reemplazo_es_409():
    session = _session([_ref("A")])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(BASE, json={"filas": FILAS})

    assert response.status_code == 409 and "reemplazo" in response.json()["detail"].lower()
    assert session.committed is False


def test_aplicar_excel_sin_confirmar_el_reemplazo_es_409():
    session = _session([_ref("A")])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(BASE + "/excel", files=_xlsx([["A", "HMCL"]]))

    assert response.status_code == 409 and session.committed is False


def test_aplicar_sin_elegir_ausentes_no_desactiva_nada():
    referencias = [_ref("A"), _ref("B")]
    session = _session(referencias, con_actividad=True)
    override_motored_db(session)

    with TestClient(app) as client:
        body = client.post(BASE, json={"filas": FILAS, "confirmar_reemplazo": True}).json()

    assert body["ok"] is True and body["resumen_reemplazo"]["seleccionadas"] == 0
    assert all(r.activa for r in referencias) and session.committed is True


def test_aplicar_con_un_codigo_que_no_es_ausente_es_409():
    referencias = [_ref("A"), _ref("B")]
    session = _session(referencias, con_actividad=True)
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(BASE, json={
            "filas": FILAS, "confirmar_reemplazo": True, "codigos_inactivar": ["A"]})

    assert response.status_code == 409 and "ausente" in response.json()["detail"].lower()
    assert all(r.activa for r in referencias) and session.committed is False


def test_aplicar_con_desactivacion_masiva_exige_la_segunda_confirmacion():
    referencias = [_ref("A"), _ref("B")]
    session = _session(referencias, con_actividad=True)
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(BASE, json={
            "filas": FILAS, "confirmar_reemplazo": True, "codigos_inactivar": ["B"]})

    assert response.status_code == 409 and "50%" in response.json()["detail"]
    assert all(r.activa for r in referencias) and session.committed is False


def test_aplicar_con_las_dos_confirmaciones_desactiva_las_ausentes():
    referencias = [_ref("A"), _ref("B")]
    session = _session(referencias, con_actividad=True)
    override_motored_db(session)

    with TestClient(app) as client:
        body = client.post(BASE, json={
            "filas": FILAS, "confirmar_reemplazo": True, "confirmar_inactivacion_masiva": True,
            "codigos_inactivar": ["B"]}).json()

    assert body["ok"] is True and body["resumen_reemplazo"]["seleccionadas"] == 1
    assert [r.activa for r in referencias] == [True, False] and session.committed is True


def test_aplicar_excel_con_las_confirmaciones_por_query_y_los_codigos_en_el_formulario():
    referencias = [_ref("A"), _ref("B"), _ref("C")]
    session = _session(referencias, con_actividad=True)
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            BASE + "/excel?confirmar_reemplazo=true&confirmar_inactivacion_masiva=true",
            files=_xlsx([["A", "HMCL"]]), data={"codigos_inactivar": '["B"]'})

    assert response.status_code == 200 and response.json()["ok"] is True
    assert [r.activa for r in referencias] == [True, False, True]


def test_aplicar_excel_con_codigos_que_no_son_una_lista_json_es_422():
    session = _session([_ref("A"), _ref("B")], con_actividad=True)
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            BASE + "/excel?confirmar_reemplazo=true",
            files=_xlsx([["A", "HMCL"]]), data={"codigos_inactivar": "B"})

    assert response.status_code == 422 and session.committed is False


def test_otras_entidades_ignoran_las_banderas_y_no_piden_confirmacion():
    session = FakeAsyncSession(execute_queue=[[], []])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post("/api/motored/maestros/sucursal/carga", json={"filas": [{"nombre": "CALI"}]})

    assert response.status_code == 200 and response.json()["ok"] is True
