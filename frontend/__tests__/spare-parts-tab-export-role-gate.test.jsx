/**
 * Tests for the "Exportar Excel" (repuestos) button visibility gate in
 * `SparePartsTab`, part of the 2026-08-24 `administrativo` role-permission
 * expansion. The guard changed from `userRole === 'superadmin'` to
 * `(userRole === 'superadmin' || userRole === 'administrativo')` — this
 * file locks in that the button is visible for `administrativo` and stays
 * hidden for a role that should remain blocked (`technician`).
 */
import React from 'react';
import { render, screen } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));
jest.mock('../lib/api', () => ({
  getApiUrl: () => 'https://api.test',
}));
jest.mock('../lib/toast', () => ({
  toast: { error: jest.fn(), success: jest.fn() },
}));
jest.mock('../components/imports/ExcelUploadModal', () => () => null);
jest.mock('../components/imports/ReconciliationModal', () => () => null);
jest.mock('../components/imports/BackorderReconciliationModal', () => () => null);
jest.mock('../components/imports/PhysicalInventoryUploadModal', () => () => null);

import SparePartsTab from '../components/imports/SparePartsTab';

function makeResponse(body) {
  return { ok: true, status: 200, json: jest.fn().mockResolvedValue(body) };
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockAuthFetch.mockResolvedValue(makeResponse({ items: [], total: 0, unique_refs: 0, declared_refs: 0 }));
});

describe('SparePartsTab — Exportar Excel (repuestos) role gate', () => {
  it('shows the export button for an administrativo user', async () => {
    render(<SparePartsTab userRole="administrativo" />);

    expect(await screen.findByRole('button', { name: /exportar excel/i })).toBeInTheDocument();
  });

  it('does NOT show the export button for a technician user', async () => {
    render(<SparePartsTab userRole="technician" />);

    await screen.findByPlaceholderText(/buscar/i);
    expect(screen.queryByRole('button', { name: /exportar excel/i })).not.toBeInTheDocument();
  });
});
