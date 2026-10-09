// Fixtures of the pending transfers (traslados) screens: one item per state, same shape as the API.
export const linea = (referencia, descripcion, cantidad) => ({ referencia, descripcion, cantidad });

export const traslado = (documento, extra = {}) => ({
  documento, bodega_salida: 'B-1', sale: 'Bogotá Av. Caracas', sucursal_id: 's-cam', llega: 'Bogotá Campin', tienda: 'Bogotá Campin',
  fecha: '2026-09-02', dias: 37, refs: 2, unidades: 2, num_lineas: 2,
  lineas: [linea('3360B-ABW-201S', 'Direccional der. tra.', 1), linea('3340B-ABW-201S', 'Direccional der. del.', 1)],
  estado: 'SIN_CONFIRMAR', aviso_erp: false, confirmado_por: null, confirmado_en: null, ...extra,
});

export const RECIBIDO = traslado('79-00000067', {
  bodega_salida: 'B-0', sale: 'Bodega 1 de Mayo Tres', sucursal_id: 's-ven', llega: 'Bogotá Venecia', tienda: 'Bogotá Venecia',
  fecha: '2026-08-03', dias: 67, refs: 1, unidades: 2, num_lineas: 1, lineas: [linea('REF-A', 'Filtro de aire', 2)],
  estado: 'RECIBIDO', aviso_erp: true, confirmado_por: 'Carlos Ruiz', confirmado_en: '2026-10-05T15:20:00Z',
});
export const SIN_CONFIRMAR = traslado('79-00000082');
export const NO_LLEGA = traslado('79-00000170', {
  bodega_salida: 'B-2', sale: 'Cali Cra 1 Dos', sucursal_id: 's-pop', llega: 'Popayán', tienda: 'Popayán',
  fecha: '2026-10-07', dias: 2, refs: 1, unidades: 2, num_lineas: 1, lineas: [linea('REF-C', 'Bujía', 2)],
  estado: 'NO_HA_LLEGADO', confirmado_por: 'Laura Díaz', confirmado_en: '2026-10-08T14:05:00Z',
});

export const ITEMS = [RECIBIDO, SIN_CONFIRMAR, NO_LLEGA];
export const ULTIMA_CARGA = '2026-10-09T12:40:00Z'; // 07:40 in Bogota
