/**
 * Field-level superadmin gate for the part's Spanish/English name on
 * SparePartsTab's `EditableCell` — `sdd/parts-description-source-of-truth`
 * PR2 (design D8/D9/D10, spec's "Field-Level Permission Split on
 * Repuestos/Reconciliación Endpoints" requirement).
 *
 * `LotItemsTable`'s `canEdit` already gates the entire editable-cell UI to
 * `superadmin`/`proveedor` (a pre-existing, unrelated frontend restriction).
 * This locks in the NEW behavior layered on top of that: within `canEdit`,
 * `description`/`description_es` are read-only for any role other than
 * `superadmin`, with a distinct tooltip reason from the confirmed-lot
 * freeze — while non-name fields (`part_number`) stay editable for a
 * non-superadmin editor (`proveedor`) as before.
 */
import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';

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

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  };
}

const lot = {
  id: 'lot-1', lot_identifier: 'E0000573-SP',
  packing_list_received: false, reconciliation_confirmed: false,
  detail_loaded: true, items_count: 1, total_qty_ordered: 10, pct_received: 100,
  models: [], rotation_pct: {}, fob_value: null, fob_value_is_estimate: false,
};

const item = {
  id: 'item-1', lot_id: 'lot-1', part_number: 'PN-001', description_es: 'Repuesto',
  description: 'Spare part', model_applicable: 'M1', qty_ordered: 10, qty_received: 10,
  qty_physical: null, qty_pending: 0, status: 'RECEIVED', unit_price: null,
  amount: null, fob_pi: null, rotation_class: null,
};

function mockFetchFor() {
  mockAuthFetch.mockImplementation((url) => {
    if (url.includes('/spare-part-lots/stats')) return Promise.resolve(makeResponse(200, { unique_refs: 1, declared_refs: 1 }));
    if (url.includes('/backorders?')) return Promise.resolve(makeResponse(200, []));
    if (url.includes(`/spare-part-lots/${lot.id}/items`)) return Promise.resolve(makeResponse(200, [item]));
    if (url.includes('/spare-part-lots?')) return Promise.resolve(makeResponse(200, [lot]));
    return Promise.resolve(makeResponse(200, []));
  });
}

async function expandLotRow() {
  const row = await screen.findByText('E0000573-SP');
  const { fireEvent } = require('@testing-library/react');
  fireEvent.click(row);
  const partNumberCell = await screen.findByText('PN-001');
  return partNumberCell.closest('table');
}

beforeEach(() => {
  mockAuthFetch.mockReset();
});

describe('SparePartsTab — description cells are superadmin-only', () => {
  it('superadmin sees the description_es cell as click-to-edit', async () => {
    mockFetchFor();
    render(<SparePartsTab userRole="superadmin" />);

    const table = await expandLotRow();
    const cell = within(table).getByText('Repuesto');
    expect(cell).toHaveAttribute('title', 'Click para editar');
  });

  it('a non-superadmin editor (proveedor) sees the description_es cell read-only with a permission-specific tooltip', async () => {
    mockFetchFor();
    render(<SparePartsTab userRole="proveedor" />);

    const table = await expandLotRow();
    const cell = within(table).getByText('Repuesto');
    expect(cell).toHaveAttribute('title', 'Solo superadmin puede editar el nombre del repuesto');

    const { fireEvent } = require('@testing-library/react');
    fireEvent.click(cell);
    expect(within(table).queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('a non-superadmin editor (proveedor) sees the English description cell read-only too', async () => {
    mockFetchFor();
    render(<SparePartsTab userRole="proveedor" />);

    const table = await expandLotRow();
    const cell = within(table).getByText('Spare part');
    expect(cell).toHaveAttribute('title', 'Solo superadmin puede editar el nombre del repuesto');
  });

  it('a non-superadmin editor (proveedor) still edits non-name fields like part_number', async () => {
    mockFetchFor();
    render(<SparePartsTab userRole="proveedor" />);

    const table = await expandLotRow();
    const cell = within(table).getByText('PN-001');
    expect(cell).toHaveAttribute('title', 'Click para editar');
  });
});
