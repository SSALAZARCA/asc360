/** Fixtures shaped like `GET /tablero-asesores/kpis/opciones` and `/kpis/ventas` (amounts in pesos). */
export const OPCIONES = {
  meses_disponibles: ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07'],
  ultimo_mes: '2026-07',
  tiendas: [
    { id: 'aaaa0001-0000-0000-0000-000000000001', nombre: 'Bogotá Av. Boyacá' },
    { id: 'aaaa0002-0000-0000-0000-000000000002', nombre: 'Cali Cra 1 Dos' },
    { id: 'aaaa0003-0000-0000-0000-000000000003', nombre: 'Popayán' },
  ],
};

export const LINEAS = ['REPUESTOS', 'ACCESORIOS', 'LLANTAS', 'LUBRICANTES', 'BATERIAS', 'GPS', 'CASCOS'];
const M = 1e6;
const POR_LINEA = [800, 50, 20, 300, 20, 80, 60].map((v) => v * M);
const MESES = ['2026-05', '2026-06', '2026-07'];

const porMesLinea = Object.fromEntries(MESES.map((mes, i) => [
  mes, Object.fromEntries(LINEAS.map((l, j) => [l, (POR_LINEA[j] / 3) * (0.9 + i * 0.1)])),
]));
const totalLinea = LINEAS.reduce((s, _, j) => s + POR_LINEA[j], 0);

const cumpl = (id, nombre, venta, presupuesto) => {
  const fraccion = presupuesto ? venta / presupuesto : null;
  const semaforo = fraccion === null ? null : fraccion >= 0.9 ? 'verde' : fraccion >= 0.7 ? 'ambar' : 'violeta';
  return {
    sucursal_id: id, nombre, presupuesto, venta_cumplimiento: venta, cumplimiento_pct: fraccion, semaforo,
    estado: { verde: 'cumple', ambar: 'en_camino', violeta: 'atrasado' }[semaforo] || 'sin_presupuesto',
    cumple: semaforo === 'verde', asesores_con_presupuesto: presupuesto ? 3 : 0,
  };
};

export const VENTAS = {
  meses: MESES,
  hmcl: 'incluir',
  sucursales: [],
  reglas: { semaforo: { verde_desde: 90, ambar_desde: 70 }, cumplimiento_base: 'con_hmcl', vigencia: '2026-07' },
  total: {
    venta: {
      total: totalLinea, hmcl: totalLinea * 0.08, sin_hmcl: totalLinea * 0.92, pct_hmcl: 0.08,
      por_mes: Object.fromEntries(MESES.map((m, i) => [m, (totalLinea / 3) * (0.9 + i * 0.1)])),
      por_linea: Object.fromEntries(LINEAS.map((l, j) => [l, POR_LINEA[j]])),
      mix: Object.fromEntries(LINEAS.map((l, j) => [l, POR_LINEA[j] / totalLinea])),
      por_mes_linea: porMesLinea,
    },
    costo: { costo_venta: totalLinea * 0.73, venta_con_costo: totalLinea, utilidad_bruta: totalLinea * 0.27, pct_margen: 0.271, pct_venta_con_costo: 1 },
    facturas: { facturas: 154387, ticket_promedio: 85615, unidades: 477698, items_por_factura: 2.66, pct_con_linea: {}, pct_multilinea: 0.4 },
    descuentos: { total: 176 * M, mes_mayor: '2026-06', pct_en_mes_mayor: 0.4, pct_descuento: 0.0131 },
    clientes: {
      pct_mostrador: 0.9, venta_tecnired: 945 * M, pct_tecnired: 0.063, clientes_unicos: 95289, pct_top5: 0.1,
      tecnired_por_mes: { '2026-05': 280 * M, '2026-06': 300 * M, '2026-07': 365 * M },
      tecnired_por_linea: { REPUESTOS: 700 * M, LUBRICANTES: 150 * M, ACCESORIOS: 40 * M, LLANTAS: 20 * M, BATERIAS: 10 * M, GPS: 15 * M, CASCOS: 10 * M },
    },
  },
  tecnired: {
    venta: 945 * M, pct: 0.063, clientes: 542, venta_por_cliente: 1.74 * M,
    por_mes: { '2026-05': { venta: 280 * M, clientes: 200 }, '2026-06': { venta: 300 * M, clientes: 210 }, '2026-07': { venta: 365 * M, clientes: 230 } },
    por_linea: { REPUESTOS: 700 * M, LUBRICANTES: 150 * M, ACCESORIOS: 40 * M, LLANTAS: 20 * M, BATERIAS: 10 * M, GPS: 15 * M, CASCOS: 10 * M },
    top5: [
      { nit: '1', razon_social: 'Taller Uno SAS', venta: 90 * M, pct: 0.095 },
      { nit: '2', razon_social: 'Taller Dos SAS', venta: 70 * M, pct: 0.074 },
      { nit: '3', razon_social: 'Taller Tres SAS', venta: 50 * M, pct: 0.053 },
      { nit: '4', razon_social: 'Taller Cuatro SAS', venta: 40 * M, pct: 0.042 },
      { nit: '5', razon_social: 'Taller Cinco SAS', venta: 30 * M, pct: 0.032 },
    ],
  },
  cumplimiento: {
    red: cumpl(null, 'Red', 1554 * M, 1993 * M),
    tiendas: [
      cumpl('t1', 'Bogotá Av. Boyacá', 200 * M, 180 * M),
      cumpl('t2', 'Cali Cra 1 Dos', 150 * M, 200 * M),
      cumpl('t3', 'Popayán', 30 * M, 100 * M),
    ],
    conteos: { asesores: {}, tiendas: { verde: 1, ambar: 1, violeta: 1 } },
  },
  tiendas: [
    { sucursal_id: 't1', nombre: 'Bogotá Av. Boyacá', venta: {}, costo: {} },
    { sucursal_id: 't4', nombre: 'Tienda Sin Presupuesto', venta: {}, costo: {} },
  ],
  venta_sin_linea: 0,
};

/** The same answer when no budget is loaded and no cost data exists. */
export const VENTAS_SIN_PRESUPUESTO = {
  ...VENTAS,
  total: { ...VENTAS.total, costo: { ...VENTAS.total.costo, venta_con_costo: 0, pct_margen: null } },
  cumplimiento: {
    red: cumpl(null, 'Red', 0, 0),
    tiendas: [],
    conteos: { asesores: {}, tiendas: { verde: 0, ambar: 0, violeta: 0 } },
  },
};
