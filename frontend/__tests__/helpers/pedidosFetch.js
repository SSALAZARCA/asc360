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
