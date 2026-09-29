"""
Real `.xlsx` date cells come back from openpyxl (`data_only=True`) as
`datetime`, a subclass of `date`. Every stored/`isoformat`'d date must be a
pure `date` ("2026-07-15", never "2026-07-15T00:00:00"), otherwise
`date.fromisoformat` fails later in `aplicar`. These tests feed real
`datetime` cells through dry-run and then Aplicar.
"""
import io
import uuid
from datetime import date, datetime

import openpyxl
import pytest

from tests.motored.conftest import FakeAsyncSession, _ExecuteResult

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import columnas, orquestador

PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()
FECHA = datetime(2026, 7, 15)


class _SesionConStaging(FakeAsyncSession):
    """Un `SELECT` sobre `carga_fila_staging` devuelve lo que el dry-run
    realmente agregó a la sesión (como haría la base de datos)."""

    async def execute(self, stmt):
        texto = str(stmt)
        if texto.lstrip().upper().startswith("SELECT") and "carga_fila_staging" in texto:
            return _ExecuteResult(self.added_of_type(CargaFilaStaging))
        return await super().execute(stmt)


def _xlsx(filas) -> bytes:
    workbook = openpyxl.Workbook()
    for fila in filas:
        workbook.active.append(fila)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _carga(tipo, **overrides) -> CargaArchivo:
    base = dict(
        id=uuid.uuid4(), tipo=tipo, nombre_archivo="a.xlsx", hash_sha256="a" * 64,
        ruta_objeto=f"{tipo}/x.xlsx", bytes=1, estado="PROCESANDO", filas_leidas=0,
        filas_validas=0, filas_rechazadas=0, lotes_staged=0, ultimo_lote_aplicado=0,
        subido_por=uuid.uuid4(),
    )
    base.update(overrides)
    return CargaArchivo(**base)


def _sesion() -> _SesionConStaging:
    cache = [
        [(SUCURSAL_ID, "CALI NORTE", None)],
        [],
        [],
        [("REF1", PROVEEDOR_ID, REFERENCIA_ID)],
        [PROVEEDOR_ID],
    ]
    return _SesionConStaging(execute_queue=cache + [[] for _ in range(30)])


_ARCHIVOS = {
    "FACTURAS_PEDIDOS": (
        [
            ["SIIC", "Sucursal", "Nota crédito", "Factura", "Fecha", "Parte", "Cantidad",
             "Vlr. Total Neto"],
            ["1779", "CALI NORTE", None, "RH193043", FECHA, "REF1", 3, 165078],
        ],
        "fecha_factura",
    ),
    "INGRESOS_FACTURAS": (
        [
            ["Nrodocumento", "Fecha", "Estado", "Dct.referencia", "Valornetolocal"],
            ["IN1", FECHA, "Contabilizado", "RH193043", 2290580],
        ],
        "fecha_ingreso",
    ),
    "BACKORDER": (
        [
            ["SIC", "Sucursal", "Número del pedido", "Estado del pedido", "Referencia Parte",
             "Cantidad Pendiente", "Fecha Creación"],
            ["1779", "CALI NORTE", 74, "BACKORDER", "REF1", 48, FECHA],
        ],
        "fecha_creacion",
    ),
}


def _preparar(tipo, monkeypatch):
    filas, _ = _ARCHIVOS[tipo]
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: _xlsx(filas))

    async def _sin_transito(session):
        return {}

    monkeypatch.setattr(orquestador, "_recalcular_transito", _sin_transito)
    return _carga(tipo, periodo_desde=date(2026, 9, 15), periodo_hasta=date(2026, 9, 15))


def test_a_fecha_normaliza_datetime_a_date_puro():
    assert columnas.a_fecha(datetime(2026, 7, 15, 13, 30)) == date(2026, 7, 15)
    assert type(columnas.a_fecha(datetime(2026, 7, 15))) is date
    assert columnas.a_fecha(date(2026, 7, 15)) == date(2026, 7, 15)


@pytest.mark.parametrize("valor", [None, "2026-07-15", 46218, ""])
def test_a_fecha_devuelve_none_si_no_es_una_fecha(valor):
    assert columnas.a_fecha(valor) is None


@pytest.mark.parametrize("tipo", list(_ARCHIVOS))
async def test_dry_run_guarda_la_fecha_como_date_iso_sin_hora(tipo, monkeypatch):
    carga = _preparar(tipo, monkeypatch)
    session = _sesion()

    await orquestador._dry_run(session, carga)

    assert carga.estado == "VALIDADO", carga.log
    (staged,) = session.added_of_type(CargaFilaStaging)
    assert staged.payload[_ARCHIVOS[tipo][1]] == "2026-07-15"


@pytest.mark.parametrize("tipo", list(_ARCHIVOS))
async def test_dry_run_y_luego_aplicar_con_celdas_datetime_no_fallan(tipo, monkeypatch):
    carga = _preparar(tipo, monkeypatch)
    session = _sesion()

    await orquestador._dry_run(session, carga)
    await orquestador.ejecutar_aplicar(session, carga)

    assert carga.estado == "APLICADO"
