"""
Shared Excel-export response builder.

Extracted from `app/api/v1/imports.py` (originally a private `_excel_response`
helper used by the Motocicletas/Pedidos/Repuestos/Backorders/Reconciliacion
exports) so a second router module (`app/api/v1/orders.py`, the "Gestión de
Órdenes" export) can reuse the exact same openpyxl + StreamingResponse
approach without importing a private helper from a sibling module.
"""
import io

import openpyxl
from starlette.responses import StreamingResponse


def excel_response(ws_title: str, headers: list, rows: list, filename: str) -> StreamingResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = ws_title
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
