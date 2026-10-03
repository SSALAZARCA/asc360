"""
T2 blocker (review 2026-09-28): a blank `.xlsx` cell arrives from openpyxl as
`None`. Before the fix it survived `validate_rows`, became an explicit kwarg
of `ReferenciaCreate`, and `model_dump(exclude_unset=True)` made the upsert-
update overwrite existing data (homologados -> [], nombre -> None, ...).

Integration-style: a REAL `.xlsx` built in memory goes through the same
pipeline the router uses -- `parse_excel_rows` -> `_resolve_referencia_
relaciones` -> `procesar_carga` (validate + upsert) -- against an existing
row with values set, and asserts those values survive.
"""
import io
import uuid
from decimal import Decimal

import openpyxl

from app.motored.api.carga import _resolve_referencia_relaciones
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.services.carga import procesar_carga
from app.motored.services.carga_excel import column_labels, parse_excel_rows
from tests.motored.conftest import FakeAsyncSession


def _xlsx(headers, rows):
    wb = openpyxl.Workbook()
    wb.active.append(headers)
    for row in rows:
        wb.active.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


async def test_blank_cells_in_the_template_wipe_existing_referencia_values():
    """Full replace (motored-referencia-identidad R2): the file is the truth,
    so a blank optional cell CLEARS the stored value."""
    proveedor = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", es_principal=True)
    existing = Referencia(
        id=uuid.uuid4(), codigo="REF1", proveedor_id=proveedor.id, nombre="Filtro viejo",
        linea_comercial="REPUESTOS", unidad_empaque=6, unidad_empaque_advertencia=False,
        precio_normal=Decimal("10"), precio_publico=Decimal("99"), homologados=["KEEP-1", "KEEP-2"], activa=True,
    )
    # Template order: Código, Código del proveedor, Nombre, Línea comercial,
    # Unidad de empaque, Precio Normal, Precio Público, Sustituta, Homologados.
    file_bytes = _xlsx(column_labels("referencia"), [["REF1", "HMCL", None, None, None, 50, None, None, None]])

    filas = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)
    # proveedor lookup, replace plan: all referencias, all proveedores
    db = FakeAsyncSession(execute_queue=[[proveedor], [existing], [proveedor]])
    filas, errores = await _resolve_referencia_relaciones(db, "referencia", filas)
    resultado = await procesar_carga(db, "referencia", filas, errores_previos=errores, confirmar_reemplazo=True)

    assert resultado.ok is True, resultado
    assert resultado.actualizados == 1
    assert existing.precio_normal == 50  # the one provided value is applied
    assert existing.nombre is None
    assert existing.linea_comercial is None
    assert existing.unidad_empaque == 1  # blank -> 1, never 0
    assert existing.unidad_empaque_advertencia is True
    assert existing.precio_publico is None
    assert existing.homologados == []
    assert existing.sustituida_por is None


async def test_blank_principal_cell_never_demotes_an_existing_principal_proveedor():
    existing = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="Viejo", es_principal=True, activa=True)
    file_bytes = _xlsx(column_labels("proveedor"), [["HMCL", "HMCL Colombia", None]])

    filas = parse_excel_rows("proveedor", "proveedores.xlsx", file_bytes)
    db = FakeAsyncSession(execute_queue=[[existing]])
    resultado = await procesar_carga(db, "proveedor", filas)

    assert resultado.ok is True, resultado
    assert existing.nombre == "HMCL Colombia"
    assert existing.es_principal is True


async def test_new_referencia_with_blank_unidad_empaque_still_defaults_to_one_with_a_warning():
    proveedor = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", es_principal=True)
    file_bytes = _xlsx(column_labels("referencia"), [["REF-NEW", "HMCL", None, None, None, None, None, None, None]])

    filas = parse_excel_rows("referencia", "referencias.xlsx", file_bytes)
    db = FakeAsyncSession(execute_queue=[[proveedor], [], [proveedor]])  # proveedor lookup, replace plan
    filas, errores = await _resolve_referencia_relaciones(db, "referencia", filas)
    resultado = await procesar_carga(db, "referencia", filas, errores_previos=errores, confirmar_reemplazo=True)

    assert resultado.ok is True, resultado
    assert resultado.insertados == 1
    created = db.added_of_type(Referencia)[0]
    assert created.unidad_empaque == 1
    assert created.unidad_empaque_advertencia is True
    assert created.homologados == []
    assert resultado.advertencias
