/** Fixture shaped like `GET /tablero-asesores/kpis/asesores` (the tablero plus `cumplimiento`; pesos, fractions for pct). */
const M = 1e6;
export const LINEAS = ['REPUESTOS', 'LUBRICANTES', 'ACCESORIOS', 'LLANTAS'];
const MESES = ['2026-05', '2026-06', '2026-07'];

const bloques = (ventaM, margen, ticket, mix, tecniredM) => {
  const total = ventaM * M;
  return {
    venta: {
      total, hmcl: 0, sin_hmcl: total, pct_hmcl: 0,
      por_mes: Object.fromEntries(MESES.map((m) => [m, total / 3])),
      por_linea: Object.fromEntries(LINEAS.map((l, i) => [l, total * mix[i]])),
      mix: Object.fromEntries(LINEAS.map((l, i) => [l, mix[i]])), por_mes_linea: {},
    },
    costo: { costo_venta: 0, venta_con_costo: total, utilidad_bruta: total * margen, pct_margen: margen, pct_venta_con_costo: 1 },
    tendencia: { ultimos_3m: null, previos_3m: null, diferencia: null, pct: null },
    facturas: { facturas: Math.round(total / ticket), ticket_promedio: ticket, unidades: 0, items_por_factura: 2.4, pct_con_linea: {}, pct_multilinea: 0.3 },
    descuentos: { total: 0, mes_mayor: null, pct_en_mes_mayor: null, pct_descuento: 0.01 },
    clientes: {
      pct_mostrador: 0.9, venta_tecnired: tecniredM * M, tecnired_por_mes: {}, tecnired_por_linea: {},
      pct_tecnired: ventaM ? tecniredM / ventaM : null, clientes_unicos: 100, pct_top5: 0.1,
    },
    ranking: null,
  };
};

// id, nombre, punto de venta, venta M, margen, ticket, mix [rep, lub, acc, llan], Tecnired M, presupuesto M
const PERSONAS = [
  ['a1', 'Jiménez Rangel Yulisa', 'Bogotá 1 de Mayo', 700, 0.228, 120000, [0.7, 0.2, 0.07, 0.03], 60, 600],
  ['a2', 'Rojas Zapata Alejandra', 'Medellín La 33', 600, 0.258, 95000, [0.65, 0.25, 0.05, 0.05], 30, 700],
  ['a3', 'Cuenca Flórez Angie', 'Cali Alfonso López', 500, 0.214, 88000, [0.6, 0.3, 0.07, 0.03], 90, 800],
  ['a4', 'Salgado Romero Andrea', 'Medellín La 33', 440, 0.298, 80000, [0.6, 0.3, 0.07, 0.03], 20, 400],
  ['a5', 'Aguja Rodríguez Yenny', 'Soacha El Dorado', 400, 0.293, 76000, [0.55, 0.35, 0.05, 0.05], 5, 500],
  ['a6', 'Ruiz Erazo Angela', 'Cali Cra 1 Dos', 350, 0.281, 70000, [0.6, 0.3, 0.07, 0.03], 40, 350],
  ['a7', 'Giraldo Jaramillo Andres', 'Cali Cra 1 Dos', 300, 0.284, 68000, [0.5, 0.4, 0.05, 0.05], 0, 600],
  ['a8', 'Gómez Muñoz Paula', 'Popayán', 250, 0.281, 67000, [0.6, 0.3, 0.05, 0.05], 10, 250],
  ['a9', 'Pinilla Guillén Luisa', 'Bogotá Kennedy', 200, 0.345, 66000, [0.7, 0.2, 0.05, 0.05], 2, 400],
  ['a10', 'Riveros Barreto Natalia', 'Bogotá Venecia', 180, 0.365, 64000, [0.65, 0.25, 0.05, 0.05], 3, 200],
  ['a11', 'Zambrano Garcés Alam', 'Bucaramanga', 60, 0.094, 60000, [0.6, 0.3, 0.05, 0.05], 0, 300],
  ['a12', 'Moreno Sánchez Viviana', 'Armenia', 30, 0.279, 58000, [0.6, 0.3, 0.05, 0.05], 1, 0],
];

const filaPersona = ([id, nombre, punto, v, m, t, mix, tec]) => ({
  clave: `P:${id}`, tipo: 'PERSONA', nombre, cargo: 'ASESOR', punto_venta: punto, cargos: ['ASESOR'], cargo_conflicto: false, personas: 1,
  ...bloques(v, m, t, mix, tec),
});
const filaGrupo = (clave, nombre, v, personas) => ({
  clave, tipo: 'GRUPO', nombre, cargo: null, punto_venta: null, cargos: [], cargo_conflicto: false, personas, ...bloques(v, 0.27, 70000, [0.6, 0.3, 0.07, 0.03], 0),
});

const cumpl = ([id, nombre, , v, , , , , presupuesto]) => {
  const fraccion = presupuesto ? v / presupuesto : null;
  const semaforo = fraccion === null ? null : fraccion >= 0.9 ? 'verde' : fraccion >= 0.7 ? 'ambar' : 'violeta';
  return {
    clave: `P:${id}`, cedula: id, nombre, sucursal_id: null, meses_con_presupuesto: presupuesto ? 3 : 0, presupuesto: presupuesto * M,
    venta_cumplimiento: v * M, cumplimiento_pct: fraccion, semaforo,
    estado: { verde: 'cumple', ambar: 'en_camino', violeta: 'atrasado' }[semaforo] || 'sin_presupuesto', cumple: semaforo === 'verde',
  };
};

const filas = [...PERSONAS.map(filaPersona), filaGrupo('COMERCIALES', 'ASESORES COMERCIALES DE SERVICIO POSVENTA (3 personas)', 100, 3),
  filaGrupo('OTROS', 'OTROS ROLES POSVENTA (4 personas)', 50, 4), filaGrupo('RESTO', 'RESTO COMPAÑÍA (20 vendedores)', 800, 20)];

export const ASESORES = {
  desde: MESES[0], hasta: MESES[2], meses: MESES, hmcl: 'incluir', sucursales: [],
  reglas: { semaforo: { verde_desde: 90, ambar_desde: 70 }, cumplimiento_base: 'con_hmcl', vigencia: '2026-07' },
  filas,
  total: {
    clave: 'TOTAL', tipo: 'TOTAL', nombre: 'TOTAL', ...bloques(5000, 0.271, 85615, [0.6, 0.3, 0.07, 0.03], 315),
    facturas: { facturas: 58400, ticket_promedio: 85615, unidades: 0, items_por_factura: 2.66, pct_con_linea: {}, pct_multilinea: 0.3 },
    clientes: { pct_mostrador: 0.9, venta_tecnired: 315 * M, tecnired_por_mes: {}, tecnired_por_linea: {}, pct_tecnired: 0.063, clientes_unicos: 1000, pct_top5: 0.1 },
  },
  venta_sin_linea: 0, pct_venta_sin_linea: 0,
  cumplimiento: {
    asesores: PERSONAS.map(cumpl),
    conteos: { asesores: { verde: 5, ambar: 2, violeta: 4, sin_presupuesto: 1 }, tiendas: {} },
    advertencias: { personas_sin_cedula: 2, venta_sin_cedula: 30 * M },
  },
};

/** No budgets loaded: nobody has compliance, every asesor is "sin presupuesto". */
export const ASESORES_SIN_PRESUPUESTO = {
  ...ASESORES,
  cumplimiento: {
    asesores: PERSONAS.map((p) => ({ ...cumpl([...p.slice(0, 8), 0]), clave: `P:${p[0]}` })),
    conteos: { asesores: { verde: 0, ambar: 0, violeta: 0, sin_presupuesto: 12 }, tiendas: {} },
    advertencias: { personas_sin_cedula: 0, venta_sin_cedula: 0 },
  },
};
