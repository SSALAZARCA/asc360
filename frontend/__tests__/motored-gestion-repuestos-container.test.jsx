/** The Ingresos facturas page: confirm buttons only for COORDINADOR_REPUESTOS, read-only for the other roles. */
import React from 'react';
import { render, screen } from '@testing-library/react';

jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }), usePathname: () => '/motored/gestion-repuestos/ingresos-facturas' }));

const mockApi = {
  getIngresosResumen: jest.fn(), getIngresosPorTienda: jest.fn(), getIngresosDetalle: jest.fn(), getIngresosHistorial: jest.fn(), confirmarIngreso: jest.fn(),
};
jest.mock('../lib/motored/gestionRepuestosApi', () => ({
  getIngresosResumen: (...a) => mockApi.getIngresosResumen(...a),
  getIngresosPorTienda: (...a) => mockApi.getIngresosPorTienda(...a),
  getIngresosDetalle: (...a) => mockApi.getIngresosDetalle(...a),
  getIngresosHistorial: (...a) => mockApi.getIngresosHistorial(...a),
  confirmarIngreso: (...a) => mockApi.confirmarIngreso(...a),
}));

import IngresosFacturasContainer from '../components/motored/gestion-repuestos/IngresosFacturasContainer';

const ITEM = {
  prefijo_rh: 'RH', numero_rh: 482915, factura: 'RH 482915', sucursal_id: 'id-cali', tienda: 'Cali', fecha: '2026-09-28', dias: 3,
  unidades: 2, valor: 100000, estado: 'SIN_CONFIRMAR', confirmado_por: null, confirmado_en: null,
};

beforeEach(() => {
  sessionStorage.clear();
  mockApi.getIngresosResumen.mockResolvedValue({
    verificable_desde: '2026-09-07',
    resumen: { pendientes: 1, llegaron_sin_ingresar: 0, sin_confirmar: 1, aun_no_llegan: 0, mas_antigua: 3, valor_pendiente: 100000 },
  });
  mockApi.getIngresosPorTienda.mockResolvedValue({ verificable_desde: '2026-09-07', tiendas: [] });
  mockApi.getIngresosDetalle.mockResolvedValue({ verificable_desde: '2026-09-07', items: [ITEM] });
});

const entrar = async (role) => {
  sessionStorage.setItem('motored_user', JSON.stringify({ role }));
  render(<IngresosFacturasContainer />);
  await screen.findByText('RH 482915');
};

test('the coordinador gets the confirm buttons', async () => {
  await entrar('COORDINADOR_REPUESTOS');
  expect(screen.getByRole('button', { name: 'Llegó' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'No ha llegado' })).toBeInTheDocument();
});

test.each(['ADMIN', 'COMPRAS', 'GERENCIA'])('%s reads without buttons', async (role) => {
  await entrar(role);
  expect(screen.queryByRole('button', { name: 'Llegó' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'No ha llegado' })).not.toBeInTheDocument();
});
