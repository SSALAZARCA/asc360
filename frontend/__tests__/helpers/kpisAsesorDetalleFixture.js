/**
 * Fixtures of the single-asesor view: `GET /kpis/asesores/detalle` for Gómez Muñoz Paula (cédula `a8`) and
 * `GET /kpis/asesores/opciones`. Pesos; every pct is a fraction.
 */
const M = 1e6;
const MESES = ['2026-05', '2026-06', '2026-07'];

const asesor = (cedula, nombre, tienda, venta) => ({ cedula, nombre, tienda, sucursal_id: `s-${cedula}`, venta });

// Twelve asesores, most sales first like the endpoint returns them: the first one is the default selection.
export const OPCIONES_ASESORES = {
  asesores: [
    asesor('a1', 'Jiménez Rangel Yulisa', 'Bogotá 1 de Mayo', 120 * M), asesor('a2', 'Rojas Zapata Alejandra', 'Medellín La 33', 110 * M),
    asesor('a3', 'Cuenca Flórez Angie', 'Cali Alfonso López', 100 * M), asesor('a4', 'Salgado Romero Andrea', 'Medellín La 33', 90 * M),
    asesor('a5', 'Aguja Rodríguez Yenny', 'Soacha El Dorado', 80 * M), asesor('a6', 'Ruiz Erazo Angela', 'Cali Cra 1 Dos', 70 * M),
    asesor('a7', 'Giraldo Jaramillo Andres', 'Cali Cra 1 Dos', 60 * M), asesor('a8', 'Gómez Muñoz Paula', 'Popayán', 50 * M),
    asesor('a9', 'Pinilla Guillén Luisa', 'Bogotá Kennedy', 40 * M), asesor('a10', 'Riveros Barreto Natalia', 'Bogotá Venecia', 30 * M),
    asesor('a11', 'Zambrano Garcés Alam', 'Bucaramanga', 20 * M), asesor('a12', 'Moreno Sánchez Viviana', 'Armenia', 10 * M),
  ],
};

const tile = (id, valor, ref, ref_de, dif_tipo, dif) => ({ id, valor, ref, ref_de, dif_tipo, dif });

export const ASESOR_DETALLE = {
  meses: MESES, hmcl: 'incluir', sucursales: [],
  reglas: { semaforo: { verde_desde: 90, ambar_desde: 70 }, cumplimiento_base: 'con_hmcl', vigencia: '2026-07' },
  usando_resumen: false, datos_actualizados_en: null,
  asesor: { cedula: 'a8', nombre: 'Gómez Muñoz Paula', cargo: 'ASESOR DE REPUESTOS', tienda: 'Popayán', sucursal_id: 's-pop' },
  puestos: { cumplimiento: { puesto: 7, de: 43 }, venta: { puesto: 8, de: 45 }, tecnired: { puesto: 5, de: 45 } },
  cumplimiento_mes: { mes: '2026-07', venta: 60.8 * M, presupuesto: 60 * M, pct: 1.014, semaforo: 'verde', red_pct: 0.78, base: 'con_hmcl' },
  comision: {
    mes: '2026-07', tramo: 'PRO', tasa_pct: 1.5, comision: 910000, venta_base: 60.7 * M, base_pago: 'sin_hmcl', presupuesto: 60 * M,
    promedio_red: 394000, cumplimiento_pct: 1.014, gate: { umbral: 95, cumple: true }, bono_total: 30000, total_a_pagar: 940000,
    bonos: [
      { linea: 'LUBRICANTES', etiqueta: 'Lubricantes', venta: 11 * M, pct_real: 0.183, pct_meta: 21, falta_venta: 3.4 * M, bono: 35000, cumple: false, paga: false, activo: true, bono_pagado: 0 },
      { linea: 'CASCOS', etiqueta: 'Cascos', venta: 4.3 * M, pct_real: 0.0712, pct_meta: 6, bono: 30000, cumple: true, paga: true, activo: true, bono_pagado: 30000 },
      { linea: 'TECNIRED', etiqueta: 'Tecnired (clientes)', venta: 1.2 * M, pct_real: 0.02, pct_meta: 6, bono: 25000, cumple: false, paga: false, activo: false, bono_pagado: 0 },
    ],
    sig: { tramo: 'ELITE', desde_pct: 105, tasa_pct: 1.8, falta: 2.2 * M, gana: 224000, meta: 63 * M },
  },
  tiles: [
    tile('venta', 421.2 * M, 209.2 * M, 'asesores', 'pct', 1.01),
    tile('ticket', 76696, 85615, 'red', 'pct', -0.104),
    tile('facturas', 5492, 2443, 'asesores', 'pct', 1.25),
    tile('clientes_unicos', 812, 640, 'asesores', 'pct', 0.269),
    tile('margen', 0.281, 0.271, 'red', 'pts', 0.01),
    tile('pct_tecnired', 0.121, 0.063, 'red', 'pts', 0.058),
  ],
  tendencia: [
    { mes: '2026-05', pct: 0.925, red_pct: 0.803 },
    { mes: '2026-06', pct: null, red_pct: 0.772 },
    { mes: '2026-07', pct: 1.014, red_pct: 0.78 },
  ],
  lineas: [
    { linea: 'REPUESTOS', pct: 0.55, red_pct: 0.604 }, { linea: 'LUBRICANTES', pct: 0.248, red_pct: 0.221 },
    { linea: 'ACCESORIOS', pct: 0.062, red_pct: 0.036 }, { linea: 'LLANTAS', pct: 0.021, red_pct: 0.013 },
  ],
  strip: {
    otros: [1.203, 1.445, 0.982, 0.833, 0.5, 0.25, 0.07],
    yo: 1.014,
    tramos: [{ nombre: 'BASE', desde_pct: 0 }, { nombre: 'PRO', desde_pct: 90 }, { nombre: 'ELITE', desde_pct: 105 }],
  },
  comparacion: {
    tienda: { nombre: 'Popayán', asesores: 2 },
    venta_mes: { yo: 60.8 * M, tienda: 52.4 * M, red: 35.6 * M },
    cumplimiento_mes: { yo: 1.014, tienda: 0.94, red: 0.78 },
    ticket: { yo: 76696, tienda: 79210, red: 85615 },
    margen: { yo: 0.281, tienda: 0.276, red: 0.271 },
    pct_tecnired: { yo: 0.121, tienda: 0.098, red: 0.063 },
  },
  tecnired: {
    venta: 51 * M, pct: 0.121, red_pct: 0.063, clientes: 14,
    top: [
      { cliente: 'Taller Uno SAS', nit: '9001', venta: 9.8 * M }, { cliente: 'Motos del Cauca', nit: '9002', venta: 7.4 * M },
      { cliente: '900123456', nit: '900123456', venta: 6.1 * M },
    ],
  },
};
