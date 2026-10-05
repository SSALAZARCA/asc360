/**
 * frontend/components/motored/cargas/tiposCarga.js
 *
 * Fuente única de los 6 tipos de MOVIMIENTO de `carga_archivo`
 * (sdd/motored-cargas-tipo-declarado; design ADR-9 tabla "¿Declara
 * período?"). `declaraPeriodo` refleja exactamente `TIPOS_QUE_DECLARAN_
 * PERIODO` en `backend/app/motored/services/ingesta/periodo.py` -- si ese
 * set cambia en el backend, esta lista debe seguirlo.
 *
 * `MAESTRO_REFERENCIAS`/`MAESTRO_BODEGAS` fueron REMOVIDOS de acá (design
 * D1/proposal decisión #3): ya no son alcanzables desde `POST /cargas` --
 * Bodegas/Referencias siguen viviendo, sin cambios, en su propia pestaña de
 * Maestros (`BulkUploadModal`). `labelTipo` conserva su fallback al valor
 * crudo para que filas HISTÓRICAS con esos dos valores (o `NULL`) sigan
 * mostrando algo legible en la grilla compartida (spec "Historical rows
 * with legacy or missing tipo remain servable").
 *
 * Las columnas esperadas de cada tipo NO viven acá: las define el backend
 * (`COLUMNAS_ESPERADAS` de cada transform) y "Descargar plantilla" las
 * obtiene del servidor (`GET /cargas/{tipo}/plantilla.xlsx`), así que no hay
 * una segunda lista que mantener sincronizada.
 */
export const TIPOS_CARGA = [
  { value: 'VENTAS', label: 'Ventas', declaraPeriodo: true, periodoLabel: 'mes' },
  { value: 'INVENTARIO', label: 'Inventario', declaraPeriodo: true, periodoLabel: 'fecha de corte' },
  { value: 'BACKORDER', label: 'Backorder', declaraPeriodo: true, periodoLabel: 'fecha de corte', sinDatos: 'backorder' },
  { value: 'DEMANDA_PERDIDA', label: 'Demanda perdida', declaraPeriodo: true, periodoLabel: 'fecha' },
  { value: 'FACTURAS_PEDIDOS', label: 'Facturas de pedidos', declaraPeriodo: false, sinDatos: 'facturas' },
  { value: 'INGRESOS_FACTURAS', label: 'Ingresos de facturas', declaraPeriodo: false, sinDatos: 'ingresos' },
];

export const ESTADOS_CARGA = [
  'PENDIENTE', 'PROCESANDO', 'VALIDADO', 'CON_ERRORES', 'APLICANDO', 'APLICADO', 'ANULADO',
];

export function labelTipo(tipo) {
  return TIPOS_CARGA.find((t) => t.value === tipo)?.label || (tipo ? tipo : 'Sin tipo');
}

export function tipoDeclaraPeriodo(tipo) {
  return TIPOS_CARGA.find((t) => t.value === tipo)?.declaraPeriodo ?? false;
}

/** A snapshot type (INVENTARIO, BACKORDER): one cutoff date, never a
 * range -- the backend takes `periodo_desde` as its `fecha_corte`. */
export function tipoUsaFechaDeCorte(tipo) {
  return TIPOS_CARGA.find((t) => t.value === tipo)?.periodoLabel === 'fecha de corte';
}

/** What a "no data at this date" declaration says is missing (BACKORDER,
 * FACTURAS_PEDIDOS, INGRESOS_FACTURAS), or `null` when the tipo cannot be
 * declared empty -- mirrors `TIPOS_SIN_DATOS` in
 * `backend/app/motored/services/ingesta/sin_datos.py`. */
export function textoSinDatos(tipo) {
  return TIPOS_CARGA.find((t) => t.value === tipo)?.sinDatos || null;
}

const ESTADO_COLOR = {
  PENDIENTE: { fg: 'var(--motored-text-muted, #5a5a5a)', bg: 'var(--motored-surface-alt, #f4f4f5)' },
  PROCESANDO: { fg: 'var(--motored-warning, #d97706)', bg: 'var(--motored-warning-bg, #fef3e2)' },
  APLICANDO: { fg: 'var(--motored-warning, #d97706)', bg: 'var(--motored-warning-bg, #fef3e2)' },
  VALIDADO: { fg: 'var(--motored-success, #15803d)', bg: 'var(--motored-success-bg, #ecfdf3)' },
  APLICADO: { fg: 'var(--motored-success, #15803d)', bg: 'var(--motored-success-bg, #ecfdf3)' },
  CON_ERRORES: { fg: 'var(--motored-danger, #c0392b)', bg: 'var(--motored-danger-bg, #fdecea)' },
  ANULADO: { fg: 'var(--motored-danger, #c0392b)', bg: 'var(--motored-danger-bg, #fdecea)' },
};

export function coloresEstado(estado) {
  return ESTADO_COLOR[estado] || ESTADO_COLOR.PENDIENTE;
}

/** ADR-9: "un mes por archivo" -- devuelve `true` cuando el rango declarado
 * abarca más de un mes calendario, para mostrar el aviso de la spec
 * ("Cargas recurrentes: un mes por archivo") -- guía, nunca bloqueo. */
export function excedeUnMes(periodoDesde, periodoHasta) {
  if (!periodoDesde || !periodoHasta) return false;
  const desde = new Date(`${periodoDesde}T00:00:00`);
  const hasta = new Date(`${periodoHasta}T00:00:00`);
  if (Number.isNaN(desde.getTime()) || Number.isNaN(hasta.getTime())) return false;
  const meses = (hasta.getFullYear() - desde.getFullYear()) * 12 + (hasta.getMonth() - desde.getMonth());
  return meses > 0;
}
