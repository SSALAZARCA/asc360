/** Fixture shaped like `GET /tablero-asesores/kpis/inventario` (pesos; every `pct` is a fraction). Corte 2026-09-30. */
const M = 1e6;

const quieta = (referencia, nombre, sucursal_id, tienda, existencia, valor, dias) =>
  ({ referencia, nombre, sucursal_id, tienda, existencia, valor: valor * M, dias_sin_venta: dias });

const agotada = (referencia, nombre, sucursal_id, tienda, vendidas, perdidas, transito) => {
  const demanda = vendidas + perdidas;
  return { referencia, nombre, sucursal_id, tienda, vendidas, perdidas, demanda, transito, cobertura: transito / demanda };
};

const AGOTADAS = [
  agotada('15410-AAF-400', 'Filtro de aceite', 't2', 'Medellín La 33', 86, 12, 60),
  agotada('06455-KVN-901', 'Pastillas de freno', 't1', 'Bogotá 1 de Mayo Dos', 54, 9, 0),
  agotada('LUB-20W50-1L', 'Aceite 20W-50 1 L', 't3', 'Cali Alfonso López', 210, 25, 144),
  agotada('22870-KWN-900', 'Guaya de clutch', 't4', 'Soacha El Dorado', 31, 6, 0),
  agotada('40530-KVN-900', 'Kit arrastre', 't5', 'Cartagena Pie de Popa CDS', 27, 11, 0),
  agotada('12391-AAK-900', 'Empaque culata', 't6', 'Bucaramanga La 27', 19, 3, 10),
  agotada('33400-ABV-012', 'Direccional delantera', 't7', 'Popayán', 16, 4, 0),
  agotada('LLT-90-90-18', 'Llanta 90/90-18', 't8', 'Pereira', 14, 7, 8),
  agotada('EXTRA-1', 'Referencia extra uno', 't1', 'Bogotá 1 de Mayo Dos', 5, 1, 0),
  agotada('EXTRA-2', 'Referencia extra dos', 't2', 'Medellín La 33', 4, 1, 0),
];

export const INVENTARIO = {
  meses: ['2026-07', '2026-08', '2026-09'], hmcl: 'incluir', sucursales: [], reglas: {}, usando_resumen: false,
  datos_actualizados_en: '2026-10-01T05:00:00Z',
  corte: '2026-09-30', costo_desde: '2026-07-01', costo_hasta: '2026-09-30', dias_ventana: 92,
  tarjetas: {
    valor: 3842 * M, valor_mes_anterior: 3763 * M, dias: 74, dias_meta: 60, rotacion: 4.93,
    sin_movimiento: { valor: 412 * M, pct: 0.107 }, disponibilidad: { pct: 0.914, agotadas: 312 },
    transito: { valor: 286 * M, facturas: 147 },
  },
  cortes_color: { verde_hasta: 60, ambar_hasta: 90 },
  tendencia: [{ mes: '2026-09', corte: '2026-09-30', valor: 3842 * M, dias: 74 }],
  antiguedad: {
    historial_desde: '2026-01',
    bandas: [
      { desde: 0, hasta: 90, valor: 2614 * M, pct: 0.68 },
      { desde: 91, hasta: 180, valor: 816 * M, pct: 0.212 },
      { desde: 181, hasta: 365, valor: 268 * M, pct: 0.07 },
      { desde: 366, hasta: null, valor: 144 * M, pct: 0.038 },
    ],
  },
  lineas: [
    { linea: 'Repuestos', valor: 2391 * M, pct: 0.622, dias: 82, rotacion: 4.45, disponibilidad_pct: 0.961 },
    { linea: 'Lubricantes', valor: 402 * M, pct: 0.105, dias: 38, rotacion: 9.6, disponibilidad_pct: 0.978 },
    { linea: 'GPS', valor: 85 * M, pct: 0.022, dias: null, rotacion: null, disponibilidad_pct: 0.906 },
  ],
  tiendas: [
    { sucursal_id: 't5', nombre: 'Cartagena Pie de Popa CDS', valor: 214 * M, dias: 118, rotacion: 3.1, sin_movimiento_valor: 46 * M, disponibilidad_pct: 0.842, agotadas: 31 },
    { sucursal_id: 't2', nombre: 'Medellín La 33', valor: 388 * M, dias: 81, rotacion: 4.5, sin_movimiento_valor: 39 * M, disponibilidad_pct: 0.925, agotadas: 24 },
    { sucursal_id: 't9', nombre: 'Bogotá Kennedy', valor: 119 * M, dias: 49, rotacion: 7.4, sin_movimiento_valor: 5 * M, disponibilidad_pct: 0.96, agotadas: 5 },
  ],
  sin_movimiento_umbral_dias: 180,
  sin_movimiento_top: [
    quieta('08CL2-MGF-000', 'Casco integral talla L', 't5', 'Cartagena Pie de Popa CDS', 42, 18.9, 412),
    quieta('17210-KVN-900', 'Filtro de aire', 't8', 'Pereira', 120, 7.2, 256),
    quieta('ACC-MALETERO-45', 'Maletero 45 L', 't1', 'Bogotá Av. Caracas', 28, 9.8, 301),
  ],
  agotadas: { total: 312, en_transito: 4, sin_pedir: 6, items: AGOTADAS },
};

export const INVENTARIO_VACIO = { ...INVENTARIO, corte: null, tarjetas: null, tendencia: [], lineas: [], tiendas: [] };
