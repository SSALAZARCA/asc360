"""
Fase 2 "Ingesta", Phase 9 "Adapter + API" (PR9), task 9.4 (sdd/motored-
pedidos-ingesta) — `services/ingesta/orquestador.py`: la pieza que compone
`lector`+`columnas`+`resolucion`+`errores`+`periodo`+cada transform en un
dry-run/aplicar real.

Mismo criterio "no live database" que el resto de `tests/motored/`
(`FakeAsyncSession` con `execute_queue`) -- `storage.descargar_archivo` se
monkeypatchea para devolver bytes de un `.xlsx` construido en memoria con
`openpyxl` (mismo convenio que `test_ingesta_lector.py`), así el pipeline
de streaming real (`lector.leer_lotes`, `columnas.encontrar_fila_
encabezado`) corre de punta a punta sin ningún archivo ni MinIO real.
"""
import io
import uuid
from datetime import date

import openpyxl
import pytest

from tests.motored.conftest import FakeAsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.schemas.carga import CargaResultado
from app.motored.services import parametros
from app.motored.services.carga_excel import ColumnaObligatoriaFaltanteError
from app.motored.services.ingesta import maestros_adapter
from app.motored.services.ingesta import orquestador
from app.motored.services.ingesta import periodo as periodo_mod

PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()


def _build_xlsx_bytes(filas: list) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for fila in filas:
        sheet.append(fila)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _carga(tipo: str, **overrides) -> CargaArchivo:
    base = dict(
        id=uuid.uuid4(),
        tipo=tipo,
        nombre_archivo="archivo.xlsx",
        hash_sha256="a" * 64,
        ruta_objeto=f"{tipo}/2026/09/x.xlsx",
        bytes=100,
        estado="PROCESANDO",
        filas_leidas=0,
        filas_validas=0,
        filas_rechazadas=0,
        periodo_desde=None,
        periodo_hasta=None,
        lotes_staged=0,
        ultimo_lote_aplicado=0,
        latido_en=None,
        log=None,
        subido_por=uuid.uuid4(),
        aplicado_en=None,
    )
    base.update(overrides)
    return CargaArchivo(**base)


# `construir_cache` (ADR-8): sucursales, bodegas, alias, referencias -- en
# ESE orden, siempre 4 SELECTs. `resolver_proveedor_principal`: 1 SELECT más.
def _queue_cache_y_proveedor(sucursales=None, referencias=None):
    return [
        list(sucursales or [(SUCURSAL_ID, "CALI NORTE", None)]),
        [],  # bodegas
        [],  # sucursal_alias
        list(referencias or [("REF1", PROVEEDOR_ID, REFERENCIA_ID)]),
        [PROVEEDOR_ID],  # proveedor.es_principal
    ]


# ---------------------------------------------------------------------------
# Task 9.4 — dry-run genérico (feliz + guard de columna obligatoria)
# ---------------------------------------------------------------------------


async def test_dry_run_inventario_happy_path_stages_rows_and_marks_validado(monkeypatch):
    carga = _carga("INVENTARIO", periodo_desde=date(2026, 9, 15), periodo_hasta=date(2026, 9, 15))
    file_bytes = _build_xlsx_bytes(
        [
            ["Referencia", "Bodega", "Desc.bodega", "Existencia"],
            ["REF1", "BA061", "CALI NORTE", 10],
        ]
    )
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: file_bytes)
    session = FakeAsyncSession(execute_queue=_queue_cache_y_proveedor())

    await orquestador._dry_run(session, carga)

    assert carga.estado == "VALIDADO"
    assert carga.filas_leidas == 1
    assert carga.filas_validas == 1
    staged = session.added_of_type(CargaFilaStaging)
    assert len(staged) == 1
    assert staged[0].sucursal_id == SUCURSAL_ID
    assert staged[0].referencia_id == REFERENCIA_ID


async def test_dry_run_missing_mandatory_column_aborts_whole_file_con_errores(monkeypatch):
    """Spec 'Missing mandatory columns abort the whole file' -- ningún
    transform module lo implementaba antes de este batch (ver docstring
    del orquestador)."""
    carga = _carga("INVENTARIO")
    # Falta "Existencia" -- columna obligatoria de INVENTARIO.
    file_bytes = _build_xlsx_bytes(
        [["Referencia", "Bodega", "Desc.bodega"], ["REF1", "BA061", "CALI NORTE"]]
    )
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: file_bytes)
    session = FakeAsyncSession(execute_queue=_queue_cache_y_proveedor())

    await orquestador._dry_run(session, carga)

    assert carga.estado == "CON_ERRORES"
    assert carga.log["columnas_faltantes"] == ["Existencia"]
    assert session.added_of_type(CargaFilaStaging) == []


async def test_dry_run_todas_las_filas_rechazadas_es_con_errores_no_validado(monkeypatch):
    carga = _carga("INVENTARIO", periodo_desde=date(2026, 9, 15), periodo_hasta=date(2026, 9, 15))
    file_bytes = _build_xlsx_bytes(
        [
            ["Referencia", "Bodega", "Desc.bodega", "Existencia"],
            ["REF1", "BA061", "CALI NORTE", "no-es-un-numero"],
        ]
    )
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: file_bytes)
    session = FakeAsyncSession(execute_queue=_queue_cache_y_proveedor())

    await orquestador._dry_run(session, carga)

    assert carga.estado == "CON_ERRORES"
    assert carga.filas_validas == 0


async def test_resolver_proveedor_principal_raises_domain_error_never_a_500(monkeypatch):
    session = FakeAsyncSession(execute_queue=[[]])  # ningún proveedor principal configurado

    with pytest.raises(orquestador.ProveedorPrincipalError):
        await orquestador.resolver_proveedor_principal(session)


# ---------------------------------------------------------------------------
# Task 9.4 — ADR-9: veredicto de período decide `estado` en el dry-run
# (regresión del bug histórico real, design edge case E1)
# ---------------------------------------------------------------------------


async def test_dry_run_ventas_periodo_mal_declarado_rechaza_archivo_completo(monkeypatch):
    """E1 (design): declarado septiembre, TODAS las filas de agosto ->
    `CON_ERRORES`, `E-CARGA-040`, staging borrado -- nunca corrompe un
    agosto ya aplicado (ADR-4 REPLACE-not-sum + ADR-9)."""
    carga = _carga("VENTAS", periodo_desde=date(2026, 9, 1), periodo_hasta=date(2026, 9, 30))
    # 2026-08-15 como serial de Excel.
    serial_agosto = 46249
    file_bytes = _build_xlsx_bytes(
        [
            ["Estado", "Módulo", "Fecha", "Cantidad inv.", "Tipo inventario",
             "Desc.bodega", "Bodega", "Referencia"],
            ["Aprobada", "MOSTRADOR", serial_agosto, 10, "0002 - REPUESTOS",
             "CALI NORTE", "BA061", "REF1"],
        ]
    )
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: file_bytes)
    queue = _queue_cache_y_proveedor() + [
        [],  # parametros.resolver_tipos_inventario_incluidos -> obtener_vigente (usa default)
        [],  # delete(CargaFilaStaging) execute
    ]
    session = FakeAsyncSession(execute_queue=queue)

    await orquestador._dry_run(session, carga)

    assert carga.estado == "CON_ERRORES"
    assert carga.log["periodo_veredicto"] == periodo_mod.TipoVeredictoPeriodo.RECHAZO.value
    # ADR-9: el rechazo DEBE borrar el staging de esta carga -- sin esto, un
    # `Aplicar` posterior (si algo lo permitiera) podría agregar filas de un
    # archivo mal-etiquetado. `executed_statements[-1]` es la última query
    # emitida por `_dry_run` en la rama RECHAZO -- un `DELETE`, nunca un `SELECT`.
    ultimo_statement = session.executed_statements[-1]
    assert ultimo_statement.is_delete
    assert ultimo_statement.table.name == "carga_fila_staging"


async def test_dry_run_ventas_periodo_correcto_queda_validado(monkeypatch):
    carga = _carga("VENTAS", periodo_desde=date(2026, 9, 1), periodo_hasta=date(2026, 9, 30))
    serial_septiembre = 46280  # 2026-09-15
    file_bytes = _build_xlsx_bytes(
        [
            ["Estado", "Módulo", "Fecha", "Cantidad inv.", "Tipo inventario",
             "Desc.bodega", "Bodega", "Referencia"],
            ["Aprobada", "MOSTRADOR", serial_septiembre, 10, "0002 - REPUESTOS",
             "CALI NORTE", "BA061", "REF1"],
        ]
    )
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: file_bytes)
    queue = _queue_cache_y_proveedor() + [[]]
    session = FakeAsyncSession(execute_queue=queue)

    await orquestador._dry_run(session, carga)

    assert carga.estado == "VALIDADO"
    assert carga.log["periodo_veredicto"] == periodo_mod.TipoVeredictoPeriodo.ACEPTADO.value


# ---------------------------------------------------------------------------
# Task 9.6 — BACKORDER "PARCIAL" ADR-9 cross-check integrado en el dry-run
# ---------------------------------------------------------------------------


async def test_dry_run_backorder_corte_posterior_advierte_sin_bloquear(monkeypatch):
    carga = _carga("BACKORDER", periodo_desde=date(2026, 9, 15), periodo_hasta=date(2026, 9, 15))
    file_bytes = _build_xlsx_bytes(
        [
            ["SIC", "Sucursal", "Número del pedido", "Estado del pedido", "Referencia Parte",
             "Cantidad Pendiente", "Fecha Creación"],
            ["1779", "CALI NORTE", 74, "BACKORDER", "REF1", 48, date(2026, 9, 20)],
        ]
    )
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: file_bytes)
    queue = _queue_cache_y_proveedor() + [
        [],  # parametros.resolver_estados_backorder_vigentes (usa default)
        [CargaFilaStaging(carga_id=carga.id, fila=2, lote=1,
                           payload={"cantidad_pendiente": "48", "numero_pedido": "74",
                                    "fecha_creacion": "2026-09-20"},
                           sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID)],
    ]
    session = FakeAsyncSession(execute_queue=queue)

    await orquestador._dry_run(session, carga)

    assert carga.estado == "VALIDADO"  # nunca bloquea (task 9.6, "Partial")
    advertencia = carga.log["backorder_corte_advertencia"]
    assert advertencia["codigo"] == periodo_mod.CODIGO_BACKORDER_CORTE_POSTERIOR
    assert advertencia["filas"] == [2]


# ---------------------------------------------------------------------------
# Task 9.4 — `ejecutar_aplicar`: dispatch por tipo + guard de estado
# ---------------------------------------------------------------------------


async def test_ejecutar_aplicar_rejects_non_validado_estado():
    carga = _carga("INVENTARIO", estado="PENDIENTE")
    session = FakeAsyncSession(execute_queue=[])

    with pytest.raises(orquestador.EstadoInvalidoParaAplicarError):
        await orquestador.ejecutar_aplicar(session, carga)


async def test_ejecutar_aplicar_inventario_marks_aplicado_and_clears_staging():
    carga = _carga(
        "INVENTARIO", estado="VALIDADO",
        periodo_desde=date(2026, 9, 15), periodo_hasta=date(2026, 9, 15), lotes_staged=3,
    )
    staged = [
        CargaFilaStaging(
            carga_id=carga.id, fila=1, lote=1, payload={"existencia": "10"},
            sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        )
    ]
    # 1) select CargaFilaStaging -> staged; 2) aplicar()'s upsert execute;
    # 3) delete(staging) execute.
    session = FakeAsyncSession(execute_queue=[staged, [], []])

    await orquestador.ejecutar_aplicar(session, carga)

    assert carga.estado == "APLICADO"
    assert carga.ultimo_lote_aplicado == 3
    assert carga.aplicado_en is not None
    assert len(session.executed_statements) == 3


async def test_ejecutar_aplicar_facturas_pedidos_triggers_transito_recalculation(monkeypatch):
    carga = _carga("FACTURAS_PEDIDOS", estado="VALIDADO")
    llamadas = {"n": 0}

    async def _fake_recalc(session):
        llamadas["n"] += 1
        return {}

    monkeypatch.setattr(orquestador, "_recalcular_transito", _fake_recalc)
    session = FakeAsyncSession(execute_queue=[[], []])  # staging select vacío + delete staging

    await orquestador.ejecutar_aplicar(session, carga)

    assert llamadas["n"] == 1
    assert carga.estado == "APLICADO"


async def test_dry_run_ventas_periodo_advertencia_emite_carga_error_por_fila_fuera_de_tolerancia(
    monkeypatch,
):
    """ADVERTENCIA (regla 2, ADR-9): un mes adyacente dentro de tolerancia
    NO rechaza el archivo, pero SÍ debe emitir un `carga_error` puntual
    (`A-CARGA-043`) por cada fila fuera del período declarado -- review-
    reliability encontró que esta rama de `_dry_run` (líneas 333-346) no
    tenía NINGÚN test de punta a punta antes de este fix."""
    carga = _carga("VENTAS", periodo_desde=date(2026, 9, 1), periodo_hasta=date(2026, 9, 30))
    serial_septiembre = 46280  # 2026-09-15
    serial_agosto_adyacente = 46265  # 2026-08-31, adyacente-anterior a septiembre
    # El veredicto se calcula por PROPORCIÓN DE FILAS (no por cantidad
    # vendida) -- 1 de 200 filas (0.5%) es el caso límite exacto de la
    # tolerancia default, mismo escenario que `test_ingesta_periodo.py`
    # ya fija para `periodo.evaluar_periodo` en aislamiento; acá se prueba
    # de punta a punta a través de `_dry_run`.
    filas_septiembre = [
        ["Aprobada", "MOSTRADOR", serial_septiembre, 1, "0002 - REPUESTOS",
         "CALI NORTE", "BA061", "REF1"]
        for _ in range(199)
    ]
    fila_agosto = ["Aprobada", "MOSTRADOR", serial_agosto_adyacente, 1, "0002 - REPUESTOS",
                   "CALI NORTE", "BA061", "REF1"]
    file_bytes = _build_xlsx_bytes(
        [["Estado", "Módulo", "Fecha", "Cantidad inv.", "Tipo inventario",
          "Desc.bodega", "Bodega", "Referencia"]]
        + filas_septiembre + [fila_agosto]
    )
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: file_bytes)
    # Header en fila 1 -> primera fila de datos es `fila=2`; con 199 filas de
    # septiembre antes, la de agosto (la fila #200 del archivo) es `fila=201`.
    fila_agosto = CargaFilaStaging(
        carga_id=carga.id, fila=201, lote=1,
        payload={"anio": 2026, "mes": 8, "origen": "MOSTRADOR", "cantidad": "1"},
        sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
    )
    queue = _queue_cache_y_proveedor() + [
        [],  # parametros.resolver_tipos_inventario_incluidos (sin fila vigente -> default)
        [fila_agosto],  # re-select de staging para detectar la fila fuera de período
    ]
    session = FakeAsyncSession(execute_queue=queue)

    await orquestador._dry_run(session, carga)

    assert carga.estado == "VALIDADO"  # ADVERTENCIA nunca bloquea el archivo
    assert carga.log["periodo_veredicto"] == periodo_mod.TipoVeredictoPeriodo.ADVERTENCIA.value
    errores = session.added_of_type(CargaError)
    assert len(errores) == 1
    assert errores[0].fila == 201
    assert errores[0].codigo_error == periodo_mod.CODIGO_FILA_FUERA_DE_PERIODO


# ---------------------------------------------------------------------------
# Task 9.4 — `ejecutar_dry_run`: el handler REAL registrado en
# `jobs.JOB_HANDLERS` (review-resilience: ningún test invocaba este wrapper
# directamente, solo `_dry_run` -- así que su propio guard "nunca debe tirar
# el loop del supervisor" nunca se había ejercitado)
# ---------------------------------------------------------------------------


async def test_ejecutar_dry_run_carga_inexistente_es_un_noop(monkeypatch):
    session = FakeAsyncSession(execute_queue=[])

    class _FakeSessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc_info):
            return False

    monkeypatch.setattr(orquestador, "motored_session_maker", lambda: _FakeSessionMaker())

    await orquestador.ejecutar_dry_run(uuid.uuid4())  # nunca debe lanzar


async def test_ejecutar_dry_run_excepcion_inesperada_termina_en_con_errores_nunca_crashea(
    monkeypatch,
):
    """El guard `except Exception` de `ejecutar_dry_run` (nunca antes
    ejercitado por ningún test, ver docstring de esta sección) debe: (1)
    hacer rollback, (2) re-obtener la carga, (3) dejarla en `CON_ERRORES`
    con un mensaje en `log`, y (4) NUNCA propagar -- esto es lo que evita
    que un archivo con un bug de parseo tire el loop del supervisor entero."""
    carga_id = uuid.uuid4()
    carga = _carga("INVENTARIO", id=carga_id)
    # `ejecutar_dry_run` llama `session.get` DOS veces: una para obtener la
    # carga al principio, otra para re-obtenerla tras el `rollback()`.
    session = FakeAsyncSession(get_queue=[carga, carga])

    class _FakeSessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc_info):
            return False

    monkeypatch.setattr(orquestador, "motored_session_maker", lambda: _FakeSessionMaker())

    async def _dry_run_que_explota(session_, carga_):
        raise RuntimeError("boom -- un bug de parseo cualquiera")

    monkeypatch.setattr(orquestador, "_dry_run", _dry_run_que_explota)

    await orquestador.ejecutar_dry_run(carga_id)  # nunca debe propagar RuntimeError

    assert session.rolled_back is True
    assert carga.estado == "CON_ERRORES"
    assert "error_interno" in carga.log


# ---------------------------------------------------------------------------
# Task 9.1/9.4 — `ejecutar_maestro`: dispatch síncrono de MAESTRO_* (review-
# resilience: sin este fix, una `CargaExcelError` real dejaba la carga
# PENDIENTE para siempre con un 500 crudo -- MAESTRO_* nunca pasa por el
# JobRunner/heartbeat, así que no hay ninguna vía de recuperación)
# ---------------------------------------------------------------------------


async def test_ejecutar_maestro_happy_path_marca_aplicado(monkeypatch):
    carga = _carga("MAESTRO_BODEGAS", estado="PENDIENTE")
    session = FakeAsyncSession()

    async def _procesar_maestro_ok(session_, carga_id, tipo, nombre, file_bytes, usuario_id):
        return CargaResultado(ok=True, total_filas=5, insertados=5)

    monkeypatch.setattr(maestros_adapter, "procesar_maestro", _procesar_maestro_ok)

    resultado = await orquestador.ejecutar_maestro(session, carga, b"x", uuid.uuid4())

    assert resultado.ok is True
    assert carga.estado == "APLICADO"
    assert carga.filas_validas == 5
    assert carga.aplicado_en is not None


async def test_ejecutar_maestro_columna_faltante_termina_en_con_errores_no_pendiente_para_siempre(
    monkeypatch,
):
    """GAP encontrado por review-resilience: antes de este fix, esta
    excepción (rutinaria -- falta una columna obligatoria) se propagaba sin
    capturar, dejando la carga en `PENDIENTE` para siempre con un 500 crudo
    en el request de subida."""
    carga = _carga("MAESTRO_BODEGAS", estado="PENDIENTE")
    session = FakeAsyncSession(get_queue=[carga])

    async def _procesar_maestro_falla(session_, carga_id, tipo, nombre, file_bytes, usuario_id):
        raise ColumnaObligatoriaFaltanteError("Falta la columna 'Código'.")

    monkeypatch.setattr(maestros_adapter, "procesar_maestro", _procesar_maestro_falla)

    resultado = await orquestador.ejecutar_maestro(session, carga, b"x", uuid.uuid4())

    assert resultado is None
    assert carga.estado == "CON_ERRORES"
    assert carga.estado != "PENDIENTE"
    assert "Código" in carga.log["error_interno"]
    assert session.rolled_back is True
    assert session.committed is True


async def test_ejecutar_maestro_excepcion_inesperada_usa_mensaje_generico_no_el_str_crudo(
    monkeypatch,
):
    """Cualquier excepción que NO sea `CargaExcelError` (spec §9.6: "the
    user never sees a stack trace") -- el mensaje interno nunca se expone
    tal cual, a diferencia de una `CargaExcelError` real."""
    carga = _carga("MAESTRO_REFERENCIAS", estado="PENDIENTE")
    session = FakeAsyncSession(get_queue=[carga])

    async def _procesar_maestro_explota(session_, carga_id, tipo, nombre, file_bytes, usuario_id):
        raise ValueError("detalle interno que no debería llegar al usuario")

    monkeypatch.setattr(maestros_adapter, "procesar_maestro", _procesar_maestro_explota)

    resultado = await orquestador.ejecutar_maestro(session, carga, b"x", uuid.uuid4())

    assert resultado is None
    assert carga.estado == "CON_ERRORES"
    assert "detalle interno" not in carga.log["error_interno"]


async def test_ejecutar_aplicar_ventas_uses_aplicar_con_periodo(monkeypatch):
    carga = _carga(
        "VENTAS", estado="VALIDADO",
        periodo_desde=date(2026, 9, 1), periodo_hasta=date(2026, 9, 30),
    )
    llamadas = {}

    async def _fake_aplicar_con_periodo(
        session, filas_staging, desde, hasta, carga_id, tolerancia_pct=None
    ):
        llamadas["desde"] = desde
        llamadas["hasta"] = hasta
        return periodo_mod.VeredictoPeriodo(tipo=periodo_mod.TipoVeredictoPeriodo.ACEPTADO)

    monkeypatch.setattr(orquestador.ventas_mod, "aplicar_con_periodo", _fake_aplicar_con_periodo)
    session = FakeAsyncSession(execute_queue=[[], []])  # staging select vacío + delete staging

    await orquestador.ejecutar_aplicar(session, carga)

    assert llamadas["desde"] == date(2026, 9, 1)
    assert carga.estado == "APLICADO"


# ---------------------------------------------------------------------------
# Verify-report WARNING #2 (sdd/motored-pedidos-ingesta): un default de
# `parametro_metodologia` usado durante una carga debe quedar registrado en
# `carga.log["parametros_default_usados"]` -- antes de este batch solo se
# emitía un `logging.warning` efímero (`services/parametros.py`), invisible
# para un ADMIN vía la pantalla de informe.
# ---------------------------------------------------------------------------


async def test_dry_run_ventas_registra_default_usado_en_carga_log(monkeypatch):
    """Base case del gap: `tipos_inventario_incluidos` SIN fila vigente ->
    el dry-run de VENTAS debe dejar constancia de qué clave defaulteó y con
    qué valor, no solo procesar la fila con el default en silencio."""
    carga = _carga("VENTAS", periodo_desde=date(2026, 9, 1), periodo_hasta=date(2026, 9, 30))
    serial_septiembre = 46280  # 2026-09-15
    file_bytes = _build_xlsx_bytes(
        [
            ["Estado", "Módulo", "Fecha", "Cantidad inv.", "Tipo inventario",
             "Desc.bodega", "Bodega", "Referencia"],
            ["Aprobada", "MOSTRADOR", serial_septiembre, 10, "0002 - REPUESTOS",
             "CALI NORTE", "BA061", "REF1"],
        ]
    )
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: file_bytes)
    queue = _queue_cache_y_proveedor() + [
        [],  # parametros.resolver_tipos_inventario_incluidos -> SIN fila vigente
    ]
    session = FakeAsyncSession(execute_queue=queue)

    await orquestador._dry_run(session, carga)

    assert carga.estado == "VALIDADO"
    assert carga.log["parametros_default_usados"] == {
        parametros.CLAVE_TIPOS_INVENTARIO_INCLUIDOS: parametros.DEFAULT_TIPOS_INVENTARIO_INCLUIDOS,
    }


async def test_dry_run_ventas_no_registra_default_cuando_la_clave_esta_configurada(monkeypatch):
    """Converse del caso anterior: con una fila `parametro_metodologia`
    vigente para `tipos_inventario_incluidos`, `resolver()` nunca defaultea
    -- `carga.log` no debe ganar la entrada de "default usado" para esa
    clave."""
    carga = _carga("VENTAS", periodo_desde=date(2026, 9, 1), periodo_hasta=date(2026, 9, 30))
    serial_septiembre = 46280  # 2026-09-15
    file_bytes = _build_xlsx_bytes(
        [
            ["Estado", "Módulo", "Fecha", "Cantidad inv.", "Tipo inventario",
             "Desc.bodega", "Bodega", "Referencia"],
            ["Aprobada", "MOSTRADOR", serial_septiembre, 10, "0002 - REPUESTOS",
             "CALI NORTE", "BA061", "REF1"],
        ]
    )
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: file_bytes)
    fila_configurada = ParametroMetodologia(
        id=uuid.uuid4(), clave=parametros.CLAVE_TIPOS_INVENTARIO_INCLUIDOS,
        valor=["0002 - REPUESTOS"], vigente_desde=date(2026, 1, 1),
    )
    queue = _queue_cache_y_proveedor() + [
        [fila_configurada],  # parametros.resolver_tipos_inventario_incluidos -> CONFIGURADA
    ]
    session = FakeAsyncSession(execute_queue=queue)

    await orquestador._dry_run(session, carga)

    assert carga.estado == "VALIDADO"
    assert "parametros_default_usados" not in carga.log


async def test_recalcular_transito_registra_defaults_usados_cuando_las_claves_no_estan_configuradas():
    """`_recalcular_transito` (invocado desde `ejecutar_aplicar` para
    FACTURAS_PEDIDOS/INGRESOS_FACTURAS) resuelve `dias_ventana_ingresos` y
    `tolerancia_ingreso_pct` -- si NINGUNA tiene fila vigente, debe retornar
    ambas en `defaults_usados` para que el caller las persista."""
    session = FakeAsyncSession(execute_queue=[
        [],  # parametros.resolver_dias_ventana_ingresos -> SIN fila vigente
        [],  # parametros.resolver_tolerancia_ingreso_pct -> SIN fila vigente
        [],  # facturas agrupadas por documento
        [],  # ingresos agrupados por documento
    ])

    defaults_usados = await orquestador._recalcular_transito(session)

    assert defaults_usados == {
        parametros.CLAVE_DIAS_VENTANA_INGRESOS: parametros.DEFAULT_DIAS_VENTANA_INGRESOS,
        parametros.CLAVE_TOLERANCIA_INGRESO_PCT: parametros.DEFAULT_TOLERANCIA_INGRESO_PCT,
    }


async def test_recalcular_transito_no_registra_defaults_cuando_ambas_claves_estan_configuradas():
    fila_dias = ParametroMetodologia(
        id=uuid.uuid4(), clave=parametros.CLAVE_DIAS_VENTANA_INGRESOS,
        valor=60, vigente_desde=date(2026, 1, 1),
    )
    fila_tolerancia = ParametroMetodologia(
        id=uuid.uuid4(), clave=parametros.CLAVE_TOLERANCIA_INGRESO_PCT,
        valor=3.0, vigente_desde=date(2026, 1, 1),
    )
    session = FakeAsyncSession(execute_queue=[
        [fila_dias],
        [fila_tolerancia],
        [],  # facturas agrupadas por documento
        [],  # ingresos agrupados por documento
    ])

    defaults_usados = await orquestador._recalcular_transito(session)

    assert defaults_usados == {}


async def test_recalcular_transito_y_registrar_defaults_persiste_en_carga_log(monkeypatch):
    """El envoltorio que `ejecutar_aplicar` realmente llama -- prueba el
    merge en `carga.log`, aislado de la mecánica interna de `_recalcular_
    transito` (ya cubierta arriba), per la regla mock-hygiene de este
    proyecto: no hace falta re-armar todo el flujo de tránsito para probar
    un merge de diccionario."""
    carga = _carga("FACTURAS_PEDIDOS", estado="VALIDADO")
    defaults_simulados = {
        parametros.CLAVE_DIAS_VENTANA_INGRESOS: 45,
        parametros.CLAVE_TOLERANCIA_INGRESO_PCT: 2.0,
    }

    async def _fake_recalcular_transito(session_):
        return dict(defaults_simulados)

    monkeypatch.setattr(orquestador, "_recalcular_transito", _fake_recalcular_transito)
    session = FakeAsyncSession(execute_queue=[])

    await orquestador._recalcular_transito_y_registrar_defaults(session, carga)

    assert carga.log["parametros_default_usados"] == defaults_simulados


async def test_recalcular_transito_y_registrar_defaults_no_toca_log_si_nada_defaulteo(monkeypatch):
    carga = _carga("FACTURAS_PEDIDOS", estado="VALIDADO")

    async def _fake_recalcular_transito(session_):
        return {}

    monkeypatch.setattr(orquestador, "_recalcular_transito", _fake_recalcular_transito)
    session = FakeAsyncSession(execute_queue=[])

    await orquestador._recalcular_transito_y_registrar_defaults(session, carga)

    assert carga.log is None


async def test_ejecutar_aplicar_facturas_pedidos_registra_defaults_de_transito_en_carga_log(
    monkeypatch,
):
    """Punta a punta a través de `ejecutar_aplicar`: un default usado por
    `_recalcular_transito` debe sobrevivir hasta `carga.log`, no solo hasta
    el `dict` interno de `_recalcular_transito_y_registrar_defaults`."""
    carga = _carga("FACTURAS_PEDIDOS", estado="VALIDADO")
    defaults_simulados = {parametros.CLAVE_DIAS_VENTANA_INGRESOS: 45}

    async def _fake_recalcular_transito(session_):
        return dict(defaults_simulados)

    monkeypatch.setattr(orquestador, "_recalcular_transito", _fake_recalcular_transito)
    session = FakeAsyncSession(execute_queue=[[], []])  # staging select vacío + delete staging

    await orquestador.ejecutar_aplicar(session, carga)

    assert carga.estado == "APLICADO"
    assert carga.log["parametros_default_usados"] == defaults_simulados
