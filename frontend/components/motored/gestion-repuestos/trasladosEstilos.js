// Look of the Traslados screen states (the rest is shared with the invoices screen: ingresosEstilos.js).

export const ESTADOS_TRASLADO = {
  RECIBIDO: { texto: 'Recibido sin cargar al ERP', estilo: { background: '#fdf1e3', color: '#8a3f06', border: '1px solid #b45309' }, punto: '#0f766e' },
  SIN_CONFIRMAR: { texto: 'Sin confirmar', estilo: { background: '#f2f2f0', color: '#3d3d3a', border: '1px solid #c9c9c6' }, punto: '#6e6e68' },
  NO_HA_LLEGADO: { texto: 'Aún no llega', estilo: { background: '#f3eafb', color: '#5a1f8c', border: '1px solid #c9b2e6' }, punto: '#b45309' },
};

export const ESTADOS_FILTRO_TRASLADOS = [
  [null, 'Todas'], ['RECIBIDO', 'Recibido sin cargar al ERP'], ['SIN_CONFIRMAR', 'Sin confirmar'], ['NO_HA_LLEGADO', 'Aún no llega'],
];

/** Amber of the "Recibidos sin cargar al ERP" card (priority). */
export const AMBAR = { borde: '#b45309', fondo: '#fdf6ec', tinta: '#8a3f06', pie: '#6b3105' };
