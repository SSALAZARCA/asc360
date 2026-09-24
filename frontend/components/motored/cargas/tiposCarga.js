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
 * `columnas` (follow-up al cambio de arriba): fuente única de las columnas
 * esperadas por tipo, para que `UploadMovimientoModal` pueda ofrecer
 * "Descargar plantilla" -- copiadas EXACTAS de `COLUMNAS_ESPERADAS` en cada
 * módulo de transform del backend (`backend/app/motored/services/ingesta/
 * {ventas,inventario,backorder,demanda_perdida,facturas,ingresos}.py`); si
 * ese `COLUMNAS_ESPERADAS` cambia en el backend, esta lista debe seguirlo,
 * igual que `declaraPeriodo` sigue a `TIPOS_QUE_DECLARAN_PERIODO`.
 * BACKORDER además incluye `Fecha Creación`, columna real que el archivo
 * puede traer (`COLUMNAS_OPCIONALES` en `backorder.py`, task 9.6) aunque no
 * sea obligatoria -- se ofrece en la plantilla para que el usuario sepa que
 * puede completarla.
 */
export const TIPOS_CARGA = [
  {
    value: 'VENTAS', label: 'Ventas', declaraPeriodo: true, periodoLabel: 'mes',
    columnas: ['Estado', 'Módulo', 'Fecha', 'Cantidad inv.', 'Tipo inventario', 'Desc.bodega', 'Bodega', 'Referencia'],
  },
  {
    value: 'INVENTARIO', label: 'Inventario', declaraPeriodo: true, periodoLabel: 'fecha de corte',
    columnas: ['Referencia', 'Bodega', 'Desc.bodega', 'Existencia'],
  },
  {
    value: 'BACKORDER', label: 'Backorder', declaraPeriodo: true, periodoLabel: 'fecha de corte',
    columnas: ['SIC', 'Sucursal', 'Número del pedido', 'Estado del pedido', 'Referencia Parte', 'Cantidad Pendiente', 'Fecha Creación'],
  },
  {
    value: 'DEMANDA_PERDIDA', label: 'Demanda perdida', declaraPeriodo: true, periodoLabel: 'fecha',
    columnas: ['sucursal', 'sucursal Drive', 'Referencia', 'Cantidad Solicitada'],
  },
  {
    value: 'FACTURAS_PEDIDOS', label: 'Facturas de pedidos', declaraPeriodo: false,
    columnas: ['SIIC', 'Sucursal', 'Nota crédito', 'Factura', 'Fecha', 'Parte', 'Cantidad', 'Vlr. Total Neto'],
  },
  {
    value: 'INGRESOS_FACTURAS', label: 'Ingresos de facturas', declaraPeriodo: false,
    columnas: ['Nrodocumento', 'Fecha', 'Estado', 'Dct.referencia', 'Valornetolocal'],
  },
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

export function columnasTipo(tipo) {
  return TIPOS_CARGA.find((t) => t.value === tipo)?.columnas || [];
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
