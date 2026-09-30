/** Labels and pure formatters shared by the detractors screens. */
export const ESTADO_LABELS = { ABIERTO: 'Abierto', EN_GESTION: 'En gestión', CERRADO: 'Cerrado' };

export const RESULTADO_LABELS = {
  RECUPERADO: 'Recuperado', NO_RECUPERADO: 'No recuperado', NO_CONTACTABLE: 'No se pudo contactar',
};

export const TIPO_LABELS = {
  APERTURA: 'Apertura', LLAMADA: 'Llamada', WHATSAPP: 'WhatsApp', NOTA: 'Nota',
  COMPENSACION: 'Compensación', CORRECCION: 'Corrección', CAMBIO_ESTADO: 'Cambio de estado',
};

// Action types an agent may register (APERTURA / CAMBIO_ESTADO are system-only).
export const TIPOS_ACCION = ['LLAMADA', 'WHATSAPP', 'NOTA', 'COMPENSACION', 'CORRECCION'];
export const TIPOS_ACCION_CERRADO = ['NOTA', 'CORRECCION'];

export const SATISFACCION_LABELS = {
  1: 'Muy insatisfecho', 2: 'Insatisfecho', 3: 'Neutral', 4: 'Satisfecho', 5: 'Muy satisfecho',
};

// Verbatim texts of the survey matrix (Q2), in form order.
export const MATRIX_ROWS = [
  ['p_explicacion_tecnica', 'La explicación y asesoría técnica que le dieron en el taller de los problemas que tenía la moto'],
  ['p_confianza_reparacion', 'La confianza en la reparación de la motocicleta realizada por el taller o centro de servicio'],
  ['p_servicio_taller', 'Servicio que le prestaron en el taller o centro de servicio'],
  ['p_calidad_mecanicos', 'La calidad del trabajo realizado por los mecánicos'],
  ['p_claridad_cobros', 'La claridad en la explicación recibida de los cobros realizados antes y después del servicio'],
  ['p_originalidad_repuestos', 'La confianza en la procedencia y originalidad de los repuestos'],
];

export function formatFecha(iso) {
  return iso ? new Date(iso).toLocaleDateString('es-CO') : '—';
}

export function formatFechaHora(iso) {
  return iso ? new Date(iso).toLocaleString('es-CO') : '—';
}

/** wa.me link only when the digits look like a Colombian mobile (3XXXXXXXXX). */
export function whatsappUrl(celular) {
  const digits = String(celular || '').replace(/\D/g, '');
  const national = digits.length === 12 && digits.startsWith('57') ? digits.slice(2) : digits;
  return /^3\d{9}$/.test(national) ? `https://wa.me/57${national}` : null;
}
