"""
Motored satisfaction survey -- Excel of survey results (per carga or by date range).

Cédula and teléfono are TEXT cells (keep leading zeros); instants are shown in
Bogota time as `AAAA-MM-DD HH:MM`.
"""
import io
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.motored.services.encuesta_resultados import fila_de
from app.motored.services.reloj import BOGOTA_OFFSET

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PREGUNTAS = [
    ("P1. Satisfacción general (1-5)", "satisfaccion_general"),
    ("P2.1 Explicación y asesoría técnica", "p_explicacion_tecnica"),
    ("P2.2 Confianza en la reparación", "p_confianza_reparacion"),
    ("P2.3 Servicio en el taller", "p_servicio_taller"),
    ("P2.4 Calidad del trabajo de los mecánicos", "p_calidad_mecanicos"),
    ("P2.5 Claridad de los cobros", "p_claridad_cobros"),
    ("P2.6 Procedencia y originalidad de los repuestos", "p_originalidad_repuestos"),
    ("P3. Observaciones", "observaciones"),
    ("P4. Autoriza uso de datos", "autoriza_datos"),
]
COLUMNAS = (
    ["ID encuesta", "Cliente", "Cédula", "Teléfono", "Tienda", "Placa", "Línea", "SIC",
     "Archivo de carga", "Fecha de envío", "Fecha de respuesta", "Estado"]
    + [etiqueta for etiqueta, _ in PREGUNTAS]
    + ["Categoría", "N.º caso", "ID caso", "Estado del caso", "Responsable", "Fecha de apertura",
       "Fecha de cierre", "Resultado", "Última actualización del caso", "N.º acciones",
       "Última acción (fecha)", "Última acción (usuario)", "Historial de gestión"]
)
COL_TEXTO = ("Cédula", "Teléfono")
COL_FECHA = ("Fecha de envío", "Fecha de respuesta", "Fecha de apertura", "Fecha de cierre",
             "Última actualización del caso", "Última acción (fecha)")
FORMATO_FECHA = "yyyy-mm-dd hh:mm"
ANCHO_HISTORIAL = 70
TEXTO = "@"
ESTADOS = {"RESPONDIDA": "Respondida", "SIN_RESPONDER": "Sin responder"}
CATEGORIAS = {"DETRACTOR": "Detractor", "SATISFECHO": "Satisfecho"}
POR_TEXTO = {"envio": "fecha de envío de la encuesta", "respuesta": "fecha de respuesta del cliente"}


def _bogota(valor: Optional[datetime]) -> Optional[datetime]:
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(BOGOTA_OFFSET)


def _fecha_hora(valor: Optional[datetime]) -> Optional[str]:
    local = _bogota(valor)
    return local.strftime("%Y-%m-%d %H:%M") if local else None


def _slug(nombre_archivo: str) -> str:
    base = re.sub(r"\.xlsx?$", "", nombre_archivo, flags=re.IGNORECASE)
    return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_") or "carga"


def nombre_por_carga(rows: List[Any]) -> str:
    dia = _bogota(rows[0].carga_created_at).date().isoformat()
    return f"encuesta_{_slug(rows[0].nombre_archivo)}_{dia}.xlsx"


def nombre_por_rango(desde: date, hasta: date, por: str) -> str:
    return f"encuestas_{por}_{desde.isoformat()}_{hasta.isoformat()}.xlsx"


def _texto(hoja: Worksheet, fila: int, columna: int, valor: Any) -> None:
    if valor is None:
        return
    celda = hoja.cell(row=fila, column=columna, value=str(valor))
    celda.number_format = TEXTO
    celda.data_type = "s"


def _ancho(nombre: str) -> int:
    if nombre == "Historial de gestión":
        return ANCHO_HISTORIAL
    if nombre in ("ID encuesta", "ID caso"):
        return 38
    if nombre in ("P3. Observaciones", "Cliente"):
        return 45
    if nombre in COL_FECHA:
        return 18
    return 14 if len(nombre) < 14 else 22


def _fecha_excel(valor: Optional[datetime]) -> Optional[datetime]:
    """Bogota wall-clock as a naive datetime (openpyxl rejects tz-aware values)."""
    local = _bogota(valor)
    return local.replace(tzinfo=None) if local else None


def _respuesta(valor: Any, respondida: bool) -> Any:
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if valor is None:
        return "NS/NR" if respondida else None
    return valor


def _historial(acciones: List[Any]) -> Optional[str]:
    lineas = []
    for a in acciones:
        fecha = _bogota(a.created_at).strftime("%d/%m/%Y %H:%M")
        autor = a.usuario_nombre or "Sistema"
        linea = f"{fecha} · {autor} · {a.tipo}: {a.descripcion}"
        if a.estado_anterior or a.estado_nuevo:
            linea += f" ({a.estado_anterior or '-'} → {a.estado_nuevo or '-'})"
        lineas.append(linea)
    return "\n".join(lineas) or None


def _fila(row: Any, caso: Any, acciones: List[Any]) -> Dict[str, Any]:
    d = fila_de(row)
    respondida = d["estado"] == "RESPONDIDA"
    fila: Dict[str, Any] = {
        "ID encuesta": str(row.registro_id), "Cliente": d["cliente"], "Cédula": d["cedula"],
        "Teléfono": d["telefono"], "Tienda": d["tienda"], "Placa": row.placa, "Línea": row.linea,
        "SIC": row.sic, "Archivo de carga": row.nombre_archivo,
        "Fecha de envío": _fecha_excel(row.carga_created_at),
        "Fecha de respuesta": _fecha_excel(row.respuesta_created_at),
        "Estado": ESTADOS[d["estado"]], "Categoría": CATEGORIAS.get(d["categoria"] or ""),
    }
    for etiqueta, campo in PREGUNTAS:
        fila[etiqueta] = _respuesta(getattr(row, campo), respondida)
    if caso is not None:
        ultima = acciones[-1] if acciones else None
        fila.update({
            "N.º caso": caso.numero, "ID caso": str(caso.caso_id), "Estado del caso": caso.estado,
            "Responsable": caso.asignado_nombre, "Fecha de apertura": _fecha_excel(caso.created_at),
            "Fecha de cierre": _fecha_excel(caso.cerrado_at), "Resultado": caso.resultado,
            "Última actualización del caso": _fecha_excel(caso.updated_at),
            "N.º acciones": len(acciones),
            "Última acción (fecha)": _fecha_excel(ultima.created_at) if ultima else None,
            "Última acción (usuario)": (ultima.usuario_nombre or "Sistema") if ultima else None,
            "Historial de gestión": _historial(acciones),
        })
    return fila


def _tabla(hoja: Worksheet, rows: List[Any], casos: List[Any], acciones: List[Any]) -> None:
    hoja.append(COLUMNAS)
    encabezado = hoja.max_row
    for celda in hoja[encabezado]:
        celda.font = Font(bold=True)
    hoja.freeze_panes = f"A{encabezado + 1}"
    por_respuesta = {c.respuesta_id: c for c in casos}
    por_caso: Dict[Any, List[Any]] = {}
    for a in acciones:
        por_caso.setdefault(a.caso_id, []).append(a)
    posicion = {nombre: i + 1 for i, nombre in enumerate(COLUMNAS)}
    for row in rows:
        caso = por_respuesta.get(row.respuesta_id) if row.respuesta_id is not None else None
        fila = _fila(row, caso, por_caso.get(caso.caso_id, []) if caso else [])
        hoja.append([None] * len(COLUMNAS))
        for nombre, valor in fila.items():
            if valor is None:
                continue
            if nombre in COL_TEXTO:
                _texto(hoja, hoja.max_row, posicion[nombre], valor)
                continue
            celda = hoja.cell(row=hoja.max_row, column=posicion[nombre], value=valor)
            if nombre in COL_FECHA:
                celda.number_format = FORMATO_FECHA
            elif nombre == "Historial de gestión":
                celda.alignment = Alignment(wrap_text=True, vertical="top")
    for nombre, indice in posicion.items():
        hoja.column_dimensions[get_column_letter(indice)].width = _ancho(nombre)


def _bytes(libro: Workbook) -> bytes:
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def construir_por_carga(rows: List[Any], casos: List[Any], acciones: List[Any]) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Encuestas"
    _tabla(hoja, rows, casos, acciones)
    return _bytes(libro)


def construir_por_rango(
    rows: List[Any], casos: List[Any], acciones: List[Any],
    desde: date, hasta: date, por: str, generado: datetime,
) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Encuestas"
    hoja.append([f"Resultados de encuestas · {desde.isoformat()} a {hasta.isoformat()}"])
    hoja["A1"].font = Font(bold=True, size=14)
    hoja.append(["Rango", f"{desde.isoformat()} a {hasta.isoformat()}"])
    hoja.append(["Filtrado por", POR_TEXTO[por]])
    hoja.append(["Generado", _fecha_hora(generado)])
    hoja.append([])
    _tabla(hoja, rows, casos, acciones)
    return _bytes(libro)
