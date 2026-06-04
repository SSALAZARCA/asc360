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
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import date
import os

# ── Colores corporativos ──────────────────────────────────────────────────────
AZUL_OSCURO   = colors.HexColor("#1E3A5F")
AZUL_MEDIO    = colors.HexColor("#2563EB")
AZUL_CLARO    = colors.HexColor("#DBEAFE")
GRIS_HEADER   = colors.HexColor("#F1F5F9")
GRIS_BORDE    = colors.HexColor("#CBD5E1")
GRIS_TEXTO    = colors.HexColor("#475569")
VERDE         = colors.HexColor("#16A34A")
NARANJA       = colors.HexColor("#EA580C")
ROJO          = colors.HexColor("#DC2626")
VIOLETA       = colors.HexColor("#7C3AED")
AMARILLO_BG   = colors.HexColor("#FEFCE8")
AMARILLO_BD   = colors.HexColor("#CA8A04")

PAGE_W, PAGE_H = A4


# ── Estilos ───────────────────────────────────────────────────────────────────
def build_styles():
    base = getSampleStyleSheet()

    styles = {
        "titulo_portada": ParagraphStyle(
            "titulo_portada", parent=base["Title"],
            fontSize=28, textColor=colors.white,
            spaceAfter=12, alignment=TA_CENTER, leading=34
        ),
        "subtitulo_portada": ParagraphStyle(
            "subtitulo_portada", parent=base["Normal"],
            fontSize=14, textColor=colors.HexColor("#BFDBFE"),
            alignment=TA_CENTER, spaceAfter=6
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"],
            fontSize=18, textColor=colors.white,
            spaceAfter=4, spaceBefore=0,
            leading=22
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"],
            fontSize=13, textColor=AZUL_OSCURO,
            spaceBefore=16, spaceAfter=6, leading=16,
            borderPad=4
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"],
            fontSize=11, textColor=AZUL_MEDIO,
            spaceBefore=10, spaceAfter=4, leading=14
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontSize=9.5, textColor=colors.HexColor("#1E293B"),
            spaceAfter=5, leading=14, alignment=TA_JUSTIFY
        ),
        "body_small": ParagraphStyle(
            "body_small", parent=base["Normal"],
            fontSize=8.5, textColor=GRIS_TEXTO,
            spaceAfter=3, leading=12
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base["Normal"],
            fontSize=9.5, textColor=colors.HexColor("#1E293B"),
            spaceAfter=3, leading=14,
            leftIndent=14, bulletIndent=4
        ),
        "formula": ParagraphStyle(
            "formula", parent=base["Normal"],
            fontSize=9, textColor=AZUL_OSCURO,
            fontName="Courier", spaceAfter=4,
            leftIndent=16, leading=13
        ),
        "nota": ParagraphStyle(
            "nota", parent=base["Normal"],
            fontSize=8.5, textColor=AMARILLO_BD,
            spaceAfter=4, leading=12,
            leftIndent=12, backColor=AMARILLO_BG,
            borderPad=6
        ),
        "th": ParagraphStyle(
            "th", parent=base["Normal"],
            fontSize=8.5, textColor=colors.white,
            fontName="Helvetica-Bold", alignment=TA_CENTER,
            leading=11
        ),
        "td": ParagraphStyle(
            "td", parent=base["Normal"],
            fontSize=8.5, textColor=colors.HexColor("#1E293B"),
            leading=11
        ),
        "td_center": ParagraphStyle(
            "td_center", parent=base["Normal"],
            fontSize=8.5, textColor=colors.HexColor("#1E293B"),
            leading=11, alignment=TA_CENTER
        ),
        "td_derivado": ParagraphStyle(
            "td_derivado", parent=base["Normal"],
            fontSize=8.5, textColor=AZUL_MEDIO,
            leading=11, fontName="Helvetica-Oblique"
        ),
    }
    return styles


# ── Helpers de tablas ──────────────────────────────────────────────────────────
def tabla_datos(styles, encabezados, filas, col_widths=None):
    """Genera una Table con header azul oscuro y filas alternadas."""
    header = [Paragraph(h, styles["th"]) for h in encabezados]
    data = [header]
    for i, fila in enumerate(filas):
        row = []
        for celda in fila:
            if isinstance(celda, tuple):
                texto, estilo = celda
                row.append(Paragraph(texto, styles[estilo]))
            else:
                row.append(Paragraph(str(celda), styles["td"]))
        data.append(row)

    if col_widths is None:
        available = PAGE_W - 3.6 * cm
        col_widths = [available / len(encabezados)] * len(encabezados)

    t = Table(data, colWidths=col_widths, repeatRows=1)

    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL_OSCURO),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("GRID",       (0, 0), (-1, -1), 0.4, GRIS_BORDE),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUND", (0, 1), (-1, -1), [GRIS_HEADER, colors.white]),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]

    for i in range(1, len(data)):
        bg = GRIS_HEADER if i % 2 == 0 else colors.white
        row_styles.append(("BACKGROUND", (0, i), (-1, i), bg))

    t.setStyle(TableStyle(row_styles))
    return t


def seccion_header(styles, numero, titulo):
    """Crea el bloque de cabecera de sección con fondo azul oscuro."""
    data = [[Paragraph(f"{numero}  {titulo}", styles["h1"])]]
    t = Table(data, colWidths=[PAGE_W - 3.6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL_OSCURO),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    return t


def caja_nota(styles, texto):
    return Paragraph(f"ⓘ  {texto}", styles["nota"])


def separador():
    return HRFlowable(width="100%", thickness=0.5, color=GRIS_BORDE, spaceAfter=8, spaceBefore=4)


# ── Portada ───────────────────────────────────────────────────────────────────
def portada(styles):
    elements = []

    # Rectángulo de color simulado con tabla
    portada_data = [[
        Paragraph("Red de Servicio UM Colombia", styles["titulo_portada"]),
    ]]
    portada_table = Table(portada_data, colWidths=[PAGE_W - 3.6 * cm])
    portada_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL_OSCURO),
        ("TOPPADDING",    (0, 0), (-1, -1), 60),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 40),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
    ]))

    elements.append(Spacer(1, 2 * cm))
    elements.append(portada_table)
    elements.append(Spacer(1, 0.5 * cm))

    # Subtítulo debajo
    sub_data = [[
        Paragraph("Guía Completa de Información y Cálculos", styles["subtitulo_portada"]),
    ]]
    sub_table = Table(sub_data, colWidths=[PAGE_W - 3.6 * cm])
    sub_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL_MEDIO),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
    ]))
    elements.append(sub_table)

    elements.append(Spacer(1, 2 * cm))
    elements.append(Paragraph(
        "Módulos cubiertos: Pedidos de Importación · Repuestos · "
        "Catálogo de Partes · Motocicletas · Backorders · Informe Gerencial",
        ParagraphStyle("desc_portada", parent=styles["body"],
                       alignment=TA_CENTER, textColor=GRIS_TEXTO, fontSize=10)
    ))
    elements.append(Spacer(1, 1 * cm))
    elements.append(Paragraph(
        f"Fecha de elaboración: {date.today().strftime('%d de %B de %Y')}",
        ParagraphStyle("fecha", parent=styles["body_small"],
                       alignment=TA_CENTER)
    ))
    elements.append(PageBreak())
    return elements


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — PEDIDOS DE IMPORTACIÓN
# ══════════════════════════════════════════════════════════════════════════════
def seccion_pedidos(styles):
    E = []
    E.append(seccion_header(styles, "01", "Pedidos de Importación"))
    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph(
        "Esta sección muestra todos los pedidos que la empresa realiza a fábrica, tanto de "
        "motocicletas completas como de kits de repuestos. Cada pedido agrupa un conjunto de "
        "unidades o referencias que viajan juntas bajo un mismo documento de importación llamado "
        "<b>PI (Proforma Invoice)</b>.",
        styles["body"]
    ))
    E.append(Spacer(1, 0.3 * cm))

    # ── 1.1 Tabla principal ──
    E.append(Paragraph("1.1  Datos de la tabla principal de pedidos", styles["h2"]))
    E.append(Paragraph(
        "Cada fila de la tabla representa un pedido activo o histórico. "
        "A continuación se explica qué significa cada columna:", styles["body"]
    ))

    filas_pedidos = [
        ("Ciclo",
         "Número de ciclo de importación al que pertenece el pedido. Un ciclo agrupa los pedidos de un mismo período comercial. Lo define el área de importaciones al crear el pedido.",
         "Directo del registro"),
        ("PI Number",
         "Código único que identifica el pedido, por ejemplo E0000573. Si es un pedido de repuestos (Spare Parts), el código lleva el sufijo -SP y un número de secuencia, por ejemplo E0000573-SP-1.",
         "Directo del registro"),
        ("Modelo",
         "Nombre del modelo de motocicleta que se está importando en ese pedido, por ejemplo RENEGADE 200 SPORT. Para pedidos de repuestos, se muestra el modelo al que aplican las partes.",
         "Directo del registro"),
        ("Cantidad (QTY)",
         "Número de unidades del pedido. Para motos es el número de motocicletas. Para repuestos (SP), la cantidad se cuenta sumando cuántos ítems distintos tiene cargado el detalle del lote.",
         "Para repuestos: se cuenta el total de ítems en el detalle del lote"),
        ("Fecha de Pedido",
         "Día en que se realizó y registró el pedido en el sistema.",
         "Directo del registro"),
        ("ETR — Estimated Time Ready",
         "Fecha estimada en que el pedido estará listo para salir de fábrica. Es la primera marca de tiempo de la cadena logística.",
         "Directo del registro (viene del Excel de seguimiento)"),
        ("ETL — Estimated Time Loading",
         "Fecha estimada en que el pedido será cargado en el barco o medio de transporte.",
         "Directo del registro"),
        ("ETD — Estimated Time Departure",
         "Fecha estimada de salida del puerto de origen.",
         "Directo del registro"),
        ("ETA — Estimated Arrival",
         "Fecha estimada de llegada al puerto de destino en Colombia.",
         "Directo del registro"),
        ("BL / Contenedor",
         "Número del Bill of Lading (documento del barco) y número del contenedor donde viaja la mercancía. Se completan cuando el pedido ya está en tránsito.",
         "Directo del registro"),
        ("Docs Digital",
         "Indica si los documentos de importación (factura, lista de empaque, BL) llegaron en formato digital. Puede estar en PENDING (pendiente) o RECEIVED (recibido).",
         "Directo del registro"),
        ("Docs Original",
         "Similar al anterior, pero para los documentos físicos originales, que en algunos casos la aduana exige.",
         "Directo del registro"),
        ("Estado",
         "Etapa logística actual del pedido. Este dato NO se ingresa manualmente; el sistema lo calcula automáticamente revisando las fechas de la cadena logística.",
         "CALCULADO automáticamente — ver detalle abajo"),
        ("Nacion.",
         "Solo aplica a pedidos de repuestos (SP). Indica si el lote ya fue nacionalizado (COMPLETO), está en proceso (PARCIAL) o aún no (vacío).",
         "Directo del registro, solo para SP"),
        ("Badge SP",
         "Etiqueta naranja que aparece junto al PI Number cuando el pedido es de repuestos (Spare Parts), para diferenciarlo visualmente de pedidos de motos.",
         "Directo del tipo de pedido"),
    ]

    W = PAGE_W - 3.6 * cm
    col_w = [3 * cm, 9.5 * cm, 4.5 * cm]
    data_header = ["Campo visible", "Qué significa", "De dónde viene"]
    data_rows = [
        (
            (c, "td"), (e, "td"), (o, "td_derivado" if "CALCULADO" in o else "td")
        )
        for c, e, o in filas_pedidos
    ]
    E.append(tabla_datos(styles, data_header, data_rows, col_w))

    E.append(Spacer(1, 0.5 * cm))

    # ── Estado calculado ──
    E.append(Paragraph("1.2  Cómo se calcula el Estado del pedido", styles["h2"]))
    E.append(Paragraph(
        "El estado que aparece en la columna Estado se determina de forma automática "
        "comparando las fechas ETR, ETL, ETD y ETA con la fecha actual. El sistema recorre "
        "una serie de reglas en orden y asigna el primer estado que corresponda:", styles["body"]
    ))
    E.append(Spacer(1, 0.2 * cm))

    estados = [
        ("cancelado",          "Se marcó manualmente como cancelado."),
        ("completado",         "La ETA ya pasó y el BL está cargado. No hay ítems pendientes."),
        ("completado_parcial", "La ETA ya pasó y el BL está cargado, pero aún quedan algunos ítems sin recibir."),
        ("nacionalizado",      "La ETA ya pasó, hay BL, y el pedido fue marcado como nacionalizado."),
        ("en_destino",         "La ETA ya pasó pero todavía no hay BL registrado."),
        ("en_transito",        "La ETD ya pasó (el barco salió) y la ETA aún no llegó."),
        ("en_transito_parcial","El barco ya salió pero solo parte del pedido está en ese barco."),
        ("en_origen",          "El ETL ya pasó (fue cargado) pero el ETD aún no llegó."),
        ("listo_fabrica",      "El ETR ya pasó (está listo en fábrica) pero aún no fue cargado."),
        ("en_preparacion",     "Ninguna de las fechas anteriores se cumplió todavía. El pedido está en proceso de fabricación."),
    ]

    E.append(tabla_datos(
        styles,
        ["Estado", "Cuándo se asigna"],
        [((s, "td"), (d, "td")) for s, d in estados],
        [4.5 * cm, 12.5 * cm]
    ))
    E.append(Spacer(1, 0.4 * cm))
    E.append(caja_nota(styles,
        "El sistema evalúa los estados de arriba hacia abajo. En cuanto encuentra uno que "
        "se cumpla, lo asigna y no sigue revisando. Por eso el orden importa."
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Línea de tiempo ──
    E.append(Paragraph("1.3  Línea de tiempo del pedido", styles["h2"]))
    E.append(Paragraph(
        "Cada pedido tiene una vista de línea de tiempo que muestra las cuatro fechas clave "
        "(ETR, ETL, ETD, ETA) con un semáforo visual:", styles["body"]
    ))
    for item in [
        "<b>Alcanzado (verde):</b> esa fecha ya pasó y el pedido avanzó a la siguiente etapa.",
        "<b>Próxima (azul):</b> es la siguiente etapa que se espera alcanzar.",
        "<b>Pendiente (gris):</b> etapas que todavía están lejos.",
    ]:
        E.append(Paragraph(f"• {item}", styles["bullet"]))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — LOTES DE REPUESTOS (SPARE PARTS)
# ══════════════════════════════════════════════════════════════════════════════
def seccion_repuestos(styles):
    E = []
    E.append(seccion_header(styles, "02", "Lotes de Repuestos (Spare Parts)"))
    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph(
        "Cuando el tipo de pedido es de repuestos (SP), dentro del pedido se despliega una "
        "pestaña especial llamada <b>Spare Parts</b>. Allí se gestiona el detalle de cada "
        "lote de repuestos: qué partes se pidieron, cuántas llegaron, cuánto valió el pedido "
        "y en qué estado está cada referencia.",
        styles["body"]
    ))
    E.append(Spacer(1, 0.3 * cm))

    # ── KPIs del encabezado ──
    E.append(Paragraph("2.1  Indicadores clave (KPIs) del encabezado", styles["h2"]))
    E.append(Paragraph(
        "Antes de la tabla de lotes aparece una fila de tarjetas con resúmenes globales. "
        "Cada una se calcula sumando los datos de todos los lotes visibles:", styles["body"]
    ))

    kpis = [
        ("Lotes activos",
         "Cuántos lotes de repuestos están activos en ese pedido. Se obtiene simplemente contando las filas de la tabla."),
        ("Unidades totales",
         "Suma del total de unidades pedidas en todos los lotes. Por ejemplo, si un lote tiene 50 unidades y otro tiene 30, el total es 80."),
        ("Referencias únicas",
         "Cuántos números de parte distintos aparecen en todos los lotes combinados. Se cuentan sin repetir aunque la misma parte aparezca en lotes distintos."),
        ("Referencias declaradas",
         "De todas las referencias únicas, cuántas ya pasaron por el proceso de declaración aduanera y tienen estado DECLARED."),
        ("Valor declarado (USD)",
         "Suma del valor declarado en aduana de todos los lotes. Este valor lo ingresa el área de importaciones cuando se hace la declaración."),
        ("Total FOB USD",
         "Suma del valor FOB (Free on Board) de todos los lotes. El FOB es el precio de la mercancía sin incluir fletes ni seguros. Si algún lote usa el precio del PI (estimado), se indica con la etiqueta 'est.' para advertir que es provisional."),
    ]

    E.append(tabla_datos(
        styles,
        ["KPI", "Cómo se calcula"],
        [((k, "td"), (d, "td")) for k, d in kpis],
        [4.5 * cm, 12.5 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Por lote ──
    E.append(Paragraph("2.2  Información por lote (fila expandible)", styles["h2"]))
    E.append(Paragraph(
        "Al hacer clic en una fila de lote, se expande para mostrar el detalle. "
        "Estos son los datos que muestra cada lote:", styles["body"]
    ))

    por_lote = [
        ("Identificador del lote",
         "El código PI del lote de repuestos, por ejemplo E0000573-SP.",
         "Directo"),
        ("Modelos",
         "Lista de los modelos de moto a los que aplican las partes de ese lote. Se arma juntando los modelos de todos los ítems del lote sin repetir.",
         "Calculado: unión de modelos únicos"),
        ("Refs (ítems únicos)",
         "Cuántos números de parte distintos tiene ese lote específico.",
         "Calculado: conteo de part_numbers únicos"),
        ("Unidades (qty total)",
         "Suma de todas las cantidades pedidas en los ítems de ese lote.",
         "Calculado: suma de qty_ordered"),
        ("% Recibido",
         "Qué porcentaje del total pedido ya llegó físicamente. Se divide la suma de unidades recibidas entre la suma de unidades pedidas y se multiplica por 100.",
         "Calculado: (recibido ÷ pedido) × 100"),
        ("Valor pedido USD",
         "El valor en dólares de lo que se pidió. Si hay Packing List confirmado, se usa el precio real (unit_price × qty_ordered). Si no hay Packing List, se usa el precio estimado del PI (fob_pi × qty_ordered).",
         "Calculado: precio × cantidad"),
        ("Valor Packing List USD",
         "El valor en dólares de lo que efectivamente llegó según el Packing List. Solo se calcula para ítems con Packing List y que no estén cancelados.",
         "Calculado: precio_packing × cant_recibida"),
        ("Rotación % por clase",
         "Para cada ítem del lote se revisa si tiene clasificación de rotación (Alta, Media, Baja). Se calcula qué porcentaje del lote corresponde a cada clase.",
         "Calculado: ítems_de_clase ÷ total_ítems × 100"),
        ("Detail loaded",
         "Indicador (sí/no) de si ya se cargó el detalle de la orden con todos los ítems.",
         "Directo"),
        ("Packing list received",
         "Indicador (sí/no) de si ya se cargó el Packing List oficial del proveedor.",
         "Directo"),
    ]

    E.append(tabla_datos(
        styles,
        ["Dato", "Qué significa y cómo se calcula", "Origen"],
        [((d, "td"), (e, "td"), (o, "td_derivado" if o.startswith("Calculado") else "td")) for d, e, o in por_lote],
        [3.8 * cm, 10 * cm, 3.2 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Tabla de ítems ──
    E.append(Paragraph("2.3  Tabla de ítems (partes individuales de cada lote)", styles["h2"]))
    E.append(Paragraph(
        "Dentro de cada lote expandido, hay una tabla con una fila por cada número de parte pedido. "
        "Estas son sus columnas:", styles["body"]
    ))

    items = [
        ("Parte # (Part Number)",
         "Código de fábrica que identifica la pieza, por ejemplo 30100-B01-0000. Se normaliza automáticamente: se convierten a mayúsculas y se quitan los espacios sobrantes para evitar duplicados por diferencias de formato.",
         "Directo"),
        ("Descripción ES",
         "Nombre de la pieza en español. Se ingresa manualmente o se importa del Excel de la orden.",
         "Directo"),
        ("Descripción (EN)",
         "Nombre de la pieza en inglés, tal como viene del fabricante.",
         "Directo"),
        ("Modelo",
         "Modelo de moto al que aplica esa pieza específica.",
         "Directo"),
        ("Rotación (Rot.)",
         "Clasificación de cuánto se mueve esa pieza en el mercado: Alta (se vende mucho), Media o Baja. Esta clasificación viene del catálogo de partes.",
         "Del catálogo de partes"),
        ("Pcs Ord. (Piezas pedidas)",
         "Cuántas unidades de esa pieza se pidieron a fábrica.",
         "Directo"),
        ("Pcs Rec. (Piezas recibidas)",
         "Cuántas unidades de esa pieza llegaron confirmadas por el Packing List.",
         "Directo"),
        ("Inv. Físico",
         "Cuántas unidades se contaron físicamente en el depósito durante la inspección. Si aparece vacío, significa que todavía no se hizo la inspección física.",
         "Directo (null = sin inspección)"),
        ("Diferencia",
         "La diferencia entre lo que se contó físicamente (o lo que llegó según Packing List si no hay inspección) y lo que se pidió. Un número negativo significa que faltaron piezas.",
         "Calculado: físico (o recibido) − pedido"),
        ("FOB PI",
         "Precio unitario en dólares que aparecía en el PI original (estimado antes de confirmar). Es el precio preliminar.",
         "Directo (del PI)"),
        ("Unit Price",
         "Precio unitario en dólares confirmado por el Packing List oficial. Es el precio real y definitivo.",
         "Directo (del Packing List)"),
        ("Amount",
         "Importe total para esa línea: precio unitario multiplicado por la cantidad pedida.",
         "Directo (calculado al cargar el Packing List)"),
        ("Estado",
         "En qué etapa está esa pieza. Los estados posibles se explican en el punto 2.4.",
         "Directo"),
    ]

    E.append(tabla_datos(
        styles,
        ["Columna", "Qué significa", "Origen"],
        [((c, "td"), (e, "td"), (o, "td_derivado" if "Calculado" in o else "td")) for c, e, o in items],
        [3.5 * cm, 10.5 * cm, 3 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Estados de ítem ──
    E.append(Paragraph("2.4  Estados posibles de cada pieza", styles["h2"]))

    estados_item = [
        ("PENDING",          "Pendiente. La pieza fue pedida pero todavía no hay Packing List ni confirmación de llegada."),
        ("PARTIAL",          "Parcial. Llegó una parte de lo pedido pero no todo."),
        ("DECLARED",         "Declarada. La pieza ya pasó por la declaración aduanera."),
        ("RECEIVED",         "Recibida. La cantidad pedida llegó completa."),
        ("BACKORDER",        "Pendiente total en backorder. La pieza no llegó en este pedido y se espera en uno futuro."),
        ("BACKORDER_PARCIAL","Pendiente parcial en backorder. Llegó una parte, pero el resto quedó pendiente para el próximo pedido."),
        ("CANCELLED",        "Cancelada. La pieza fue retirada del pedido y no se espera que llegue."),
    ]

    E.append(tabla_datos(
        styles,
        ["Estado", "Qué significa"],
        [((s, "td"), (d, "td")) for s, d in estados_item],
        [4.5 * cm, 12.5 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Reconciliación ──
    E.append(Paragraph("2.5  Reconciliación: Packing List vs. Pedido", styles["h2"]))
    E.append(Paragraph(
        "Cuando llega el Packing List del proveedor, el sistema compara automáticamente "
        "lo que se pedió con lo que el proveedor dice que envió. A este proceso se le llama "
        "reconciliación. El resultado para cada pieza puede ser:", styles["body"]
    ))

    rec = [
        ("COMPLETE",  "La cantidad que dice el Packing List es exactamente igual a la que se pidió."),
        ("PARTIAL",   "El Packing List confirma una cantidad menor a la pedida."),
        ("MISSING",   "El Packing List no incluye esa pieza en absoluto."),
        ("EXTRA",     "El Packing List incluye una pieza que no estaba en el pedido original, o incluye más unidades de las pedidas."),
    ]

    E.append(tabla_datos(
        styles,
        ["Resultado", "Qué significa"],
        [((r, "td"), (d, "td")) for r, d in rec],
        [3.5 * cm, 13.5 * cm]
    ))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — BACKORDERS
# ══════════════════════════════════════════════════════════════════════════════
def seccion_backorders(styles):
    E = []
    E.append(seccion_header(styles, "03", "Backorders"))
    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph(
        "Un backorder es una pieza que se pidió pero que no llegó en el pedido esperado. "
        "La pestaña Backorders centraliza todos esos pendientes para hacer seguimiento "
        "de cuándo van a llegar y en qué estado están.",
        styles["body"]
    ))
    E.append(Spacer(1, 0.3 * cm))

    # ── KPIs ──
    E.append(Paragraph("3.1  Indicadores clave (KPIs) del encabezado", styles["h2"]))

    kpis_bo = [
        ("Backorders activos",
         "Cuántos backorders todavía no se resolvieron. Se cuentan los que tienen estado 'activo'."),
        ("Partes únicas afectadas",
         "Cuántos números de parte distintos tienen backorders activos. Una misma pieza podría aparecer en varios backorders, pero se cuenta una sola vez."),
        ("Mayor antigüedad (días)",
         "El backorder más viejo: cuántos días han pasado desde que se creó el más antiguo de los activos."),
        ("Sin PI asignado",
         "Cuántos backorders activos todavía no tienen asignado un pedido futuro donde se espera que lleguen."),
    ]

    E.append(tabla_datos(
        styles,
        ["KPI", "Cómo se calcula"],
        [((k, "td"), (d, "td")) for k, d in kpis_bo],
        [4.5 * cm, 12.5 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Tabla de backorders ──
    E.append(Paragraph("3.2  Columnas de la tabla de backorders", styles["h2"]))

    cols_bo = [
        ("Parte #",        "El código de la pieza pendiente.",                              "Directo"),
        ("Rotación (Rot.)", "Clasificación Alta / Media / Baja de esa pieza en el catálogo.", "Del catálogo"),
        ("Descripción",    "Nombre de la pieza en español.",                                "Directo"),
        ("Moto",           "Modelo de moto al que aplica la pieza.",                        "Directo"),
        ("PI Origen",      "El pedido donde se pidió originalmente la pieza y no llegó.",   "Directo"),
        ("PI Esperado",    "El pedido futuro donde se espera que llegue la pieza. Puede estar vacío si aún no se sabe.", "Directo"),
        ("Sin Cobrar",
         "Cuántas unidades no llegaron ni siquiera parcialmente. Se calcula como: máximo entre 0 y (cantidad pedida − cantidad recibida).",
         "Calculado: max(0, pedido − recibido)"),
        ("Cobrado",
         "Cuántas unidades llegaron pero que el sistema aún no registró como inspeccionadas físicamente. Se calcula: máximo entre 0 y (cantidad recibida − cantidad contada físicamente).",
         "Calculado: max(0, recibido − físico)"),
        ("Total pendiente", "La suma de 'Sin Cobrar' más 'Cobrado'.",                       "Calculado: suma de los dos anteriores"),
        ("Días",           "Cuántos días han pasado desde que se registró el backorder.",   "Calculado: días desde creación"),
        ("Estado",         "Activo (aún pendiente) o Resuelto (ya llegó o se canceló).",   "Directo"),
    ]

    E.append(tabla_datos(
        styles,
        ["Columna", "Qué significa", "Origen"],
        [((c, "td"), (d, "td"), (o, "td_derivado" if "Calculado" in o else "td")) for c, d, o in cols_bo],
        [3.2 * cm, 10.8 * cm, 3 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))
    E.append(caja_nota(styles,
        "La distinción entre 'Sin Cobrar' y 'Cobrado' es importante para el área de inventario: "
        "'Sin Cobrar' refleja piezas que nunca llegaron, mientras que 'Cobrado' refleja piezas "
        "que el proveedor dice que envió pero que el depósito todavía no confirmó físicamente."
    ))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — MOTOCICLETAS IMPORTADAS
# ══════════════════════════════════════════════════════════════════════════════
def seccion_motos(styles):
    E = []
    E.append(seccion_header(styles, "04", "Motocicletas Importadas"))
    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph(
        "La pestaña de Motocicletas muestra el registro individual de cada unidad importada. "
        "A diferencia de los repuestos, donde se trabaja con cantidades, aquí cada moto tiene "
        "su propia fila con información de trazabilidad: VIN, motor, color, empadronamiento y más.",
        styles["body"]
    ))
    E.append(Spacer(1, 0.3 * cm))

    # ── KPIs ──
    E.append(Paragraph("4.1  Indicadores clave (KPIs) del encabezado", styles["h2"]))

    kpis_motos = [
        ("Total unidades",      "Cuántas motos en total hay registradas (con todos los filtros activos)."),
        ("Empadronadas",        "Cuántas de esas motos ya tienen el certificado de empadronamiento generado."),
        ("Pendientes",          "Cuántas motos todavía no están empadronadas. Es simplemente el total menos las empadronadas."),
    ]

    E.append(tabla_datos(
        styles,
        ["KPI", "Cómo se calcula"],
        [((k, "td"), (d, "td")) for k, d in kpis_motos],
        [4.5 * cm, 12.5 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Columnas ──
    E.append(Paragraph("4.2  Columnas de la tabla de unidades", styles["h2"]))

    cols_motos = [
        ("PI Number",         "El código del pedido de donde viene esta moto.",                                       "Directo"),
        ("Modelo",            "Nombre del modelo de la moto.",                                                        "Directo"),
        ("VIN",               "Número de identificación del vehículo (Vehicle Identification Number). Es único para cada moto en el mundo.", "Directo"),
        ("Motor No.",         "Número de serie del motor de esta moto.",                                              "Directo"),
        ("Color RUNT",        "El nombre oficial del color según el Registro Único Nacional de Tránsito (RUNT). El color original del Packing List se traduce automáticamente al nombre RUNT usando una tabla de conversión que el sistema mantiene.", "Calculado: traducción vía tabla de colores RUNT"),
        ("Año Modelo",        "El año del modelo de la moto.",                                                        "Directo"),
        ("No. Levante",       "Número de levante aduanero asignado por la DIAN cuando la mercancía es autorizada para salir de aduana.", "Directo (del proceso DIAN)"),
        ("Ubicación",         "Lugar físico donde está guardada la moto (depósito, bodega, concesionario).",          "Directo"),
        ("Naciol.",           "Indica si esta moto fue separada específicamente para el proceso de nacionalización.", "Directo"),
        ("Observación",       "Si la moto tiene alguna novedad (daño, faltante de accesorios, etc.), aparece aquí la descripción de esa observación.", "Directo"),
        ("Empadronamiento",   "Muestra si ya se generó el certificado de empadronamiento y, si es así, la fecha en que se generó.", "Directo (bool + fecha)"),
        ("Gestión Distribuidor", "Conjunto de tres indicadores del estado con el distribuidor: si el empadronamiento físico fue enviado al distribuidor, si ya fue facturada, y si ya fue cargada en el RUNT.", "Directo (tres indicadores)"),
    ]

    E.append(tabla_datos(
        styles,
        ["Columna", "Qué significa", "Origen"],
        [((c, "td"), (d, "td"), (o, "td_derivado" if "Calculado" in o else "td")) for c, d, o in cols_motos],
        [3.5 * cm, 10 * cm, 3.5 * cm]
    ))

    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph("4.3  Datos adicionales (accesibles en el formulario de edición)", styles["h2"]))
    E.append(Paragraph(
        "Al abrir el detalle de una moto se pueden ver y editar datos adicionales:", styles["body"]
    ))

    for campo in [
        "<b>Ítem No.:</b> Número de línea que tenía esta moto en el Packing List original del proveedor.",
        "<b>Contenedor No.:</b> En qué contenedor viajó esta moto.",
        "<b>Sello No. (Seal):</b> El sello de seguridad del contenedor.",
        "<b>No. Aceptación:</b> Número de aceptación aduanera asignado por la DIAN.",
        "<b>Fecha Aceptación:</b> Cuándo la DIAN aceptó la declaración de importación.",
        "<b>Fecha Levante:</b> Cuándo la DIAN autorizó el levante de la mercancía (salida de aduana).",
        "<b>Color original:</b> El color tal como viene escrito en el Packing List del proveedor, antes de la traducción a RUNT.",
        "<b>Nombre distribuidor:</b> El nombre del distribuidor al que fue asignada para empadronamiento.",
        "<b>PDF DIM:</b> El documento DIM (Declaración de Importación) en formato PDF, almacenado en el sistema.",
    ]:
        E.append(Paragraph(f"• {campo}", styles["bullet"]))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — CATÁLOGO DE PARTES
# ══════════════════════════════════════════════════════════════════════════════
def seccion_catalogo(styles):
    E = []
    E.append(seccion_header(styles, "05", "Catálogo de Partes"))
    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph(
        "El Catálogo de Partes es el corazón del módulo de repuestos. Contiene el registro "
        "canónico de todas las referencias de piezas que se manejan, con sus descripciones, "
        "precios, rotación y cobertura. Es la fuente de verdad desde donde el sistema "
        "calcula precios, gestiona inventario y clasifica las piezas.",
        styles["body"]
    ))
    E.append(Spacer(1, 0.3 * cm))

    # ── Campos base ──
    E.append(Paragraph("5.1  Campos principales del catálogo", styles["h2"]))

    campos_cat = [
        ("Ref. Fábrica",       "El código de parte oficial del fabricante (ej: 30100-B01-0000). Es el identificador único de cada pieza en el catálogo. Se normaliza a mayúsculas y sin espacios.", "Clave primaria"),
        ("Ref. UM Colombia",   "Código interno que UM Colombia asigna a la pieza. Puede diferir del código de fábrica.",                                             "Directo"),
        ("Descripción (EN)",   "Nombre oficial de la pieza en inglés, extraído del PDF de despiece.",                                                                "Del PDF"),
        ("Descripción ES",     "Nombre de la pieza en español. Lo ingresa manualmente el equipo de UM Colombia.",                                                    "Manual"),
        ("Códigos anteriores", "Si la pieza tuvo cambios de código con el tiempo (actualizaciones del fabricante), aquí se guardan los códigos viejos. El sistema puede buscar por cualquiera de ellos.", "Histórico"),
        ("Unidad de medida",   "Cómo se mide y vende la pieza: por unidad, por par, por kit, etc.",                                                                  "Directo"),
        ("Rotación",           "Clasificación de movimiento: Alta (se vende frecuentemente), Media o Baja. La establece el equipo de ventas o importaciones.",       "Manual o importado"),
        ("FOB Promedio (USD)", "El precio promedio ponderado que ha costado esa pieza en todos los pedidos anteriores. Ver cálculo detallado en punto 5.2.",         "Calculado"),
        ("FOB Preliminar",     "Precio estimado del PI, usado solo cuando todavía no llegó ningún Packing List real para esa pieza. Aparece con la etiqueta PREL.", "Importado del PI"),
        ("Flag revisión precio", "Marca que indica que el precio de esta pieza necesita ser revisado por el área comercial.",                                        "Manual"),
    ]

    E.append(tabla_datos(
        styles,
        ["Campo", "Qué significa", "Origen"],
        [((c, "td"), (d, "td"), (o, "td_derivado" if o == "Calculado" else "td")) for c, d, o in campos_cat],
        [3.5 * cm, 10.5 * cm, 3 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Costo FOB promedio ──
    E.append(Paragraph("5.2  Cómo se calcula el FOB Promedio (costo histórico)", styles["h2"]))
    E.append(Paragraph(
        "El FOB Promedio es el precio unitario ponderado que históricamente ha tenido esa pieza "
        "en todos los Packing Lists confirmados. Se usa para calcular los precios de venta. "
        "La lógica es:", styles["body"]
    ))
    E.append(Spacer(1, 0.2 * cm))
    E.append(Paragraph(
        "1. Se buscan todos los ítems de Spare Parts que correspondan a esa referencia "
        "(incluyendo códigos anteriores si los tiene).", styles["body"]
    ))
    E.append(Paragraph(
        "2. Solo se toman en cuenta los ítems que tienen precio unitario real (del Packing List) "
        "y cantidad pedida mayor a cero.", styles["body"]
    ))
    E.append(Paragraph(
        "3. Se calcula el promedio ponderado por cantidad:", styles["body"]
    ))
    E.append(Spacer(1, 0.15 * cm))
    E.append(Paragraph(
        "FOB Promedio  =  Suma de (precio_unitario × cantidad_pedida)  ÷  Suma de (cantidad_pedida)",
        styles["formula"]
    ))
    E.append(Spacer(1, 0.2 * cm))
    E.append(Paragraph(
        "Este promedio se recalcula automáticamente cada vez que se carga un nuevo Packing List. "
        "Si todavía no hay ningún Packing List confirmado, se usa el precio preliminar del PI "
        "(FOB Preliminar), y la columna se marca con PREL para indicar que es estimado.",
        styles["body"]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Cadena de precios ──
    E.append(Paragraph("5.3  Cadena de precios: de FOB a Precio Público", styles["h2"]))
    E.append(Paragraph(
        "La aplicación calcula automáticamente cuánto debería costar una pieza para el distribuidor "
        "y para el público final, partiendo del costo FOB y aplicando una cadena de factores. "
        "Estos factores son configurables por el administrador del sistema:",
        styles["body"]
    ))
    E.append(Spacer(1, 0.3 * cm))

    factores = [
        ("Factor de importación", "1.42 (42% sobre el FOB)",
         "Cubre todos los costos de traer la pieza al país: flete internacional, seguro, arancel, IVA de importación, y gastos de aduana. "
         "Al multiplicar el FOB por este factor se obtiene lo que realmente costó la pieza puesta en Colombia."),
        ("Margen proveedor",      "35% (0.35)",
         "El porcentaje que UM Colombia agrega sobre el costo importado para cubrir sus costos operativos y obtener su utilidad."),
        ("Margen distribuidor",   "35% (0.35)",
         "El porcentaje que el distribuidor aplica sobre el precio que UM le vende, para llegar al precio que le cobran al público."),
        ("IVA",                   "19% (0.19)",
         "El Impuesto al Valor Agregado que aplica Colombia sobre la venta de repuestos."),
        ("TRM",                   "3.800 COP/USD (configurable)",
         "La Tasa de Cambio Representativa del Mercado. Se usa para convertir los precios de dólares a pesos colombianos."),
    ]

    E.append(tabla_datos(
        styles,
        ["Factor", "Valor por defecto", "Para qué sirve"],
        [((f, "td"), (v, "td"), (d, "td")) for f, v, d in factores],
        [3.8 * cm, 3.2 * cm, 10 * cm]
    ))

    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph("Paso a paso del cálculo de precios:", styles["h3"]))

    pasos = [
        ("Costo importado (USD)",
         "FOB Promedio  ×  Factor de importación",
         "Ej: USD 10 × 1.42 = USD 14.20"),
        ("Precio al distribuidor (USD)",
         "Costo importado  ×  (1 + Margen proveedor)  ×  (1 + IVA)",
         "Ej: 14.20 × 1.35 × 1.19 = USD 22.83"),
        ("Precio público calculado (USD)",
         "Precio distribuidor  ×  (1 + Margen distribuidor)  ×  (1 + IVA)",
         "Ej: 22.83 × 1.35 × 1.19 = USD 36.69"),
        ("Conversión a COP",
         "Cada precio anterior  ×  TRM",
         "Ej: USD 36.69 × 3.800 = COP 139.422"),
    ]

    for paso, formula, ejemplo in pasos:
        E.append(Paragraph(f"<b>{paso}</b>", styles["body"]))
        E.append(Paragraph(formula, styles["formula"]))
        E.append(Paragraph(f"      → {ejemplo}", styles["body_small"]))
        E.append(Spacer(1, 0.15 * cm))

    E.append(caja_nota(styles,
        "Si el área comercial establece un Precio Final manual para una pieza, ese precio "
        "manual prevalece sobre el calculado. El precio calculado sigue apareciendo, pero "
        "en cursiva, para referencia."
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Margen implícito ──
    E.append(Paragraph("5.4  Margen implícito del proveedor (semáforo)", styles["h2"]))
    E.append(Paragraph(
        "La aplicación calcula el margen que realmente está ganando UM Colombia sobre cada pieza, "
        "considerando el precio final que se le cobra al distribuidor. Este margen tiene un semáforo "
        "de colores para identificar de un vistazo las piezas con márgenes preocupantes:",
        styles["body"]
    ))

    margenes = [
        ("Verde",   "≥ 30%",  "Margen saludable. La pieza genera buena rentabilidad."),
        ("Amarillo","≥ 10%",  "Margen aceptable. Está dentro de lo esperado pero con poco margen de maniobra."),
        ("Naranja", "≥ 0%",   "Margen justo. Apenas cubre costos; hay riesgo de pérdida ante cualquier variación."),
        ("Rojo",    "< 0%",   "Margen negativo. Se está vendiendo por debajo del costo. Requiere revisión urgente."),
    ]

    E.append(tabla_datos(
        styles,
        ["Color", "Cuándo aparece", "Qué significa"],
        [((c, "td"), (v, "td"), (d, "td")) for c, v, d in margenes],
        [2.5 * cm, 3 * cm, 11.5 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Cobertura ──
    E.append(Paragraph("5.5  Cobertura de cada pieza (punto de color en la tabla)", styles["h2"]))
    E.append(Paragraph(
        "Al inicio de la columna de referencia de fábrica aparece un pequeño punto de color "
        "que indica en qué situación está esa pieza en términos de disponibilidad:", styles["body"]
    ))

    cobertura = [
        ("Verde  — Aquí",         "La pieza tiene stock físico confirmado en el depósito. Hay unidades contadas y disponibles."),
        ("Azul   — En camino",    "La pieza ya fue recibida en el packing list (el proveedor la envió) pero todavía no fue inspeccionada físicamente en el depósito."),
        ("Violeta — Pedido",      "La pieza está incluida en un pedido activo pero todavía no llegó. Puede estar en tránsito o pendiente de despacho."),
        ("Rojo   — Sin pedido",   "La pieza no está en stock, no está en camino y no está incluida en ningún pedido activo. No hay cobertura."),
    ]

    E.append(tabla_datos(
        styles,
        ["Estado de cobertura", "Qué significa"],
        [((c, "td"), (d, "td")) for c, d in cobertura],
        [4.5 * cm, 12.5 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Panel de cobertura por rotación ──
    E.append(Paragraph("5.6  Panel de cobertura por clase de rotación", styles["h2"]))
    E.append(Paragraph(
        "El panel de cobertura muestra, para cada clase de rotación (Alta, Media, Baja), "
        "cuántas piezas hay en cada estado de cobertura y qué porcentaje representan. "
        "Permite identificar rápidamente si las piezas más críticas (alta rotación) "
        "están cubiertas o si hay faltantes.",
        styles["body"]
    ))
    E.append(Spacer(1, 0.2 * cm))
    E.append(Paragraph(
        "También permite exportar a Excel la lista de piezas que no tienen ningún pedido "
        "activo ('no pedidas'), filtradas por clase de rotación. Esto facilita la tarea de "
        "armar el próximo pedido de repuestos.",
        styles["body"]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Secciones del catálogo de despiece ──
    E.append(Paragraph("5.7  Secciones del catálogo de despiece (diagramas)", styles["h2"]))
    E.append(Paragraph(
        "El catálogo también incluye los diagramas de despiece organizados por modelo y sección. "
        "Cada sección tiene:", styles["body"]
    ))
    for item in [
        "<b>Código de modelo:</b> el modelo de moto al que pertenece esa sección (ej: RENEGADE200).",
        "<b>Código de sección:</b> identificador de la sección dentro del manual (ej: B1, E11).",
        "<b>Nombre de la sección:</b> descripción en inglés del conjunto de piezas (ej: FRAME, AIR CLEANER ASSY).",
        "<b>Diagrama:</b> imagen del despiece correspondiente, almacenada en el sistema.",
    ]:
        E.append(Paragraph(f"• {item}", styles["bullet"]))

    E.append(Spacer(1, 0.5 * cm))

    # ── Sustitutos ──
    E.append(Paragraph("5.8  Sustitutos de partes", styles["h2"]))
    E.append(Paragraph(
        "Cada pieza puede tener hasta tres referencias sustitutas registradas. "
        "Un sustituto es una pieza alternativa (puede ser de otra marca o modelo) "
        "que reemplaza funcionalmente a la original. Los datos que se registran son:", styles["body"]
    ))
    for item in [
        "<b>Código del sustituto:</b> el número de parte de la pieza alternativa.",
        "<b>Marca:</b> fabricante del sustituto.",
        "<b>Modelo aplicable:</b> en qué moto funciona este sustituto.",
        "<b>Posición:</b> orden de preferencia (1 es el primer sustituto a considerar).",
    ]:
        E.append(Paragraph(f"• {item}", styles["bullet"]))

    E.append(Spacer(1, 0.5 * cm))

    # ── Historial de costos ──
    E.append(Paragraph("5.9  Historial de costos de cada pieza", styles["h2"]))
    E.append(Paragraph(
        "El sistema guarda un registro histórico de todos los precios que ha tenido cada pieza "
        "a lo largo de los diferentes pedidos. Esto permite ver cómo evolucionó el precio con el tiempo. "
        "El historial incluye:", styles["body"]
    ))
    for item in [
        "<b>Lote (PI):</b> de qué pedido vino el precio.",
        "<b>Código usado:</b> el código exacto que trajo ese pedido (puede ser un código anterior al actual).",
        "<b>Precio unitario FOB:</b> el precio de ese Packing List.",
        "<b>Cantidad:</b> cuántas unidades se trajeron a ese precio.",
        "<b>Fecha de registro:</b> cuándo se registró ese dato en el sistema.",
    ]:
        E.append(Paragraph(f"• {item}", styles["bullet"]))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 6 — MODELOS DE MOTOCICLETA
# ══════════════════════════════════════════════════════════════════════════════
def seccion_modelos(styles):
    E = []
    E.append(seccion_header(styles, "06", "Modelos de Motocicleta"))
    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph(
        "El módulo de Modelos de Motocicleta contiene las especificaciones técnicas oficiales "
        "de cada modelo que UM Colombia comercializa. Esta información es de referencia y se "
        "usa también para vincular los pedidos y el catálogo de partes con cada modelo.",
        styles["body"]
    ))
    E.append(Spacer(1, 0.3 * cm))

    E.append(Paragraph("6.1  Especificaciones técnicas por modelo", styles["h2"]))

    specs = [
        ("Nombre del modelo",       "Nombre comercial completo, por ejemplo RENEGADE 200 SPORT."),
        ("Marca",                   "Siempre UM (UM Motorcycles)."),
        ("Cilindrada",              "Volumen del motor en centímetros cúbicos, por ejemplo 200cc."),
        ("Potencia",                "Potencia máxima del motor."),
        ("Peso",                    "Peso total de la moto en vacío."),
        ("Vueltas de aire",         "Ajuste del carburador: cuántas vueltas tiene la aguja de aire. Dato de servicio técnico."),
        ("Posición de cortina",     "Ajuste de la cortina del carburador. Dato de servicio técnico."),
        ("Sistemas de control",     "Si tiene ABS u otros sistemas electrónicos de control."),
        ("Sistema de combustible",  "Si el motor es carburado (CARBURADOR) o inyectado (INYECCION)."),
        ("Largo / Ancho / Alto",    "Dimensiones totales de la moto en milímetros."),
        ("Altura de silla",         "Distancia desde el piso hasta el asiento, en milímetros."),
        ("Distancia al suelo",      "Distancia del chasis al piso (ground clearance), en milímetros."),
        ("Distancia entre ejes",    "Separación entre el eje delantero y trasero, en milímetros."),
        ("Tanque de combustible",   "Capacidad del tanque en litros."),
        ("Relación de compresión",  "Qué tan comprimida está la mezcla antes de la explosión. Dato técnico del motor."),
        ("Llanta delantera",        "Medida del neumático delantero, por ejemplo 90/90-19."),
        ("Llanta trasera",          "Medida del neumático trasero."),
    ]

    E.append(tabla_datos(
        styles,
        ["Especificación", "Qué es"],
        [((s, "td"), (d, "td")) for s, d in specs],
        [5 * cm, 12 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    E.append(Paragraph("6.2  Vinculación de modelos con el catálogo de partes", styles["h2"]))
    E.append(Paragraph(
        "Para que el catálogo de partes sepa qué secciones de despiece mostrar para cada modelo, "
        "existe una tabla de vinculación. Esta tabla conecta:", styles["body"]
    ))
    for item in [
        "<b>Nombre del modelo en los pedidos</b> (ej: el texto que viene en el Packing List como 'RENEGADE 200 SPORT').",
        "<b>Código de catálogo</b> (ej: 'RENEGADE200'): el código que usa el sistema para buscar las secciones y diagramas de esa moto.",
    ]:
        E.append(Paragraph(f"• {item}", styles["bullet"]))
    E.append(Paragraph(
        "Esta vinculación permite que al filtrar el catálogo por modelo, "
        "el sistema encuentre correctamente las piezas aunque el nombre en el pedido "
        "sea ligeramente diferente al del catálogo.",
        styles["body"]
    ))

    E.append(Spacer(1, 0.5 * cm))

    E.append(Paragraph("6.3  Colores RUNT", styles["h2"]))
    E.append(Paragraph(
        "El sistema mantiene una tabla de conversión de colores. Cuando el proveedor describe "
        "el color de una moto de cierta manera en el Packing List (por ejemplo 'RED' o 'ROJO VINO'), "
        "el sistema lo busca en esta tabla y lo convierte automáticamente al código y nombre oficial "
        "que requiere el RUNT (Registro Único Nacional de Tránsito). "
        "Esta conversión es obligatoria para poder realizar el trámite de empadronamiento en Colombia.",
        styles["body"]
    ))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 7 — INFORME GERENCIAL
# ══════════════════════════════════════════════════════════════════════════════
def seccion_gerencial(styles):
    E = []
    E.append(seccion_header(styles, "07", "Informe Gerencial (PDF)"))
    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph(
        "El Informe Gerencial es un reporte en PDF que consolida el estado del negocio "
        "en un momento determinado. Se genera filtrando por un rango de fechas (desde / hasta) "
        "y cubre siete secciones denominadas F2 a F8. Está pensado para que la gerencia "
        "tenga una vista ejecutiva sin necesidad de navegar por los distintos módulos.",
        styles["body"]
    ))
    E.append(Spacer(1, 0.3 * cm))

    # ── F2 ──
    E.append(Paragraph("7.1  F2 — Pedidos de Importación (vista instantánea)", styles["h2"]))
    E.append(Paragraph(
        "Muestra el estado actual de todos los pedidos activos al momento de generar el informe. "
        "No se filtra por fecha, sino que refleja la situación en tiempo real.", styles["body"]
    ))

    f2 = [
        ("Pedidos activos total",     "Cuántos pedidos están en curso (no completados ni cancelados)."),
        ("Pedidos de motos activos",  "Cuántos de esos pedidos activos son de motocicletas completas."),
        ("Pedidos de repuestos activos", "Cuántos de esos pedidos activos son de kits de repuestos (SP)."),
        ("Motos por estado",          "Desglose de los pedidos de motos: cuántos están nacionalizados, en tránsito o en origen."),
        ("Unidades de motos totales", "Suma de todas las unidades de motos en pedidos activos."),
        ("Repuestos FOB total",       "Suma del valor FOB en dólares de todos los ítems de repuestos en pedidos activos. Se usa el precio del PI (estimado) para los ítems sin packing list confirmado."),
    ]

    E.append(tabla_datos(
        styles,
        ["Dato en el informe", "Cómo se calcula"],
        [((d, "td"), (c, "td")) for d, c in f2],
        [5.5 * cm, 11.5 * cm]
    ))

    E.append(Spacer(1, 0.4 * cm))

    # ── F3 ──
    E.append(Paragraph("7.2  F3 — Inventario de Motocicletas (vista completa, sin filtro de fecha)", styles["h2"]))
    E.append(Paragraph(
        "Muestra el estado del inventario físico de motos. Tampoco se filtra por fecha; "
        "refleja el inventario actual en el momento de generar el reporte.", styles["body"]
    ))

    f3 = [
        ("Total unidades",             "Todas las motos registradas en el sistema."),
        ("Disponibles",                "Motos sin observación, sin separar para nacionalización, no facturadas."),
        ("Separadas para nacion.",     "Motos que el área de importaciones marcó como separadas para el proceso de nacionalización."),
        ("Pendientes de empadronamiento", "Motos que todavía no tienen el certificado de empadronamiento generado."),
        ("Con observación",            "Motos que tienen alguna novedad registrada (daño, faltante, etc.)."),
        ("Con RUNT",                   "Motos que ya fueron cargadas en el sistema RUNT."),
        ("Facturadas histórico",       "Total de motos que en algún momento fueron facturadas al distribuidor."),
        ("Desglose por modelo",        "Para cada modelo de moto: cuántas unidades están disponibles y cuántas hay en total."),
    ]

    E.append(tabla_datos(
        styles,
        ["Dato en el informe", "Cómo se calcula"],
        [((d, "td"), (c, "td")) for d, c in f3],
        [5.5 * cm, 11.5 * cm]
    ))

    E.append(Spacer(1, 0.4 * cm))

    # ── F4 ──
    E.append(Paragraph("7.3  F4 — Cobertura de Repuestos (vista instantánea)", styles["h2"]))

    f4 = [
        ("Total referencias en catálogo", "Cuántas referencias de piezas distintas existen en el catálogo."),
        ("Aquí",         "Cuántas referencias tienen stock físico confirmado en el depósito."),
        ("En camino",    "Cuántas referencias están en algún pedido con packing list recibido pero sin inspección física."),
        ("Pedido",       "Cuántas referencias están en algún pedido activo pero todavía sin confirmación de llegada."),
        ("Sin cobertura","Cuántas referencias no tienen stock, no están en camino y no están pedidas."),
        ("FOB en stock", "El valor total en dólares (FOB) del stock físico disponible. Se calcula multiplicando la cantidad disponible de cada pieza por su FOB Promedio."),
    ]

    E.append(tabla_datos(
        styles,
        ["Dato en el informe", "Cómo se calcula"],
        [((d, "td"), (c, "td")) for d, c in f4],
        [5.5 * cm, 11.5 * cm]
    ))

    E.append(Spacer(1, 0.4 * cm))

    # ── F5 ──
    E.append(Paragraph("7.4  F5 — Rotación de Repuestos (vista instantánea)", styles["h2"]))
    E.append(Paragraph(
        "Para cada clase de rotación (Alta, Media, Baja) muestra:", styles["body"]
    ))

    f5 = [
        ("Refs en la clase",  "Cuántas referencias del catálogo están clasificadas en Alta / Media / Baja rotación."),
        ("FOB disponible",    "El valor FOB total del stock físico disponible para esa clase de rotación."),
        ("FOB en riesgo",     "Solo para rotación Media y Baja: el valor FOB de piezas que están pedidas pero no han llegado todavía. Se consideran 'en riesgo' porque son piezas de baja demanda cuya inversión podría quedarse inmovilizada."),
    ]

    E.append(tabla_datos(
        styles,
        ["Dato en el informe", "Cómo se calcula"],
        [((d, "td"), (c, "td")) for d, c in f5],
        [5.5 * cm, 11.5 * cm]
    ))

    E.append(Spacer(1, 0.4 * cm))

    # ── F6 ──
    E.append(Paragraph("7.5  F6 — Backorders (filtrado por período)", styles["h2"]))
    E.append(Paragraph(
        "Esta sección sí se filtra por el rango de fechas seleccionado al generar el informe.", styles["body"]
    ))

    f6 = [
        ("Backorders activos",       "Cuántos backorders están sin resolver en el período."),
        ("Resueltos en el período",  "Cuántos backorders se resolvieron (llegó la pieza o se canceló) dentro del rango de fechas."),
        ("Referencias afectadas",    "Cuántos números de parte distintos tienen backorders activos."),
        ("FOB pendiente",            "El valor FOB en dólares de todo lo que está en backorder activo. Se calcula: suma de (cantidad pendiente × precio unitario) para cada backorder activo."),
    ]

    E.append(tabla_datos(
        styles,
        ["Dato en el informe", "Cómo se calcula"],
        [((d, "td"), (c, "td")) for d, c in f6],
        [5.5 * cm, 11.5 * cm]
    ))

    E.append(Spacer(1, 0.4 * cm))

    # ── F7 ──
    E.append(Paragraph("7.6  F7 — Ajuste de Pedidos (filtrado por período)", styles["h2"]))
    E.append(Paragraph(
        "Muestra el estado de las solicitudes de ajuste sobre pedidos activos "
        "(cancelaciones y cambios de cantidad).", styles["body"]
    ))

    f7 = [
        ("Pendientes de cancelar",    "Cuántos ítems tienen una solicitud de cancelación pendiente de confirmar con fábrica."),
        ("Pendientes de cambiar",     "Cuántos ítems tienen una solicitud de cambio de cantidad pendiente."),
        ("Ejecutados en el período",  "Cuántas cancelaciones se concretaron efectivamente dentro del período."),
        ("FOB en cancelaciones pendientes",  "El valor FOB de los ítems que están esperando ser cancelados."),
        ("FOB en cancelaciones ejecutadas",  "El valor FOB de los ítems que ya fueron cancelados en el período."),
    ]

    E.append(tabla_datos(
        styles,
        ["Dato en el informe", "Cómo se calcula"],
        [((d, "td"), (c, "td")) for d, c in f7],
        [5.5 * cm, 11.5 * cm]
    ))

    E.append(Spacer(1, 0.4 * cm))

    # ── F8 ──
    E.append(Paragraph("7.7  F8 — Remisiones de Inventario (filtrado por período)", styles["h2"]))
    E.append(Paragraph(
        "Las remisiones son los despachos de repuestos desde el depósito central. "
        "Para cada tipo de remisión muestra:", styles["body"]
    ))

    f8_tipos = [
        ("PEDIDO",         "Despacho de repuestos por un pedido formal de un distribuidor o taller."),
        ("GARANTIA",       "Despacho de repuestos para cubrir una garantía."),
        ("CORTESIA",       "Repuesto entregado sin cobro como cortesía."),
        ("VEHICULO_PROPIO","Repuesto usado en motos del propio inventario de UM Colombia."),
    ]

    E.append(tabla_datos(
        styles,
        ["Tipo de remisión", "Qué significa"],
        [((t, "td"), (d, "td")) for t, d in f8_tipos],
        [4.5 * cm, 12.5 * cm]
    ))

    E.append(Spacer(1, 0.2 * cm))
    E.append(Paragraph(
        "Para cada tipo se reportan: total de despachos realizados, valor FOB despachado, "
        "y total de anulaciones en el período.",
        styles["body"]
    ))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 8 — ÓRDENES DE SERVICIO (componente repuestos)
# ══════════════════════════════════════════════════════════════════════════════
def seccion_ots(styles):
    E = []
    E.append(seccion_header(styles, "08", "Órdenes de Servicio — Gestión de Repuestos"))
    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph(
        "Las Órdenes de Servicio (OTs) representan los trabajos de taller: reparaciones, "
        "revisiones por kilometraje, garantías y PDI (Pre-Delivery Inspection). "
        "En cada OT pueden registrarse los repuestos utilizados.",
        styles["body"]
    ))
    E.append(Spacer(1, 0.3 * cm))

    # ── Semáforo ──
    E.append(Paragraph("8.1  Semáforo de vehículos en taller (dashboard)", styles["h2"]))
    E.append(Paragraph(
        "El dashboard principal muestra los vehículos que están actualmente en taller "
        "con un semáforo visual que indica cuánto tiempo llevan:", styles["body"]
    ))

    semaforo = [
        ("Verde",    "El vehículo lleva 2 días o menos en taller. Tiempo normal."),
        ("Amarillo", "Lleva entre 3 y 5 días. Está tardando más de lo esperado."),
        ("Rojo",     "Lleva más de 5 días. Requiere atención inmediata para no afectar la experiencia del cliente."),
    ]

    E.append(tabla_datos(
        styles,
        ["Color", "Criterio y significado"],
        [((c, "td"), (d, "td")) for c, d in semaforo],
        [3 * cm, 14 * cm]
    ))

    E.append(Spacer(1, 0.3 * cm))
    E.append(caja_nota(styles,
        "El tiempo en taller se cuenta en días desde que se creó la orden de servicio "
        "hasta el momento actual (o hasta la fecha de entrega si ya fue entregado)."
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Repuestos en OT ──
    E.append(Paragraph("8.2  Repuestos registrados en una OT", styles["h2"]))
    E.append(Paragraph(
        "Dentro de cada OT se pueden registrar los repuestos que se usaron o solicitaron:", styles["body"]
    ))

    rep_ot = [
        ("Referencia",   "El número de parte del repuesto utilizado."),
        ("Cantidad",     "Cuántas unidades de ese repuesto se usaron."),
        ("Tipo",         "Si el repuesto es de garantía (warranty), pagado por el cliente (paid) o en cotización (quote)."),
        ("Estado",       "Si el repuesto está pendiente de conseguir (pending), disponible en depósito (available) o ya aplicado a la moto (applied)."),
    ]

    E.append(tabla_datos(
        styles,
        ["Campo", "Qué significa"],
        [((c, "td"), (d, "td")) for c, d in rep_ot],
        [3.5 * cm, 13.5 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))

    # ── Remisiones ──
    E.append(Paragraph("8.3  Remisiones de inventario", styles["h2"]))
    E.append(Paragraph(
        "Una remisión es la salida oficial de repuestos del depósito. Cada remisión tiene:", styles["body"]
    ))

    rem_campos = [
        ("Tipo",             "El motivo del despacho: PEDIDO, GARANTIA, CORTESIA o VEHICULO_PROPIO."),
        ("Estado",           "BORRADOR (en preparación), DESPACHADO (salió del depósito) o ANULADO (se canceló)."),
        ("Número de remisión", "El código único asignado automáticamente al momento del despacho, con el formato REM-AÑO-SECUENCIA (ej: REM-2025-0042)."),
        ("Lote asociado",    "Si el tipo es PEDIDO, se vincula con el lote de repuestos específico que origina el despacho."),
        ("Notas",            "Observaciones adicionales sobre el despacho."),
        ("Ítems",            "Lista de las piezas despachadas con su cantidad."),
        ("Movimientos",      "Registro de cambios en el inventario: un número negativo significa salida (despacho), un número positivo significa entrada (anulación de una remisión anterior)."),
    ]

    E.append(tabla_datos(
        styles,
        ["Campo", "Qué significa"],
        [((c, "td"), (d, "td")) for c, d in rem_campos],
        [4 * cm, 13 * cm]
    ))

    E.append(PageBreak())
    return E


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 9 — EXPORTACIONES Y ACCIONES DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
def seccion_exportaciones(styles):
    E = []
    E.append(seccion_header(styles, "09", "Exportaciones y Cargas de Datos"))
    E.append(Spacer(1, 0.4 * cm))
    E.append(Paragraph(
        "El sistema permite tanto exportar información hacia Excel o PDF, como cargar datos "
        "masivamente desde archivos Excel. Esta sección resume todas esas acciones disponibles.",
        styles["body"]
    ))
    E.append(Spacer(1, 0.3 * cm))

    E.append(Paragraph("9.1  Exportaciones disponibles", styles["h2"]))

    exports = [
        ("Pedidos de importación",
         "Exporta la tabla de pedidos al formato Excel con las columnas: PI Number, Modelo, Ciclo, Cantidad, Tipo, Estado, Contenedores, ETR, ETL, ETD, ETA, Docs Digitales, Docs Originales, Vessel, BL/Contenedor, Observaciones."),
        ("Ítems de repuestos",
         "Exporta todos los ítems de Spare Parts al formato Excel con: Lote (PI), Part Number, Descripción ES, Descripción EN, Modelo Aplicable, Qty Pedido, Qty Recibido, Qty Pendiente, Estado, PI Backorder, Precio Unitario USD, Monto USD."),
        ("Backorders",
         "Exporta la lista de backorders al formato Excel con: Part Number, Descripción ES, Modelo, Qty Pendiente, PI Origen, PI Esperado, Días desde origen, Fuente, Estado, Fecha de Creación."),
        ("Unidades de motos",
         "Exporta el registro de motocicletas con todos sus campos incluyendo VIN, motor, color, empadronamiento y estado."),
        ("Partes sin pedido por rotación",
         "Exporta por separado (filtrado por clase Alta, Media o Baja) la lista de referencias que no tienen cobertura activa. Muy útil para armar el próximo pedido de repuestos."),
        ("Informe Gerencial",
         "Genera el PDF ejecutivo con el resumen de las 7 secciones (F2 a F8) para el período seleccionado."),
    ]

    E.append(tabla_datos(
        styles,
        ["Exportación", "Contenido"],
        [((ex, "td"), (c, "td")) for ex, c in exports],
        [4.5 * cm, 12.5 * cm]
    ))

    E.append(Spacer(1, 0.5 * cm))
    E.append(Paragraph("9.2  Cargas de datos (uploads)", styles["h2"]))

    uploads = [
        ("Excel de seguimiento de pedidos",
         "Carga masiva del estado de pedidos desde una planilla Excel. Solo disponible para superadministradores. Actualiza los campos de fechas ETR, ETL, ETD, ETA, BL, contenedor y estados de documentación."),
        ("Packing List de motos (VINs)",
         "Carga el listado de VINs y números de motor de las motos incluidas en un pedido, junto con datos de contenedor, sello, colores e ítems."),
        ("Detalle de orden de repuestos",
         "Carga el detalle de los ítems de un lote de repuestos (qué piezas se pidieron, en qué cantidad y a qué precio del PI)."),
        ("Packing List de repuestos",
         "Carga el packing list oficial del proveedor para un lote SP. Dispara la reconciliación automática y actualiza las cantidades recibidas y precios reales."),
        ("Clasificación de rotación masiva",
         "Carga un Excel con dos columnas (código de parte y clase de rotación) para clasificar masivamente muchas piezas a la vez."),
        ("FOB preliminar desde PI",
         "Carga un Excel con los precios estimados (del PI) para piezas que todavía no tienen Packing List confirmado."),
        ("Catálogo de despiece (PDF)",
         "Carga el PDF del manual de despiece de un modelo específico. El sistema extrae automáticamente los números de parte y los agrega al catálogo."),
    ]

    E.append(tabla_datos(
        styles,
        ["Carga", "Qué hace"],
        [((u, "td"), (d, "td")) for u, d in uploads],
        [4.5 * cm, 12.5 * cm]
    ))

    return E


# ══════════════════════════════════════════════════════════════════════════════
# CONSTRUCCIÓN Y GENERACIÓN DEL PDF
# ══════════════════════════════════════════════════════════════════════════════
def build_pdf(output_path: str):
    styles = build_styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Guía de Datos — Red de Servicio UM Colombia",
        author="UM Colombia",
        subject="Módulos de Pedidos, Repuestos y Catálogo de Partes",
    )

    # Numeración de páginas
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GRIS_TEXTO)
        page_num = f"Página {doc.page}"
        canvas.drawRightString(PAGE_W - 1.8 * cm, 1.2 * cm, page_num)
        canvas.drawString(1.8 * cm, 1.2 * cm, "Red de Servicio UM Colombia — Guía de Datos")
        canvas.restoreState()

    elements = []
    elements += portada(styles)
    elements += seccion_pedidos(styles)
    elements += seccion_repuestos(styles)
    elements += seccion_backorders(styles)
    elements += seccion_motos(styles)
    elements += seccion_catalogo(styles)
    elements += seccion_modelos(styles)
    elements += seccion_gerencial(styles)
    elements += seccion_ots(styles)
    elements += seccion_exportaciones(styles)

    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF generado correctamente: {output_path}")


if __name__ == "__main__":
    output = os.path.join(
        r"C:\proyectos IA\UM Colombia\Aplicación red de servicio - copia",
        "Guia_Datos_Pedidos_Repuestos_Catalogo.pdf"
    )
    build_pdf(output)
