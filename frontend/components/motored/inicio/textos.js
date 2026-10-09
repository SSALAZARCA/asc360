/**
 * Inicio: fixed copy and the greeting's date helpers. Pure data.
 */
import { horaBogota } from '../../../lib/motored/fechas';

export const ROL_NOMBRE = {
  ADMIN: 'Administrador',
  COMPRAS: 'Compras',
  GERENCIA: 'Gerencia',
  SERVICIO_CLIENTE: 'Servicio al cliente',
  COORDINADOR_REPUESTOS: 'Coordinador de repuestos',
};

/** The same line under the greeting for every role. */
export const BAJADA = 'Así viene la red, de un vistazo.';

export const NO_DISPONIBLE = 'No disponible por ahora';

const FECHA_LARGA = new Intl.DateTimeFormat('es-CO', {
  timeZone: 'America/Bogota', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
});

/** "Martes, 6 de octubre de 2026" in Bogota, whatever the browser zone. */
export function fechaLarga(fecha) {
  const texto = FECHA_LARGA.format(fecha);
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** Greeting by the Bogota hour (design: before 12, before 19, after). */
export function momentoDelDia(fecha) {
  const hora = Number.parseInt(horaBogota(fecha), 10);
  if (hora < 12) return 'Buenos días';
  return hora < 19 ? 'Buenas tardes' : 'Buenas noches';
}

const palabras = (nombre) => String(nombre || '').trim().split(/\s+/).filter(Boolean);

export function primerNombre(nombre) {
  return palabras(nombre)[0] || '';
}

/** "Ana María Pérez" -> "AP". */
export function iniciales(nombre) {
  const partes = palabras(nombre);
  if (!partes.length) return '?';
  const ultima = partes.length > 1 ? partes[partes.length - 1][0] : '';
  return `${partes[0][0]}${ultima}`.toUpperCase();
}
