"""
Constructores compartidos por los tests de la API de corridas (S7): el
dict que devuelven las consultas, la línea ORM y la instalación de dobles en
el módulo de la API.

Las consultas y el servicio tienen su propia suite; los tests de la API y del
RBAC reemplazan esos colaboradores por dobles que graban sus argumentos, así
lo que se prueba acá es el contrato HTTP: roles, alcance por sucursal,
códigos de estado, formato de los errores y qué se le pide a cada capa.
"""
import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.motored.api import corridas as api
from app.motored.api import corridas_pedido as api_pedido
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.services.corridas import (
    edicion,
    envio,
    exportacion,
    exportacion_hmcl,
    pedido_tienda,
)

CORRIDA_ID = uuid.UUID(int=500)
PROVEEDOR_ID = uuid.UUID(int=501)
SUC_A, SUC_B = uuid.UUID(int=601), uuid.UUID(int=602)
CORTE = datetime.date(2026, 9, 21)
CREADA = datetime.datetime(2026, 9, 21, 10, 0)


def item_lista(**campos):
    base = dict(
        id=CORRIDA_ID, codigo="PED-2026-S39-001", proveedor_id=PROVEEDOR_ID,
        fecha_corte=CORTE, estado="BORRADOR", es_escenario=False,
        alcance="TODAS", invalidada=False, sucursales_total=2,
        sucursales_procesadas=2, nota=None, created_at=CREADA,
        terminado_en=None, cerrada_en=None)
    return {**base, **campos}


def detalle(**campos):
    base = dict(
        item_lista(),
        parametros_en_fecha=CORTE, overrides=None, motivo_invalidacion=None,
        motivo_anulacion=None, iniciado_en=None, anulada_en=None,
        intentos=1,
        cargas_usadas={"VENTAS": [{
            "carga_id": uuid.UUID(int=700), "nombre_archivo": "ventas.xlsx",
            "estado": "APLICADO", "periodo_desde": datetime.date(2026, 3, 1),
            "periodo_hasta": datetime.date(2026, 9, 14)}]},
        parametros={"parametros": {}},
        antiguedad={"inventario": {
            "carga_id": str(uuid.UUID(int=701)), "fecha_usada": "2026-09-19",
            "antiguedad_dias": 2, "limite_dias": 7,
            "fuente_limite": "DEFAULT"}},
        mes_en_curso={"modo_efectivo": "EXCLUIDO"},
        advertencias=[], sucursales=[], resumen=[], resumen_por_clase=[],
        totales={"unidades": Decimal("0"), "referencias": 0,
                 "valor": Decimal("0")})
    return {**base, **campos}


def sucursal_estado(sucursal_id=SUC_A, nombre="UNO", **campos):
    base = dict(
        sucursal_id=sucursal_id, nombre=nombre, orden=1, estado="OK",
        codigo=None, mensaje=None, lineas=3, excluidas=0,
        unidades=Decimal("10.00"), valor=Decimal("4607.50"),
        fecha_apertura=None, divisor=21, dias_empaque=Decimal("3.00"),
        dias_transito=Decimal("2.00"), dias_seguridad=Decimal("2.50"),
        dias_entre_pedidos=Decimal("30.00"), intentos=1)
    return {**base, **campos}


def progreso(**campos):
    base = dict(
        estado="CALCULANDO", total=2, procesadas=1, ok=1, omitidas=0,
        fallidas=0, actual="Sucursal 2 de 2 — DOS", latido_en=None,
        intentos=1, errores=[], advertencias=[])
    return {**base, **campos}


def linea(sucursal_id=SUC_A, codigo="94109-12000S", **campos):
    """`CorridaLinea` con todas las columnas NOT NULL (nunca pasa por un
    flush, así que ningún default de columna se aplica)."""
    cero = Decimal("0.00")
    base = dict(
        id=1, corrida_id=CORRIDA_ID, sucursal_id=sucursal_id,
        referencia_id=uuid.uuid4(), codigo_referencia=codigo,
        nombre_parte="PARTE", unidad_empaque=1, banderas=[],
        **{f"venta_m{m}": cero for m in range(1, 7)},
        **{f"perdida_m{m}": cero for m in range(1, 7)},
        inventario=cero, transito=cero, backorder=cero, ajuste=cero,
        pedido_sugerido=Decimal("50.00"), pedido_final=Decimal("50.00"),
        clase="AF", estado_quiebre="NORMAL")
    return CorridaLinea(**{**base, **campos})


USUARIO_EDITOR = uuid.UUID(int=900)


def totales_tienda(**campos):
    base = dict(
        unidades_a_pedir=Decimal("1010.00"),
        valor_a_pedir=Decimal("6000000.00"),
        unidades_sugerido=Decimal("1000.00"),
        valor_sugerido=Decimal("5000000.00"))
    return {**base, **campos}


def historial_fila(**campos):
    base = dict(
        id=1, linea_id=7, campo="pedido_final",
        valor_anterior=Decimal("50.00"), valor_nuevo=Decimal("60.00"),
        motivo="MANUAL", detalle=None, usuario_id=USUARIO_EDITOR,
        usuario="Maria", creado_en=CREADA)
    return {**base, **campos}


def resultado_edicion(**campos):
    """Lo que devuelve `edicion.editar_linea`: la línea editada (50 -> 60),
    la última edición y los totales de la tienda."""
    base = dict(
        linea=linea(
            id=7, pedido_sugerido=Decimal("50.00"),
            pedido_final=Decimal("60.00"), precio=Decimal("460.75"),
            valor_pedido=Decimal("27645.00"), unidad_empaque=12),
        ultima_edicion=None, totales_tienda=totales_tienda())
    return edicion.ResultadoEdicion(**{**base, **campos})


def cabecera_tienda(**campos):
    """Lo que devuelve `lecturas_pedido.cabecera_tienda`."""
    base = dict(
        corrida_id=CORRIDA_ID, corrida_codigo="PED-2026-S39-001",
        fecha_corte=CORTE, corrida_estado="BORRADOR", es_escenario=False,
        invalidada=False, sucursal_id=SUC_A, nombre="UNO", sic="SIC-1",
        estado="OK", codigo=None, mensaje=None, estado_pedido="BORRADOR",
        totales=totales_tienda(), ultimo_evento=None,
        acciones={"cerrar": True, "reabrir": False, "editar": True})
    return {**base, **campos}


def fila_envio(sucursal_id=SUC_A, numero="12345", **campos):
    """Lo que deja un envío: la fila `corrida_envio` (ya con sus defaults)."""
    base = dict(
        corrida_id=CORRIDA_ID, sucursal_id=sucursal_id,
        numero_pedido_proveedor=numero, fecha_envio=datetime.date(2026, 9, 22),
        enviada_por=USUARIO_EDITOR, enviada_en=CREADA)
    return SimpleNamespace(**{**base, **campos})


def evento_pedido(**campos):
    base = dict(
        id=1, evento="CERRADO", motivo=None, detalle=None,
        usuario_id=USUARIO_EDITOR, usuario="Maria", creado_en=CREADA)
    return {**base, **campos}


def datos_exportacion(nombre="Manizales", sic="1234", lineas=None):
    """Lo que devuelve `exportacion.preparar_tienda`: los datos del archivo
    HMCL de una tienda (el libro se arma de verdad, es chico)."""
    lineas = [("94109-12000S", Decimal("50.00")),
              ("00123-AB", Decimal("12.00"))] if lineas is None else lineas
    return exportacion_hmcl.DatosTienda(nombre, sic, CORTE, lineas)


def seleccion_zip(**campos):
    """Lo que devuelve `exportacion.preparar_corrida`: dos tiendas en el zip
    y una omitida."""
    base = dict(
        corrida=SimpleNamespace(
            id=CORRIDA_ID, codigo="PED-2026-S39-001", fecha_corte=CORTE),
        tiendas=[
            datos_exportacion(),
            datos_exportacion("Medellín Poblado", "77",
                              [("55512-A", Decimal("7.00"))])],
        omitidas=[{
            "sucursal_id": str(SUC_B), "nombre": "Pereira",
            "codigo": "BORRADOR", "motivo": "El pedido sigue en BORRADOR"}])
    return exportacion.SeleccionZip(**{**base, **campos})


def propuesta_recorte(**campos):
    """Lo que devuelve `tope.previsualizar` con un recorte de una línea."""
    base = dict(
        activo=True, motivo_inactivo=None, modo_activo=True,
        corrida_id=CORRIDA_ID, sucursal_id=SUC_A, tope=Decimal("9000"),
        valor_actual=Decimal("11000.00"), exceso=Decimal("2000.00"),
        recortes=[{
            "linea_id": 1, "codigo": "C-1", "nombre": "PARTE",
            "clase_abc": "C", "unidad_empaque": 10,
            "pedido_actual": Decimal("50.00"),
            "pedido_propuesto": Decimal("30.00"),
            "empaques_recortados": Decimal("2"),
            "valor_recortado": Decimal("2000.00")}],
        valor_final=Decimal("9000.00"), exceso_residual=Decimal("0.00"),
        lineas_sin_precio=0, advertencias=[], token="ab" * 32)
    return {**base, **campos}


def recorte_aplicado(**campos):
    """Lo que devuelve `tope.aplicar`."""
    base = dict(
        corrida_id=CORRIDA_ID, sucursal_id=SUC_A, tope=Decimal("9000"),
        lineas_recortadas=1, valor_liberado=Decimal("2000.00"),
        valor_final=Decimal("9000.00"), exceso_residual=Decimal("0.00"),
        advertencias=[], totales_tienda=totales_tienda())
    return {**base, **campos}


def resumen_topes(**campos):
    """Lo que devuelve `tope.resumen_topes` con el modo tope encendido."""
    base = dict(
        activo=True, corrida_id=CORRIDA_ID,
        tiendas=[{
            "sucursal_id": SUC_A, "nombre": "UNO",
            "estado_pedido": "BORRADOR", "tope": Decimal("9000"),
            "valor_a_pedir": Decimal("11000.00"),
            "exceso": Decimal("2000.00"), "lineas_sin_precio": 2}])
    return {**base, **campos}


class Espia:
    """Doble de `consultas` y `servicio`: graba las llamadas y responde lo
    configurado."""

    def __init__(self):
        self.llamadas = []
        self.lista = ([item_lista()], 1)
        self.detalle = detalle()
        self.progreso = progreso()
        self.lineas = ([linea()], 1)
        self.creada = SimpleNamespace(
            id=CORRIDA_ID, codigo="PED-2026-S39-001", estado="PENDIENTE",
            es_escenario=False)
        self.lote = pedido_tienda.ResultadoLote(
            SimpleNamespace(
                id=CORRIDA_ID, codigo="PED-2026-S39-001",
                estado="BORRADOR"),
            [SUC_A, SUC_B], 0)
        self.tienda = SimpleNamespace(
            corrida_id=CORRIDA_ID, sucursal_id=SUC_A,
            estado_pedido="CERRADO")
        self.envios = envio.ResultadoEnvios(
            SimpleNamespace(
                id=CORRIDA_ID, codigo="PED-2026-S39-001",
                estado="BORRADOR"),
            [fila_envio(SUC_A, "12345"), fila_envio(SUC_B, "12346")])
        self.correccion = envio.ResultadoCorreccion(
            SimpleNamespace(estado_pedido="ENVIADO"),
            fila_envio(SUC_A, "99999"), True)
        self.cabecera = cabecera_tienda()
        self.datos_tienda = datos_exportacion()
        self.seleccion = seleccion_zip()
        self.eventos = [evento_pedido()]
        self.propuesta = propuesta_recorte()
        self.recortado = recorte_aplicado()
        self.topes = resumen_topes()
        self.anulada = SimpleNamespace(
            id=CORRIDA_ID, codigo="PED-2026-S39-001", estado="ANULADA",
            cerrada_en=None)
        self.editada = resultado_edicion()
        self.historial = [historial_fila()]
        self.ediciones = {}
        self.error = None
        self.encolados = []

    def _registrar(self, nombre, *args, **kwargs):
        self.llamadas.append((nombre, args, kwargs))
        if self.error is not None and nombre in self.error[0]:
            raise self.error[1]

    def ultima(self, nombre):
        return [c for c in self.llamadas if c[0] == nombre][-1]


class RunnerDoble:
    def __init__(self, espia, falla=False):
        self.espia, self.falla = espia, falla

    async def enqueue(self, corrida_id):
        self.espia.encolados.append(corrida_id)
        if self.falla:
            raise RuntimeError("el loop no arrancó")


def instalar(monkeypatch, espia=None):
    """Reemplaza consultas y servicio del módulo de la API por el `Espia`."""
    espia = espia or Espia()

    async def listar(db, **kw):
        espia._registrar("listar", **kw)
        return espia.lista

    async def detalle_(db, corrida_id, alcance):
        espia._registrar("detalle", corrida_id, alcance)
        return espia.detalle

    async def progreso_(db, corrida_id, alcance):
        espia._registrar("progreso", corrida_id, alcance)
        return espia.progreso

    async def lineas(db, corrida_id, alcance, **kw):
        espia._registrar("lineas", corrida_id, alcance, **kw)
        return espia.lineas

    async def crear(db, **kw):
        espia._registrar("crear", **kw)
        return espia.creada

    async def anular(db, corrida_id, usuario_id, motivo):
        espia._registrar("anular", corrida_id, usuario_id, motivo)
        return espia.anulada

    for nombre, doble in (
            ("listar", listar), ("detalle", detalle_),
            ("progreso", progreso_), ("lineas", lineas)):
        monkeypatch.setattr(api.consultas, nombre, doble)
    for nombre, doble in (
            ("crear_corrida", crear), ("anular_corrida", anular)):
        monkeypatch.setattr(api.servicio, nombre, doble)
    _instalar_edicion(monkeypatch, espia)
    _instalar_pedido_tienda(monkeypatch, espia)
    _instalar_envio(monkeypatch, espia)
    _instalar_exportacion(monkeypatch, espia)
    _instalar_tope(monkeypatch, espia)
    return espia


def _instalar_tope(monkeypatch, espia):
    """Dobles del recorte al tope de presupuesto (F4, B5b): el resumen de la
    corrida, la propuesta de una tienda y su aplicación."""
    async def resumen(db, corrida_id):
        espia._registrar("topes", corrida_id)
        return espia.topes

    async def previsualizar(db, corrida_id, sucursal_id):
        espia._registrar("recorte_ver", corrida_id, sucursal_id)
        return espia.propuesta

    async def aplicar(db, corrida_id, sucursal_id, token, usuario_id):
        espia._registrar(
            "recorte_aplicar", corrida_id, sucursal_id, token, usuario_id)
        return espia.recortado

    for nombre, doble in (
            ("resumen_topes", resumen), ("previsualizar", previsualizar),
            ("aplicar", aplicar)):
        monkeypatch.setattr(api_pedido.tope, nombre, doble)


def _instalar_exportacion(monkeypatch, espia):
    """Dobles de la lectura de datos de la exportación HMCL (F4, B4): los
    constructores del archivo corren de verdad."""
    async def preparar_tienda(db, corrida_id, sucursal_id):
        espia._registrar("exportar_tienda", corrida_id, sucursal_id)
        return espia.datos_tienda

    async def preparar_corrida(db, corrida_id, sucursal_ids=None):
        espia._registrar("exportar_corrida", corrida_id, sucursal_ids)
        return espia.seleccion

    monkeypatch.setattr(
        api_pedido.exportacion, "preparar_tienda", preparar_tienda)
    monkeypatch.setattr(
        api_pedido.exportacion, "preparar_corrida", preparar_corrida)


def _instalar_envio(monkeypatch, espia):
    """Dobles del envío del pedido por tienda (F4, B3b): enviar una, enviar
    varias y corregir el número de orden."""
    async def enviar_tienda(db, corrida_id, sucursal_id, numero, fecha,
                            usuario_id):
        espia._registrar(
            "enviar_tienda", corrida_id, sucursal_id, numero, fecha,
            usuario_id)
        return envio.ResultadoEnvios(
            espia.envios.corrida, espia.envios.envios[:1])

    async def enviar_lote(db, corrida_id, pedidos, usuario_id):
        espia._registrar("enviar_lote", corrida_id, pedidos, usuario_id)
        return espia.envios

    async def corregir_numero(db, corrida_id, sucursal_id, numero,
                              usuario_id):
        espia._registrar(
            "corregir", corrida_id, sucursal_id, numero, usuario_id)
        return espia.correccion

    for nombre, doble in (
            ("enviar_tienda", enviar_tienda), ("enviar_lote", enviar_lote),
            ("corregir_numero", corregir_numero)):
        monkeypatch.setattr(api_pedido.envio, nombre, doble)


def _instalar_pedido_tienda(monkeypatch, espia):
    """Dobles del ciclo de vida del pedido por tienda (F4, B3a): cerrar,
    reabrir y las lecturas de cabecera y eventos."""
    async def cerrar_todas(db, corrida_id, usuario_id, sucursal_ids=None):
        espia._registrar("cerrar", corrida_id, usuario_id, sucursal_ids)
        return espia.lote

    async def cerrar_tienda(db, corrida_id, sucursal_id, usuario_id):
        espia._registrar("cerrar_tienda", corrida_id, sucursal_id, usuario_id)
        return espia.tienda

    async def reabrir_tienda(db, corrida_id, sucursal_id, usuario_id, motivo):
        espia._registrar(
            "reabrir", corrida_id, sucursal_id, usuario_id, motivo)
        return espia.tienda

    async def cabecera(db, corrida_id, sucursal_id, alcance):
        espia._registrar("cabecera", corrida_id, sucursal_id, alcance)
        return espia.cabecera

    async def eventos(db, corrida_id, sucursal_id, alcance):
        espia._registrar("eventos", corrida_id, sucursal_id, alcance)
        return espia.eventos

    for nombre, doble in (
            ("cerrar_todas", cerrar_todas), ("cerrar_tienda", cerrar_tienda),
            ("reabrir_tienda", reabrir_tienda)):
        monkeypatch.setattr(api_pedido.pedido_tienda, nombre, doble)
    for nombre, doble in (
            ("cabecera_tienda", cabecera), ("eventos_tienda", eventos)):
        monkeypatch.setattr(api_pedido.lecturas_pedido, nombre, doble)


def _instalar_edicion(monkeypatch, espia):
    """Dobles de la edición de líneas (F4, B2): el servicio y las lecturas
    de historial y de última edición."""
    async def editar_linea(db, corrida_id, linea_id, cantidad, esperado,
                           usuario_id):
        espia._registrar(
            "editar", corrida_id, linea_id, cantidad, esperado, usuario_id)
        return espia.editada

    async def historial_linea(db, corrida_id, linea_id):
        espia._registrar("historial", corrida_id, linea_id)
        return espia.historial

    async def ediciones_de(db, linea_ids):
        return espia.ediciones

    monkeypatch.setattr(api_pedido.edicion, "editar_linea", editar_linea)
    monkeypatch.setattr(api.consultas, "historial_linea", historial_linea)
    monkeypatch.setattr(api.consultas, "ediciones_de", ediciones_de)
