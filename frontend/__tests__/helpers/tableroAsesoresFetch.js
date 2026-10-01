/**
 * Fixtures for the "Tablero de asesores" tests (feature motored-tablero-asesores,
 * T4). The shape mirrors `GET /api/motored/tablero-asesores`. Not a test file:
 * jest only runs `*.test.*`.
 */
export const LINEAS = ['REPUESTOS', 'ACCESORIOS', 'LLANTAS', 'LUBRICANTES', 'BATERIAS', 'GPS', 'CASCOS'];
export const MESES = ['2026-04', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09'];

const porLinea = (valores = {}) => Object.fromEntries(LINEAS.map((l) => [l, valores[l] ?? 0]));
const porMes = (valor) => Object.fromEntries(MESES.map((m) => [m, valor]));

export function fila(over = {}) {
  return {
    clave: 'P:a', tipo: 'PERSONA', nombre: 'Ana Pérez', cargo: 'ASESOR DE REPUESTOS',
    punto_venta: 'CALI NORTE', personas: 1,
    venta: {
      total: 3500, hmcl: 2000, sin_hmcl: 1500, pct_hmcl: 0.5714, por_mes: porMes(500),
      por_linea: porLinea({ REPUESTOS: 3000, LLANTAS: 500 }),
      mix: porLinea({ REPUESTOS: 0.857, LLANTAS: 0.143 }),
    },
    costo: {
      costo_venta: 1800, venta_con_costo: 3000, utilidad_bruta: 1200, pct_margen: 0.4, pct_venta_con_costo: 0.857,
    },
    tendencia: { ultimos_3m: 1800, previos_3m: 1200, diferencia: 600, pct: 0.5 },
    facturas: {
      facturas: 4, ticket_promedio: 875, unidades: 12, items_por_factura: 2,
      pct_con_linea: porLinea({ REPUESTOS: 0.75, LLANTAS: 0.25 }), pct_multilinea: 0.25,
    },
    descuentos: { total: 400, mes_mayor: '2026-09', pct_en_mes_mayor: 0.75, pct_descuento: 0.1026 },
    clientes: {
      pct_mostrador: 0.2857, venta_tecnired: 500, pct_tecnired: 0.1429, clientes_unicos: 3, pct_top5: 0.857,
    },
    ranking: {
      indice_vs_promedio: 0.875, rank_total: 2, rank_repuestos: 1, rank_accesorios: 2, rank_lubricantes: 1,
    },
    ...over,
  };
}

export const GRUPO_RESTO = fila({
  clave: 'RESTO', tipo: 'GRUPO', nombre: 'RESTO COMPAÑÍA (3 vendedores)', cargo: null, punto_venta: null,
  personas: 3, ranking: null,
});
export const TOTAL = fila({
  clave: 'TOTAL', tipo: 'TOTAL', nombre: 'TOTAL', cargo: null, punto_venta: null, personas: 4, ranking: null,
});

export const TABLERO = {
  desde: '2026-04', hasta: '2026-09', hmcl: 'incluir', meses: MESES,
  meses_disponibles: ['2026-03', ...MESES],
  fecha_corte_costos: '2026-09-03',
  venta_sin_linea: 0, pct_venta_sin_linea: null,
  filas: [
    fila(),
    fila({ clave: 'P:b', nombre: 'Beto Ruiz', punto_venta: 'BOGOTA', cargo: 'ASESOR DE REPUESTOS SUPERNUMERARIO' }),
    GRUPO_RESTO,
  ],
  total: TOTAL,
};

export const conSinLinea = (valor, pct) => ({ ...TABLERO, venta_sin_linea: valor, pct_venta_sin_linea: pct });
