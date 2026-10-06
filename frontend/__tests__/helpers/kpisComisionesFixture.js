/** Fixture shaped like `GET /tablero-asesores/kpis/comisiones` (pesos; `cumplimiento_pct` as a fraction). July 2026, default tiers. */
const M = 1e6;
const TRAMOS = [
  { nombre: 'BASE', desde_pct: 0, tasa_pct: 1.0, hasta_pct: 90, asesores: 2 },
  { nombre: 'PRO', desde_pct: 90, tasa_pct: 1.5, hasta_pct: 105, asesores: 1 },
  { nombre: 'ELITE', desde_pct: 105, tasa_pct: 1.8, hasta_pct: null, asesores: 1 },
];

const asesor = (cedula, nombre, tienda, presupuesto, vcump, vcom, tramo, tasa, comision, sig) => ({
  cedula, nombre, tienda, sucursal_id: `s-${cedula}`, presupuesto, venta_cumplimiento: vcump, venta_comision: vcom,
  cumplimiento_pct: vcump / presupuesto, tramo, tasa_pct: tasa, comision, sig,
});

export const ASESORES_COMISION = [
  asesor('2', 'Jiménez Rangel Yulisa', 'Bogotá 1 de Mayo', 200 * M, 190 * M, 180 * M, 'PRO', 1.5, 2.7 * M,
    { nombre: 'ELITE', desde_pct: 105, tasa_pct: 1.8, falta: 20 * M, gana: 0.9 * M }),
  asesor('1', 'Rojas Zapata Alejandra', 'Medellín La 33', 100 * M, 120 * M, 100 * M, 'ELITE', 1.8, 1.8 * M, null),
  asesor('4', 'Salgado Romero Andrea', 'Medellín La 33', 100 * M, 85 * M, 80 * M, 'BASE', 1.0, 0.8 * M,
    { nombre: 'PRO', desde_pct: 90, tasa_pct: 1.5, falta: 5 * M, gana: 0.475 * M }),
  asesor('3', 'Cuenca Flórez Angie', 'Cali Alfonso López', 100 * M, 40 * M, 40 * M, 'BASE', 1.0, 0.4 * M,
    { nombre: 'PRO', desde_pct: 90, tasa_pct: 1.5, falta: 50 * M, gana: 0.95 * M }),
];

export const COMISIONES = {
  meses: ['2026-05', '2026-06', '2026-07'], hmcl: 'incluir', sucursales: [], usando_resumen: false, datos_actualizados_en: null,
  mes_liquidado: '2026-07',
  reglas: {
    semaforo: { verde_desde: 90, ambar_desde: 70 }, cumplimiento_base: 'con_hmcl', vigencia: '2026-07',
    comision_tramos: TRAMOS.map(({ nombre, desde_pct, tasa_pct }) => ({ nombre, desde_pct, tasa_pct })),
    comision_base_pago: 'sin_hmcl', comision_cargos_asesor: ['ASESOR DE REPUESTOS'],
  },
  resumen: {
    asesores: 4, comision_total: 5.7 * M, venta_base: 400 * M, comision_promedio: 1.425 * M,
    comision_mayor: { cedula: '2', nombre: 'Jiménez Rangel Yulisa', comision: 2.7 * M }, comision_pct_venta: 5.7 / 400,
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
  resumen: { asesores: 0, comision_total: 0, venta_base: 0, comision_promedio: 0, comision_mayor: null, comision_pct_venta: null },
  tramos: TRAMOS.map((t) => ({ ...t, asesores: 0 })), asesores: [], cerca_de_subir: [],
  advertencias: { ...COMISIONES.advertencias, sin_presupuestos: true },
};
