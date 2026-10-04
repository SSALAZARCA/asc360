"""
Catálogo de códigos de error y aviso de F3 (sdd/motored-pedidos-motor).

Cada código lleva un mensaje de usuario en español con marcadores con
nombre; el detalle técnico va aparte, en el `log` de la corrida. Los códigos
A-CORRIDA-102/103/105/106/110 nacen dentro del motor puro
(`services/motor/tipos.py`) y aquí sólo se reutilizan las constantes.
"""
from app.motored.services.motor import tipos

# Parámetros (POST /parametros)
E_PARAM_CLAVE_DESCONOCIDA = "E-PARAM-001"
E_PARAM_VALOR_INVALIDO = "E-PARAM-002"
E_PARAM_AMBITO_INVALIDO = "E-PARAM-003"
E_PARAM_SOLO_SUCURSAL = "E-PARAM-004"
E_PARAM_VIGENCIA_PASADA = "E-PARAM-005"

# Corrida: preflight (crear la corrida)
E_CORRIDA_VENTAS_SIN_CUBRIR = "E-CORRIDA-001"
E_CORRIDA_INVENTARIO_AUSENTE = "E-CORRIDA-002"
E_CORRIDA_INVENTARIO_VIEJO = "E-CORRIDA-003"
E_CORRIDA_BACKORDER_AUSENTE = "E-CORRIDA-004"
E_CORRIDA_BACKORDER_VIEJO = "E-CORRIDA-005"
E_CORRIDA_FACTURAS_AUSENTE_O_VIEJA = "E-CORRIDA-006"
E_CORRIDA_INGRESOS_AUSENTE_O_VIEJO = "E-CORRIDA-007"
E_CORRIDA_MAESTRO_REFERENCIAS_AUSENTE = "E-CORRIDA-008"
E_CORRIDA_CORTE_FUTURO = "E-CORRIDA-009"
E_CORRIDA_OVERRIDE_INVALIDO = "E-CORRIDA-010"
E_CORRIDA_SUCURSAL_INVALIDA = "E-CORRIDA-011"

# Corrida: sucursal, estados terminales, transiciones, interno
E_CORRIDA_SIN_EMPAQUE_NI_TRANSITO = "E-CORRIDA-020"
E_CORRIDA_SUCURSAL_SIN_SIC = "E-CORRIDA-021"
E_CORRIDA_TODAS_FALLIDAS = "E-CORRIDA-030"
E_CORRIDA_REINTENTOS_AGOTADOS = "E-CORRIDA-031"
E_CORRIDA_ESTADO_NO_ADMITE = "E-CORRIDA-040"
E_CORRIDA_INVALIDADA = "E-CORRIDA-041"
E_CORRIDA_ESCENARIO_NO_SE_CIERRA = "E-CORRIDA-042"
# RETIRADO en F4 (nunca se reutiliza): el cierre es por tienda.
E_CORRIDA_SUCURSAL_FALLIDA = "E-CORRIDA-043"
E_CORRIDA_INTERNO = "E-CORRIDA-099"

# Fase 4 (sdd/motored-pedidos-ui, R3 de las tareas): edición de líneas del
# pedido de una tienda. 052-054 y 066 son de B2; 065 la comparten todas las
# acciones por tienda. 042 (escenario) ahora dice QUÉ acción no admite.
# 044-046, 062 y 064 son de B3a (reabrir, cerrar y escenarios). 043 está
# RETIRADO: una tienda fallida ya no bloquea el cierre de las demás. 051 es
# de B3b (anular una corrida con pedidos cerrados o enviados), igual que
# 047-050, 056 y 067 (enviar y corregir el número de orden, F4-11/13/15).
# 055 y 057 son de B4 (exportar el pedido a HMCL, F4-1); 056 también cubre
# "nada que exportar". 058-061 son de B5b (recortar el pedido de una tienda al
# tope de presupuesto, F4-7). 063 es de B6 (comparar un escenario con la
# corrida real de la misma semana, F4-8).
E_CORRIDA_REABRIR_BORRADOR = "E-CORRIDA-044"
E_CORRIDA_REABRIR_ENVIADO = "E-CORRIDA-045"
E_CORRIDA_REABRIR_MOTIVO = "E-CORRIDA-046"
E_CORRIDA_ENVIAR_NO_CERRADO = "E-CORRIDA-047"
E_CORRIDA_ENVIO_INVALIDO = "E-CORRIDA-048"
E_CORRIDA_ENVIAR_YA_ENVIADO = "E-CORRIDA-049"
E_CORRIDA_ENVIO_DUPLICADO = "E-CORRIDA-050"
E_CORRIDA_ANULAR_CON_PEDIDOS = "E-CORRIDA-051"
E_CORRIDA_EXPORTAR_NO_CERRADO = "E-CORRIDA-055"
E_CORRIDA_NADA_QUE_ENVIAR = "E-CORRIDA-056"
E_CORRIDA_EXPORTAR_SIN_SIC = "E-CORRIDA-057"
E_CORRIDA_RECORTE_MODO_OFF = "E-CORRIDA-058"
E_CORRIDA_RECORTE_SIN_TOPE = "E-CORRIDA-059"
E_CORRIDA_PROPUESTA_DESACTUALIZADA = "E-CORRIDA-060"
E_CORRIDA_RECORTE_NO_BORRADOR = "E-CORRIDA-061"
E_CORRIDA_CORREGIR_NO_ENVIADO = "E-CORRIDA-067"
E_CORRIDA_OVERRIDES_SOLO_ADMIN = "E-CORRIDA-062"
E_CORRIDA_COMPARACION_INVALIDA = "E-CORRIDA-063"
E_CORRIDA_CERRAR_NO_BORRADOR = "E-CORRIDA-064"
E_CORRIDA_PEDIDO_NO_BORRADOR = "E-CORRIDA-052"
E_CORRIDA_CANTIDAD_INVALIDA = "E-CORRIDA-053"
E_CORRIDA_LINEA_EXCLUIDA = "E-CORRIDA-054"
E_CORRIDA_SIN_PEDIDO = "E-CORRIDA-065"
E_CORRIDA_EDICION_DESACTUALIZADA = "E-CORRIDA-066"

# Avisos
A_CORRIDA_DEMANDA_PERDIDA_AUSENTE = "A-CORRIDA-101"
A_CORRIDA_SUCURSAL_OMITIDA = tipos.COD_SUCURSAL_OMITIDA
A_CORRIDA_CADENA_CICLICA = tipos.COD_CADENA_CICLICA
A_CORRIDA_SIN_PRECIO = "A-CORRIDA-104"
# F4 (B5b): avisos del recorte al tope de presupuesto.
A_CORRIDA_FUERA_DE_EMPAQUE = "A-CORRIDA-120"
A_CORRIDA_TOPE_SIN_PRECIO = "A-CORRIDA-121"
A_CORRIDA_MES_EN_CURSO_NO_DISPONIBLE = tipos.COD_MES_EN_CURSO_NO_DISPONIBLE
A_CORRIDA_MES_EN_CURSO_CORTO = tipos.COD_MES_EN_CURSO_CORTO
A_CORRIDA_SUMA_NO_POSITIVA = tipos.COD_SUMA_NO_POSITIVA

# Carga: guarda de anulación (F2)
E_CARGA_ANULACION_BLOQUEADA = "E-CARGA-050"

_EDAD = (
    "Los datos de {dataset} tienen {antiguedad} días y el máximo permitido "
    "es {limite}. Cargue un archivo más reciente."
)

CATALOGO = {
    E_PARAM_CLAVE_DESCONOCIDA: "La clave «{clave}» no es un parámetro válido.",
    E_PARAM_VALOR_INVALIDO: (
        "Valor no válido para «{clave}»: {detalle}."
    ),
    E_PARAM_AMBITO_INVALIDO: (
        "El parámetro «{clave}» es global y no admite sucursal."
    ),
    E_PARAM_SOLO_SUCURSAL: (
        "El parámetro «{clave}» es de cada tienda: indique la sucursal."
    ),
    E_PARAM_VIGENCIA_PASADA: (
        "Valor no válido para «{clave}»: {detalle}."
    ),
    E_CORRIDA_VENTAS_SIN_CUBRIR: (
        "Las ventas de {mes} no están cubiertas por ninguna carga aplicada."
    ),
    E_CORRIDA_INVENTARIO_AUSENTE: (
        "No hay una carga de INVENTARIO aplicada a la fecha de corte."
    ),
    E_CORRIDA_INVENTARIO_VIEJO: _EDAD,
    E_CORRIDA_BACKORDER_AUSENTE: (
        "No hay una carga de BACKORDER aplicada a la fecha de corte."
    ),
    E_CORRIDA_BACKORDER_VIEJO: _EDAD,
    E_CORRIDA_FACTURAS_AUSENTE_O_VIEJA: (
        "Faltan las facturas de pedidos o están desactualizadas. " + _EDAD
    ),
    E_CORRIDA_INGRESOS_AUSENTE_O_VIEJO: (
        "Faltan los ingresos de facturas o están desactualizados. " + _EDAD
    ),
    E_CORRIDA_MAESTRO_REFERENCIAS_AUSENTE: (
        "No hay referencias en el maestro. Cargue el maestro de "
        "referencias antes de calcular."
    ),
    E_CORRIDA_CORTE_FUTURO: "La fecha de corte no puede estar en el futuro.",
    E_CORRIDA_OVERRIDE_INVALIDO: (
        "Parámetro de escenario no válido «{clave}»: {detalle}."
    ),
    E_CORRIDA_SUCURSAL_INVALIDA: (
        "Sucursales no válidas para la corrida: {detalle}."
    ),
    E_CORRIDA_ESTADO_NO_ADMITE: (
        "La corrida no admite esta operación en su estado actual "
        "({estado})."
    ),
    E_CORRIDA_SIN_EMPAQUE_NI_TRANSITO: (
        "La sucursal {sucursal} no tiene días de empaque ni de tránsito."
    ),
    E_CORRIDA_SUCURSAL_SIN_SIC: "La sucursal {sucursal} no tiene SIC.",
    E_CORRIDA_TODAS_FALLIDAS: "Ninguna sucursal se pudo calcular.",
    E_CORRIDA_REINTENTOS_AGOTADOS: (
        "La corrida agotó sus reintentos sin terminar."
    ),
    E_CORRIDA_INVALIDADA: (
        "La corrida quedó invalidada por la anulación de una carga."
    ),
    E_CORRIDA_ESCENARIO_NO_SE_CIERRA: (
        "Un escenario es solo de prueba: no se puede {accion}."
    ),
    E_CORRIDA_PEDIDO_NO_BORRADOR: (
        "El pedido de esta tienda está {estado}: no se puede editar. "
        "Reábralo para ajustar sus cantidades."
    ),
    E_CORRIDA_CANTIDAD_INVALIDA: (
        "La cantidad a pedir debe ser un número entero entre 0 y "
        "9.999.999."
    ),
    E_CORRIDA_LINEA_EXCLUIDA: (
        "La línea {referencia} no se puede editar: está excluida del "
        "pedido ({motivo})."
    ),
    E_CORRIDA_SIN_PEDIDO: "La tienda no tiene pedido en esta corrida.",
    E_CORRIDA_REABRIR_BORRADOR: (
        "El pedido de esta tienda está en BORRADOR: no hay nada que "
        "reabrir."
    ),
    E_CORRIDA_REABRIR_ENVIADO: (
        "El pedido de esta tienda ya se envió (orden {numero}) y no se "
        "puede reabrir."
    ),
    E_CORRIDA_REABRIR_MOTIVO: (
        "Indique el motivo de la reapertura (entre 1 y 500 caracteres)."
    ),
    E_CORRIDA_ENVIAR_NO_CERRADO: (
        "El pedido de {tienda} no está cerrado (está {estado}): ciérrelo "
        "antes de enviarlo."
    ),
    E_CORRIDA_ENVIO_INVALIDO: "Datos de envío no válidos: {detalle}.",
    E_CORRIDA_ENVIAR_YA_ENVIADO: (
        "El pedido de {tienda} ya se envió (orden {numero})."
    ),
    E_CORRIDA_ENVIO_DUPLICADO: (
        "{tienda} ya tiene un pedido enviado para esta semana (corrida "
        "{corrida}, orden {numero})."
    ),
    E_CORRIDA_NADA_QUE_ENVIAR: (
        "{tienda} no tiene nada que pedir (todas sus cantidades son 0): "
        "no se puede enviar."
    ),
    E_CORRIDA_EXPORTAR_NO_CERRADO: "No se puede exportar: {detalle}.",
    E_CORRIDA_EXPORTAR_SIN_SIC: (
        "{tienda} no tiene SIC: no se puede nombrar el archivo de pedido. "
        "Cargue el SIC de la tienda."
    ),
    E_CORRIDA_CORREGIR_NO_ENVIADO: (
        "El pedido de esta tienda no está enviado (está {estado}): no hay "
        "un número de orden que corregir."
    ),
    E_CORRIDA_RECORTE_MODO_OFF: (
        "El modo tope de presupuesto está apagado: no hay recorte que "
        "aplicar."
    ),
    E_CORRIDA_RECORTE_SIN_TOPE: (
        "Esta tienda no tiene un tope de presupuesto definido: no hay "
        "recorte que aplicar."
    ),
    E_CORRIDA_PROPUESTA_DESACTUALIZADA: (
        "La propuesta de recorte cambió desde que la vio, o ya no hay nada "
        "que recortar. Revise la propuesta nueva y vuelva a aplicarla."
    ),
    E_CORRIDA_RECORTE_NO_BORRADOR: (
        "Solo se puede recortar el pedido de una tienda en BORRADOR (este "
        "está {estado}). Reábralo para ajustar sus cantidades."
    ),
    E_CORRIDA_ANULAR_CON_PEDIDOS: (
        "No se puede anular la corrida: tiene pedidos cerrados o enviados "
        "({tiendas})."
    ),
    E_CORRIDA_OVERRIDES_SOLO_ADMIN: (
        "Solo un administrador puede lanzar un escenario (una corrida con "
        "parámetros alternativos)."
    ),
    E_CORRIDA_COMPARACION_INVALIDA: "No se puede comparar: {detalle}.",
    E_CORRIDA_CERRAR_NO_BORRADOR: "No se puede cerrar: {detalle}.",
    E_CORRIDA_EDICION_DESACTUALIZADA: (
        "La cantidad de la línea cambió mientras la editaba (ahora es "
        "{actual}). Revise la pantalla y vuelva a intentar."
    ),
    E_CORRIDA_SUCURSAL_FALLIDA: (
        "Hay sucursales fallidas: no se puede cerrar la corrida."
    ),
    E_CORRIDA_INTERNO: "Error interno al calcular la corrida.",
    E_CARGA_ANULACION_BLOQUEADA: (
        "La carga la usa la corrida cerrada {corrida} y no se puede anular."
    ),
    A_CORRIDA_DEMANDA_PERDIDA_AUSENTE: (
        "No hay demanda perdida cargada: se calcula sin ella."
    ),
    A_CORRIDA_SIN_PRECIO: "La referencia {referencia} no tiene precio.",
    A_CORRIDA_FUERA_DE_EMPAQUE: (
        "{cantidad} línea(s) del recorte no estaban en múltiplos del "
        "empaque: el recorte las baja al múltiplo inferior."
    ),
    A_CORRIDA_TOPE_SIN_PRECIO: (
        "{cantidad} línea(s) sin precio no suman al valor del pedido: el "
        "tope no las considera."
    ),
}

# F4 (B3b): E-CARGA-050 cuando lo que depende de la carga es el pedido
# CERRADO o ENVIADO de una tienda (el texto de arriba queda para la corrida
# que F3 dejó CERRADA y no tiene tienda que nombrar).
CATALOGO_CARGA_PEDIDO = (
    "La carga la usa el pedido {estado} de {tienda} (corrida {corrida}) y "
    "no se puede anular."
)

# Variante "no hay ninguna carga" de los códigos que también cubren "vieja".
CATALOGO_AUSENTE = {
    E_CORRIDA_FACTURAS_AUSENTE_O_VIEJA: (
        "No hay una carga de {dataset} aplicada. Cargue el archivo de "
        "{dataset}."
    ),
    E_CORRIDA_INGRESOS_AUSENTE_O_VIEJO: (
        "No hay una carga de {dataset} aplicada. Cargue el archivo de "
        "{dataset}."
    ),
}


class ErrorCorrida(Exception):
    """Error codificado de la corrida (creación, ciclo de vida, guardas).

    `detalle` es un dict serializable con el contexto técnico (por ejemplo el
    bloque de antigüedades de un preflight rechazado).
    """

    def __init__(self, codigo: str, mensaje: str, detalle=None):
        super().__init__(f"{codigo}: {mensaje}")
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalle = detalle


def mensaje(codigo: str, **datos) -> str:
    """Mensaje en español del código, con sus marcadores rellenados."""
    return CATALOGO[codigo].format(**datos)


def mensaje_escenario(accion: str) -> str:
    """E-CORRIDA-042: un escenario no admite `accion` (cerrar, editar...)."""
    return mensaje(E_CORRIDA_ESCENARIO_NO_SE_CIERRA, accion=accion)


def mensaje_nada_que_exportar(tienda=None) -> str:
    """E-CORRIDA-056 al exportar: la tienda (o, sin nombre, todas las
    pedidas) no tiene ninguna cantidad mayor que 0."""
    if tienda is None:
        return "Ninguna de las tiendas tiene cantidades para exportar."
    return (f"{tienda} no tiene nada que pedir (todas sus cantidades son "
            "0): no hay nada que exportar.")


def mensaje_carga_bloqueada(corrida: str, tienda=None, estado=None) -> str:
    """E-CARGA-050: con tienda, nombra el pedido cerrado o enviado y la
    corrida; sin tienda (corrida CERRADA de F3), sólo la corrida."""
    if tienda is None:
        return mensaje(E_CARGA_ANULACION_BLOQUEADA, corrida=corrida)
    return CATALOGO_CARGA_PEDIDO.format(
        estado=str(estado).lower(), tienda=tienda, corrida=corrida)


def mensaje_vigencia(codigo: str, dataset: str, antiguedad, limite) -> str:
    """Mensaje de un chequeo de vigencia; sin antigüedad = sin carga."""
    if antiguedad is None and codigo in CATALOGO_AUSENTE:
        return CATALOGO_AUSENTE[codigo].format(dataset=dataset)
    return mensaje(
        codigo, dataset=dataset, antiguedad=antiguedad, limite=limite)
