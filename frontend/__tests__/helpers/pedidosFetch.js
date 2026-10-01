/**
 * Shared fixtures and a path-routed `fetch` double for the Pedidos screens
 * tests (sdd/motored-pedidos-ui). Not a test file: jest only runs `*.test.*`.
 */
export const jsonRes = (body, status = 200) => ({
  ok: status < 400, status, json: async () => body, clone() { return this; },
});

export const coded = (status, code, message, detalle) => jsonRes({
  detail: { code, message, ...(detalle ? { detalle } : {}) },
}, status);

const base = (over) => ({
  proveedor_id: 'p1', fecha_corte: '2026-10-01', es_escenario: false, alcance: 'TODAS',
  invalidada: false, sucursales_total: 47, sucursales_procesadas: 47, nota: null,
  created_at: '2026-10-01T15:30:00', terminado_en: '2026-10-01T15:40:00', cerrada_en: null,
  pedidos: null, ...over,
});

export const C_CALCULADA = base({
  id: 'c1', codigo: 'PED-2026-S40-001', estado: 'BORRADOR',
  pedidos: { total: 47, borrador: 34, cerrados: 10, enviados: 3 },
});
export const C_CALCULANDO = base({
  id: 'c2', codigo: 'PED-2026-S40-002', estado: 'CALCULANDO', sucursales_procesadas: 12,
  terminado_en: null,
});
export const C_FALLIDA = base({ id: 'c3', codigo: 'PED-2026-S40-003', estado: 'FALLIDA' });
export const C_ANULADA = base({ id: 'c4', codigo: 'PED-2026-S40-004', estado: 'ANULADA' });
export const C_PRUEBA = base({ id: 'c5', codigo: 'ESC-2026-S40-001', estado: 'BORRADOR', es_escenario: true });
export const C_PENDIENTE = base({
  id: 'c6', codigo: 'PED-2026-S40-006', estado: 'PENDIENTE', sucursales_procesadas: 0, terminado_en: null,
});
export const C_LIMPIA = base({
  id: 'c7', codigo: 'PED-2026-S40-007', estado: 'BORRADOR',
  pedidos: { total: 47, borrador: 47, cerrados: 0, enviados: 0 },
});
export const C_INVALIDADA = base({
  id: 'c8', codigo: 'PED-2026-S40-008', estado: 'BORRADOR', invalidada: true,
  pedidos: { total: 47, borrador: 47, cerrados: 0, enviados: 0 },
});

export const C_SOLO_ENVIADAS = base({
  id: 'c9', codigo: 'PED-2026-S40-009', estado: 'BORRADOR',
  pedidos: { total: 47, borrador: 40, cerrados: 0, enviados: 7 },
});

export const pagina = (items, over = {}) => ({
  items, total: items.length, limite: 50, offset: 0, ...over,
});

export const PROGRESO = {
  estado: 'CALCULANDO', total: 47, procesadas: 12, ok: 12, omitidas: 0, fallidas: 0,
  actual: 'Pereira', latido_en: null, intentos: 1, errores: [], advertencias: [],
};

export const SUCURSALES = [
  { id: 's1', nombre: 'Manizales', activa: true },
  { id: 's2', nombre: 'Pereira', activa: true },
  { id: 's3', nombre: 'Cerrada vieja', activa: false },
];

// --- Corrida detail / tienda page fixtures (F2a) ---------------------------

const ACCIONES = {
  cerrar: false, reabrir: false, editar: false, enviar: false, corregir_envio: false, exportar: false,
};

const tienda = (over) => ({
  sucursal_id: 's1', nombre: 'Manizales', orden: 1, estado: 'OK', codigo: null, mensaje: null,
  lineas: 259, excluidas: 3, unidades: '1000.00', valor: '5000000.00', intentos: 1,
  estado_pedido: 'BORRADOR', unidades_a_pedir: '1010.00', valor_a_pedir: '5400000.00',
  ultimo_evento: null, acciones: { ...ACCIONES, cerrar: true, editar: true }, envio: null, ...over,
});

export const T_BORRADOR = tienda({});
export const T_CERRADO = tienda({
  sucursal_id: 's2', nombre: 'Pereira', orden: 2, estado_pedido: 'CERRADO',
  unidades_a_pedir: '800.00', valor_a_pedir: '3200000.00',
  ultimo_evento: { evento: 'CERRADO', usuario: 'Compras Uno', creado_en: '2026-10-02T09:15:00' },
  acciones: { ...ACCIONES, reabrir: true, enviar: true, exportar: true },
});
export const T_ENVIADO = tienda({
  sucursal_id: 's3', nombre: 'Cali', orden: 3, estado_pedido: 'ENVIADO',
  unidades_a_pedir: '500.00', valor_a_pedir: '2500000.00',
  ultimo_evento: { evento: 'ENVIADO', usuario: 'Ana Gómez', creado_en: '2026-10-02T11:00:00' },
  acciones: { ...ACCIONES, corregir_envio: true, exportar: true },
  envio: { numero_orden: '12345', fecha_envio: '2026-10-02', enviado_por: 'Ana Gómez', enviado_en: '2026-10-02T11:00:00' },
});
export const T_FALLIDA = tienda({
  sucursal_id: 's4', nombre: 'Armenia', orden: 4, estado: 'FALLIDA', codigo: 'E-CORRIDA-020',
  mensaje: 'La tienda no tiene precios cargados.', lineas: 0, excluidas: 0, unidades: null, valor: null,
  estado_pedido: null, unidades_a_pedir: null, valor_a_pedir: null, acciones: ACCIONES,
});
export const T_OMITIDA = tienda({
  sucursal_id: 's5', nombre: 'Ibagué', orden: 5, estado: 'OMITIDA', codigo: null,
  mensaje: 'Tienda sin ventas en el periodo.', lineas: 0, excluidas: 0, unidades: null, valor: null,
  estado_pedido: null, unidades_a_pedir: null, valor_a_pedir: null, acciones: ACCIONES,
});

const fila = (sucursal_id, clase, unidades, referencias, valor, porcentaje_peso) => (
  { sucursal_id, clase, unidades, referencias, valor, porcentaje_peso }
);

export const D_DETALLE = {
  ...C_CALCULADA,
  pedidos: { total: 3, borrador: 1, cerrados: 1, enviados: 1, sin_pedido: 0 },
  parametros_en_fecha: '2026-10-01', overrides: null, motivo_invalidacion: null, motivo_anulacion: null,
  iniciado_en: null, anulada_en: null, intentos: 1, cargas_usadas: {}, parametros: {},
  antiguedad: {
    inventario: { carga_id: 'k1', fecha_usada: '2026-09-30', antiguedad_dias: 1, limite_dias: 7, fuente_limite: 'GLOBAL' },
    backorder: { carga_id: 'k2', fecha_usada: '2026-09-28', antiguedad_dias: 3, limite_dias: 7, fuente_limite: 'GLOBAL' },
    facturas: { carga_id: 'k3', fecha_usada: '2026-09-10', antiguedad_dias: 21, limite_dias: 14, fuente_limite: 'GLOBAL' },
  },
  mes_en_curso: null,
  advertencias: [{ sucursal_id: null, sucursal: null, codigo: 'A-CORRIDA-101', mensaje: 'Sin demanda perdida cargada.' }],
  sucursales: [T_BORRADOR, T_CERRADO, T_ENVIADO, T_FALLIDA, T_OMITIDA],
  resumen: [
    fila('s1', 'AF', '300.00', 20, '2000000.00', '30.00'),
    fila('s1', 'CM', '700.00', 100, '3000000.00', '70.00'),
    fila('s1', 'TOTAL', '1000.00', 120, '5000000.00', '100.00'),
    fila('s2', 'AF', '800.00', 30, '3200000.00', '100.00'),
  ],
  resumen_por_clase: [],
  totales: { unidades: '2300.00', referencias: 150, valor: '10200000.00' },
  resumen_a_pedir: [
    fila('s1', 'AF', '310.00', 20, '2100000.00', '30.69'),
    fila('s1', 'CM', '700.00', 100, '3300000.00', '69.31'),
    fila('s1', 'TOTAL', '1010.00', 120, '5400000.00', '100.00'),
    fila('s2', 'AF', '800.00', 30, '3200000.00', '100.00'),
  ],
  totales_a_pedir: { unidades: '2310.00', referencias: 150, valor: '10600000.00' },
};

export const D_PRUEBA = { ...D_DETALLE, ...C_PRUEBA, sucursales: [tienda({ estado_pedido: null, acciones: ACCIONES })] };

export const CAB_BORRADOR = {
  corrida_id: 'c1', corrida_codigo: 'PED-2026-S40-001', fecha_corte: '2026-10-01', corrida_estado: 'BORRADOR',
  es_escenario: false, invalidada: false, sucursal_id: 's1', nombre: 'Manizales', sic: '1234',
  estado: 'OK', codigo: null, mensaje: null, estado_pedido: 'BORRADOR',
  totales: { unidades_a_pedir: '1010.00', valor_a_pedir: '5400000.00', unidades_sugerido: '1000.00', valor_sugerido: '5000000.00' },
  ultimo_evento: null, acciones: { ...ACCIONES, cerrar: true, editar: true }, envio: null,
};
export const CAB_CERRADO = {
  ...CAB_BORRADOR, sucursal_id: 's2', nombre: 'Pereira', sic: '5678', estado_pedido: 'CERRADO',
  ultimo_evento: { evento: 'CERRADO', usuario: 'Compras Uno', creado_en: '2026-10-02T09:15:00' },
  acciones: { ...ACCIONES, reabrir: true, enviar: true, exportar: true },
};
export const CAB_ENVIADO = {
  ...CAB_BORRADOR, sucursal_id: 's3', nombre: 'Cali', sic: '9012', estado_pedido: 'ENVIADO',
  envio: { numero_orden: '12345', fecha_envio: '2026-10-02', enviado_por: 'Ana Gómez', enviado_en: '2026-10-02T11:00:00' },
  acciones: { ...ACCIONES, corregir_envio: true, exportar: true },
};
export const CAB_FALLIDA = {
  ...CAB_BORRADOR, sucursal_id: 's4', nombre: 'Armenia', sic: '3456', estado: 'FALLIDA', codigo: 'E-CORRIDA-020',
  mensaje: 'La tienda no tiene precios cargados.', estado_pedido: null, acciones: ACCIONES,
};
export const CAB_PRUEBA = { ...CAB_BORRADOR, es_escenario: true, estado_pedido: null, acciones: ACCIONES };

const linea = (over) => ({
  id: 1, sucursal_id: 's1', referencia_id: 'r1', codigo_referencia: '94109-12000S', nombre_parte: 'Filtro de aceite',
  clase: 'AF', unidad_empaque: 12, precio: '15000.00', pedido_sugerido: '48.00', pedido_final: '48.00',
  valor_pedido: '720000.00', valor_sugerido: '720000.00', estado_quiebre: 'NORMAL', motivo_exclusion: null,
  fuera_de_empaque: false, editada: false, editado_por: null, editado_en: null, motivo_edicion: null,
  ajuste: '5.00', ...over,
});

export const L_NORMAL = linea({});
export const L_EDITADA = linea({
  id: 2, codigo_referencia: '55512-A', nombre_parte: 'Bujía', clase: 'CM', unidad_empaque: 10,
  pedido_sugerido: '50.00', pedido_final: '60.00', valor_pedido: '27645.00', valor_sugerido: '23037.50',
  estado_quiebre: 'BAJO_MINIMO', editada: true, editado_por: 'Compras Uno', editado_en: '2026-10-02T10:15:00',
  motivo_edicion: 'MANUAL',
});
export const L_FUERA = linea({
  id: 3, codigo_referencia: '00123-AB', nombre_parte: 'Pastilla de freno', clase: 'BM',
  pedido_sugerido: '30.00', pedido_final: '30.00', valor_pedido: '450000.00', fuera_de_empaque: true,
  estado_quiebre: 'QUIEBRE_TOTAL',
});
export const L_EXCLUIDA = linea({
  id: 4, codigo_referencia: '77700-X', nombre_parte: 'Filtro sustituido', clase: 'DS',
  pedido_sugerido: '0.00', pedido_final: '0.00', valor_pedido: '0.00', motivo_exclusion: 'SUSTITUIDA',
  estado_quiebre: 'SIN_MOVIMIENTO',
});

export const paginaLineas = (items, over = {}) => ({ items, total: items.length, limite: 50, offset: 0, ...over });

/** Body of a successful PATCH of a line: the refreshed line (edited by Compras Uno) and the tienda totals. */
export const lineaEditada = (base, cantidad, over = {}) => {
  const q = Number(cantidad);
  const precio = Number(base.precio || 0);
  return jsonRes({
    linea: {
      ...base, pedido_final: `${q}.00`, valor_pedido: (q * precio).toFixed(2),
      fuera_de_empaque: q > 0 && q % base.unidad_empaque !== 0,
      editada: `${q}.00` !== base.pedido_sugerido, editado_por: 'Compras Uno',
      editado_en: '2026-10-02T10:15:00', motivo_edicion: 'MANUAL', ...over,
    },
    totales_tienda: {
      unidades_a_pedir: '1022.00', valor_a_pedir: '5580000.00', unidades_sugerido: '1000.00', valor_sugerido: '5000000.00',
    },
  });
};

/**
 * Installs `global.fetch` as a router: `routes` maps "METHOD /path" (path
 * without the API base and query) to a response or a function of the URL and
 * options. Unknown routes fail the test loudly.
 */
export function installFetch(routes) {
  const calls = [];
  global.fetch = jest.fn(async (url, options = {}) => {
    const parsed = new URL(url);
    const method = (options.method || 'GET').toUpperCase();
    const path = parsed.pathname.replace(/^\/api\/motored/, '');
    const handler = routes[`${method} ${path}`];
    calls.push({ method, path, query: parsed.searchParams, body: options.body ? JSON.parse(options.body) : null });
    if (handler === undefined) throw new Error(`Unmocked ${method} ${path}`);
    return typeof handler === 'function' ? handler(parsed, options) : handler;
  });
  global.fetch.calls = calls;
  return calls;
}

export function setSession(role = 'COMPRAS') {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'Compras Uno', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

// --- Lifecycle, export (F3) --------------------------------------------------

/** A successful file download response; `cabeceras` are the (lower-case) response headers. */
export const fileRes = (cabeceras = {}) => ({
  ok: true, status: 200, headers: { get: (k) => cabeceras[k.toLowerCase()] ?? null },
  blob: async () => ({}), clone() { return this; },
});

/** The same tienda as `base` under another id and name (for lists of drafts, closed tiendas...). */
export const otraTienda = (base, sucursal_id, nombre, orden) => ({ ...base, sucursal_id, nombre, orden });

/**
 * Stubs the browser download (object URL + anchor click) so no test navigates;
 * returns the list that receives the file name of every download asked for.
 */
export function installDescargas() {
  const nombres = [];
  global.URL.createObjectURL = jest.fn(() => 'blob:x');
  global.URL.revokeObjectURL = jest.fn();
  jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function click() {
    nombres.push(this.download);
  });
  return nombres;
}

// --- Budget cap (F4) ------------------------------------------------------------

/** A recorte proposal for tienda s1 (CAB_BORRADOR): cuts L_EDITADA (60 -> 50) and L_FUERA (30 -> 24), frees 95,000. */
export const PROPUESTA_TOPE = {
  activo: true, motivo_inactivo: null, modo_activo: true, corrida_id: 'c1', sucursal_id: 's1',
  tope: '5310000.00', valor_actual: '5400000.00', exceso: '90000.00',
  recortes: [
    {
      linea_id: 2, codigo: '55512-A', nombre: 'Bujía', clase_abc: 'CM', unidad_empaque: 10,
      pedido_actual: '60.00', pedido_propuesto: '50.00', empaques_recortados: '1.00', valor_recortado: '5000.00',
    },
    {
      linea_id: 3, codigo: '00123-AB', nombre: 'Pastilla de freno', clase_abc: 'BM', unidad_empaque: 12,
      pedido_actual: '30.00', pedido_propuesto: '24.00', empaques_recortados: '0.50', valor_recortado: '90000.00',
    },
  ],
  valor_final: '5305000.00', exceso_residual: '0.00', lineas_sin_precio: 0, advertencias: [], token: 'tok-1',
};

/** The answer of the recorte preview when there is nothing to propose (`motivo`: MODO_OFF, SIN_TOPE, ...). */
export const propuestaInactiva = (motivo = 'MODO_OFF') => ({
  activo: false, motivo_inactivo: motivo, modo_activo: motivo === 'MODO_OFF' ? false : true, corrida_id: 'c1',
  sucursal_id: 's1', tope: null, valor_actual: null, exceso: null, recortes: [], valor_final: null,
  exceso_residual: null, lineas_sin_precio: 0, advertencias: [], token: null,
});

/** One tienda of `GET /corridas/{id}/topes`. */
export const topeTienda = (over = {}) => ({
  sucursal_id: 's1', nombre: 'Manizales', estado_pedido: 'BORRADOR', tope: '3000000.00',
  valor_a_pedir: '5400000.00', exceso: '2400000.00', lineas_sin_precio: 0, ...over,
});

export const TOPES_CORRIDA = {
  activo: true, corrida_id: 'c1',
  tiendas: [
    topeTienda({}),
    topeTienda({ sucursal_id: 's2', nombre: 'Pereira', estado_pedido: 'CERRADO', tope: '4000000.00', valor_a_pedir: '3200000.00', exceso: '0.00' }),
    topeTienda({ sucursal_id: 's3', nombre: 'Cali', estado_pedido: 'ENVIADO', tope: null, valor_a_pedir: '2500000.00', exceso: null }),
  ],
};

/** The cap screen read: switch and one cap per active tienda. */
export const TOPES_PRESUPUESTO = {
  modo_activo: false, modo_vigente_desde: null,
  topes: [
    { sucursal_id: 's1', nombre: 'Manizales', valor: '80000000.00', vigente_desde: '2026-09-30' },
    { sucursal_id: 's2', nombre: 'Pereira', valor: null, vigente_desde: null },
    { sucursal_id: 's3', nombre: 'Cali', valor: '45000000.50', vigente_desde: '2026-09-15' },
  ],
};

// --- Consolidated network matrix (F5a) ---------------------------------------

/** One column of `GET /corridas/{id}/consolidado` (a tienda with the state of its calculation and of its pedido). */
export const tiendaConsolidado = (over = {}) => ({
  sucursal_id: 's1', nombre: 'Manizales', estado: 'OK', estado_pedido: 'BORRADOR', codigo: null, mensaje: null,
  unidades: '1010.00', valor: '5400000.00', ...over,
});

const fCons = (referencia_id, codigo, nombre, total, celdas) => ({ referencia_id, codigo, nombre, total, celdas });

/**
 * Three references (page) over four tiendas: Manizales (Borrador), Pereira (Cerrado), Cali (Enviado) and a FALLIDA
 * Armenia. Quantities are whole packs; the tienda totals cover the WHOLE corrida (more references than this page).
 */
export const CONSOLIDADO = {
  corrida_id: 'c1', codigo: 'PED-2026-S40-001', estado: 'BORRADOR', es_escenario: false,
  tiendas: [
    tiendaConsolidado({}),
    tiendaConsolidado({ sucursal_id: 's2', nombre: 'Pereira', estado_pedido: 'CERRADO', unidades: '800.00', valor: '3200000.00' }),
    tiendaConsolidado({ sucursal_id: 's3', nombre: 'Villavicencio', estado_pedido: 'ENVIADO', unidades: '500.00', valor: '2500000.00' }),
    tiendaConsolidado({
      sucursal_id: 's4', nombre: 'Armenia', estado: 'FALLIDA', estado_pedido: null, codigo: 'E-CORRIDA-020',
      mensaje: 'La tienda no tiene precios cargados.', unidades: null, valor: null,
    }),
  ],
  filas: [
    fCons('r1', '94109-12000S', 'Filtro de aceite', '108.00', { s1: '48.00', s2: '36.00', s3: '24.00' }),
    fCons('r2', '55512-A', 'Bujía', '60.00', { s1: '60.00' }),
    fCons('r3', '00123-AB', 'Pastilla de freno', '42.00', { s1: '30.00', s3: '12.00' }),
  ],
  totales: { unidades: '2310.00', valor: '11100000.00' },
  total: 3, limite: 100, offset: 0,
};

export const CONSOLIDADO_VACIO = { ...CONSOLIDADO, tiendas: [], filas: [], totales: { unidades: '0.00', valor: '0.00' }, total: 0 };
