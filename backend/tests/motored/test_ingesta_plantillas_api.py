"""
Server-generated `.xlsx` templates for the 6 movement upload types:
`GET /api/motored/cargas/{tipo}/plantilla.xlsx`. Headers come from the
backend's own column definitions (`plantillas.columnas_plantilla`), the same
tuples the upload path uses to verify and parse a file, so a template can
never drift from what the backend accepts. Round-trip: a downloaded template
passes type verification and header/column mapping.
"""
import io
import uuid

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import cargas as cargas_api
from app.motored.services.auth import MotoredUser
from app.motored.services.ingesta import columnas, deteccion, orquestador, plantillas
from tests.motored.conftest import override_motored_user


def _url(tipo: str) -> str:
    return f"/api/motored/cargas/{tipo}/plantilla.xlsx"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "plantilla-cargas-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "plantilla-cargas-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    yield
    app.dependency_overrides.clear()


def _filas(content: bytes):
    workbook = openpyxl.load_workbook(io.BytesIO(content))
    try:
        return [[c.value for c in fila] for fila in workbook.active.iter_rows()]
    finally:
        workbook.close()


def _descargar(tipo: str):
    with TestClient(app) as client:
        return client.get(_url(tipo))


@pytest.mark.parametrize("tipo", orquestador.TIPOS_MOVIMIENTO)
def test_plantilla_devuelve_un_xlsx_con_el_encabezado_del_backend(tipo):
    response = _descargar(tipo)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"] == (
        f'attachment; filename="plantilla_{tipo.lower()}.xlsx"'
    )
    assert _filas(response.content) == [list(plantillas.columnas_plantilla(tipo))]


def test_plantilla_de_backorder_incluye_la_columna_opcional_fecha_creacion():
    header = _filas(_descargar("BACKORDER").content)[0]

    assert header[-1] == "Fecha Creación"
    assert header[:-1] == list(orquestador._COLUMNAS_POR_TIPO["BACKORDER"])


@pytest.mark.parametrize("tipo", orquestador.TIPOS_MOVIMIENTO)
def test_columnas_de_la_plantilla_son_las_que_el_orquestador_espera(tipo):
    opcionales = deteccion.COLUMNAS_OPCIONALES_POR_TIPO.get(tipo, ())
    esperado = orquestador._COLUMNAS_POR_TIPO[tipo] + opcionales

    assert plantillas.columnas_plantilla(tipo) == esperado


@pytest.mark.parametrize("tipo", orquestador.TIPOS_MOVIMIENTO)
def test_la_plantilla_descargada_pasa_la_verificacion_de_tipo_y_el_mapeo_de_columnas(tipo):
    content = _descargar(tipo).content

    cargas_api._verificar_tipo_o_400(tipo, content)  # no debe lanzar
    muestra = deteccion.extraer_filas_muestra(
        content, columnas_esperadas=deteccion.columnas_esperadas_de(tipo)
    )
    mapa = columnas.construir_mapa_columnas(
        muestra[0], plantillas.columnas_plantilla(tipo)
    )
    assert set(mapa) == set(plantillas.columnas_plantilla(tipo))


@pytest.mark.parametrize("tipo", ["MAESTRO_REFERENCIAS", "MAESTRO_BODEGAS", "NO_EXISTE", "ventas"])
def test_plantilla_de_un_tipo_desconocido_o_de_maestro_es_404(tipo):
    assert _descargar(tipo).status_code == 404


def test_plantilla_rechaza_un_rol_sin_permiso_de_escritura_con_403():
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="CONSULTA"))

    assert _descargar("VENTAS").status_code == 403


def test_plantilla_permite_el_rol_compras():
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="COMPRAS"))

    assert _descargar("INVENTARIO").status_code == 200


def test_la_plantilla_de_inventario_trae_el_costo_promedio_como_ultima_columna():
    encabezado = _filas(_descargar("INVENTARIO").content)[0]

    assert tuple(encabezado) == (
        "Referencia", "Bodega", "Desc.bodega", "Existencia", "Costo prom. uni."
    )
