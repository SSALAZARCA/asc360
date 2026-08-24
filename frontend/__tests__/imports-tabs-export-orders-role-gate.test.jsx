/**
 * Tests for the "Exportar Excel" (pedidos) button visibility gate in
 * `ImportsTabs`, part of the 2026-08-24 `administrativo` role-permission
 * expansion. The guard changed from `userRole === 'superadmin'` to
 * `(userRole === 'superadmin' || userRole === 'administrativo')` — this
 * file locks in that the button is visible for `administrativo` and stays
 * hidden for a role that should remain blocked (`technician`).
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));
jest.mock('../lib/api', () => ({
  getApiUrl: () => 'https://api.test',
}));

// Sub-tabs and modals are irrelevant to this gate — mock them away so the
// component mounts cheaply and only the "Pedidos" toolbar is exercised.
jest.mock('../components/imports/ShipmentTable', () => () => null);
jest.mock('../components/imports/ExcelUploadModal', () => () => null);
jest.mock('../components/imports/OrderDetailModal', () => () => null);
jest.mock('../components/imports/SparePartsTab', () => () => null);
jest.mock('../components/imports/MotocicletasTab', () => () => null);
jest.mock('../components/imports/BackorderTab', () => () => null);
jest.mock('../components/imports/DashboardTab', () => () => null);
jest.mock('../components/imports/AnalisisRepuestosTab', () => () => null);
jest.mock('../components/imports/RemisionesTab', () => () => null);
jest.mock('../components/imports/ComparativaTab', () => () => null);
jest.mock('../components/imports/ShipmentOrderFormModal', () => () => null);
jest.mock('../components/imports/NuevoPedidoModal', () => () => null);
jest.mock('../components/imports/InformeGerencialModal', () => () => null);

import ImportsTabs from '../components/imports/ImportsTabs';

function makeResponse(body) {
  return { ok: true, status: 200, json: jest.fn().mockResolvedValue(body) };
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockAuthFetch.mockResolvedValue(makeResponse({ items: [], total: 0 }));
});

async function goToPedidosTab() {
  fireEvent.click(screen.getByText('Pedidos'));
  // fetchOrders fires on tab switch — let it settle.
  await screen.findByText('Pedidos');
}

describe('ImportsTabs — Exportar Excel (pedidos) role gate', () => {
  it('shows the export button for an administrativo user', async () => {
    render(<ImportsTabs userRole="administrativo" />);
    await goToPedidosTab();

    expect(screen.getByRole('button', { name: /exportar excel/i })).toBeInTheDocument();
  });

  it('does NOT show the export button for a technician user', async () => {
    render(<ImportsTabs userRole="technician" />);
    await goToPedidosTab();

    expect(screen.queryByRole('button', { name: /exportar excel/i })).not.toBeInTheDocument();
  });
});
