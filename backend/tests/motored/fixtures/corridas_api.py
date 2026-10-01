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
from app.motored.services.corridas import edicion

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
        self.cerrada = SimpleNamespace(
            id=CORRIDA_ID, codigo="PED-2026-S39-001", estado="CERRADA",
            cerrada_en=None)
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

    async def cerrar(db, corrida_id, usuario_id):
        espia._registrar("cerrar", corrida_id, usuario_id)
        return espia.cerrada

    async def anular(db, corrida_id, usuario_id, motivo):
        espia._registrar("anular", corrida_id, usuario_id, motivo)
        return espia.anulada

    for nombre, doble in (
            ("listar", listar), ("detalle", detalle_),
            ("progreso", progreso_), ("lineas", lineas)):
        monkeypatch.setattr(api.consultas, nombre, doble)
    for nombre, doble in (
            ("crear_corrida", crear), ("cerrar_corrida", cerrar),
            ("anular_corrida", anular)):
        monkeypatch.setattr(api.servicio, nombre, doble)
    _instalar_edicion(monkeypatch, espia)
    return espia


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
