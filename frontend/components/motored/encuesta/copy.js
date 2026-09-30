/**
 * Customer-facing Spanish copy of the public satisfaction survey. The four
 * questions are verbatim from the Google Form "ENCUESTA TALLERES".
 */
export const COPY = {
  label: 'ENCUESTA DE SATISFACCIÓN',
  intro:
    'En estos momentos estamos haciendo un estudio sobre la satisfacción del servicio de posventa prestado en nuestros talleres.',
  cedulaQuestion: 'Ingresa tu número de cédula',
  cedulaHint: 'La cédula de la persona a cuyo nombre está registrada la motocicleta.',
  celularQuestion: 'Últimos 4 dígitos de tu celular',
  celularHint: 'Los del número donde te llegó el mensaje de WhatsApp.',
  pickBike: '¿Sobre cuál moto nos cuentas?',
  q1:
    'En una calificación de 1 a 5, donde 5 es "Muy Satisfecho" y 1 es "Muy Insatisfecho", en general, ¿qué tan satisfecho se siente usted con el servicio de posventa recibida por el taller?',
  q2Intro:
    'Pensando en su experiencia en el taller al que asistió, por favor califique utilizando la misma escala de 1 a 5, donde 5 es "excelente" y 1 es "pésimo", como califica usted:',
  q3: '¿Qué observaciones tiene respecto al servicio que obtuvo en el taller?',
  q4:
    'PHD2. Dando cumplimiento a la ley de Protección de Datos Personales le solicito su autorización para que Motos red Nacional pueda contactarlo nuevamente en caso de ser necesario con fines de supervisión de esta encuesta y futuras encuestas. ¿Está usted de acuerdo?',
  rateLimited: 'Hiciste demasiados intentos. Espera un minuto e inténtalo de nuevo.',
  network: 'No pudimos conectarnos. Revisa tu conexión e inténtalo de nuevo.',
  genericIdentify: 'No pudimos revisar tu cédula. Inténtalo de nuevo en un momento.',
  submitFailed: 'No pudimos enviar tus respuestas. Inténtalo de nuevo.',
  submitLost: 'No pudimos registrar tu respuesta. Vuelve a ingresar tu cédula e inténtalo de nuevo.',
  offline: 'Se perdió la conexión.',
  offlineHint: 'Tus respuestas siguen guardadas en esta pantalla.',
};

// Matrix rows in backend payload order: [payload key, verbatim row text].
export const MATRIX_ROWS = [
  ['p_explicacion_tecnica', 'La explicación y asesoría técnica que le dieron en el taller de los problemas que tenía la moto'],
  ['p_confianza_reparacion', 'La confianza en la reparación de la motocicleta realizada por el taller o centro de servicio'],
  ['p_servicio_taller', 'Servicio que le prestaron en el taller o centro de servicio'],
  ['p_calidad_mecanicos', 'La calidad del trabajo realizado por los mecánicos'],
  ['p_claridad_cobros', 'La claridad en la explicación recibida de los cobros realizados antes y después del servicio'],
  ['p_originalidad_repuestos', 'La confianza en la procedencia y originalidad de los repuestos'],
];

export const SCALE_WORDS = {
  1: 'Muy insatisfecho',
  2: 'Insatisfecho',
  3: 'Ni satisfecho ni insatisfecho',
  4: 'Satisfecho',
  5: 'Muy satisfecho',
};

const MONTHS = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];

/** "2026-09-28T15:30:00" -> "28 de septiembre" (read from the string, no timezone shift). */
export function formatDay(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
  if (!match) return null;
  return `${Number(match[3])} de ${MONTHS[Number(match[2]) - 1]}`;
}
