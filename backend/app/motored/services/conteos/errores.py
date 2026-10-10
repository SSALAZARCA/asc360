"""
Inventory counts -- domain errors (odd/motored-conteos-inventario, WU5).

Every error carries a stable `codigo` (the API maps it to an HTTP status
and sends it as `detail.code`), a Spanish `mensaje` for the person and
optional `datos` (JSON-safe facts, e.g. the carga date of a stale
inventory). The services never raise HTTP errors themselves.
"""
from typing import Any, Optional


class ErrorConteo(Exception):
    """Base of every inventory-count domain error."""

    codigo = "CONTEO_ERROR"
    MENSAJE = "No se pudo completar la operación del conteo."

    def __init__(self, mensaje: Optional[str] = None, **datos: Any):
        self.mensaje = mensaje or self.MENSAJE
        self.datos = datos
        super().__init__(self.mensaje)


class ConteoNoEncontrado(ErrorConteo):
    codigo = "CONTEO_NO_ENCONTRADO"
    MENSAJE = "El conteo no existe."


class SucursalInvalida(ErrorConteo):
    codigo = "SUCURSAL_INVALIDA"
    MENSAJE = "La tienda no existe o está inactiva."


class LiderInvalido(ErrorConteo):
    codigo = "LIDER_INVALIDO"
    MENSAJE = (
        "El líder asignado debe ser un usuario activo con el rol "
        "Líder de inventarios, Coordinador de repuestos o "
        "Administrador.")


class EstadoInvalido(ErrorConteo):
    codigo = "ESTADO_INVALIDO"
    MENSAJE = "El conteo no está en un estado que permita esta acción."


class NoEsPrueba(ErrorConteo):
    codigo = "NO_ES_PRUEBA"
    MENSAJE = "Solo se puede borrar un conteo de prueba."


class ConteoTotalAbierto(ErrorConteo):
    codigo = "CONTEO_TOTAL_ABIERTO"
    MENSAJE = (
        "Esta tienda ya tiene un conteo total en curso. Ciérrelo o "
        "anúlelo antes de iniciar otro.")


class SinInventario(ErrorConteo):
    codigo = "SIN_INVENTARIO"
    MENSAJE = (
        "La tienda no tiene ningún inventario cargado en Maestros. Cargue "
        "el inventario antes de iniciar el conteo.")


class InventarioAntiguo(ErrorConteo):
    codigo = "INVENTARIO_ANTIGUO"
    MENSAJE = (
        "El último inventario de la tienda es más viejo de lo permitido. "
        "Cargue uno nuevo o confirme que quiere contar contra ese.")


class PendientesPorSanear(ErrorConteo):
    """Warning, never a block: Iniciar goes on with `confirmar_pendientes`
    (odd/motored-conteos-inventario, WU15)."""

    codigo = "PENDIENTES_POR_SANEAR"
    MENSAJE = (
        "La tienda tiene facturas por ingresar o traslados por recibir en "
        "el ERP. Confirme si quiere iniciar igual.")


class PendienteNoEncontrado(ErrorConteo):
    codigo = "PENDIENTE_NO_ENCONTRADO"
    MENSAJE = "Ese pendiente ya no está en la lista de la tienda."


class PendienteInvalido(ErrorConteo):
    codigo = "PENDIENTE_INVALIDO"
    MENSAJE = "El pendiente debe ser una factura o un traslado."


class UmbralesInvalidos(ErrorConteo):
    codigo = "UMBRALES_INVALIDOS"
    MENSAJE = (
        "En Configuración, el monto que pide reconteo debe ser menor que "
        "el monto de diferencia crítica. Corríjalo antes de iniciar.")


class MotivoRequerido(ErrorConteo):
    codigo = "MOTIVO_REQUERIDO"
    MENSAJE = "Escriba el motivo de la anulación."


class EnlaceSinConfigurar(ErrorConteo):
    codigo = "ENLACE_SIN_CONFIGURAR"
    MENSAJE = (
        "Falta configurar MOTORED_PUBLIC_URL: no se puede armar el enlace "
        "ni el QR del conteo.")


class SesionNoEncontrada(ErrorConteo):
    codigo = "SESION_NO_ENCONTRADA"
    MENSAJE = "La pareja no existe en este conteo."


# --- pair access (public routes) ---------------------------------------------
# One generic message for every failed join (wrong link, wrong code, count
# not running): nothing tells a guesser which part was wrong (design §8.2).


class AccesoInvalido(ErrorConteo):
    codigo = "ACCESO_INVALIDO"
    MENSAJE = "Código o enlace no válidos."


class DemasiadosIntentos(ErrorConteo):
    codigo = "DEMASIADOS_INTENTOS"
    MENSAJE = "Demasiados intentos. Espere unos minutos e intente de nuevo."


class DatosIngresoInvalidos(ErrorConteo):
    codigo = "DATOS_INGRESO_INVALIDOS"
    MENSAJE = (
        "Revise los datos: escriba el código y el nombre y la cédula (solo "
        "números) de 2 o 3 personas distintas.")


class SesionInactiva(ErrorConteo):
    codigo = "SESION_INACTIVA"
    MENSAJE = (
        "Su sesión de conteo terminó. Vuelva a ingresar con el código del "
        "conteo.")


# --- locations and readings (WU8) --------------------------------------------


class UbicacionInvalida(ErrorConteo):
    codigo = "UBICACION_INVALIDA"
    MENSAJE = (
        "Escriba o escanee un código de ubicación de 1 a 30 caracteres.")


class UbicacionInactiva(ErrorConteo):
    codigo = "UBICACION_INACTIVA"
    MENSAJE = (
        "Esa ubicación está desactivada. Pídale al líder que la active o "
        "use otra.")


class UbicacionDuplicada(ErrorConteo):
    codigo = "UBICACION_DUPLICADA"
    MENSAJE = "Ya existe una ubicación con ese código en esta tienda."


class UbicacionChocaReferencia(ErrorConteo):
    codigo = "UBICACION_CHOCA_REFERENCIA"
    MENSAJE = (
        "Ese código de ubicación se confunde con el código de una "
        "referencia. Use otro.")


class UbicacionNoEncontrada(ErrorConteo):
    codigo = "UBICACION_NO_ENCONTRADA"
    MENSAJE = "La ubicación no existe en esta tienda."


class SinUbicacion(ErrorConteo):
    codigo = "SIN_UBICACION"
    MENSAJE = "Primero indique la ubicación."


class LecturaNoEncontrada(ErrorConteo):
    codigo = "LECTURA_NO_ENCONTRADA"
    MENSAJE = "La lectura no existe o no es de esta pareja."


class RondaCerrada(ErrorConteo):
    codigo = "RONDA_CERRADA"
    MENSAJE = "La ronda de conteo de esa lectura ya terminó."


# --- reconteo (WU9) ----------------------------------------------------------


class ReconteoNoEncontrado(ErrorConteo):
    codigo = "RECONTEO_NO_ENCONTRADO"
    MENSAJE = "El reconteo no existe o no está asignado a esta pareja."


class ReconteoDuplicado(ErrorConteo):
    codigo = "RECONTEO_DUPLICADO"
    MENSAJE = "Esa referencia ya tiene un reconteo activo en este conteo."


class CodigoDesconocido(ErrorConteo):
    codigo = "CODIGO_DESCONOCIDO"
    MENSAJE = (
        "Ese código no existe en el maestro de referencias ni se leyó en "
        "el conteo.")


class SesionNoDisponible(ErrorConteo):
    codigo = "SESION_NO_DISPONIBLE"
    MENSAJE = (
        "Esa pareja ya no está conectada. Elija una pareja conectada.")


class MismaPareja(ErrorConteo):
    codigo = "MISMA_PAREJA"
    MENSAJE = (
        "Esa pareja comparte una persona con quien contó esta referencia "
        "en la primera ronda. Asigne otra pareja.")


class HayParejaElegible(ErrorConteo):
    codigo = "HAY_PAREJA_ELEGIBLE"
    MENSAJE = (
        "Hay otra pareja conectada que puede hacer este reconteo. Solo se "
        "autoriza a la misma pareja cuando no hay ninguna otra.")


# --- close (WU10) ------------------------------------------------------------


class ReconteosAbiertos(ErrorConteo):
    codigo = "RECONTEOS_ABIERTOS"
    MENSAJE = (
        "Todavía hay reconteos sin terminar. Espere a que terminen, "
        "cancélelos o cierre de forma forzada con un motivo.")


class SinBodegaPrincipal(ErrorConteo):
    codigo = "SIN_BODEGA_PRINCIPAL"
    MENSAJE = (
        "La tienda no tiene una bodega principal registrada, así que no "
        "hay a qué bodega asignar los ajustes. Configúrela en Maestros > "
        "Sucursales antes de cerrar.")
