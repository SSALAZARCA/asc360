"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B4, ADR-7, spec
EX-01, EX-02, EX-06..EX-13, EX-15, decisión F4-1): el contrato HTTP de
exportar el pedido a HMCL, de una tienda (`.xlsx`) y de la corrida (`.zip`).

La lectura de los datos se reemplaza por dobles que graban sus argumentos
(`tests/motored/fixtures/corridas_api.py`); los constructores del archivo
corren de verdad y el cuerpo de la respuesta se ABRE (openpyxl, zipfile): lo
que se prueba es qué recibe quien descarga, con qué nombre, y que un
rechazo codificado (404, 409) no devuelve ningún archivo. Las reglas están
en `test_exportacion_servicio.py`, el archivo en `test_exportacion_hmcl.py`
y contra Postgres real en `pg_real/test_exportacion_pg.py`. El RBAC de
cada ruta, en `test_corridas_rbac.py`.
"""
import datetime
import io
import json
import tempfile
import uuid
import zipfile
from decimal import Decimal
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.config import settings
from app.main import app
from app.motored.api import corridas as api
from app.motored.api import corridas_comun as comun
from app.motored.api import corridas_pedido as api_pedido
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import codigos
from app.motored.services.corridas.codigos import ErrorCorrida
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)
from tests.motored.fixtures import corridas_api as fx

BASE = "/api/motored/corridas"
USUARIO = str(uuid.UUID(int=900))
CORRIDA = fx.CORRIDA_ID
TIENDA = f"{BASE}/{CORRIDA}/sucursales/{fx.SUC_A}/exportar"
ZIP = f"{BASE}/{CORRIDA}/exportar"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RECHAZOS = [
    codigos.E_CORRIDA_ESTADO_NO_ADMITE,
    codigos.E_CORRIDA_INVALIDADA,
    codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA,
    codigos.E_CORRIDA_SIN_PEDIDO,
    codigos.E_CORRIDA_EXPORTAR_NO_CERRADO,
    codigos.E_CORRIDA_NADA_QUE_ENVIAR,
    codigos.E_CORRIDA_EXPORTAR_SIN_SIC,
]


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "export-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "export-asc360")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def espia(monkeypatch):
    doble = fx.instalar(monkeypatch)
    app.dependency_overrides[api.get_corrida_runner] = (
        lambda: fx.RunnerDoble(doble))
    return doble


def _cliente(rol="COMPRAS"):
    sesion = FakeAsyncSession(execute_queue=[[]] * 8)
    override_motored_user(MotoredUser(user_id=USUARIO, role=rol))
    override_motored_db(sesion)
    return TestClient(app), sesion


def _rechazo(codigo, mensaje="no se puede", detalle=None):
    return ErrorCorrida(codigo, mensaje, detalle)


# --- GET .../sucursales/{sid}/exportar ---------------------------------------


def test_exporting_one_tienda_downloads_its_xlsx_ex_01(espia):
    cliente, sesion = _cliente()

    respuesta = cliente.get(TIENDA)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"] == XLSX
    hoja = load_workbook(io.BytesIO(respuesta.content))["Pedido"]
    assert [[c.value for c in fila] for fila in hoja.iter_rows()][:7] == [
        ["Tienda", "Manizales"], ["SIC", "1234"],
        ["Fecha", datetime.datetime(2026, 9, 21)],
        [None, None], ["Código", "Cantidad"],
        ["00123-AB", 12], ["94109-12000S", 50]]
    assert espia.ultima("exportar_tienda")[1] == (CORRIDA, fx.SUC_A)
    assert sesion.committed is True


def test_the_download_carries_the_f4_1_name_in_both_header_forms(espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(TIENDA)

    assert respuesta.headers["content-disposition"] == (
        'attachment; filename="Pedido_SIC1234_Manizales_2026-09-21.xlsx"; '
        "filename*=UTF-8''Pedido_SIC1234_Manizales_2026-09-21.xlsx")


def test_an_accented_tienda_name_gives_the_ascii_file_name_ex_14(espia):
    espia.datos_tienda = fx.datos_exportacion("Medellín Poblado", "77")
    cliente, _ = _cliente()

    respuesta = cliente.get(TIENDA)

    assert 'filename="Pedido_SIC77_Medellin_Poblado_2026-09-21.xlsx"' in (
        respuesta.headers["content-disposition"])


def test_the_response_states_its_exact_size_and_is_never_cached(espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(TIENDA)

    assert int(respuesta.headers["content-length"]) == len(respuesta.content)
    assert respuesta.headers["cache-control"] == "no-store"


def test_a_code_that_looks_like_a_formula_is_downloaded_as_text(espia):
    espia.datos_tienda = fx.datos_exportacion(
        lineas=[("=HYPERLINK(\"http://x\")", Decimal("4.00")),
                ("000123", Decimal("2.00"))])
    cliente, _ = _cliente()

    respuesta = cliente.get(TIENDA)

    hoja = load_workbook(io.BytesIO(respuesta.content))["Pedido"]
    assert [(c.value, c.data_type) for c in hoja["A"][5:]] == [
        ("000123", "s"), ('=HYPERLINK("http://x")', "s")]


@pytest.mark.parametrize("codigo", RECHAZOS)
def test_a_refused_export_is_a_coded_409_with_no_file(espia, codigo):
    espia.error = ({"exportar_tienda"}, _rechazo(codigo))
    cliente, sesion = _cliente()

    respuesta = cliente.get(TIENDA)

    assert respuesta.status_code == 409
    assert respuesta.headers["content-type"] == "application/json"
    assert respuesta.json()["detail"] == {
        "code": codigo, "message": "no se puede"}
    assert sesion.committed is False and sesion.rolled_back is True


def test_the_refusal_detail_reaches_the_client(espia):
    espia.error = ({"exportar_tienda"}, _rechazo(
        codigos.E_CORRIDA_EXPORTAR_SIN_SIC, "Cali no tiene SIC",
        {"sucursal_id": str(fx.SUC_A), "tienda": "Cali"}))
    cliente, _ = _cliente()

    cuerpo = cliente.get(TIENDA).json()["detail"]

    assert cuerpo["detalle"] == {
        "sucursal_id": str(fx.SUC_A), "tienda": "Cali"}


def test_an_unknown_tienda_or_corrida_is_a_404(espia):
    espia.error = ({"exportar_tienda"}, LookupError("no existe"))
    cliente, sesion = _cliente()

    assert cliente.get(TIENDA).status_code == 404
    assert sesion.rolled_back is True


def test_the_book_is_built_in_a_worker_thread_and_the_temp_file_is_closed(
        espia, monkeypatch):
    hilos = []
    archivos = []

    async def en_hilo(funcion, *args):
        hilos.append(funcion.__name__)
        archivo, tamano = funcion(*args)
        archivos.append(archivo)
        return archivo, tamano

    monkeypatch.setattr(api_pedido, "run_in_threadpool", en_hilo)
    cliente, _ = _cliente()

    respuesta = cliente.get(TIENDA)

    assert respuesta.status_code == 200
    assert hilos == ["construir_xlsx"]
    assert len(archivos) == 1 and archivos[0].closed is True


def test_a_malformed_tienda_id_is_a_422_and_reads_nothing(espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(f"{BASE}/{CORRIDA}/sucursales/no-es-uuid/exportar")

    assert respuesta.status_code == 422 and espia.llamadas == []


# --- GET /{id}/exportar (zip) ------------------------------------------------


def _paquete(respuesta):
    return zipfile.ZipFile(io.BytesIO(respuesta.content))


def test_exporting_the_corrida_downloads_a_zip_with_one_file_per_tienda_ex_02(
        espia):
    cliente, sesion = _cliente()

    respuesta = cliente.get(ZIP)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"] == "application/zip"
    paquete = _paquete(respuesta)
    assert paquete.namelist() == [
        "Pedido_SIC1234_Manizales_2026-09-21.xlsx",
        "Pedido_SIC77_Medellin_Poblado_2026-09-21.xlsx"]
    hoja = load_workbook(io.BytesIO(paquete.read(paquete.namelist()[1])))
    assert hoja["Pedido"]["A6"].value == "55512-A"
    assert hoja["Pedido"]["B6"].value == 7
    assert espia.ultima("exportar_corrida")[1] == (CORRIDA, None)
    assert sesion.committed is True


def test_the_zip_name_and_size_are_in_the_headers(espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(ZIP)

    assert respuesta.headers["content-disposition"] == (
        'attachment; filename="Pedidos_PED-2026-S39-001_2026-09-21.zip"; '
        "filename*=UTF-8''Pedidos_PED-2026-S39-001_2026-09-21.zip")
    assert int(respuesta.headers["content-length"]) == len(respuesta.content)
    assert respuesta.headers["cache-control"] == "no-store"


def test_the_skipped_tiendas_travel_in_an_exposed_ascii_header_ex_02(espia):
    espia.seleccion = fx.seleccion_zip(omitidas=[{
        "sucursal_id": str(fx.SUC_B), "nombre": "Medellín",
        "codigo": "BORRADOR", "motivo": "El pedido sigue en BORRADOR"}])
    cliente, _ = _cliente()

    respuesta = cliente.get(ZIP)

    valor = respuesta.headers["x-tiendas-omitidas"]
    assert valor.isascii()
    assert json.loads(unquote(valor)) == [{
        "sucursal_id": str(fx.SUC_B), "nombre": "Medellín",
        "codigo": "BORRADOR", "motivo": "El pedido sigue en BORRADOR"}]
    expuestas = respuesta.headers["access-control-expose-headers"]
    assert {h.strip().lower() for h in expuestas.split(",")} == {
        "content-disposition", "x-tiendas-omitidas"}


def test_nothing_skipped_is_an_empty_list_not_a_missing_header(espia):
    espia.seleccion = fx.seleccion_zip(omitidas=[])
    cliente, _ = _cliente()

    respuesta = cliente.get(ZIP)

    assert json.loads(unquote(respuesta.headers["x-tiendas-omitidas"])) == []


def test_listed_tiendas_reach_the_service_as_uuids(espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(
        ZIP, params=[("sucursal_id", str(fx.SUC_A)),
                     ("sucursal_id", str(fx.SUC_B))])

    assert respuesta.status_code == 200
    assert espia.ultima("exportar_corrida")[1] == (
        CORRIDA, [fx.SUC_A, fx.SUC_B])


def test_a_malformed_listed_id_is_a_422_and_reads_nothing(espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(ZIP, params={"sucursal_id": "nada"})

    assert respuesta.status_code == 422 and espia.llamadas == []


@pytest.mark.parametrize("codigo", RECHAZOS)
def test_a_refused_zip_is_a_coded_409_with_no_file(espia, codigo):
    espia.error = ({"exportar_corrida"}, _rechazo(codigo))
    cliente, sesion = _cliente()

    respuesta = cliente.get(ZIP)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == codigo
    assert "x-tiendas-omitidas" not in respuesta.headers
    assert sesion.committed is False and sesion.rolled_back is True


def test_an_unknown_corrida_for_the_zip_is_a_404(espia):
    espia.error = ({"exportar_corrida"}, LookupError("no existe"))
    cliente, _ = _cliente()

    assert cliente.get(ZIP).status_code == 404


def test_the_zip_is_built_in_a_worker_thread_and_the_temp_file_is_closed(
        espia, monkeypatch):
    hilos = []
    archivos = []

    async def en_hilo(funcion, *args):
        hilos.append(funcion.__name__)
        archivo, tamano = funcion(*args)
        archivos.append(archivo)
        return archivo, tamano

    monkeypatch.setattr(api_pedido, "run_in_threadpool", en_hilo)
    cliente, _ = _cliente()

    respuesta = cliente.get(ZIP)

    assert respuesta.status_code == 200
    assert hilos == ["construir_zip"]
    assert len(archivos) == 1 and archivos[0].closed is True


def test_the_sucursal_id_filter_is_the_only_query_parameter_the_zip_reads(
        espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(ZIP, params={"limite": "1", "otro": "x"})

    assert respuesta.status_code == 200
    assert espia.ultima("exportar_corrida")[1] == (CORRIDA, None)


def test_the_temp_file_closes_even_if_the_client_stops_reading_mid_download():
    archivo = tempfile.SpooledTemporaryFile(max_size=1024)
    archivo.write(b"x" * (3 * comun.TAMANO_BLOQUE))
    archivo.seek(0)
    flujo = comun._bloques(archivo)

    assert len(next(flujo)) == comun.TAMANO_BLOQUE
    flujo.close()

    assert archivo.closed is True


def test_the_download_streams_every_byte_in_blocks():
    archivo = tempfile.SpooledTemporaryFile(max_size=1024)
    archivo.write(b"y" * (2 * comun.TAMANO_BLOQUE + 5))
    archivo.seek(0)

    bloques = list(comun._bloques(archivo))

    assert [len(b) for b in bloques] == [
        comun.TAMANO_BLOQUE, comun.TAMANO_BLOQUE, 5]
    assert archivo.closed is True
