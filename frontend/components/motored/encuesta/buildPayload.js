import { MATRIX_ROWS } from './copy';

/** POST /respuestas body; NS/NR matrix answers are sent as null. */
export function buildPayload({ cedula, celular4, registroId, q1, matrix, observaciones }, autoriza) {
  const payload = {
    cedula: cedula.trim(),
    celular_ultimos4: celular4.trim(),
    registro_id: registroId,
    satisfaccion_general: q1,
  };
  MATRIX_ROWS.forEach(([key], i) => {
    payload[key] = matrix[i] === 'NS' ? null : matrix[i];
  });
  payload.observaciones = observaciones.trim() || null;
  payload.autoriza_datos = autoriza;
  return payload;
}
