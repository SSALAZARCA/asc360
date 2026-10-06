/** Fixture shaped like `GET /tablero-asesores/kpis/comisiones` (pesos; `cumplimiento_pct` as a fraction). July 2026, default tiers. */
const M = 1e6;
const TRAMOS = [
  { nombre: 'BASE', desde_pct: 0, tasa_pct: 1.0, hasta_pct: 90, asesores: 2 },
  { nombre: 'PRO', desde_pct: 90, tasa_pct: 1.5, hasta_pct: 105, asesores: 1 },
  { nombre: 'ELITE', desde_pct: 105, tasa_pct: 1.8, hasta_pct: null, asesores: 1 },
];

export const LINEAS_BONO = [
  { linea: 'LUBRICANTES', etiqueta: 'Lubricantes', pct_meta: 21, bono: 35000, activo: true },
  { linea: 'CASCOS', etiqueta: 'Cascos', pct_meta: 6, bono: 30000, activo: true },
  { linea: 'TECNIRED', etiqueta: 'Tecnired (clientes)', pct_meta: 6, bono: 25000, activo: false },
];

/** One bonus entry as the API returns it; `pcts` is [lubricantes, cascos, tecnired] as fractions of her total sale. */
const bonos = (gate, pcts) => LINEAS_BONO.map((l, i) => {
  const cumple = pcts[i] * 100 >= l.pct_meta;
  const paga = gate && l.activo && cumple;
  return { linea: l.linea, etiqueta: l.etiqueta, venta: pcts[i] * 1e8, pct_real: pcts[i], pct_meta: l.pct_meta, bono: l.bono, cumple, paga, activo: l.activo, bono_pagado: paga ? l.bono : 0 };
});

const asesor = (cedula, nombre, tienda, presupuesto, vcump, vcom, tramo, tasa, comision, sig, pcts) => {
  const gate = vcump / presupuesto >= 0.95;
  const lineas = bonos(gate, pcts);
  const bonoTotal = lineas.reduce((t, b) => t + b.bono_pagado, 0);
  return {
    cedula, nombre, tienda, sucursal_id: `s-${cedula}`, presupuesto, venta_cumplimiento: vcump, venta_comision: vcom,
    cumplimiento_pct: vcump / presupuesto, tramo, tasa_pct: tasa, comision, sig,
    gate: { umbral: 95, cumple: gate }, bonos: lineas, bono_total: bonoTotal, total_a_pagar: comision + bonoTotal,
  };
};

export const ASESORES_COMISION = [
  asesor('2', 'Jiménez Rangel Yulisa', 'Bogotá 1 de Mayo', 200 * M, 190 * M, 180 * M, 'PRO', 1.5, 2.7 * M,
    { nombre: 'ELITE', desde_pct: 105, tasa_pct: 1.8, falta: 20 * M, gana: 0.9 * M }, [0.25, 0.08, 0.1]),
  asesor('1', 'Rojas Zapata Alejandra', 'Medellín La 33', 100 * M, 120 * M, 100 * M, 'ELITE', 1.8, 1.8 * M, null, [0.15, 0.07, 0.02]),
  asesor('4', 'Salgado Romero Andrea', 'Medellín La 33', 100 * M, 85 * M, 80 * M, 'BASE', 1.0, 0.8 * M,
    { nombre: 'PRO', desde_pct: 90, tasa_pct: 1.5, falta: 5 * M, gana: 0.475 * M }, [0.3, 0.01, 0]),
  asesor('3', 'Cuenca Flórez Angie', 'Cali Alfonso López', 100 * M, 40 * M, 40 * M, 'BASE', 1.0, 0.4 * M,
    { nombre: 'PRO', desde_pct: 90, tasa_pct: 1.5, falta: 50 * M, gana: 0.95 * M }, [0, 0, 0]),
];

export const COMISIONES = {
  meses: ['2026-05', '2026-06', '2026-07'], hmcl: 'incluir', sucursales: [], usando_resumen: false, datos_actualizados_en: null,
  mes_liquidado: '2026-07',
  reglas: {
    semaforo: { verde_desde: 90, ambar_desde: 70 }, cumplimiento_base: 'con_hmcl', vigencia: '2026-07',
    comision_tramos: TRAMOS.map(({ nombre, desde_pct, tasa_pct }) => ({ nombre, desde_pct, tasa_pct })),
    comision_base_pago: 'sin_hmcl', comision_cargos_asesor: ['ASESOR DE REPUESTOS'],
    comision_lineas: LINEAS_BONO, comision_bono_umbral_pct: 95,
  },
  resumen: {
    asesores: 4, comision_total: 5.7 * M, venta_base: 400 * M, comision_promedio: 1.425 * M,
    comision_mayor: { cedula: '2', nombre: 'Jiménez Rangel Yulisa', comision: 2.7 * M }, comision_pct_venta: 5.7 / 400,
    bonos_total: 95000, total_a_pagar: 5.7 * M + 95000,
    por_linea: [
      { linea: 'LUBRICANTES', etiqueta: 'Lubricantes', ganadores: 1, monto: 35000 },
      { linea: 'CASCOS', etiqueta: 'Cascos', ganadores: 2, monto: 60000 },
      { linea: 'TECNIRED', etiqueta: 'Tecnired (clientes)', ganadores: 0, monto: 0 },
    ],
  },
  tramos: TRAMOS,
  asesores: ASESORES_COMISION,
  cerca_de_subir: [
    { cedula: '4', nombre: 'Salgado Romero Andrea', tienda: 'Medellín La 33', tramo: 'BASE', cumplimiento_pct: 0.85, siguiente: 'PRO', brecha_pts: 5, falta: 5 * M, gana: 0.475 * M },
    { cedula: '2', nombre: 'Jiménez Rangel Yulisa', tienda: 'Bogotá 1 de Mayo', tramo: 'PRO', cumplimiento_pct: 0.95, siguiente: 'ELITE', brecha_pts: 10, falta: 20 * M, gana: 0.9 * M },
  ],
  advertencias: { sin_presupuesto: [], cargo_desconocido: 0, sin_cedula: { personas: 0, venta: 0 }, sin_presupuestos: false },
};

export const COMISIONES_SIN_PRESUPUESTO = {
  ...COMISIONES,
  resumen: { asesores: 0, comision_total: 0, venta_base: 0, comision_promedio: 0, comision_mayor: null, comision_pct_venta: null, bonos_total: 0, total_a_pagar: 0, por_linea: [] },
  tramos: TRAMOS.map((t) => ({ ...t, asesores: 0 })), asesores: [], cerca_de_subir: [],
  advertencias: { ...COMISIONES.advertencias, sin_presupuestos: true },
};
