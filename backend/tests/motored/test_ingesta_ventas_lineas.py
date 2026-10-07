"""
VENTAS line rules (pure parts): the ERP type denylist, the class of a row by
its master line, the apply-time re-evaluation and the PUT guards/roles.
The end-to-end behavior against Postgres is in
`pg_real/test_ingesta_ventas_lineas_pg.py`.
"""
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.auth import MotoredUser
from app.motored.services.ingesta import ventas, ventas_lineas as vl
from app.motored.services.ingesta.resolucion import CacheResolucion
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

REGLAS = vl.compilar_excluidos([
    {"codigo": "IM19", "modo": "prefijo"},
    {"codigo": "ST003", "modo": "exacto"},
    {"codigo": " obs2 ", "modo": "exacto"},
])


@pytest.mark.parametrize("tipo, esperado", [
    ("IM19", True), ("IM1901", True), ("im19xx", True), ("  IM19 ", True),
    ("IM1", False), ("XIM19", False),
    ("ST003", True), (" st003 ", True), ("ST0031", False), ("ST00", False),
    ("OBS2", True), ("OBS", False),
    ("REPUE", False), ("", False), (None, False),
])
def test_denylist_prefix_vs_exact_ignoring_case_and_spaces(tipo, esperado):
    assert vl.es_tipo_excluido(tipo, REGLAS) is esperado


def test_empty_denylist_excludes_nothing():
    assert vl.es_tipo_excluido("IM1901", vl.compilar_excluidos([])) is False


@pytest.mark.parametrize("linea, clase", [
    ("REPUESTOS", vl.CLASE_INCLUIDA),
    ("MOTOS", vl.CLASE_FUERA_DE_LINEA),
    ("NO COMERCIAL", vl.CLASE_FUERA_DE_LINEA),
    ("", vl.CLASE_SIN_LINEA),
])
def test_class_of_a_row_by_its_master_line(linea, clase):
    assert vl.clasificar(linea, frozenset({"REPUESTOS"})) == clase


def test_line_normalization_matches_the_kpi_rule():
    assert vl.normalizar_linea("  Baterías ") == "BATERIAS"
    assert vl.normalizar_linea(None) == ""
    assert vl.normalizar_linea("   ") == ""


# --- procesar_fila ----------------------------------------------------------

REF = uuid.uuid4()
SUC = uuid.uuid4()
MAPA = {n: i for i, n in enumerate(ventas.COLUMNAS_ESPERADAS)}


def _procesar(tipo, linea="REPUESTOS", reglas=REGLAS, ref="R1"):
    fila = ("Aprobada", "MOSTRADOR", 46280, 5, tipo, "CALI", "BA061", ref,
            "Ana", 1000, 0, "Taller", "FV-1")
    return ventas.procesar_fila(
        fila, numero_fila=2, lote=1, mapa_columnas=MAPA,
        cache=CacheResolucion(
            sucursal_por_texto={"CALI": SUC, "BA061": SUC},
            referencia_por_codigo={"R1": (REF, uuid.uuid4())}),
        carga_id=uuid.uuid4(), proveedor_id=uuid.uuid4(),
        lineas_incluidas=["REPUESTOS"],
        linea_por_referencia={REF: linea} if linea else {},
        tipos_excluidos=reglas)


def test_an_excluded_erp_type_is_kept_only_for_the_detail_with_no_error():
    staging, errores = _procesar("IM1901")

    assert errores == []
    assert staging.payload["solo_detalle"] is True
    assert staging.payload[vl.CLAVE_CLASE_LINEA] == vl.CLASE_TIPO_EXCLUIDO
    assert (staging.sucursal_id, staging.referencia_id) == (SUC, REF)
    assert ventas.agregar_unidades([staging]) == {}
    assert ventas.construir_filas_por_periodo([staging]) == {}


@pytest.mark.parametrize("fila_mala", [
    {"ref": "NOEXISTE"},
])
def test_an_excluded_erp_type_that_cannot_be_staged_is_skipped_and_counted(fila_mala):
    assert _procesar("IM1901", **fila_mala) is vl.MarcaTipoExcluido.TIPO_EXCLUIDO


def test_denylist_wins_even_if_the_referencia_is_unknown():
    assert _procesar("ST003", ref="NOEXISTE") is vl.MarcaTipoExcluido.TIPO_EXCLUIDO


def test_the_erp_code_never_decides_the_line():
    staging, errores = _procesar("REPUE")  # a code, not a line name

    assert errores == []
    assert staging.payload[vl.CLAVE_CLASE_LINEA] == vl.CLASE_INCLUIDA
    assert "solo_detalle" not in staging.payload


def test_empty_master_line_is_staged_as_sin_linea_not_as_the_file_text():
    staging, errores = _procesar("REPUESTOS", linea="")

    assert errores == []
    assert staging.payload[vl.CLAVE_CLASE_LINEA] == vl.CLASE_SIN_LINEA
    assert staging.payload["solo_detalle"] is True


def test_a_sin_linea_row_stages_fully_resolved_like_an_included_row():
    sin_linea, _ = _procesar("REPUESTOS", linea="")
    incluida, _ = _procesar("REPUESTOS")

    quitar = {"solo_detalle", vl.CLAVE_CLASE_LINEA}
    assert ({k: v for k, v in sin_linea.payload.items() if k not in quitar}
            == {k: v for k, v in incluida.payload.items() if k not in quitar})
    assert (sin_linea.sucursal_id, sin_linea.referencia_id) == (SUC, REF)


def test_a_sin_linea_row_with_a_bad_date_gives_the_same_visible_error_as_an_included_one():
    fila = ("Aprobada", "MOSTRADOR", "no es fecha", 5, "REPUESTOS", "CALI",
            "BA061", "R1", "Ana", 1000, 0, "Taller", "FV-1")

    def procesar(linea):
        return ventas.procesar_fila(
            fila, numero_fila=2, lote=1, mapa_columnas=MAPA,
            cache=CacheResolucion(
                sucursal_por_texto={"CALI": SUC, "BA061": SUC},
                referencia_por_codigo={"R1": (REF, uuid.uuid4())}),
            carga_id=uuid.uuid4(), proveedor_id=uuid.uuid4(),
            lineas_incluidas=["REPUESTOS"], linea_por_referencia={REF: linea},
            tipos_excluidos=REGLAS)

    staging, errores = procesar("")
    _, errores_incluida = procesar("REPUESTOS")

    assert staging is None
    assert [e.codigo_error for e in errores] == [
        e.codigo_error for e in errores_incluida] != []


def test_a_sin_linea_row_with_an_unresolved_sucursal_keeps_the_visible_error():
    fila = ("Aprobada", "MOSTRADOR", 46280, 5, "REPUESTOS", "NOEXISTE", "ZZ",
            "R1", "Ana", 1000, 0, "Taller", "FV-1")
    staging, errores = ventas.procesar_fila(
        fila, numero_fila=2, lote=1, mapa_columnas=MAPA,
        cache=CacheResolucion(
            sucursal_por_texto={}, referencia_por_codigo={"R1": (REF, uuid.uuid4())}),
        carga_id=uuid.uuid4(), proveedor_id=uuid.uuid4(),
        lineas_incluidas=["REPUESTOS"], linea_por_referencia={},
        tipos_excluidos=REGLAS)

    assert len(errores) == 1
    assert staging.payload["solo_detalle"] is True


def test_unknown_referencia_keeps_the_existing_row_error():
    staging, errores = _procesar("REPUE", ref="NOEXISTE")

    assert [e.codigo_error for e in errores] == ["REFERENCIA_NO_ENCONTRADA"]
    assert staging.referencia_id is None


# --- reclasificar -----------------------------------------------------------


def _staged(clase, ref=REF, solo=False, **extra):
    payload = {"anio": 2026, "mes": 9, "dia": 15, "origen": "MOSTRADOR",
               "cantidad": "1", vl.CLAVE_CLASE_LINEA: clase, **extra}
    if solo:
        payload["solo_detalle"] = True
    return CargaFilaStaging(
        carga_id=uuid.uuid4(), fila=1, lote=1, payload=payload,
        sucursal_id=SUC, referencia_id=ref)


def test_reclasificar_sends_to_venta_mensual_only_rows_of_an_included_line():
    incluidas = frozenset({"REPUESTOS"})
    filas = [_staged(vl.CLASE_SIN_LINEA, solo=True)]

    (incluida,) = vl.reclasificar(filas, {REF: "REPUESTOS"}, incluidas)
    assert "solo_detalle" not in incluida.payload
    assert "solo_detalle" in filas[0].payload  # the ORM row is not touched

    # Another line (or none): the row stays, detail only.
    for lineas in ({REF: "MOTOS"}, {}):
        (solo,) = vl.reclasificar(filas, lineas, incluidas)
        assert solo.payload["solo_detalle"] is True
        assert ventas.agregar_unidades([solo]) == {}


def test_a_row_of_an_excluded_erp_type_stays_detail_only_whatever_its_line():
    fila = _staged(vl.CLASE_TIPO_EXCLUIDO, solo=True)

    (solo,) = vl.reclasificar([fila], {REF: "REPUESTOS"}, frozenset({"REPUESTOS"}))

    assert solo.payload["solo_detalle"] is True
    assert vl.clase_de_staging(
        fila.payload, REF, {}, frozenset({"REPUESTOS"})) == vl.CLASE_TIPO_EXCLUIDO


def test_reclasificar_passes_unresolved_and_legacy_rows_through():
    sin_referencia = _staged(vl.CLASE_INCLUIDA, ref=None)
    legado = _staged(vl.CLASE_INCLUIDA)
    del legado.payload[vl.CLAVE_CLASE_LINEA]

    aplicables = vl.reclasificar(
        [sin_referencia, legado], {}, frozenset({"REPUESTOS"}))

    assert len(aplicables) == 2


# --- PUT: roles and guards (fake session) -----------------------------------

URL = "/api/motored/cargas"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "lineas-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "lineas-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _carga(tipo="VENTAS", estado="VALIDADO"):
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen="EXCEL", nombre_archivo="a.xlsx",
        hash_sha256="a" * 64, ruta_objeto="x", bytes=1, estado=estado,
        filas_leidas=0, filas_validas=0, filas_rechazadas=0, lotes_staged=0,
        ultimo_lote_aplicado=0, subido_por=uuid.uuid4(),
        created_at=datetime(2026, 9, 21, 10))


def _cliente(rol, cola):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    override_motored_db(FakeAsyncSession(execute_queue=cola))
    return TestClient(app)


def _puts(carga):
    una = f"{URL}/{carga.id}/referencias-sin-linea/{uuid.uuid4()}"
    return [
        ("single", una, {"linea_comercial": "GPS"}),
        ("bulk", f"{URL}/{carga.id}/referencias-sin-linea",
         [{"referencia_id": str(uuid.uuid4()), "linea_comercial": "GPS"}]),
    ]


@pytest.mark.parametrize("rol", ["SUCURSAL", "CONSULTA"])
def test_only_admin_and_compras_can_assign_lines(rol):
    carga = _carga()
    for _, url, cuerpo in _puts(carga):
        assert _cliente(rol, [[], [carga]]).put(url, json=cuerpo).status_code == 403


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS"])
@pytest.mark.parametrize("tipo, estado", [
    ("INVENTARIO", "VALIDADO"), ("VENTAS", "APLICADO"), ("VENTAS", "ANULADO")])
def test_assignment_needs_an_open_ventas_carga(rol, tipo, estado):
    carga = _carga(tipo, estado)
    for _, url, cuerpo in _puts(carga):
        respuesta = _cliente(rol, [[], [carga]]).put(url, json=cuerpo)
        assert respuesta.status_code == 409, respuesta.text
        assert isinstance(respuesta.json()["detail"], str)


def test_an_empty_bulk_body_is_a_422_in_spanish():
    carga = _carga()
    respuesta = _cliente("ADMIN", [[], [carga]]).put(
        f"{URL}/{carga.id}/referencias-sin-linea", json=[])

    assert respuesta.status_code == 422
    assert isinstance(respuesta.json()["detail"], str)


# --- D1, R4: GET roles and the row lock ---------------------------------------


@pytest.mark.parametrize("rol", ["SUCURSAL", "CONSULTA", "GERENCIA"])
def test_only_admin_and_compras_read_the_sin_linea_report(rol):
    carga = _carga()
    respuesta = _cliente(rol, [[], [carga]]).get(
        f"{URL}/{carga.id}/referencias-sin-linea")

    assert respuesta.status_code == 403


def _bloqueos(sesion):
    from sqlalchemy.dialects import postgresql

    return [str(e.compile(dialect=postgresql.dialect()))
            for e in sesion.executed_statements
            if "FOR UPDATE" in str(e.compile(dialect=postgresql.dialect()))]


def test_both_puts_and_the_apply_lock_the_carga_row_before_validating():
    carga = _carga(estado="APLICADO")
    pedidos = [
        ("put", f"{URL}/{carga.id}/referencias-sin-linea/{uuid.uuid4()}",
         {"linea_comercial": "GPS"}),
        ("put", f"{URL}/{carga.id}/referencias-sin-linea",
         [{"referencia_id": str(uuid.uuid4()), "linea_comercial": "GPS"}]),
        ("post", f"{URL}/{carga.id}/aplicar", None),
    ]
    for metodo, url, cuerpo in pedidos:
        override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
        sesion = FakeAsyncSession(execute_queue=[[], [carga]])
        override_motored_db(sesion)
        respuesta = getattr(TestClient(app), metodo)(url, json=cuerpo) \
            if cuerpo is not None else TestClient(app).post(url)

        assert respuesta.status_code == 409, (url, respuesta.text)
        (bloqueo,) = _bloqueos(sesion)
        assert "carga_archivo" in bloqueo
