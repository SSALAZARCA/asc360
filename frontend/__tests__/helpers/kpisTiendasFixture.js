/** Fixture shaped like `GET /tablero-asesores/kpis/tiendas` (amounts in pesos, fractions for every pct). */
const M = 1e6;
export const LINEAS = ['REPUESTOS', 'LUBRICANTES', 'ACCESORIOS', 'LLANTAS'];
const MESES = ['2026-05', '2026-06', '2026-07'];
const CORTE = '2026-07-31';

const cumpl = (id, nombre, venta, presupuesto) => {
  const fraccion = presupuesto ? venta / presupuesto : null;
  const semaforo = fraccion === null ? null : fraccion >= 0.9 ? 'verde' : fraccion >= 0.7 ? 'ambar' : 'violeta';
  return {
    sucursal_id: id, nombre, presupuesto, venta_cumplimiento: venta, cumplimiento_pct: fraccion, semaforo,
    estado: { verde: 'cumple', ambar: 'en_camino', violeta: 'atrasado' }[semaforo] || 'sin_presupuesto',
    cumple: semaforo === 'verde', asesores_con_presupuesto: presupuesto ? 3 : 0,
  };
};

// id, nombre, venta por mes (M), margen, crecimiento (fraccion|null), clasificacion, facturas, ticket, mix [rep, lub, acc, llan], presupuesto (M), dias inv
const TIENDAS_BASE = [
  ['t1', 'Bogotá Av. Boyacá', [90, 100, 110], 0.28, 0.18, 'crece', 2500, 120000, [0.6, 0.25, 0.1, 0.05], 270, 41],
  ['t2', 'Medellín La 33', [80, 90, 100], 0.31, 0.1, 'crece', 2200, 98000, [0.55, 0.3, 0.1, 0.05], 300, 52],
  ['t3', 'Cali Cra 1 Dos', [70, 65, 55], 0.24, -0.12, 'cae', 1800, 76000, [0.5, 0.3, 0.15, 0.05], 190, 98],
  ['t4', 'Popayán', [30, 28, 20], 0.19, -0.2, 'cae', 900, 52000, [0.45, 0.35, 0.15, 0.05], 100, null],
  ['t5', 'Armenia Nueva', [0, 10, 25], null, null, 'nueva', 400, 61000, [0.7, 0.2, 0.05, 0.05], null, null],
];

const fila = ([id, nombre, porMes, margen, crec, clasif, facturas, ticket, mix, presupuesto, dias]) => {
  const total = porMes.reduce((s, v) => s + v, 0) * M;
  const ventaConCosto = margen === null ? 0 : total;
  const lineaTotal = Object.fromEntries(LINEAS.map((l, i) => [l, total * mix[i]]));
  return {
    sucursal_id: id, nombre,
    venta: {
      total, hmcl: total * 0.05, sin_hmcl: total * 0.95, pct_hmcl: 0.05,
      por_mes: Object.fromEntries(MESES.map((m, i) => [m, porMes[i] * M])),
      por_linea: lineaTotal,
      mix: Object.fromEntries(LINEAS.map((l, i) => [l, mix[i]])),
      por_mes_linea: Object.fromEntries(MESES.map((m, i) => [m, Object.fromEntries(LINEAS.map((l, j) => [l, porMes[i] * M * mix[j]]))])),
    },
    costo: {
      costo_venta: margen === null ? 0 : total * (1 - margen), venta_con_costo: ventaConCosto,
      utilidad_bruta: margen === null ? 0 : total * margen, pct_margen: margen, pct_venta_con_costo: margen === null ? 0 : 1,
    },
    facturas: { facturas, ticket_promedio: ticket, unidades: facturas * 3, items_por_factura: 2.4, pct_con_linea: {}, pct_multilinea: 0.3 },
    descuentos: { total: total * 0.01, mes_mayor: '2026-06', pct_en_mes_mayor: 0.4, pct_descuento: 0.01 },
    clientes: { pct_mostrador: 0.9, venta_tecnired: total * 0.06, tecnired_por_mes: {}, tecnired_por_linea: {}, pct_tecnired: 0.06, clientes_unicos: 300, pct_top5: 0.1 },
    crecimiento: { ultimos_3m: total, previos_3m: crec === null ? 0 : total / (1 + crec), diferencia: 0, pct: crec, clasificacion: clasif },
    cumplimiento: presupuesto ? cumpl(id, nombre, total, presupuesto * M) : null,
    dias_inventario: dias === null ? null : { valor_inventario: dias * 1e6, costo_venta_diario: 1e6, dias, lineas_sin_costo: 0, fecha_corte: CORTE },
  };
};

const tiendas = TIENDAS_BASE.map(fila);
const conPresupuesto = tiendas.filter((t) => t.cumplimiento).map((t) => t.cumplimiento);

export const TIENDAS = {
  meses: MESES,
  hmcl: 'incluir',
  sucursales: [],
  reglas: { semaforo: { verde_desde: 90, ambar_desde: 70 }, cumplimiento_base: 'con_hmcl', vigencia: '2026-07' },
  tiendas,
  inventario: { fecha_corte: CORTE, dias_ventana: 92, tiendas: {}, red: {} },
  cumplimiento: {
    tiendas: conPresupuesto,
    red: cumpl(null, 'Red', conPresupuesto.reduce((s, c) => s + c.venta_cumplimiento, 0), conPresupuesto.reduce((s, c) => s + c.presupuesto, 0)),
    conteos: { asesores: {}, tiendas: { verde: 2, ambar: 1, violeta: 1 } },
  },
  resumen_crecimiento: { crece: 2, cae: 2, nueva: 1 },
  venta_sin_linea: 0,
};

/** No budgets loaded and no inventory: strips show the empty state and the days become dashes. */
export const TIENDAS_SIN_PRESUPUESTO = {
  ...TIENDAS,
  tiendas: tiendas.map((t) => ({ ...t, cumplimiento: null, dias_inventario: null })),
  cumplimiento: { tiendas: [], red: cumpl(null, 'Red', 0, 0), conteos: { asesores: {}, tiendas: { verde: 0, ambar: 0, violeta: 0 } } },
  inventario: { fecha_corte: null, dias_ventana: 92, tiendas: {}, red: {} },
};
