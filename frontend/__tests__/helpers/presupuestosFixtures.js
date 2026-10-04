export const MES = {
  id: 'v2', mes: '2026-10', version: 2, origen: 'MANUAL', archivo_nombre: null, nota: null,
  created_at: '2026-10-03T15:00:00', asesores: 3, total: 4500000,
  lineas: [
    { cedula: '111', asesor: 'Ana Gómez', sucursal_id: 's1', tienda: 'Cali', monto: 1500000 },
    { cedula: '222', asesor: 'Beto Ruiz', sucursal_id: 's1', tienda: 'Cali', monto: 1000000 },
    { cedula: '333', asesor: 'Carla Díaz', sucursal_id: 's2', tienda: 'Bogotá', monto: 2000000 },
  ],
  por_tienda: [
    { sucursal_id: 's2', tienda: 'Bogotá', asesores: 1, total: 2000000 },
    { sucursal_id: 's1', tienda: 'Cali', asesores: 2, total: 2500000 },
  ],
};

export const LISTA = [
  { mes: '2026-10', version: 2, origen: 'MANUAL', created_at: '2026-10-03T15:00:00', asesores: 3, total: 4500000 },
  { mes: '2026-09', version: 1, origen: 'EXCEL', created_at: '2026-09-01T10:00:00', asesores: 2, total: 3000000 },
];

export const TIENDAS = [{ id: 's1', nombre: 'Cali' }, { id: 's2', nombre: 'Bogotá' }];

export const VERSIONES = [
  { id: 'v2', version: 2, origen: 'MANUAL', archivo_nombre: null, nota: 'ajuste Ana', created_at: '2026-10-03T15:00:00', created_by_nombre: 'Gerente Uno', lineas: 3, total: 4500000 },
  { id: 'v1', version: 1, origen: 'EXCEL', archivo_nombre: 'oct.xlsx', nota: null, created_at: '2026-10-01T09:00:00', created_by_nombre: 'Admin', lineas: 2, total: 3000000 },
];
