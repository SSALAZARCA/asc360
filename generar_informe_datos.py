"""
Script para generar el PDF de documentación de datos de la aplicación.
Uso: python generar_informe_datos.py
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from datetime import date
import os

AZUL_OSCURO  = colors.HexColor("#1E3A5F")
AZUL_MEDIO   = colors.HexColor("#2563EB")
AZUL_CLARO   = colors.HexColor("#DBEAFE")
GRIS_HEADER  = colors.HexColor("#F1F5F9")
GRIS_BORDE   = colors.HexColor("#CBD5E1")
GRIS_TEXTO   = colors.HexColor("#475569")
VERDE        = colors.HexColor("#16A34A")
NARANJA      = colors.HexColor("#EA580C")
ROJO         = colors.HexColor("#DC2626")
VIOLETA      = colors.HexColor("#7C3AED")
AMARILLO_BG  = colors.HexColor("#FEFCE8")
AMARILLO_BD  = colors.HexColor("#CA8A04")

PAGE_W, PAGE_H = A4


def build_styles():
    base = getSampleStyleSheet()
    return {
        "titulo_portada": ParagraphStyle("titulo_portada", parent=base["Title"],
            fontSize=26, textColor=colors.white, spaceAfter=12, alignment=TA_CENTER, leading=32),
        "subtitulo_portada": ParagraphStyle("subtitulo_portada", parent=base["Normal"],
            fontSize=13, textColor=colors.HexColor("#BFDBFE"), alignment=TA_CENTER, spaceAfter=6),
        "h1": ParagraphStyle("h1", parent=base["Heading1"],
            fontSize=17, textColor=colors.white, spaceAfter=4, spaceBefore=0, leading=21),
        "h2": ParagraphStyle("h2", parent=base["Heading2"],
            fontSize=13, textColor=AZUL_OSCURO, spaceBefore=16, spaceAfter=6, leading=16),
        "h3": ParagraphStyle("h3", parent=base["Heading3"],
            fontSize=11, textColor=AZUL_MEDIO, spaceBefore=10, spaceAfter=4, leading=14),
        "body": ParagraphStyle("body", parent=base["Normal"],
            fontSize=9.5, textColor=colors.HexColor("#1E293B"), spaceAfter=5, leading=14, alignment=TA_JUSTIFY),
        "body_small": ParagraphStyle("body_small", parent=base["Normal"],
            fontSize=8.5, textColor=GRIS_TEXTO, spaceAfter=3, leading=12),
        "bullet": ParagraphStyle("bullet", parent=base["Normal"],
            fontSize=9.5, textColor=colors.HexColor("#1E293B"), spaceAfter=3, leading=14,
            leftIndent=14, bulletIndent=4),
        "formula": ParagraphStyle("formula", parent=base["Normal"],
            fontSize=9, textColor=AZUL_OSCURO, fontName="Courier", spaceAfter=4,
            leftIndent=16, leading=13),
        "nota": ParagraphStyle("nota", parent=base["Normal"],
            fontSize=8.5, textColor=AMARILLO_BD, spaceAfter=4, leading=12,
            leftIndent=12, backColor=AMARILLO_BG, borderPad=6),
        "th": ParagraphStyle("th", parent=base["Normal"],
            fontSize=8.5, textColor=colors.white, fontName="Helvetica-Bold",
            alignment=TA_CENTER, leading=11),
        "td": ParagraphStyle("td", parent=base["Normal"],
            fontSize=8.5, textColor=colors.HexColor("#1E293B"), leading=11),
        "td_center": ParagraphStyle("td_center", parent=base["Normal"],
            fontSize=8.5, textColor=colors.HexColor("#1E293B"), leading=11, alignment=TA_CENTER),
        "td_calc": ParagraphStyle("td_calc", parent=base["Normal"],
            fontSize=8.5, textColor=AZUL_MEDIO, leading=11, fontName="Helvetica-Oblique"),
    }


def tabla(styles, headers, rows, col_widths=None):
    header_row = [Paragraph(h, styles["th"]) for h in headers]
    data = [header_row]
    for i, row in enumerate(rows):
        r = []
        for cell in row:
            if isinstance(cell, tuple):
                txt, sty = cell
                r.append(Paragraph(txt, styles[sty]))
            else:
                r.append(Paragraph(str(cell), styles["td"]))
        data.append(r)
    if col_widths is None:
        w = PAGE_W - 3.6 * cm
        col_widths = [w / len(headers)] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    st = [
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_OSCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",          (0, 0), (-1, -1), 0.4, GRIS_BORDE),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(data)):
        bg = GRIS_HEADER if i % 2 == 0 else colors.white
        st.append(("BACKGROUND", (0, i), (-1, i), bg))
    t.setStyle(TableStyle(st))
    return t


def sec_header(styles, num, title):
    d = [[Paragraph(f"{num}  {title}", styles["h1"])]]
    t = Table(d, colWidths=[PAGE_W - 3.6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL_OSCURO),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
    ]))
    return t


def nota(styles, txt):
    return Paragraph(f"ⓘ  {txt}", styles["nota"])


def sp():
    return Spacer(1, 0.4 * cm)


def sp_s():
    return Spacer(1, 0.2 * cm)


# ── Portada ───────────────────────────────────────────────────────────────────
def portada(s):
    E = []
    pt = Table([[Paragraph("Red de Servicio UM Colombia", s["titulo_portada"])]],
               colWidths=[PAGE_W - 3.6 * cm])
    pt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), AZUL_OSCURO),
        ("TOPPADDING",    (0,0),(-1,-1), 60),
        ("BOTTOMPADDING", (0,0),(-1,-1), 40),
        ("LEFTPADDING",   (0,0),(-1,-1), 20),
        ("RIGHTPADDING",  (0,0),(-1,-1), 20),
    ]))
    E.append(Spacer(1, 2*cm))
    E.append(pt)
    E.append(Spacer(1, 0.4*cm))
    sub = Table([[Paragraph("Guía Completa de Información y Cálculos", s["subtitulo_portada"])]],
                colWidths=[PAGE_W - 3.6 * cm])
    sub.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), AZUL_MEDIO),
        ("TOPPADDING",    (0,0),(-1,-1), 14),
        ("BOTTOMPADDING", (0,0),(-1,-1), 14),
        ("LEFTPADDING",   (0,0),(-1,-1), 20),
        ("RIGHTPADDING",  (0,0),(-1,-1), 20),
    ]))
    E.append(sub)
    E.append(Spacer(1, 1.5*cm))
    modulos = (
        "Módulos cubiertos: Pedidos · Estados de Pedidos · Repuestos · Backorders · "
        "Motocicletas · Maestro de Partes · Comparativa de Precios · "
        "Ajuste de Pedidos · Remisiones · Modelos · Informe Gerencial"
    )
    E.append(Paragraph(modulos, ParagraphStyle("dp", parent=s["body"],
        alignment=TA_CENTER, textColor=GRIS_TEXTO, fontSize=9.5)))
    E.append(Spacer(1, 0.8*cm))
    E.append(Paragraph(
        f"Fecha de elaboración: {date.today().strftime('%d de %B de %Y')}",
        ParagraphStyle("fecha", parent=s["body_small"], alignment=TA_CENTER)))
    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 01 — PEDIDOS DE IMPORTACIÓN
# ══════════════════════════════════════════════════════════════════════════════
def s01_pedidos(s):
    E = [sec_header(s,"01","Pedidos de Importación"), sp()]
    E.append(Paragraph(
        "Esta sección muestra todos los pedidos realizados a fábrica, tanto de motocicletas "
        "completas como de kits de repuestos. Cada pedido agrupa un conjunto de unidades o "
        "referencias bajo un mismo documento llamado <b>PI (Proforma Invoice)</b>.", s["body"]))
    E.append(sp())

    E.append(Paragraph("1.1  Columnas de la tabla principal de pedidos", s["h2"]))
    cols = [
        ("Ciclo", "Número de ciclo de importación. Un ciclo agrupa los pedidos de un mismo período comercial.", "Directo"),
        ("PI Number", "Código único del pedido (ej: E0000573). Los pedidos de repuestos llevan el sufijo -SP y un número de secuencia (ej: E0000573-SP-1). Aparece en azul si es SP.", "Directo"),
        ("Modelo", "Nombre del modelo de moto importado, por ejemplo RENEGADE 200 SPORT.", "Directo"),
        ("Cantidad (QTY)", "Para motos: número de unidades. Para repuestos (SP): cantidad de ítems cargados en el detalle del lote. Si no hay detalle cargado todavía, muestra '1LOT'.", "SP: conteo de ítems"),
        ("Fecha de Pedido", "Día en que se registró el pedido.", "Directo"),
        ("ETD", "Estimated Time Departure — fecha estimada de salida del puerto de origen.", "Directo (del Excel de seguimiento)"),
        ("ETA", "Estimated Arrival — fecha estimada de llegada al puerto en Colombia.", "Directo"),
        ("BL / Contenedor", "Número del Bill of Lading y del contenedor. Se completan cuando el pedido ya está en tránsito.", "Directo"),
        ("Docs Digital", "Si los documentos de importación llegaron en formato digital. Valores: PENDING (pendiente) o UPLOADED/READY (recibido).", "Directo"),
        ("Docs Original", "Si los documentos físicos originales fueron recibidos.", "Directo"),
        ("Estado", "Etapa logística actual. Se calcula automáticamente comparando las fechas clave con la fecha de hoy. Ver sección 02.", "CALCULADO"),
        ("Nacion.", "Solo para pedidos SP. Si el lote ya fue nacionalizado: PARCIAL o COMPLETO.", "Directo, solo SP"),
        ("Badge SP", "Etiqueta naranja que aparece cuando el pedido es de repuestos, para diferenciarlo de pedidos de motos.", "Visual"),
    ]
    E.append(tabla(s, ["Campo visible","Qué significa","Origen"],
        [((c,"td"),(d,"td"),(o,"td_calc" if "CALCULADO" in o else "td")) for c,d,o in cols],
        [3.2*cm, 10*cm, 4*cm]))

    E.append(sp())
    E.append(Paragraph("1.2  Fechas de la cadena logística (ETR, ETL, ETD, ETA)", s["h2"]))
    fechas = [
        ("ETR — Estimated Time Ready", "Fecha en que el pedido estará listo para salir de fábrica. Primera etapa."),
        ("ETL — Estimated Time Loading", "Fecha en que el pedido será cargado en el barco."),
        ("ETD — Estimated Time Departure", "Fecha de salida del puerto de origen."),
        ("ETA — Estimated Arrival", "Fecha de llegada al puerto de destino en Colombia."),
    ]
    E.append(tabla(s, ["Fecha","Qué representa"],
        [((f,"td"),(d,"td")) for f,d in fechas], [5*cm, 12*cm]))
    E.append(sp())
    E.append(nota(s, "Cada pedido tiene una línea de tiempo visual que muestra estas cuatro fechas con semáforo: "
        "Verde = alcanzado, Azul = próxima etapa, Gris = pendiente."))

    E.append(sp())
    E.append(Paragraph("1.3  Acciones disponibles sobre los pedidos", s["h2"]))
    acciones = [
        ("Ver detalle", "Abre un modal con las unidades de moto o los lotes de repuestos del pedido.", "Editor de importaciones"),
        ("Editar pedido", "Permite cambiar fechas, modelo, BL, estado de documentos y otros datos.", "Editor, superadmin"),
        ("Eliminar pedido", "Elimina el pedido. Requiere confirmación.", "Superadmin, administrativo"),
        ("Cambiar Nacion.", "Selector inline para marcar si el lote SP fue nacionalizado parcial o totalmente.", "Editor, superadmin (solo SP)"),
        ("Ver línea de tiempo", "Muestra las cuatro fechas con su estado visual de progreso.", "Editor, superadmin"),
        ("Exportar Excel", "Descarga un archivo .xlsx con todos los campos del pedido.", "Superadmin"),
        ("Importar Shipment Status", "Sube un Excel masivo que crea o actualiza pedidos en bloque.", "Superadmin"),
        ("Importar Packing List Motos", "Sube un Excel con los VINs y números de motor de las motos.", "Superadmin, administrativo"),
        ("Nuevo Pedido", "Crea un pedido de motos o SP manualmente o desde un Excel.", "Superadmin, editor"),
    ]
    E.append(tabla(s, ["Acción","Qué hace","Quién puede usarla"],
        [((a,"td"),(d,"td"),(r,"td")) for a,d,r in acciones],
        [3.5*cm, 9*cm, 4.5*cm]))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 02 — ESTADOS DE PEDIDOS
# ══════════════════════════════════════════════════════════════════════════════
def s02_estados(s):
    E = [sec_header(s,"02","Estados de Pedidos"), sp()]
    E.append(Paragraph(
        "El campo Estado es uno de los más importantes de la tabla de pedidos. "
        "No se ingresa manualmente: el sistema lo calcula automáticamente en cada consulta "
        "comparando las cuatro fechas logísticas (ETR, ETL, ETD, ETA) con la fecha actual. "
        "Si el estado guardado quedó desactualizado, el sistema lo corrige solo al volver a consultarlo.",
        s["body"]))
    E.append(sp())

    E.append(Paragraph("2.1  Estados posibles del pedido y cuándo se asignan", s["h2"]))
    E.append(Paragraph(
        "El sistema evalúa los estados en el orden de la tabla de arriba hacia abajo. "
        "Asigna el primero que se cumpla y no sigue revisando.", s["body"]))
    E.append(sp_s())
    estados_pedido = [
        ("cancelado",          "Azul gris",  "El pedido fue marcado manualmente como cancelado."),
        ("completado",         "Verde",      "La ETA ya pasó, hay BL registrado y no quedan ítems pendientes."),
        ("completado_parcial", "Verde suave","La ETA ya pasó, hay BL, pero aún quedan algunos ítems sin recibir."),
        ("nacionalizado",      "Verde",      "La ETA pasó, hay BL, y se marcó el pedido como nacionalizado."),
        ("en_destino",         "Amarillo",   "La ETA ya pasó pero todavía no hay BL registrado."),
        ("en_transito",        "Naranja",    "El barco ya salió (ETD pasó) y la ETA aún no llegó."),
        ("en_transito_parcial","Naranja",    "El barco salió, pero solo una parte del pedido va en ese embarque."),
        ("en_origen",          "Violeta",    "El ETL pasó (fue cargado) pero el ETD aún no llegó."),
        ("listo_fabrica",      "Violeta",    "El ETR pasó (está listo en fábrica) pero todavía no fue cargado."),
        ("en_preparacion",     "Azul",       "Ninguna fecha de la cadena se cumplió todavía. El pedido está en fabricación."),
    ]
    E.append(tabla(s, ["Estado","Color badge","Cuándo se asigna"],
        [((st,"td"),(c,"td"),(d,"td")) for st,c,d in estados_pedido],
        [4*cm, 2.5*cm, 10.5*cm]))

    E.append(sp())
    E.append(Paragraph("2.2  Estados de documentos (Docs Digital y Docs Original)", s["h2"]))
    estados_docs = [
        ("PENDING",         "Naranja", "Los documentos todavía no llegaron."),
        ("UPLOADED / READY","Verde",   "Los documentos fueron recibidos y cargados en el sistema."),
    ]
    E.append(tabla(s, ["Estado","Color","Qué significa"],
        [((st,"td"),(c,"td"),(d,"td")) for st,c,d in estados_docs],
        [4*cm, 2.5*cm, 10.5*cm]))

    E.append(sp())
    E.append(Paragraph("2.3  Estados de ítems de repuesto (dentro de cada lote SP)", s["h2"]))
    E.append(Paragraph(
        "Cada referencia dentro de un lote de repuestos tiene su propio estado que indica "
        "en qué etapa está esa pieza específica:", s["body"]))
    E.append(sp_s())
    estados_item = [
        ("PENDING",           "Gris",       "La pieza fue pedida pero no hay ninguna confirmación de llegada todavía."),
        ("PARTIAL",           "Naranja",    "Llegó una parte de lo pedido, pero no todo."),
        ("DECLARED",          "Azul",       "La pieza ya pasó por la declaración aduanera."),
        ("RECEIVED",          "Verde",      "La cantidad pedida llegó completa."),
        ("BACKORDER",         "Rojo suave", "La pieza no llegó en este pedido. Se espera en un pedido futuro."),
        ("BACKORDER_PARCIAL", "Naranja",    "Llegó una parte; el resto quedó pendiente para el próximo pedido."),
        ("CANCELLED",         "Gris oscuro","La pieza fue retirada del pedido y no se espera que llegue."),
    ]
    E.append(tabla(s, ["Estado","Color","Qué significa"],
        [((st,"td"),(c,"td"),(d,"td")) for st,c,d in estados_item],
        [4*cm, 2.5*cm, 10.5*cm]))

    E.append(sp())
    E.append(nota(s, "El estado 'qty_pending' (cantidad pendiente) se recalcula automáticamente "
        "en el backend cada vez que se actualiza un ítem: es simplemente la diferencia entre "
        "lo pedido y lo recibido, con un mínimo de cero."))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 03 — LOTES DE REPUESTOS (SPARE PARTS)
# ══════════════════════════════════════════════════════════════════════════════
def s03_repuestos(s):
    E = [sec_header(s,"03","Lotes de Repuestos (Spare Parts)"), sp()]
    E.append(Paragraph(
        "Cuando un pedido es de repuestos (SP), dentro del pedido se activa la pestaña "
        "<b>Spare Parts</b>. Allí se gestiona el detalle de cada lote: qué partes se pidieron, "
        "cuántas llegaron, cuánto valió el pedido y en qué estado está cada referencia.", s["body"]))
    E.append(sp())

    E.append(Paragraph("3.1  KPIs del encabezado (tarjetas de resumen)", s["h2"]))
    kpis = [
        ("Lotes activos",      "Cuántos lotes de repuestos están activos. Es simplemente el conteo de filas visibles en la tabla."),
        ("Unidades totales",   "Suma de las cantidades pedidas en todos los lotes. Si un lote tiene 50 unidades y otro 30, el total es 80."),
        ("Refs. únicas",       "Cuántos números de parte distintos hay en todos los lotes combinados. Una misma referencia no se cuenta dos veces aunque aparezca en lotes distintos."),
        ("Refs. declaradas",   "De todas las referencias, cuántas tienen estado DECLARED (ya pasaron por declaración aduanera)."),
        ("Valor declarado USD","Suma del valor declarado en aduana de todos los lotes. Lo ingresa el área de importaciones al hacer la declaración."),
        ("Total FOB USD",      "Suma del valor FOB (precio sin flete ni seguro) de todos los lotes. Si algún lote todavía usa precio estimado del PI (sin Packing List real), se muestra en naranja con la etiqueta 'est.'"),
    ]
    E.append(tabla(s, ["KPI","Cómo se calcula"],
        [((k,"td"),(d,"td")) for k,d in kpis], [4.5*cm, 12.5*cm]))

    E.append(sp())
    E.append(Paragraph("3.2  Información que muestra cada lote (fila expandible)", s["h2"]))
    lote = [
        ("Identificador del lote",  "El código PI del lote SP (ej: E0000573-SP).", "Directo"),
        ("Modelos",                 "Lista de modelos de moto a los que aplican las partes. Se arma juntando sin repetir los modelos de todos los ítems.", "Calculado: modelos únicos"),
        ("Refs (ítems únicos)",     "Cuántos números de parte distintos tiene ese lote.", "Calculado: conteo de part_numbers"),
        ("Unidades (qty total)",    "Suma de todas las cantidades pedidas en los ítems del lote.", "Calculado: suma de qty_ordered"),
        ("% Recibido",              "Qué porcentaje del total pedido llegó físicamente. Fórmula: (suma de recibidos ÷ suma de pedidos) × 100. Se muestra como barra de progreso.", "Calculado: recibido ÷ pedido × 100"),
        ("Valor pedido USD",        "Valor de lo pedido. Si hay Packing List: precio_real × qty_ordenada. Si no: precio_estimado_PI × qty_ordenada.", "Calculado según disponibilidad de PL"),
        ("Valor Packing List USD",  "Valor de lo que realmente llegó según el Packing List: precio_real × cantidad_recibida. Solo para ítems con packing list y no cancelados.", "Calculado: precio_PL × cant_recibida"),
        ("Rotación % por clase",    "Para cada ítem del lote se revisa su clase de rotación. Se calcula qué % del lote pertenece a Alta, Media, Baja o sin clasificar.", "Calculado: ítems_clase ÷ total × 100"),
        ("Detail loaded",           "Indica si ya se cargó el detalle de la orden con todos los ítems (sí/no).", "Directo"),
        ("Packing list received",   "Indica si ya se cargó el Packing List oficial del proveedor (sí/no).", "Directo"),
    ]
    E.append(tabla(s, ["Dato","Qué significa y cómo se calcula","Origen"],
        [((d,"td"),(e,"td"),(o,"td_calc" if "Calculado" in o else "td")) for d,e,o in lote],
        [3.8*cm, 9.5*cm, 3.7*cm]))

    E.append(sp())
    E.append(Paragraph("3.3  Columnas de la tabla de ítems (partes individuales)", s["h2"]))
    items = [
        ("Parte #",       "Código de fábrica de la pieza (ej: 30100-B01-0000). Se normaliza automáticamente: mayúsculas y sin espacios.", "Directo (normalizado)"),
        ("Descripción ES","Nombre en español. Se ingresa manualmente o se importa del Excel.", "Directo"),
        ("Descripción EN","Nombre en inglés del fabricante.", "Directo"),
        ("Modelo",        "Modelo de moto al que aplica la pieza.", "Directo"),
        ("Rot.",          "Alta / Media / Baja. Viene del catálogo de partes.", "Del catálogo"),
        ("Pcs Ord.",      "Cuántas unidades se pidieron a fábrica.", "Directo"),
        ("Pcs Rec.",      "Cuántas unidades llegaron según el Packing List.", "Directo"),
        ("Inv. Físico",   "Cuántas unidades se contaron en el depósito durante la inspección. Vacío = no inspeccionado todavía.", "Directo (null = sin inspección)"),
        ("Diferencia",    "La diferencia entre lo contado (o recibido si no hay inspección) y lo pedido. Negativo = faltaron piezas.", "Calculado: físico (o recibido) − pedido"),
        ("FOB PI",        "Precio unitario USD estimado del PI original. Es el precio preliminar.", "Directo del PI"),
        ("Unit Price",    "Precio unitario USD confirmado por el Packing List. Es el precio real definitivo.", "Directo del Packing List"),
        ("Amount",        "Importe total de la línea: precio unitario × cantidad pedida.", "Calculado al cargar el PL"),
        ("Estado",        "Estado de esa pieza. Ver tabla de estados en sección 02.", "Directo"),
    ]
    E.append(tabla(s, ["Columna","Qué significa","Origen"],
        [((c,"td"),(d,"td"),(o,"td_calc" if "Calculado" in o else "td")) for c,d,o in items],
        [3.2*cm, 10.5*cm, 3.3*cm]))

    E.append(sp())
    E.append(Paragraph("3.4  Acciones disponibles sobre los lotes", s["h2"]))
    acc_lotes = [
        ("Reconciliar Packing List",   "Se sube el Excel del proveedor. El sistema cruza cada ítem contra el pedido y asigna COMPLETE / PARTIAL / MISSING / EXTRA.", "Editor+"),
        ("Confirmar reconciliación",   "Bloquea el lote y genera automáticamente los backorders para las piezas que no llegaron.", "Editor+"),
        ("Cargar Inv. Físico (Excel)", "Solo cuando hay Packing List. Se sube un Excel con part_number y cantidad contada.", "Superadmin, proveedor"),
        ("Editar inv. físico inline",  "Edición celda por celda del campo qty_physical.", "Superadmin, proveedor"),
        ("Cancelar pendientes ítem",   "Cierra los backorders abiertos de un ítem específico.", "Superadmin, administrativo"),
        ("Rollback de lote",           "Borra todos los ítems, backorders y packing list del lote para poder volver a cargarlo.", "Superadmin"),
        ("Cargar FOB PI masivo",       "Excel con columnas referencia / pi_number / fob_price. Actualiza los precios estimados.", "Superadmin"),
        ("Exportar ítems Excel",       "Descarga .xlsx con todos los ítems de los lotes visibles.", "Superadmin"),
    ]
    E.append(tabla(s, ["Acción","Qué hace","Quién"],
        [((a,"td"),(d,"td"),(r,"td")) for a,d,r in acc_lotes],
        [4.5*cm, 9*cm, 3.5*cm]))

    E.append(sp())
    E.append(Paragraph("3.5  Reconciliación: Packing List vs. Pedido", s["h2"]))
    E.append(Paragraph(
        "Al cargar el Packing List del proveedor, el sistema compara automáticamente lo pedido "
        "con lo que el proveedor dice que envió. El resultado por cada ítem puede ser:", s["body"]))
    rec = [
        ("COMPLETE", "La cantidad del Packing List es exactamente igual a la pedida."),
        ("PARTIAL",  "El Packing List confirma menos unidades de las pedidas."),
        ("MISSING",  "El Packing List no incluye esa pieza en absoluto."),
        ("EXTRA",    "El Packing List incluye una pieza que no estaba en el pedido, o más unidades de las pedidas."),
    ]
    E.append(tabla(s, ["Resultado","Qué significa"],
        [((r,"td"),(d,"td")) for r,d in rec], [3.5*cm, 13.5*cm]))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 04 — BACKORDERS
# ══════════════════════════════════════════════════════════════════════════════
def s04_backorders(s):
    E = [sec_header(s,"04","Backorders"), sp()]
    E.append(Paragraph(
        "Un backorder es una pieza que se pidió pero no llegó en el pedido esperado. "
        "La pestaña Backorders centraliza todos esos pendientes para hacer seguimiento "
        "de cuándo van a llegar y en qué estado están.", s["body"]))
    E.append(sp())

    E.append(Paragraph("4.1  KPIs del encabezado", s["h2"]))
    kpis = [
        ("Backorders activos",   "Cuántos backorders todavía no se resolvieron."),
        ("Partes únicas afectadas", "Cuántos números de parte distintos tienen backorders activos. Una misma pieza puede tener varios backorders pero se cuenta una sola vez."),
        ("Mayor antigüedad (días)", "Cuántos días tiene el backorder más antiguo de los activos."),
        ("Sin PI asignado",      "Cuántos backorders activos todavía no tienen asignado un pedido futuro donde se espera que lleguen."),
    ]
    E.append(tabla(s, ["KPI","Cómo se calcula"],
        [((k,"td"),(d,"td")) for k,d in kpis], [4.5*cm, 12.5*cm]))

    E.append(sp())
    E.append(Paragraph("4.2  Columnas de la tabla de backorders", s["h2"]))
    cols = [
        ("Parte #",         "El código de la pieza pendiente.", "Directo"),
        ("Rotación",        "Alta / Media / Baja. Del catálogo de partes.", "Del catálogo"),
        ("Descripción",     "Nombre de la pieza en español.", "Directo"),
        ("Moto",            "Modelo de moto al que aplica la pieza.", "Directo"),
        ("PI Origen",       "El pedido donde se pidió originalmente la pieza y no llegó.", "Directo"),
        ("PI Esperado",     "El pedido futuro donde se espera que llegue la pieza. Puede estar vacío.", "Directo"),
        ("Sin Cobrar",      "Unidades que no llegaron ni parcialmente. Fórmula: máximo entre 0 y (pedidas − recibidas).", "Calculado: max(0, pedido − recibido)"),
        ("Cobrado",         "Unidades que llegaron pero que el depósito todavía no inspeccionó físicamente. Fórmula: máximo entre 0 y (recibidas − contadas físicamente).", "Calculado: max(0, recibido − físico)"),
        ("Total pendiente", "La suma de 'Sin Cobrar' más 'Cobrado'.", "Calculado: suma de ambos"),
        ("Días",            "Cuántos días pasaron desde que se registró el backorder.", "Calculado: días desde creación"),
        ("Estado",          "Activo (pendiente) o Resuelto (ya llegó o se canceló).", "Directo"),
    ]
    E.append(tabla(s, ["Columna","Qué significa","Origen"],
        [((c,"td"),(d,"td"),(o,"td_calc" if "Calculado" in o else "td")) for c,d,o in cols],
        [3*cm, 10.5*cm, 3.5*cm]))

    E.append(sp())
    E.append(nota(s, "'Sin Cobrar' = piezas que nunca llegaron. 'Cobrado' = piezas que el proveedor "
        "dice que envió pero que el depósito todavía no confirmó físicamente. "
        "La distinción ayuda al área de inventario a saber si el problema es del proveedor o del depósito."))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 05 — MOTOCICLETAS IMPORTADAS
# ══════════════════════════════════════════════════════════════════════════════
def s05_motos(s):
    E = [sec_header(s,"05","Motocicletas Importadas"), sp()]
    E.append(Paragraph(
        "La pestaña Motocicletas muestra el registro individual de cada unidad importada. "
        "A diferencia de los repuestos (que se manejan por cantidad), aquí cada moto tiene "
        "su propia fila con trazabilidad completa: VIN, motor, color, empadronamiento y gestión con distribuidores.",
        s["body"]))
    E.append(sp())

    E.append(Paragraph("5.1  KPIs del encabezado", s["h2"]))
    kpis = [
        ("Total unidades",   "Cuántas motos hay en el sistema con los filtros activos."),
        ("Empadronadas",     "Cuántas ya tienen el certificado de empadronamiento generado."),
        ("Pendientes",       "Cuántas todavía no están empadronadas. Es el total menos las empadronadas."),
    ]
    E.append(tabla(s, ["KPI","Cómo se calcula"],
        [((k,"td"),(d,"td")) for k,d in kpis], [4*cm, 13*cm]))

    E.append(sp())
    E.append(Paragraph("5.2  Columnas de la tabla de unidades", s["h2"]))
    cols = [
        ("PI Number",          "El código del pedido de donde proviene esta moto.", "Directo"),
        ("Modelo",             "Nombre del modelo.", "Directo"),
        ("VIN",                "Vehicle Identification Number. Código único para cada moto en el mundo.", "Directo"),
        ("Motor No.",          "Número de serie del motor.", "Directo"),
        ("Color RUNT",         "El nombre oficial del color según el RUNT. El color original del Packing List se traduce automáticamente usando una tabla de conversión que mantiene el sistema.", "Calculado: traducción vía tabla RUNT"),
        ("Año Modelo",         "El año del modelo de la moto.", "Directo"),
        ("No. Levante",        "Número de levante aduanero asignado por la DIAN al autorizar la salida de aduana.", "Directo, proceso DIAN"),
        ("Ubicación",          "Lugar físico donde está guardada la moto.", "Directo"),
        ("Naciol.",            "Si esta moto fue separada para el proceso de nacionalización.", "Directo"),
        ("Observación",        "Si tiene alguna novedad (daño, faltante de accesorio, etc.).", "Directo"),
        ("Empadronamiento",    "Si se generó el certificado y, si es así, la fecha en que se generó.", "Directo"),
        ("Gestión Distribuidor","Tres indicadores: si el empadronamiento físico fue enviado al distribuidor, si la moto fue facturada, y si fue cargada al RUNT.", "Directo (tres indicadores)"),
    ]
    E.append(tabla(s, ["Columna","Qué significa","Origen"],
        [((c,"td"),(d,"td"),(o,"td_calc" if "Calculado" in o else "td")) for c,d,o in cols],
        [3.5*cm, 9.5*cm, 4*cm]))

    E.append(sp())
    E.append(Paragraph("5.3  Datos adicionales en el formulario de edición", s["h2"]))
    for item in [
        "<b>Ítem No.:</b> Número de línea que tenía esta moto en el Packing List del proveedor.",
        "<b>Contenedor No.:</b> En qué contenedor viajó esta moto.",
        "<b>Sello No. (Seal):</b> El sello de seguridad del contenedor.",
        "<b>No. Aceptación:</b> Número de aceptación aduanera de la DIAN.",
        "<b>Fecha Aceptación:</b> Cuándo la DIAN aceptó la declaración de importación.",
        "<b>Fecha Levante:</b> Cuándo la DIAN autorizó la salida de aduana.",
        "<b>Color original:</b> El color tal como viene en el Packing List, antes de la traducción a RUNT.",
        "<b>Nombre distribuidor:</b> El distribuidor asignado para el empadronamiento.",
        "<b>PDF DIM:</b> La Declaración de Importación en PDF, almacenada en el sistema.",
    ]:
        E.append(Paragraph(f"• {item}", s["bullet"]))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 06 — MAESTRO DE PARTES
# ══════════════════════════════════════════════════════════════════════════════
def s06_maestro(s):
    E = [sec_header(s,"06","Maestro de Partes"), sp()]
    E.append(Paragraph(
        "El Maestro de Partes es la vista administrativa del catálogo de referencias. "
        "Solo accesible a superadministradores, contiene el registro canónico de todas las piezas "
        "que se manejan, con sus descripciones, precios, rotación, cobertura y acciones de gestión. "
        "Es la fuente de verdad desde la que el sistema calcula precios, gestiona inventario y clasifica piezas.",
        s["body"]))
    E.append(sp())

    E.append(Paragraph("6.1  Panel de cobertura por clase de rotación", s["h2"]))
    E.append(Paragraph(
        "Arriba de la tabla principal aparecen cuatro tarjetas (Alta, Media, Baja, Sin clasificar). "
        "Cada tarjeta muestra para esa clase de rotación:", s["body"]))
    cob_panel = [
        ("Total de partes",  "Cuántas referencias del catálogo están en esa clase."),
        ("Aquí",             "Partes con stock físico confirmado (cantidad contada > 0 en el depósito)."),
        ("En camino",        "Partes recibidas en el Packing List pero sin inspección física todavía."),
        ("Pedido",           "Partes incluidas en un pedido activo sin confirmación de llegada, o en backorder."),
        ("No pedidas",       "Partes que no tienen stock, no están en camino y no están en ningún pedido activo."),
        ("Barras de progreso","Cada estado se muestra como porcentaje visual sobre el total de la clase."),
        ("Exportar no pedidas","Botón para descargar un Excel con las partes sin cobertura de esa clase. Útil para armar el próximo pedido."),
    ]
    E.append(tabla(s, ["Dato","Qué significa"],
        [((d,"td"),(e,"td")) for d,e in cob_panel], [4.5*cm, 12.5*cm]))

    E.append(sp())
    E.append(Paragraph("6.2  Filtros de la tabla", s["h2"]))
    filtros = [
        ("Búsqueda de texto",  "Busca en el código de fábrica, descripción en inglés y descripción en español. Tiene un retardo de 150ms para no hacer llamadas mientras se escribe."),
        ("Modelo",             "Filtra las partes que pertenecen a un modelo de moto específico."),
        ("Rotación",           "Alta / Media / Baja / Sin clasificar."),
        ("Solo pendientes",    "Muestra solo las partes que tienen una tarea activa de verificación de cambio de código."),
        ("Revisar precio",     "Muestra solo las partes marcadas con la bandera de revisión de precio."),
        ("Cobertura",          "Filtra por estado de disponibilidad: Aquí / En camino / Pedido / No pedidas."),
        ("Ordenamiento",       "Haciendo click en los encabezados de columna se ordena de forma ascendente/descendente. El ordenamiento se hace en el servidor, no en el navegador."),
    ]
    E.append(tabla(s, ["Filtro","Cómo funciona"],
        [((f,"td"),(d,"td")) for f,d in filtros], [4*cm, 13*cm]))

    E.append(sp())
    E.append(Paragraph("6.3  Columnas de la tabla principal", s["h2"]))
    cols_m = [
        ("Ref. Fábrica",        "Código oficial del fabricante (ej: 30100-B01-0000) en tipografía naranja. Al inicio de la celda hay un punto de color que indica la cobertura: Verde=Aquí, Azul=En camino, Violeta=Pedido, Rojo=No pedida.", "Clave primaria"),
        ("Descripción (EN)",    "Nombre en inglés extraído del PDF de despiece.", "Del PDF"),
        ("Descripción ES",      "Nombre en español. Toma el texto manual si existe; si no, usa la primera descripción en español que llegó de algún pedido.", "Manual o de pedidos"),
        ("Modelo",              "Modelo de moto al que pertenece la pieza según el catálogo de despiece.", "Del catálogo"),
        ("Rotación",            "Tres botones inline: A (alta), M (media), B (baja). Al hacer click se cambia la clasificación directamente sin abrir ningún modal.", "Manual, editable inline"),
        ("FOB Prom. USD",       "El costo promedio ponderado histórico en dólares. Si todavía no hay Packing List confirmado, se muestra el precio estimado del PI con el badge 'PREL' en naranja.", "Calculado: ver sección 6.4"),
        ("C. Importado COP",    "El costo de traer la pieza a Colombia: FOB Promedio × Factor de importación × TRM.", "Calculado"),
        ("P. Distribuidor COP", "El precio al que UM Colombia le vende la pieza al distribuidor.", "Calculado"),
        ("P. Público Calc. COP","El precio sugerido al público final, calculado automáticamente.", "Calculado"),
        ("Precio Final COP",    "Si hay precio manual definido: aparece en blanco y en negrita. Si no, se usa el calculado en verde itálico. Debajo muestra el margen implícito del proveedor en color semáforo.", "Manual o calculado"),
        ("Flag revisión",       "Bandera amarilla que indica que el precio de esta pieza necesita revisión por el área comercial.", "Manual"),
    ]
    E.append(tabla(s, ["Columna","Qué muestra","Origen"],
        [((c,"td"),(d,"td"),(o,"td_calc" if o=="Calculado" else "td")) for c,d,o in cols_m],
        [3.2*cm, 10.3*cm, 3.5*cm]))

    E.append(sp())
    E.append(Paragraph("6.4  Cómo se calcula el FOB Promedio (costo histórico)", s["h2"]))
    E.append(Paragraph(
        "El FOB Promedio es el precio unitario ponderado de todos los Packing Lists confirmados "
        "que ha tenido esa pieza. Se recalcula automáticamente cada vez que llega un nuevo Packing List.", s["body"]))
    E.append(sp_s())
    E.append(Paragraph(
        "Pasos del cálculo:", s["body"]))
    for paso in [
        "1. Se buscan todos los ítems de pedidos SP que correspondan a esa referencia (incluyendo códigos anteriores si los tiene).",
        "2. Solo se toman los que tienen precio unitario real (del Packing List) y cantidad pedida mayor a cero.",
        "3. Se calcula el promedio ponderado por cantidad:",
    ]:
        E.append(Paragraph(f"   {paso}", s["body"]))
    E.append(Paragraph(
        "FOB Promedio  =  Suma de (precio_unitario × cantidad_pedida)  ÷  Suma de (cantidad_pedida)",
        s["formula"]))
    E.append(Paragraph(
        "Si no hay ningún Packing List confirmado todavía, se usa el precio del PI (FOB Preliminar) "
        "y la columna se marca con PREL.", s["body"]))

    E.append(sp())
    E.append(Paragraph("6.5  Cadena de precios: de FOB a Precio Público", s["h2"]))
    E.append(Paragraph(
        "Todos los factores de la cadena son configurables por el administrador del sistema. "
        "Estos son los valores por defecto:", s["body"]))
    E.append(sp_s())
    factores = [
        ("Factor de importación", "1.42 (42%)", "Cubre flete, seguro, arancel, IVA de importación y gastos de aduana. Al multiplicar el FOB por este factor se obtiene lo que realmente costó la pieza puesta en Colombia."),
        ("Margen proveedor",      "0.35 (35%)", "El margen que UM Colombia aplica sobre el costo importado para cubrir operaciones y utilidad."),
        ("Margen distribuidor",   "0.35 (35%)", "El margen que el distribuidor aplica para llegar al precio público."),
        ("IVA",                   "0.19 (19%)", "El Impuesto al Valor Agregado colombiano."),
        ("TRM",                   "3.800 COP/USD", "Tasa de Cambio Representativa del Mercado. Convierte de dólares a pesos."),
    ]
    E.append(tabla(s, ["Factor","Valor por defecto","Para qué sirve"],
        [((f,"td"),(v,"td"),(d,"td")) for f,v,d in factores],
        [3.8*cm, 3.2*cm, 10*cm]))

    E.append(sp())
    E.append(Paragraph("Paso a paso del cálculo:", s["h3"]))
    pasos = [
        ("Costo importado (USD)",      "FOB Promedio × Factor de importación",                                         "Ej: USD 10 × 1.42 = USD 14.20"),
        ("Precio al distribuidor (USD)","Costo importado × (1 + Margen proveedor) × (1 + IVA)",                       "Ej: 14.20 × 1.35 × 1.19 = USD 22.83"),
        ("Precio público calc. (USD)", "Precio distribuidor × (1 + Margen distribuidor) × (1 + IVA)",                 "Ej: 22.83 × 1.35 × 1.19 = USD 36.69"),
        ("Conversión a pesos (COP)",   "Cualquiera de los precios anteriores × TRM",                                   "Ej: USD 36.69 × 3.800 = COP 139.422"),
    ]
    for paso, formula, ej in pasos:
        E.append(Paragraph(f"<b>{paso}</b>", s["body"]))
        E.append(Paragraph(formula, s["formula"]))
        E.append(Paragraph(f"      → {ej}", s["body_small"]))
        E.append(Spacer(1, 0.12*cm))

    E.append(nota(s, "Si el área comercial define un Precio Final manual, ese precio prevalece sobre el calculado. "
        "El calculado sigue apareciendo en cursiva como referencia."))

    E.append(sp())
    E.append(Paragraph("6.6  Margen implícito del proveedor (semáforo de colores)", s["h2"]))
    E.append(Paragraph(
        "La aplicación calcula qué margen está ganando realmente UM Colombia sobre cada pieza "
        "y lo muestra con un semáforo de colores:", s["body"]))
    semaforo = [
        ("Verde",   "≥ 30%", "Margen saludable."),
        ("Amarillo","≥ 10%", "Margen aceptable, con poco margen de maniobra."),
        ("Naranja", "≥ 0%",  "Margen justo. Riesgo ante cualquier variación de costos."),
        ("Rojo",    "< 0%",  "Margen negativo. Se vende por debajo del costo. Revisión urgente."),
    ]
    E.append(tabla(s, ["Color","Cuándo aparece","Qué significa"],
        [((c,"td"),(v,"td"),(d,"td")) for c,v,d in semaforo],
        [2.5*cm, 3*cm, 11.5*cm]))

    E.append(sp())
    E.append(Paragraph("6.7  Acciones disponibles en el Maestro de Partes", s["h2"]))
    acciones = [
        ("Clasificar rotación masiva", "Sube un Excel con columnas 'part_code' y 'rotation_class' para clasificar muchas piezas de una sola vez.", "Superadmin"),
        ("Recalcular costos (backfill)","Recalcula el FOB Promedio de todas las referencias usando los Packing Lists confirmados que hay en la base de datos.", "Superadmin"),
        ("Cargar FOB PI masivo",        "Sube un Excel con columnas referencia / pi_number / fob_price para actualizar precios estimados.", "Superadmin"),
        ("Exportar no pedidas",         "Por clase de rotación. Genera un Excel con todas las partes que no tienen cobertura activa.", "Superadmin"),
        ("Editar parte",                "Abre un modal para editar descripción, rotación, precio final, códigos anteriores y sustitutos.", "Superadmin"),
        ("Eliminar parte",              "Solo disponible si la parte nunca tuvo un Packing List confirmado (FOB Promedio = vacío). Requiere confirmación.", "Superadmin"),
        ("Verificar cambio de código",  "Cuando el sistema detecta que un código nuevo de un pedido es muy similar a uno ya en el catálogo, genera una alerta para que el admin decida si actualiza el código.", "Superadmin"),
        ("Cargar catálogo PDF",         "Carga el PDF del manual de despiece de un modelo. El sistema extrae automáticamente los números de parte y los agrega al catálogo.", "Superadmin, desde Configuración"),
    ]
    E.append(tabla(s, ["Acción","Qué hace","Quién"],
        [((a,"td"),(d,"td"),(r,"td")) for a,d,r in acciones],
        [4*cm, 10*cm, 3*cm]))

    E.append(sp())
    E.append(Paragraph("6.8  Sustitutos de partes", s["h2"]))
    E.append(Paragraph(
        "Cada pieza puede tener hasta tres referencias sustitutas. Un sustituto es una pieza "
        "alternativa (puede ser de otra marca) que reemplaza funcionalmente a la original. "
        "Se registran: código del sustituto, marca, modelo aplicable y posición de preferencia (1, 2 o 3).",
        s["body"]))

    E.append(sp())
    E.append(Paragraph("6.9  Historial de costos de cada pieza", s["h2"]))
    E.append(Paragraph(
        "El sistema guarda un registro de cada precio que tuvo la pieza en cada pedido. "
        "El historial incluye: lote (PI) que trajo ese precio, código exacto usado en ese pedido, "
        "precio FOB unitario, cantidad, y fecha de registro. "
        "Permite ver cómo evolucionó el costo con el tiempo.",
        s["body"]))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 07 — COMPARATIVA DE PRECIOS
# ══════════════════════════════════════════════════════════════════════════════
def s07_comparativa(s):
    E = [sec_header(s,"07","Comparativa de Precios entre Modelos"), sp()]
    E.append(Paragraph(
        "La pestaña Comparativa permite ver, de un vistazo, qué piezas son compartidas entre "
        "dos o más modelos de moto y cómo varían sus precios FOB entre esos modelos. "
        "Es una herramienta de análisis para el equipo de compras. Solo accesible a superadministradores.",
        s["body"]))
    E.append(sp())

    E.append(Paragraph("7.1  Qué compara y cómo funciona", s["h2"]))
    E.append(Paragraph(
        "El sistema busca todas las referencias de repuestos que aparecen en pedidos de "
        "<b>dos o más modelos de moto distintos</b>. Para cada una muestra el precio FOB "
        "que tuvo en cada modelo. El resultado es una tabla donde las filas son piezas "
        "y las columnas son modelos.", s["body"]))
    E.append(sp_s())
    E.append(Paragraph(
        "Las columnas de modelos son dinámicas: si hay datos para tres modelos, aparecen "
        "tres columnas de precio. Si se filtra por un modelo específico, ese encabezado "
        "se resalta en naranja con borde.", s["body"]))

    E.append(sp())
    E.append(Paragraph("7.2  Columnas de la tabla", s["h2"]))
    cols_comp = [
        ("Referencia",    "Código de fábrica de la pieza (naranja, monospace). Es fija al desplazar la tabla horizontalmente.", "Directo"),
        ("Descripción",   "Nombre en español si existe (en verde); si no, nombre en inglés (en gris).", "Del catálogo"),
        ("Rot.",          "Clasificación de rotación: BAJA (rojo) o MEDIA (amarillo). Sin clasificar muestra '—'.", "Del catálogo"),
        ("[Modelo] precio","Una columna por cada modelo de moto en los datos. Muestra el precio FOB con el sufijo 'PL' (Packing List confirmado) o 'PI' (precio estimado del PI).", "Calculado por modelo"),
    ]
    E.append(tabla(s, ["Columna","Qué muestra","Origen"],
        [((c,"td"),(d,"td"),(o,"td_calc" if "Calculado" in o else "td")) for c,d,o in cols_comp],
        [3.2*cm, 10.3*cm, 3.5*cm]))

    E.append(sp())
    E.append(Paragraph("7.3  Cómo se calcula el precio por celda", s["h2"]))
    E.append(Paragraph(
        "Para cada par (referencia, modelo) el sistema toma el precio más alto registrado "
        "en cualquier pedido de ese modelo:", s["body"]))
    E.append(Paragraph(
        "Precio de celda  =  Máximo entre (unit_price, fob_pi)  de todos los pedidos SP de ese modelo",
        s["formula"]))
    E.append(Paragraph(
        "Adicionalmente se registra si hay al menos un Packing List confirmado para ese par "
        "(is_confirmed). Esto determina el sufijo y el color de fondo de la celda:", s["body"]))
    E.append(sp_s())
    colores_comp = [
        ("Amarillo",   "Es el precio mínimo de esa referencia entre todos sus modelos. Resalta la opción más barata.", "PL o PI"),
        ("Verde suave","Precio confirmado por Packing List (no es el mínimo).", "PL"),
        ("Azul suave", "Precio estimado del PI (sin Packing List). Puede cambiar cuando llegue el packing list real.", "PI"),
        ("Sin color",  "Esa pieza no tiene ningún pedido en ese modelo.", "—"),
    ]
    E.append(tabla(s, ["Color de celda","Qué significa","Sufijo"],
        [((c,"td"),(d,"td"),(suf,"td")) for c,d,suf in colores_comp],
        [3.5*cm, 12*cm, 1.5*cm]))

    E.append(sp())
    E.append(Paragraph("7.4  Filtros disponibles", s["h2"]))
    filtros_comp = [
        ("Búsqueda de texto","Filtra por código de fábrica o descripción. Se aplica en el navegador (sin llamada al servidor)."),
        ("Select de modelo", "Pasa el modelo al servidor. El backend devuelve solo las referencias que tengan precio para ese modelo. El encabezado de esa columna se resalta en naranja."),
    ]
    E.append(tabla(s, ["Filtro","Cómo funciona"],
        [((f,"td"),(d,"td")) for f,d in filtros_comp], [4*cm, 13*cm]))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 08 — AJUSTE DE PEDIDOS
# ══════════════════════════════════════════════════════════════════════════════
def s08_ajuste(s):
    E = [sec_header(s,"08","Ajuste de Pedidos"), sp()]
    E.append(Paragraph(
        "La pestaña Ajuste de Pedidos (o Análisis de Repuestos) ayuda al equipo a "
        "identificar referencias de <b>baja y media rotación</b> que están en pedidos activos "
        "pero que todavía no llegaron, para decidir si conviene cancelarlas o cambiar la cantidad "
        "antes de que el proveedor las despache. Solo accesible a superadministradores.",
        s["body"]))
    E.append(sp())

    E.append(Paragraph("8.1  Criterios de inclusión en la lista", s["h2"]))
    E.append(Paragraph(
        "Una referencia aparece en esta pantalla solo si cumple todos estos criterios a la vez:",
        s["body"]))
    for crit in [
        "La rotación es <b>Baja o Media</b> (las piezas de alta rotación no se incluyen porque siempre conviene tenerlas).",
        "El Packing List <b>todavía no fue recibido</b> para ese lote (es decir, todavía se puede cancelar antes del despacho).",
        "La pieza <b>no tiene stock físico</b> disponible en el depósito.",
        "La pieza <b>no está 'en camino'</b> (sin BL ni packing list confirmado).",
    ]:
        E.append(Paragraph(f"• {crit}", s["bullet"]))

    E.append(sp())
    E.append(Paragraph("8.2  KPIs del encabezado", s["h2"]))
    kpis = [
        ("Para revisar",    "Cuántas referencias únicas cumplen los criterios y aparecen en la lista."),
        ("Unidades totales","Suma de todas las unidades pedidas de esas referencias."),
        ("Baja rotación",   "Cuántas de las referencias son de baja rotación."),
        ("Media rotación",  "Cuántas son de media rotación."),
        ("Total a cancelar","Solo aparece cuando se marcan ítems. Es la suma del valor FOB (USD) de todo lo marcado para cancelar.", "Calculado: FOB × qty para ítems marcados"),
    ]
    E.append(tabla(s, ["KPI","Cómo se calcula"],
        [((k,"td"),(d,"td")) for k,d in [(k,d) for k,d,*_ in kpis]],
        [4*cm, 13*cm]))

    E.append(sp())
    E.append(Paragraph("8.3  Columnas de la tabla", s["h2"]))
    cols_aj = [
        ("Rotación",     "Badge BAJA (verde) o MEDIA (amarillo) de esa referencia.", "Del catálogo"),
        ("Código",       "El código de fábrica de la pieza (naranja, monospace).", "Del catálogo"),
        ("Descripción",  "Nombre en español si existe (verde); si no, nombre en inglés.", "Del catálogo"),
        ("Modelos",      "Lista de modelos de moto que usan esta pieza.", "Del catálogo"),
        ("N° PIs",       "En cuántos lotes distintos está pedida esta referencia.", "Calculado: conteo de lotes"),
        ("Total",        "Suma de las unidades pedidas en todos los PIs de esa referencia.", "Calculado: suma de qty_ordered"),
        ("Costo FOB",    "El precio FOB promedio ponderado de esa referencia en los pedidos activos. Se calcula como el promedio ponderado del máximo entre unit_price y fob_pi por lote.", "Calculado: promedio ponderado"),
        ("PI × cantidad","Chips interactivos: uno por cada lote donde está pedida la pieza. Muestra 'PI-code × cantidad'. Al hacer click se cicla el estado: sin marcar → cancelar → cambiar → sin marcar.", "Interactivo"),
    ]
    E.append(tabla(s, ["Columna","Qué muestra","Origen"],
        [((c,"td"),(d,"td"),(o,"td_calc" if "Calculado" in o else "td")) for c,d,o in cols_aj],
        [3.2*cm, 10.3*cm, 3.5*cm]))

    E.append(sp())
    E.append(Paragraph("8.4  Cómo funciona el marcado de decisiones", s["h2"]))
    E.append(Paragraph(
        "Al hacer click en el chip de un PI, el sistema guarda inmediatamente la decisión "
        "en la base de datos. Las decisiones posibles son:", s["body"]))
    decisiones = [
        ("Sin marcar", "Sin color",  "No se tomó ninguna decisión para ese ítem en ese PI."),
        ("Cancelar",   "Rojo",       "Se cancelará ese ítem de ese PI. El sistema lo eliminará del pedido activo cuando se ejecute."),
        ("Cambiar",    "Naranja",    "Se solicitará un cambio de cantidad para ese ítem. Queda registrado para tramitar con el proveedor."),
    ]
    E.append(tabla(s, ["Decisión","Color","Qué significa"],
        [((d,"td"),(c,"td"),(e,"td")) for d,c,e in decisiones],
        [3*cm, 3*cm, 11*cm]))

    E.append(sp())
    E.append(Paragraph("8.5  Acciones disponibles", s["h2"]))
    acciones_aj = [
        ("Marcar para cancelar / cambiar","Click en el chip del PI. Se persiste de inmediato en la base de datos.", "Superadmin"),
        ("Proceder con cancelaciones",    "Ejecuta las cancelaciones marcadas. Cambia el estado de los ítems a CANCELLED, pone la cantidad pendiente en 0 y recalcula el precio FOB preliminar de la referencia en el catálogo.", "Superadmin"),
        ("Limpiar marcas",                "Borra todas las decisiones del estado local y de la base de datos.", "Superadmin"),
        ("Exportar Excel",                "Genera un .xlsx con columnas: Rotación, Código, Descripción, Modelos, PI Number, Cantidad, Total de la referencia, Decisión.", "Superadmin"),
        ("Filtrar por rotación",          "Toggle: Todas / Solo Baja / Solo Media.", "Superadmin"),
        ("Ordenar",                       "Por: Rotación (default), N° PIs o Total de unidades.", "Superadmin"),
    ]
    E.append(tabla(s, ["Acción","Qué hace","Quién"],
        [((a,"td"),(d,"td"),(r,"td")) for a,d,r in acciones_aj],
        [4*cm, 10*cm, 3*cm]))

    E.append(sp())
    E.append(nota(s, "Las cancelaciones ejecutadas quedan reflejadas en el Informe Gerencial (sección F7) "
        "separadas entre 'ejecutadas en el período' y 'pendientes de ejecutar'."))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 09 — REMISIONES DE INVENTARIO
# ══════════════════════════════════════════════════════════════════════════════
def s09_remisiones(s):
    E = [sec_header(s,"09","Remisiones de Inventario"), sp()]
    E.append(Paragraph(
        "Una remisión es la salida oficial de repuestos del depósito central. "
        "El módulo de Remisiones lleva un registro inmutable de cada despacho: "
        "qué piezas salieron, cuántas, para qué propósito y en qué estado está el despacho. "
        "Solo accesible a superadministradores.",
        s["body"]))
    E.append(sp())

    E.append(Paragraph("9.1  Tipos de remisión", s["h2"]))
    tipos = [
        ("PEDIDO",         "Despacho de repuestos para atender un pedido formal de un distribuidor o taller. Requiere vincular un lote de repuestos de referencia."),
        ("GARANTIA",       "Repuestos despachados para cubrir una garantía."),
        ("CORTESIA",       "Repuesto entregado sin cobro como cortesía al cliente o distribuidor."),
        ("VEHICULO_PROPIO","Repuesto usado en motos del propio inventario de UM Colombia."),
    ]
    E.append(tabla(s, ["Tipo","Qué significa"],
        [((t,"td"),(d,"td")) for t,d in tipos], [3.5*cm, 13.5*cm]))

    E.append(sp())
    E.append(Paragraph("9.2  Estados del ciclo de vida de una remisión", s["h2"]))
    E.append(Paragraph(
        "El ciclo es unidireccional: solo avanza hacia adelante, nunca retrocede.", s["body"]))
    estados_rem = [
        ("BORRADOR",   "Amarillo","La remisión está en preparación. Se pueden agregar, editar o eliminar los ítems. El stock no se afecta todavía."),
        ("DESPACHADO", "Verde",   "La remisión fue confirmada. Se asignó el número de remisión y se registraron los movimientos de inventario (salidas). El stock se redujo."),
        ("ANULADO",    "Rojo",    "La remisión fue revertida. Se generaron movimientos de inventario inversos (entradas) para restaurar el stock."),
    ]
    E.append(tabla(s, ["Estado","Color badge","Qué significa"],
        [((st,"td"),(c,"td"),(d,"td")) for st,c,d in estados_rem],
        [3.5*cm, 3*cm, 10.5*cm]))

    E.append(sp())
    E.append(Paragraph("9.3  Columnas de la tabla de remisiones", s["h2"]))
    cols_rem = [
        ("Número",   "El código único de la remisión. Formato: REM-AÑO-SECUENCIA (ej: REM-2025-0042). Si todavía está en borrador, muestra 'Borrador' en lugar del número.", "Asignado al despachar"),
        ("Tipo",     "El propósito del despacho: PEDIDO, GARANTIA, CORTESIA o VEHICULO_PROPIO.", "Directo"),
        ("Fecha",    "Fecha de creación de la remisión.", "Directo"),
        ("Estado",   "Badge de color según el estado actual.", "Directo"),
        ("Ítems",    "Cuántas líneas de piezas distintas tiene la remisión.", "Calculado: conteo de ítems"),
        ("Acciones", "Varían según el estado. Ver tabla de acciones abajo.", "Condicional"),
    ]
    E.append(tabla(s, ["Columna","Qué muestra","Origen"],
        [((c,"td"),(d,"td"),(o,"td_calc" if "Calculado" in o or "Asignado" in o else "td")) for c,d,o in cols_rem],
        [3*cm, 11*cm, 3*cm]))

    E.append(sp())
    E.append(Paragraph("9.4  Acciones disponibles según estado", s["h2"]))
    acciones_rem = [
        ("Despachar",  "BORRADOR",   "Confirma la remisión. Asigna el número correlativo, valida la disponibilidad de stock (con bloqueo para evitar conflictos) y registra los movimientos de salida."),
        ("Editar",     "BORRADOR",   "Abre el formulario para modificar los ítems antes de despachar."),
        ("Eliminar",   "BORRADOR",   "Elimina la remisión en borrador definitivamente."),
        ("Anular",     "DESPACHADO", "Revierte el despacho. Requiere ingresar un motivo de al menos 5 caracteres. Genera movimientos de entrada para restaurar el stock."),
    ]
    E.append(tabla(s, ["Acción","En estado","Qué hace"],
        [((a,"td"),(e,"td"),(d,"td")) for a,e,d in acciones_rem],
        [3*cm, 3.5*cm, 10.5*cm]))

    E.append(sp())
    E.append(Paragraph("9.5  Formulario de creación/edición de remisión", s["h2"]))
    E.append(Paragraph("Campos del formulario:", s["body"]))
    campos_form = [
        ("Tipo",               "Select para elegir el propósito del despacho."),
        ("Lote de Referencia", "Solo aparece cuando el tipo es PEDIDO. Permite seleccionar el lote de repuestos al que está asociado este despacho."),
        ("Notas",              "Campo opcional para agregar observaciones."),
        ("Ítems",              "Tabla donde se agregan las piezas a despachar. Por cada ítem: código de pieza (con buscador), disponibilidad actual en stock, y cantidad a despachar (no puede superar el disponible)."),
    ]
    E.append(tabla(s, ["Campo","Qué hace"],
        [((c,"td"),(d,"td")) for c,d in campos_form], [4*cm, 13*cm]))

    E.append(sp())
    E.append(Paragraph("9.6  Cómo funciona el control de stock al despachar", s["h2"]))
    E.append(Paragraph(
        "Para evitar que dos despachos simultáneos descuenten el mismo stock, el sistema usa "
        "un mecanismo de bloqueo pesimista:", s["body"]))
    for paso in [
        "1. Al confirmar el despacho, el sistema bloquea los registros de inventario de todas las piezas de la remisión (otros procesos deben esperar).",
        "2. Dentro del bloqueo, vuelve a verificar si hay stock suficiente. Si alguna pieza quedó sin stock desde que se creó el borrador, el despacho se cancela con un error que indica cuáles piezas son el problema.",
        "3. Si todo está bien, registra los movimientos de salida con un número negativo (delta = −cantidad_despachada) y libera el bloqueo.",
        "4. Al anular, registra movimientos de entrada con número positivo (delta = +cantidad_despachada original) para restaurar el stock.",
    ]:
        E.append(Paragraph(paso, s["body"]))

    E.append(sp())
    E.append(Paragraph("9.7  Numeración automática de remisiones", s["h2"]))
    E.append(Paragraph(
        "El número de remisión se asigna automáticamente al momento del despacho, dentro del mismo "
        "bloqueo de stock. El formato es <b>REM-AÑO-SECUENCIA</b>: el año del momento del despacho "
        "y un número secuencial de cuatro dígitos que se reinicia cada año. Ejemplos: "
        "REM-2025-0001, REM-2025-0042, REM-2026-0001.", s["body"]))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 10 — MODELOS DE MOTOCICLETA
# ══════════════════════════════════════════════════════════════════════════════
def s10_modelos(s):
    E = [sec_header(s,"10","Modelos de Motocicleta"), sp()]
    E.append(Paragraph(
        "El módulo de Modelos contiene las especificaciones técnicas oficiales de cada modelo "
        "que UM Colombia comercializa. Se usa también para vincular los pedidos y el catálogo "
        "de partes con cada modelo específico.", s["body"]))
    E.append(sp())

    E.append(Paragraph("10.1  Especificaciones técnicas", s["h2"]))
    specs = [
        ("Nombre del modelo",        "Nombre comercial completo (ej: RENEGADE 200 SPORT)."),
        ("Marca",                    "Siempre UM (UM Motorcycles)."),
        ("Cilindrada",               "Volumen del motor en cc (ej: 200cc)."),
        ("Potencia",                 "Potencia máxima del motor."),
        ("Peso",                     "Peso total de la moto en vacío."),
        ("Vueltas de aire",          "Ajuste del carburador: cuántas vueltas tiene la aguja de aire. Dato de servicio técnico."),
        ("Posición de cortina",      "Ajuste de la cortina del carburador. Dato de servicio técnico."),
        ("Sistemas de control",      "Si tiene ABS u otros sistemas electrónicos."),
        ("Sistema de combustible",   "CARBURADOR o INYECCION."),
        ("Largo / Ancho / Alto",     "Dimensiones totales en milímetros."),
        ("Altura de silla",          "Distancia del piso al asiento en mm."),
        ("Distancia al suelo",       "Ground clearance: distancia del chasis al piso en mm."),
        ("Distancia entre ejes",     "Separación entre eje delantero y trasero en mm."),
        ("Tanque de combustible",    "Capacidad en litros."),
        ("Relación de compresión",   "Cuánto se comprime la mezcla antes de la explosión. Dato técnico del motor."),
        ("Llanta delantera",         "Medida del neumático delantero (ej: 90/90-19)."),
        ("Llanta trasera",           "Medida del neumático trasero."),
    ]
    E.append(tabla(s, ["Especificación","Qué es"],
        [((sp_n,"td"),(d,"td")) for sp_n,d in specs], [5*cm, 12*cm]))

    E.append(sp())
    E.append(Paragraph("10.2  Vinculación de modelos con el catálogo de partes", s["h2"]))
    E.append(Paragraph(
        "Para que el catálogo sepa qué secciones de despiece mostrar para cada modelo, "
        "existe una tabla de vinculación que conecta el nombre del modelo en los pedidos "
        "(tal como viene en el Packing List, ej: 'RENEGADE 200 SPORT') con el código interno "
        "del catálogo (ej: 'RENEGADE200'). Esto permite filtrar las partes por modelo aunque "
        "el nombre en el pedido sea ligeramente distinto al del catálogo.", s["body"]))

    E.append(sp())
    E.append(Paragraph("10.3  Tabla de colores RUNT", s["h2"]))
    E.append(Paragraph(
        "El sistema mantiene una tabla de conversión de colores. Cuando el proveedor describe "
        "el color de una moto en el Packing List (ej: 'RED' o 'ROJO VINO'), el sistema lo busca "
        "en esta tabla y lo convierte automáticamente al código y nombre oficial del RUNT "
        "(Registro Único Nacional de Tránsito). Esta conversión es obligatoria para el "
        "trámite de empadronamiento en Colombia.", s["body"]))
    E.append(Paragraph(
        "La tabla guarda: el color original (tal como viene del proveedor), "
        "el código numérico RUNT y el nombre oficial RUNT.", s["body"]))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 11 — INFORME GERENCIAL
# ══════════════════════════════════════════════════════════════════════════════
def s11_gerencial(s):
    E = [sec_header(s,"11","Informe Gerencial (PDF)"), sp()]
    E.append(Paragraph(
        "El Informe Gerencial es un reporte en PDF que consolida el estado del negocio "
        "en un momento determinado. Se genera eligiendo un rango de fechas (desde / hasta) "
        "y cubre siete secciones denominadas F2 a F8. Está diseñado para que la gerencia "
        "tenga una vista ejecutiva sin necesidad de navegar por los distintos módulos.", s["body"]))
    E.append(sp())

    def sub(titulo, items_list):
        E.append(Paragraph(titulo, s["h2"]))
        E.append(tabla(s, ["Dato en el informe","Cómo se calcula"],
            [((d,"td"),(c,"td")) for d,c in items_list], [5.5*cm, 11.5*cm]))
        E.append(sp())

    sub("11.1  F2 — Pedidos de Importación (sin filtro de fecha — estado actual)", [
        ("Pedidos activos total",      "Todos los pedidos que no están completados ni cancelados."),
        ("Pedidos de motos activos",   "Pedidos activos que son de motocicletas."),
        ("Pedidos de repuestos activos","Pedidos activos que son de Spare Parts (SP)."),
        ("Motos por estado",           "Desglose: cuántos pedidos de motos están en cada estado (nacionalizado, en tránsito, en origen)."),
        ("Unidades de motos totales",  "Suma de las unidades de moto en todos los pedidos activos."),
        ("Repuestos FOB total (USD)",  "Suma del valor FOB de todos los ítems SP en pedidos activos. Usa precio del PI si no hay packing list."),
    ])

    sub("11.2  F3 — Inventario de Motocicletas (sin filtro de fecha — estado actual)", [
        ("Total unidades",                "Todas las motos registradas en el sistema."),
        ("Disponibles",                   "Motos sin observación, sin separar para nacionalización y no facturadas."),
        ("Separadas para nacionalización","Motos marcadas para el proceso de nacionalización."),
        ("Pendientes de empadronamiento", "Motos sin certificado de empadronamiento generado."),
        ("Con observación",               "Motos con alguna novedad registrada."),
        ("Con RUNT",                      "Motos ya cargadas en el sistema RUNT."),
        ("Facturadas histórico",          "Total de motos que alguna vez fueron facturadas al distribuidor."),
        ("Desglose por modelo",           "Para cada modelo: cuántas unidades disponibles y cuántas en total."),
    ])

    sub("11.3  F4 — Cobertura de Repuestos (sin filtro de fecha — estado actual)", [
        ("Total referencias",  "Cuántas referencias distintas hay en el catálogo."),
        ("Aquí",               "Referencias con stock físico confirmado en el depósito."),
        ("En camino",          "Referencias con packing list recibido pero sin inspección física."),
        ("Pedido",             "Referencias en algún pedido activo sin confirmación de llegada."),
        ("Sin cobertura",      "Referencias sin stock, sin en camino y sin pedido activo."),
        ("FOB en stock (USD)", "Valor FOB del stock físico disponible: suma de (cantidad disponible × FOB Promedio) para cada pieza."),
    ])

    sub("11.4  F5 — Rotación de Repuestos (sin filtro de fecha — estado actual)", [
        ("Refs en la clase Alta",   "Cuántas referencias están clasificadas como Alta rotación."),
        ("Refs en la clase Media",  "Cuántas en Media."),
        ("Refs en la clase Baja",   "Cuántas en Baja."),
        ("FOB disponible por clase","El valor FOB del stock físico para cada clase de rotación."),
        ("FOB en riesgo (Media/Baja)","El valor FOB de piezas pedidas pero no llegadas para Media y Baja rotación. Se consideran en riesgo porque son piezas de baja demanda cuya inversión podría quedar inmovilizada."),
    ])

    sub("11.5  F6 — Backorders (filtrado por período seleccionado)", [
        ("Backorders activos",      "Cuántos backorders están sin resolver en el período."),
        ("Resueltos en el período", "Backorders que se resolvieron dentro del rango de fechas seleccionado."),
        ("Referencias afectadas",   "Cuántos números de parte distintos tienen backorders activos."),
        ("FOB pendiente (USD)",     "Valor FOB de los backorders activos: suma de (cantidad pendiente × precio unitario) para cada backorder."),
    ])

    sub("11.6  F7 — Ajuste de Pedidos (filtrado por período)", [
        ("Pendientes de cancelar",        "Decisiones de cancelar marcadas en el módulo Ajuste de Pedidos que todavía no se ejecutaron."),
        ("Pendientes de cambiar",         "Decisiones de cambiar cantidad marcadas pero pendientes."),
        ("Ejecutados en el período",      "Cancelaciones que se concretaron dentro del período."),
        ("FOB en cancelaciones pendientes","Valor FOB de los ítems esperando ser cancelados."),
        ("FOB en cancelaciones ejecutadas","Valor FOB de los ítems ya cancelados en el período."),
    ])

    sub("11.7  F8 — Remisiones de Inventario (filtrado por período)", [
        ("Total despachos",       "Cuántas remisiones en estado DESPACHADO hubo en el período, por tipo."),
        ("FOB despachado (USD)",  "Valor FOB de los ítems despachados en el período: suma de (cantidad × MAX(unit_price, fob_pi)) para los movimientos de tipo DESPACHO."),
        ("Desglose por concepto", "Cada tipo (PEDIDO, GARANTIA, CORTESIA, VEHICULO_PROPIO) con su total de despachos y FOB."),
        ("Total anulaciones",     "Cuántas remisiones fueron anuladas en el período."),
    ])

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# 12 — EXPORTACIONES Y CARGAS
# ══════════════════════════════════════════════════════════════════════════════
def s12_exportaciones(s):
    E = [sec_header(s,"12","Exportaciones y Cargas de Datos"), sp()]
    E.append(Paragraph(
        "El sistema permite tanto exportar información hacia Excel o PDF, como cargar datos "
        "masivamente desde archivos Excel. Esta sección resume todas esas acciones.", s["body"]))
    E.append(sp())

    E.append(Paragraph("12.1  Exportaciones disponibles", s["h2"]))
    exports = [
        ("Pedidos de importación","Excel con columnas: PI Number, Modelo, Ciclo, Cantidad, Tipo, Estado, Contenedores, ETR, ETL, ETD, ETA, Docs Digital, Docs Original, Vessel, BL/Contenedor, Observaciones."),
        ("Ítems de repuestos",    "Excel con columnas: Lote (PI), Part Number, Descripción ES, Descripción EN, Modelo, Qty Pedido, Qty Recibido, Qty Pendiente, Estado, PI Backorder, Precio Unitario USD, Monto USD."),
        ("Backorders",            "Excel con columnas: Part Number, Descripción ES, Modelo, Qty Pendiente, PI Origen, PI Esperado, Días desde origen, Fuente, Estado, Fecha de Creación."),
        ("Motocicletas",          "Excel con todos los campos de cada unidad: VIN, motor, color, empadronamiento y gestión con distribuidor."),
        ("Partes sin pedido",     "Por clase de rotación (Alta/Media/Baja). Excel con referencias que no tienen cobertura activa. Ideal para armar el próximo pedido."),
        ("Ajuste de Pedidos",     "Excel con: Rotación, Código, Descripción, Modelos, PI Number, Cantidad, Total de la referencia, Decisión tomada."),
        ("Informe Gerencial",     "PDF ejecutivo con las 7 secciones (F2–F8) del período seleccionado."),
    ]
    E.append(tabla(s, ["Exportación","Contenido"],
        [((ex,"td"),(c,"td")) for ex,c in exports], [4.5*cm, 12.5*cm]))

    E.append(sp())
    E.append(Paragraph("12.2  Cargas de datos (uploads)", s["h2"]))
    uploads = [
        ("Excel de seguimiento de pedidos", "Crea o actualiza pedidos masivamente: fechas ETR, ETL, ETD, ETA, BL, contenedor y estado de documentos. Solo superadmin."),
        ("Packing List de motos (VINs)",    "Carga los VINs, números de motor, contenedor, sello, colores e ítems de las motos de un pedido."),
        ("Detalle de orden de repuestos",   "Carga los ítems de un lote SP: qué piezas se pidieron, en qué cantidad y a qué precio del PI."),
        ("Packing List de repuestos",       "Carga el packing list oficial del proveedor. Dispara la reconciliación automática y actualiza cantidades y precios."),
        ("Clasificación de rotación masiva","Excel con columnas 'part_code' y 'rotation_class' para clasificar muchas piezas de una vez."),
        ("FOB preliminar desde PI",         "Excel con columnas referencia / pi_number / fob_price para actualizar precios estimados."),
        ("Catálogo de despiece (PDF)",      "El PDF del manual de despiece de un modelo. El sistema extrae automáticamente los números de parte."),
    ]
    E.append(tabla(s, ["Carga","Qué hace"],
        [((u,"td"),(d,"td")) for u,d in uploads], [4.5*cm, 12.5*cm]))

    return E


# ══════════════════════════════════════════════════════════════════════════════
# GENERACIÓN DEL PDF
# ══════════════════════════════════════════════════════════════════════════════
def build_pdf(output_path):
    s = build_styles()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Guía de Datos — Red de Servicio UM Colombia",
        author="UM Colombia",
        subject="Pedidos, Repuestos, Catálogo de Partes y módulos relacionados",
    )

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GRIS_TEXTO)
        canvas.drawRightString(PAGE_W - 1.8*cm, 1.2*cm, f"Página {doc.page}")
        canvas.drawString(1.8*cm, 1.2*cm, "Red de Servicio UM Colombia — Guía de Datos")
        canvas.restoreState()

    elements = []
    elements += portada(s)
    elements += s01_pedidos(s)
    elements += s02_estados(s)
    elements += s03_repuestos(s)
    elements += s04_backorders(s)
    elements += s05_motos(s)
    elements += s06_maestro(s)
    elements += s07_comparativa(s)
    elements += s08_ajuste(s)
    elements += s09_remisiones(s)
    elements += s10_modelos(s)
    elements += s11_gerencial(s)
    elements += s12_exportaciones(s)

    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF generado: {output_path}")


if __name__ == "__main__":
    out = os.path.join(
        r"C:\proyectos IA\UM Colombia\Aplicación red de servicio - copia",
        "Guia_Datos_Pedidos_Repuestos_Catalogo.pdf"
    )
    build_pdf(out)
