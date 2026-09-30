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

# Corrida: sucursal, estados terminales, transiciones, interno
E_CORRIDA_SIN_EMPAQUE_NI_TRANSITO = "E-CORRIDA-020"
E_CORRIDA_SUCURSAL_SIN_SIC = "E-CORRIDA-021"
E_CORRIDA_TODAS_FALLIDAS = "E-CORRIDA-030"
E_CORRIDA_REINTENTOS_AGOTADOS = "E-CORRIDA-031"
E_CORRIDA_INVALIDADA = "E-CORRIDA-041"
E_CORRIDA_ESCENARIO_NO_SE_CIERRA = "E-CORRIDA-042"
E_CORRIDA_SUCURSAL_FALLIDA = "E-CORRIDA-043"
E_CORRIDA_INTERNO = "E-CORRIDA-099"

# Avisos
A_CORRIDA_DEMANDA_PERDIDA_AUSENTE = "A-CORRIDA-101"
A_CORRIDA_SUCURSAL_OMITIDA = tipos.COD_SUCURSAL_OMITIDA
A_CORRIDA_CADENA_CICLICA = tipos.COD_CADENA_CICLICA
A_CORRIDA_SIN_PRECIO = "A-CORRIDA-104"
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
    E_CORRIDA_ESCENARIO_NO_SE_CIERRA: "Un escenario no se puede cerrar.",
    E_CORRIDA_SUCURSAL_FALLIDA: (
        "Hay sucursales fallidas: no se puede cerrar la corrida."
    ),
    E_CORRIDA_INTERNO: "Error interno al calcular la corrida.",
    E_CARGA_ANULACION_BLOQUEADA: (
        "La carga la usa la corrida cerrada {codigo} y no se puede anular."
    ),
    A_CORRIDA_DEMANDA_PERDIDA_AUSENTE: (
        "No hay demanda perdida cargada: se calcula sin ella."
    ),
    A_CORRIDA_SIN_PRECIO: "La referencia {referencia} no tiene precio.",
}

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


def mensaje(codigo: str, **datos) -> str:
    """Mensaje en español del código, con sus marcadores rellenados."""
    return CATALOGO[codigo].format(**datos)


def mensaje_vigencia(codigo: str, dataset: str, antiguedad, limite) -> str:
    """Mensaje de un chequeo de vigencia; sin antigüedad = sin carga."""
    if antiguedad is None and codigo in CATALOGO_AUSENTE:
        return CATALOGO_AUSENTE[codigo].format(dataset=dataset)
    return mensaje(
        codigo, dataset=dataset, antiguedad=antiguedad, limite=limite)
