"""
Maestro de vendedores (feature motored-tablero-asesores, T3).

Toda persona que vende, con o sin usuario en la app. La llave es el nombre del
ERP normalizado con la MISMA funcion que `venta_detalle.vendedor_norm`
(`normalizar_vendedor`), para que el cruce con las ventas sea exacto. Se carga
por Excel (upsert por `nombre_norm`, nunca borra gente) y se edita a mano.
`GET /vendedores/sin-registrar` lista a quienes venden pero no estan cargados.
"""
import datetime
import io
import uuid

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api.carga import _resolver_relaciones
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.schemas.vendedor import VendedorCreate, VendedorUpdate
from app.motored.services import carga, carga_excel, maestros, validators
from app.motored.services.auth import MotoredUser
from app.motored.services.ingesta.ventas import normalizar_vendedor
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

SUC_ID = uuid.uuid4()


# --- Schema -------------------------------------------------------------------


def test_cargo_se_normaliza_a_mayusculas_sin_espacios_de_mas():
    data = VendedorCreate(nombre="Ana Perez", cargo="  asesor de   repuestos ", cedula="1")

    assert data.cargo == "ASESOR DE REPUESTOS"


@pytest.mark.parametrize("cargo", ["", "   ", "X" * 81])
def test_cargo_vacio_o_demasiado_largo_se_rechaza(cargo):
    with pytest.raises(ValueError):
        VendedorCreate(nombre="Ana", cargo=cargo, cedula="1")


def test_nombre_vacio_se_rechaza():
    with pytest.raises(ValueError):
        VendedorCreate(nombre="   ", cargo="OTRO", cedula="1")


@pytest.mark.parametrize("crudo, esperado", [
    (" 12345.0 ", "12345"),
    (1130123456.0, "1130123456"),
    (1130123456, "1130123456"),
    ("1.130.123.456", "1130123456"),
    ("1 130 123 456", "1130123456"),
    ("  1130123456  ", "1130123456"),
])
def test_cedula_se_limpia_a_solo_digitos(crudo, esperado):
    assert VendedorCreate(nombre="A", cargo="OTRO", cedula=crudo).cedula == esperado


@pytest.mark.parametrize("crudo", [None, "", "   ", "...", "ABC123", "12-34"])
def test_cedula_es_obligatoria_y_solo_numerica(crudo):
    with pytest.raises(ValueError) as exc:
        VendedorCreate(nombre="A", cargo="OTRO", cedula=crudo)

    assert "cédula" in str(exc.value).lower()


def test_crear_sin_la_clave_cedula_se_rechaza():
    with pytest.raises(ValueError):
        VendedorCreate(nombre="A", cargo="OTRO")


@pytest.mark.parametrize("crudo", [None, "", "  ", "abc"])
def test_update_rechaza_una_cedula_enviada_pero_vacia_o_invalida(crudo):
    with pytest.raises(ValueError):
        VendedorUpdate(cedula=crudo)


def test_update_normaliza_la_cedula_enviada():
    assert VendedorUpdate(cedula=" 1.234.567.0 ").cedula == "1234567"


def test_update_solo_normaliza_los_campos_enviados():
    data = VendedorUpdate(cargo=" jefe de taller ")

    assert data.cargo == "JEFE DE TALLER"
    assert data.model_dump(exclude_unset=True) == {"cargo": "JEFE DE TALLER"}


# --- Servicio: la llave es la MISMA normalizacion de venta_detalle ----------------


async def test_create_vendedor_calcula_nombre_norm_como_venta_detalle():
    db = FakeAsyncSession()

    vendedor = await maestros.create_vendedor(
        db, VendedorCreate(nombre="  Ana  Pérez ", cargo="OTRO", cedula="1"), uuid.uuid4())

    assert vendedor.nombre_norm == normalizar_vendedor("  Ana  Pérez ") == "ANA PEREZ"
    assert vendedor.nombre == "Ana Pérez"
    assert vendedor.activo is True


async def test_update_vendedor_recalcula_nombre_norm_si_cambia_el_nombre():
    existente = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula="1")
    db = FakeAsyncSession()

    await maestros.update_vendedor(db, existente, VendedorUpdate(nombre="Ana María"), None)

    assert existente.nombre_norm == "ANA MARIA"


async def test_deactivate_vendedor_no_borra_y_audita():
    existente = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula="1")
    db = FakeAsyncSession()

    await maestros.deactivate_vendedor(db, existente, uuid.uuid4())

    assert existente.activo is False
    assert any(getattr(a, "accion", None) == "deactivate" for a in db.added)


# --- Validacion de filas ----------------------------------------------------------


def test_validate_rows_exige_nombre_cargo_y_cedula():
    _v, errores = validators.validate_rows("vendedor", [
        {"nombre": "Ana", "cedula": "1"}, {"cargo": "OTRO", "cedula": "1"}, {"nombre": "Luis", "cargo": "OTRO"}])

    assert [e["fila"] for e in errores] == [1, 2, 3]
    assert "'cedula'" in errores[2]["motivo"]


def test_una_cedula_con_letras_es_error_de_fila_en_español():
    _v, errores = validators.validate_rows(
        "vendedor", [{"nombre": "Ana", "cargo": "OTRO", "cedula": "12AB"}])

    assert [e["fila"] for e in errores] == [1]
    assert "solo números" in errores[0]["motivo"]


def test_la_cedula_del_excel_como_numero_se_normaliza_al_validar():
    validas, errores = validators.validate_rows(
        "vendedor", [{"nombre": "Ana", "cargo": "OTRO", "cedula": 1130123456.0}])

    assert errores == [] and len(validas) == 1


def test_misma_cedula_con_otro_cargo_o_sucursal_advierte_pero_no_rechaza():
    suc_a, suc_b = uuid.uuid4(), uuid.uuid4()
    validas, errores = validators.validate_rows("vendedor", [
        {"nombre": "MORA DIANA PATRICIA", "cargo": "ASESOR DE REPUESTOS", "cedula": "55", "sucursal_id": suc_a},
        {"nombre": "MORA BUSTOS DIANA PATRICIA", "cargo": "asesor de repuestos", "cedula": "55.0", "sucursal_id": suc_a},
        {"nombre": "OTRA", "cargo": "ASESOR DE REPUESTOS", "cedula": "77", "sucursal_id": suc_a},
        {"nombre": "MORA D P", "cargo": "JEFE DE TALLER", "cedula": "55", "sucursal_id": suc_b},
    ])

    assert errores == []
    assert validas[0]["_warnings"] == [] and validas[2]["_warnings"] == []
    # La 2da es igual a la 1ra en cargo y sucursal: sin aviso. La 4ta difiere.
    assert validas[1]["_warnings"] == []
    [aviso] = validas[3]["_warnings"]
    assert "55" in aviso and "cargo" in aviso and "sucursal" in aviso


def test_un_archivo_de_vendedores_vacio_no_es_error():
    # A diferencia de CLIENTES TECNIRED, subir vendedores nunca borra a nadie.
    _v, errores = validators.validate_rows("vendedor", [])

    assert errores == []


# --- Resolucion de sucursal y duplicados en el archivo -------------------------------


async def test_sucursal_conocida_se_resuelve_por_nombre_normalizado():
    db = FakeAsyncSession(execute_queue=[[(SUC_ID, "CALI NORTE", None)], []])  # sucursales, alias
    filas = [{"nombre": "Ana", "cargo": "OTRO", "sucursal_nombre": "MR Cali  Norte"}]

    resueltas, errores = await _resolver_relaciones(db, "vendedor", filas)

    assert errores == []
    assert resueltas[0]["sucursal_id"] == SUC_ID


async def test_sucursal_se_resuelve_por_codigo_co_sin_importar_mayusculas():
    db = FakeAsyncSession(execute_queue=[[(SUC_ID, "CALI NORTE", "B08")], []])
    filas = [
        {"nombre": "Ana", "cargo": "OTRO", "sucursal_nombre": "B08"},
        {"nombre": "Beto", "cargo": "OTRO", "sucursal_nombre": " b08 "},
    ]

    resueltas, errores = await _resolver_relaciones(db, "vendedor", filas)

    assert errores == []
    assert [f["sucursal_id"] for f in resueltas] == [SUC_ID, SUC_ID]


async def test_sucursal_desconocida_es_error_de_fila():
    db = FakeAsyncSession(execute_queue=[[(SUC_ID, "CALI NORTE", None)], []])
    filas = [
        {"nombre": "Ana", "cargo": "OTRO", "sucursal_nombre": "CALI NORTE"},
        {"nombre": "Luis", "cargo": "OTRO", "sucursal_nombre": "NO EXISTE"},
    ]

    _res, errores = await _resolver_relaciones(db, "vendedor", filas)

    assert [e["fila"] for e in errores] == [2]
    assert "NO EXISTE" in errores[0]["motivo"]


async def test_sin_sucursales_en_el_archivo_no_consulta_la_base():
    db = FakeAsyncSession()  # cualquier execute() revienta
    filas = [{"nombre": "Ana", "cargo": "OTRO", "sucursal_nombre": ""}, {"nombre": "Luis", "cargo": "OTRO"}]

    resueltas, errores = await _resolver_relaciones(db, "vendedor", filas)

    assert errores == [] and "sucursal_id" not in resueltas[0]


async def test_vendedor_repetido_en_el_archivo_es_error_aunque_cambie_la_escritura():
    db = FakeAsyncSession()
    filas = [
        {"nombre": "Ana Pérez", "cargo": "OTRO"},
        {"nombre": "luis", "cargo": "OTRO"},
        {"nombre": "ANA  PEREZ", "cargo": "JEFE DE TALLER"},
    ]

    _res, errores = await _resolver_relaciones(db, "vendedor", filas)

    assert [e["fila"] for e in errores] == [3]
    assert "fila 1" in errores[0]["motivo"]


# --- procesar_carga: upsert por nombre_norm ---------------------------------------


async def test_carga_crea_los_nuevos_con_nombre_norm():
    db = FakeAsyncSession(execute_queue=[[]])  # no existe

    resultado = await carga.procesar_carga(
        db, "vendedor",
        [{"nombre": "Ana Pérez", "cargo": "asesor comercial", "sucursal_id": SUC_ID, "cedula": "123"}])

    assert resultado.ok and resultado.insertados == 1 and resultado.actualizados == 0
    [nuevo] = db.added_of_type(Vendedor)
    assert (nuevo.nombre_norm, nuevo.cargo, nuevo.sucursal_id) == ("ANA PEREZ", "ASESOR COMERCIAL", SUC_ID)
    assert nuevo.cedula == "123"
    assert db.committed is True


async def test_carga_actualiza_por_nombre_norm_sin_pisar_lo_que_no_vino():
    usuario = uuid.uuid4()
    existente = Vendedor(
        id=uuid.uuid4(), nombre="Ana Perez", nombre_norm="ANA PEREZ", cargo="OTRO",
        cedula="999", usuario_id=usuario, sucursal_id=SUC_ID, activo=True)
    db = FakeAsyncSession(execute_queue=[[existente]])

    resultado = await carga.procesar_carga(
        db, "vendedor", [{"nombre": "ANA  PÉREZ", "cargo": "JEFE DE TALLER", "cedula": "1000"}])

    assert resultado.ok and resultado.actualizados == 1 and resultado.insertados == 0
    assert existente.cargo == "JEFE DE TALLER"
    assert existente.cedula == "1000"  # la cédula del archivo reemplaza la guardada
    assert existente.usuario_id == usuario  # el Excel nunca toca el usuario
    assert existente.sucursal_id == SUC_ID
    assert db.added_of_type(Vendedor) == []


async def test_carga_sin_cedula_no_escribe_nada():
    db = FakeAsyncSession()

    resultado = await carga.procesar_carga(
        db, "vendedor", [{"nombre": "Ana", "cargo": "OTRO", "cedula": ""}])

    assert resultado.ok is False and resultado.errores[0].fila == 1
    assert "cedula" in resultado.errores[0].motivo
    assert db.added == [] and db.committed is False


async def test_carga_con_la_misma_cedula_en_dos_nombres_crea_las_dos_filas_y_advierte():
    db = FakeAsyncSession(execute_queue=[[], []])
    filas = [
        {"nombre": "MORA DIANA PATRICIA", "cargo": "OTRO", "cedula": "55"},
        {"nombre": "MORA BUSTOS DIANA PATRICIA", "cargo": "JEFE", "cedula": "55"},
    ]

    resultado = await carga.procesar_carga(db, "vendedor", filas)

    assert resultado.ok and resultado.insertados == 2
    assert [v.cedula for v in db.added_of_type(Vendedor)] == ["55", "55"]
    assert [a["fila"] for a in resultado.advertencias] == [2]


async def test_carga_invalida_no_escribe_nada():
    db = FakeAsyncSession()

    resultado = await carga.procesar_carga(
        db, "vendedor",
        [{"nombre": "Ana", "cargo": "OTRO", "cedula": "1"}, {"nombre": "", "cargo": "OTRO", "cedula": "2"}])

    assert resultado.ok is False and db.added == [] and db.committed is False


# --- Excel -----------------------------------------------------------------------------


def test_plantilla_de_vendedores():
    assert carga_excel.column_labels("vendedor") == ["Nombre vendedor", "Cargo", "Sucursal", "Cédula"]


def _xlsx(encabezados, filas) -> bytes:
    libro = openpyxl.Workbook()
    libro.active.append(encabezados)
    for fila in filas:
        libro.active.append(fila)
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_el_excel_se_parsea_con_las_columnas_del_maestro():
    contenido = _xlsx(
        ["Nombre vendedor", "Cargo", "Sucursal", "Cédula"],
        [["Ana Pérez", "Asesor de repuestos", "Cali Norte", 1130123456]],
    )

    filas = carga_excel.parse_excel_rows("vendedor", "v.xlsx", contenido)

    assert filas == [{
        "nombre": "Ana Pérez", "cargo": "Asesor de repuestos",
        "sucursal_nombre": "Cali Norte", "cedula": "1130123456",
    }]


def test_el_excel_sin_la_columna_cedula_se_rechaza():
    contenido = _xlsx(["Nombre vendedor", "Cargo"], [["Ana", "OTRO"]])

    with pytest.raises(carga_excel.ColumnaObligatoriaFaltanteError):
        carga_excel.parse_excel_rows("vendedor", "v.xlsx", contenido)


def test_el_excel_sin_cargo_se_rechaza():
    contenido = _xlsx(["Nombre vendedor", "Cédula"], [["Ana", "1"]])

    with pytest.raises(carga_excel.ColumnaObligatoriaFaltanteError):
        carga_excel.parse_excel_rows("vendedor", "v.xlsx", contenido)


# --- Migracion ----------------------------------------------------------------------------


def test_la_migracion_encadena_sobre_cliente_tecnired_y_crea_los_indices():
    import importlib.util
    from pathlib import Path
    from unittest.mock import patch

    archivo = (
        Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
        / "e8c2a5f17b93_vendedor.py")
    spec = importlib.util.spec_from_file_location("tablero_t3_vendedor", archivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    assert m.down_revision == "d3b7f19a4c26"
    with patch.object(m, "op") as op_mock:
        m.upgrade()
    assert [c.args[0] for c in op_mock.create_table.call_args_list] == ["vendedor"]
    indices = {c.args[0]: c.kwargs.get("unique", False) for c in op_mock.create_index.call_args_list}
    assert indices == {"uq_vendedor_nombre_norm": True, "ix_vendedor_cargo": False}


# --- HTTP ----------------------------------------------------------------------------------


@pytest.fixture
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "vendedores-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "vendedores-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _como(rol):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))


URL = "/api/motored/vendedores"


@pytest.mark.parametrize("metodo, ruta", [
    ("get", ""), ("get", "/sin-registrar"), ("get", "/usuarios-disponibles"),
    ("post", ""), ("patch", f"/{uuid.uuid4()}"), ("delete", f"/{uuid.uuid4()}"),
    ("post", f"/{uuid.uuid4()}/reactivar"),
])
def test_todo_el_modulo_exige_admin_o_compras(_motored_ready, metodo, ruta):
    _como("CONSULTA")
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))

    with TestClient(app) as client:
        r = getattr(client, metodo)(URL + ruta, **({"json": {}} if metodo in ("post", "patch") else {}))

    assert r.status_code == 403


def test_listar_devuelve_sucursal_y_usuario_legibles(_motored_ready):
    _como("COMPRAS")
    v = Vendedor(
        id=uuid.uuid4(), nombre="Ana Perez", nombre_norm="ANA PEREZ", cargo="OTRO",
        sucursal_id=SUC_ID, usuario_id=None, activo=True)
    override_motored_db(FakeAsyncSession(execute_queue=[[], [(v, "CALI NORTE", None)]]))

    with TestClient(app) as client:
        r = client.get(URL, params={"q": "ana", "cargo": "OTRO", "activo": "true"})

    assert r.status_code == 200
    [item] = r.json()
    assert item["nombre_norm"] == "ANA PEREZ" and item["sucursal_nombre"] == "CALI NORTE"
    assert item["usuario_nombre"] is None


def test_crear_responde_201_y_confirma(_motored_ready):
    _como("ADMIN")
    db = FakeAsyncSession(execute_queue=[[], [], []])  # sonda, existe nombre_norm?, (reservado)
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.post(URL, json={"nombre": "Ana Pérez", "cargo": "jefe de taller", "cedula": "1.130.123"})

    assert r.status_code == 201
    assert r.json()["nombre_norm"] == "ANA PEREZ" and r.json()["cargo"] == "JEFE DE TALLER"
    assert r.json()["cedula"] == "1130123"
    assert db.committed is True


@pytest.mark.parametrize("cedula", [None, "", "  ", "abc"])
def test_crear_sin_cedula_valida_es_422_y_no_escribe(_motored_ready, cedula):
    _como("ADMIN")
    db = FakeAsyncSession(execute_queue=[[], [], []])
    override_motored_db(db)
    payload = {"nombre": "Ana", "cargo": "OTRO"}
    if cedula is not None:
        payload["cedula"] = cedula

    with TestClient(app) as client:
        r = client.post(URL, json=payload)

    assert r.status_code == 422
    assert "cédula" in str(r.json()["detail"]).lower()
    assert db.committed is False and db.added == []


def test_editar_un_vendedor_sin_cedula_exige_llenarla(_motored_ready):
    _como("ADMIN")
    v = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula=None)
    db = FakeAsyncSession(execute_queue=[[], [v]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.patch(f"{URL}/{v.id}", json={"cargo": "jefe"})

    assert r.status_code == 422 and "cédula" in str(r.json()["detail"]).lower()
    assert db.committed is False and v.cargo == "OTRO"


def test_editar_un_vendedor_sin_cedula_con_la_cedula_funciona(_motored_ready):
    _como("ADMIN")
    v = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula="")
    db = FakeAsyncSession(execute_queue=[[], [v]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.patch(f"{URL}/{v.id}", json={"cedula": "1.234"})

    assert r.status_code == 200 and v.cedula == "1234" and db.committed is True


@pytest.mark.parametrize("cedula", ["", None, "xx"])
def test_editar_no_permite_borrar_la_cedula(_motored_ready, cedula):
    _como("ADMIN")
    v = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula="99")
    db = FakeAsyncSession(execute_queue=[[], [v]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.patch(f"{URL}/{v.id}", json={"cedula": cedula})

    assert r.status_code == 422 and v.cedula == "99" and db.committed is False


def test_editar_un_vendedor_con_cedula_sin_enviarla_conserva_la_guardada(_motored_ready):
    _como("ADMIN")
    v = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula="99")
    db = FakeAsyncSession(execute_queue=[[], [v]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.patch(f"{URL}/{v.id}", json={"cargo": "jefe"})

    assert r.status_code == 200 and v.cedula == "99" and v.cargo == "JEFE"


def test_crear_con_nombre_ya_existente_es_409(_motored_ready):
    _como("ADMIN")
    existente = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA PEREZ", cargo="OTRO", activo=True)
    db = FakeAsyncSession(execute_queue=[[], [existente]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.post(URL, json={"nombre": "ana  pérez", "cargo": "OTRO", "cedula": "1"})

    assert r.status_code == 409
    assert db.committed is False


def test_crear_con_carrera_en_el_indice_unico_es_409_y_hace_rollback(_motored_ready):
    _como("ADMIN")
    # El nombre parece libre al verificar, pero otro pedido lo creo antes del commit.
    db = FakeAsyncSession(execute_queue=[[], []], raise_integrity_error=True)
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.post(URL, json={"nombre": "Ana", "cargo": "OTRO", "cedula": "1"})

    assert r.status_code == 409
    assert db.rolled_back is True and db.committed is False


def test_editar_con_carrera_en_el_indice_unico_es_409_y_hace_rollback(_motored_ready):
    _como("ADMIN")
    v = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula="1")
    db = FakeAsyncSession(execute_queue=[[], [v], []], raise_integrity_error=True)
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.patch(f"{URL}/{v.id}", json={"nombre": "Ana María"})

    assert r.status_code == 409
    assert db.rolled_back is True and db.committed is False


def test_crear_con_usuario_inexistente_es_422(_motored_ready):
    _como("ADMIN")
    # sonda, nombre_norm libre, usuario no existe
    db = FakeAsyncSession(execute_queue=[[], [], []])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.post(URL, json={"nombre": "Ana", "cargo": "OTRO", "cedula": "1", "usuario_id": str(uuid.uuid4())})

    assert r.status_code == 422
    assert db.committed is False


def test_editar_enlaza_un_usuario_y_audita(_motored_ready):
    _como("ADMIN")
    usuario = uuid.uuid4()
    v = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula="1")
    # sonda, vendedor, usuario existe, nombres para la respuesta
    db = FakeAsyncSession(execute_queue=[[], [v], [(usuario,)], [(None, "Ana Usuaria")]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.patch(f"{URL}/{v.id}", json={"usuario_id": str(usuario)})

    assert r.status_code == 200
    assert v.usuario_id == usuario and db.committed is True
    assert any(getattr(a, "campo", None) == "usuario_id" for a in db.added)


def test_editar_puede_desenlazar_el_usuario_con_null(_motored_ready):
    _como("ADMIN")
    v = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, usuario_id=uuid.uuid4(), cedula="1")
    db = FakeAsyncSession(execute_queue=[[], [v]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.patch(f"{URL}/{v.id}", json={"usuario_id": None})

    assert r.status_code == 200 and v.usuario_id is None


def test_editar_el_nombre_a_uno_de_otra_persona_es_409(_motored_ready):
    _como("ADMIN")
    v = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula="1")
    otra = Vendedor(id=uuid.uuid4(), nombre="Luis", nombre_norm="LUIS", cargo="OTRO", activo=True, cedula="2")
    db = FakeAsyncSession(execute_queue=[[], [v], [otra]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.patch(f"{URL}/{v.id}", json={"nombre": "luis"})

    assert r.status_code == 409 and db.committed is False


def test_desactivar_marca_inactivo_sin_borrar(_motored_ready):
    _como("COMPRAS")
    v = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula="1")
    db = FakeAsyncSession(execute_queue=[[], [v]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.delete(f"{URL}/{v.id}")

    assert r.status_code == 200 and r.json()["activo"] is False
    assert v.activo is False and db.committed is True


def test_vendedores_sin_registrar_devuelve_el_resumen(_motored_ready):
    _como("ADMIN")
    filas = [("JUAN GOMEZ", "Juan Gómez", datetime.date(2026, 9, 30), 42)]
    override_motored_db(FakeAsyncSession(execute_queue=[[], filas]))

    with TestClient(app) as client:
        r = client.get(f"{URL}/sin-registrar")

    assert r.status_code == 200
    assert r.json() == [{
        "vendedor_norm": "JUAN GOMEZ", "vendedor_ejemplo": "Juan Gómez",
        "ultima_venta": "2026-09-30", "lineas": 42,
    }]


def test_usuarios_disponibles_no_expone_correos(_motored_ready):
    _como("COMPRAS")
    uid = uuid.uuid4()
    override_motored_db(FakeAsyncSession(execute_queue=[[], [(uid, "Ana Admin", "COMPRAS")]]))

    with TestClient(app) as client:
        r = client.get(f"{URL}/usuarios-disponibles")

    assert r.status_code == 200
    assert r.json() == [{"id": str(uid), "nombre": "Ana Admin", "role": "COMPRAS"}]


# --- Aislamiento --------------------------------------------------------------------------------


def test_vendedor_no_es_movimiento_ni_lo_lee_el_motor():
    from app.motored.services.corridas import vigencia
    from app.motored.services.ingesta import orquestador

    assert not any("VENDEDOR" in t.upper() for t in orquestador.TIPOS_MOVIMIENTO)
    assert "VENDEDOR" not in repr(vigencia._TIPOS).upper()


# --- Advertencias de la revision de T3 ------------------------------------------------------


def test_sin_registrar_excluye_vendedor_norm_nulo_o_vacio(_motored_ready):
    from sqlalchemy.dialects import postgresql

    _como("ADMIN")
    db = FakeAsyncSession(execute_queue=[[], []])
    override_motored_db(db)

    with TestClient(app) as client:
        assert client.get(f"{URL}/sin-registrar").status_code == 200

    sql = str(db.executed_statements[-1].compile(dialect=postgresql.dialect()))
    assert "venta_detalle.vendedor_norm IS NOT NULL" in sql
    assert "venta_detalle.vendedor_norm != " in sql


def test_crear_devuelve_los_nombres_reales_de_sucursal_y_usuario(_motored_ready):
    _como("ADMIN")
    suc, usr = uuid.uuid4(), uuid.uuid4()
    # sonda, nombre libre, sucursal existe, usuario existe, nombres para la respuesta
    db = FakeAsyncSession(execute_queue=[[], [], [(suc,)], [(usr,)], [("CALI NORTE", "Ana Usuaria")]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.post(URL, json={
            "nombre": "Ana", "cargo": "OTRO", "cedula": "1", "sucursal_id": str(suc), "usuario_id": str(usr)})

    assert r.status_code == 201
    assert r.json()["sucursal_nombre"] == "CALI NORTE"
    assert r.json()["usuario_nombre"] == "Ana Usuaria"


def test_editar_devuelve_los_nombres_reales_de_sucursal_y_usuario(_motored_ready):
    _como("ADMIN")
    suc = uuid.uuid4()
    v = Vendedor(id=uuid.uuid4(), nombre="Ana", nombre_norm="ANA", cargo="OTRO", activo=True, cedula="1")
    # sonda, vendedor, sucursal existe, nombres para la respuesta
    db = FakeAsyncSession(execute_queue=[[], [v], [(suc,)], [("CALI NORTE", None)]])
    override_motored_db(db)

    with TestClient(app) as client:
        r = client.patch(f"{URL}/{v.id}", json={"sucursal_id": str(suc)})

    assert r.status_code == 200
    assert r.json()["sucursal_nombre"] == "CALI NORTE"
    assert r.json()["usuario_nombre"] is None
