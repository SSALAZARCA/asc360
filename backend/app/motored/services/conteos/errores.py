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
        "Líder de inventarios.")


class EstadoInvalido(ErrorConteo):
    codigo = "ESTADO_INVALIDO"
    MENSAJE = "El conteo no está en un estado que permita esta acción."


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
