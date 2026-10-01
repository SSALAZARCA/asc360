/** Pure rules of the pedido lifecycle controls (which actions a tienda shows, send-form checks). */

// Display order and label of each backend `acciones` flag. `editar` is not a lifecycle control.
const ACCIONES_CICLO = [
  ['cerrar', 'Cerrar'],
  ['reabrir', 'Reabrir'],
  ['exportar', 'Exportar'],
  ['enviar', 'Marcar como enviado'],
  ['corregir_envio', 'Corregir número'],
];

const MOTIVO_SIN_CANTIDAD = 'Esta tienda no tiene nada que pedir: no se puede marcar como enviada.';
const MAX_NUMERO_ORDEN = 50;

/** True when the quantity to order is known and zero (A1: closable, not sendable). */
export function sinCantidad(unidades) {
  if (unidades == null || String(unidades).trim() === '') return false;
  return Number(unidades) === 0;
}

/**
 * The lifecycle actions to show for a tienda, from the backend `acciones`:
 * `[{ clave, accion, deshabilitada, motivo }]` in display order.
 */
export function accionesVisibles(acciones, unidadesAPedir) {
  if (!acciones) return [];
  return ACCIONES_CICLO
    .filter(([clave]) => acciones[clave])
    .map(([clave, accion]) => {
      const sinNada = clave === 'enviar' && sinCantidad(unidadesAPedir);
      return { clave, accion, deshabilitada: sinNada, motivo: sinNada ? MOTIVO_SIN_CANTIDAD : '' };
    });
}

/** The tienda page header in the shape of a Tiendas table row. */
export function tiendaDeCabecera(cabecera) {
  return {
    sucursal_id: cabecera.sucursal_id,
    nombre: cabecera.nombre,
    estado_pedido: cabecera.estado_pedido,
    unidades_a_pedir: cabecera.totales ? cabecera.totales.unidades_a_pedir : null,
    acciones: cabecera.acciones,
    envio: cabecera.envio,
  };
}

/** Today in Bogota as `YYYY-MM-DD` (the backend validates the send date against it). */
export function hoyBogota(ahora = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Bogota', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(ahora);
}

/** Message for an invalid order number or send date, or `''` when the pair is fine (the server re-checks). */
export function validarEnvio({ numero, fecha }, { desde, hasta }) {
  const limpio = String(numero || '').trim();
  if (limpio === '') return 'Escriba el número de orden de HMCL.';
  if (limpio.length > MAX_NUMERO_ORDEN) return `El número de orden admite hasta ${MAX_NUMERO_ORDEN} caracteres.`;
  if (!fecha) return 'Elija la fecha de envío.';
  if (fecha > hasta) return 'La fecha de envío no puede ser posterior a hoy.';
  if (fecha < desde) return 'La fecha de envío no puede ser anterior al corte.';
  return '';
}
