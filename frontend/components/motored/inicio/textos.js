/**
 * Inicio: fixed copy and colors (approved design, 2026-10-05). Pure data.
 */
import { horaBogota } from '../../../lib/motored/fechas';

export const ROL_NOMBRE = {
  ADMIN: 'Administrador',
  COMPRAS: 'Compras',
  GERENCIA: 'Gerencia',
  SERVICIO_CLIENTE: 'Servicio al cliente',
};

export const BAJADA = {
  ADMIN: 'Esto es lo que conviene mirar hoy antes de ponerte con el resto.',
  COMPRAS: 'Tus pedidos y los datos que los alimentan, en un vistazo.',
  GERENCIA: 'Cómo viene el mes, de un vistazo.',
  SERVICIO_CLIENTE: 'Las encuestas y los clientes que esperan respuesta.',
};

// Chip colors: Motored tokens, all at least 4.5:1 text on background.
export const TONOS = {
  ok: { fondo: 'var(--motored-success-bg, #ecfdf3)', tinta: 'var(--motored-success, #15803d)' },
  ojo: { fondo: 'var(--motored-warning-bg, #fef3e2)', tinta: 'var(--motored-data-mid-ink, #8a4104)' },
  mal: { fondo: 'var(--motored-danger-bg, #fdecea)', tinta: 'var(--motored-danger, #c0392b)' },
  neutro: { fondo: 'var(--motored-info-soft, #eaf0f8)', tinta: 'var(--motored-info, #1d4e89)' },
};

/** Data types of "Estado de los datos", in the backend's order. */
export const NOMBRE_DATO = {
  INVENTARIO: 'Inventario',
  BACKORDER: 'Backorder',
  FACTURAS_PEDIDOS: 'Facturas de pedidos',
  INGRESOS_FACTURAS: 'Ingresos de facturas',
  VENTAS: 'Ventas',
};

/** One line under each "Ir a" link, by sidebar entry id. */
export const AYUDA_ACCESO = {
  'tablero-asesores': 'Ventas, tiendas y asesores',
  pedidos: 'Calcular, revisar y enviar',
  maestros: 'Sucursales, referencias y cargas',
  'ventas-perdidas': 'Lo que se pidió y no había',
  'encuesta-satisfaccion': 'Subir el archivo del mes',
  detractores: 'Llamar y registrar la gestión',
  configuracion: 'Ajustes del cálculo y avisos',
  'usuarios-gestion': 'Usuarios, roles y permisos',
  ingresos: 'Quién entró y cuándo',
};
// GERENCIA only reaches the Presupuestos tab inside Maestros.
export const AYUDA_MAESTROS_GERENCIA = 'Presupuestos por asesor y mes';

export const NO_DISPONIBLE = 'No disponible por ahora';

const FECHA_LARGA = new Intl.DateTimeFormat('es-CO', {
  timeZone: 'America/Bogota', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
});

/** "Lunes, 5 de octubre de 2026" in Bogota, whatever the browser zone. */
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
