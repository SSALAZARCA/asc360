/**
 * Tests for the G4 frontend guard in SparePartsTab, introduced in:
 *   fix(imports): read reconciliation_confirmed instead of packing_list_received
 *   (sdd/packing-list-reupload-requires-rollback, Phase 8)
 *
 * Bug fixed: `LotRow` passed `isConfirmed={!!lot.packing_list_received}` into
 * `LotItemsTable` — but `packing_list_received` flips true as soon as a
 * packing list is UPLOADED, well before the reconciliation is actually
 * CONFIRMED. This let the physical-inventory UI (qty_physical column, "Inv.
 * Físico Excel" button) unlock too early, and never gated the G4-guarded
 * item fields (part_number/qty_ordered/qty_received/status) at all. Phase 6
 * added the correct `reconciliation_confirmed` field to the lot payload;
 * this locks in that `isConfirmed` now derives from THAT field, and that the
 * G4-guarded fields become read-only exactly when it's true.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

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

// The regression case: packing list was uploaded (packing_list_received)
// but reconciliation is NOT yet confirmed. The bug used
// `packing_list_received` as the confirmed signal — this fixture would have
// wrongly unlocked the G4-guarded fields under the old code.
const lotPlReceivedButNotConfirmed = {
  id: 'lot-1', lot_identifier: 'E0000573-SP',
  packing_list_received: true, reconciliation_confirmed: false,
  detail_loaded: true, items_count: 1, total_qty_ordered: 10, pct_received: 100,
  models: [], rotation_pct: {}, fob_value: null, fob_value_is_estimate: false,
};

const lotConfirmed = {
  ...lotPlReceivedButNotConfirmed,
  id: 'lot-2', lot_identifier: 'E0000999-SP', reconciliation_confirmed: true,
};

const item = {
  id: 'item-1', lot_id: 'lot-1', part_number: 'PN-001', description_es: 'Repuesto',
  description: null, model_applicable: 'M1', qty_ordered: 10, qty_received: 10,
  qty_physical: null, qty_pending: 0, status: 'RECEIVED', unit_price: null,
  amount: null, fob_pi: null, rotation_class: null,
};

function mockFetchFor(lot) {
  mockAuthFetch.mockImplementation((url) => {
    if (url.includes('/spare-part-lots/stats')) return Promise.resolve(makeResponse(200, { unique_refs: 1, declared_refs: 1 }));
    if (url.includes('/backorders?')) return Promise.resolve(makeResponse(200, []));
    if (url.includes(`/spare-part-lots/${lot.id}/items`)) return Promise.resolve(makeResponse(200, [item]));
    if (url.includes('/spare-part-lots?')) return Promise.resolve(makeResponse(200, [lot]));
    return Promise.resolve(makeResponse(200, []));
  });
}

async function expandLotRow(lotIdentifier) {
  const row = await screen.findByText(lotIdentifier);
  fireEvent.click(row);
  const partNumberCell = await screen.findByText('PN-001');
  return partNumberCell.closest('table');
}

beforeEach(() => {
  mockAuthFetch.mockReset();
});

describe('SparePartsTab — isConfirmed reads reconciliation_confirmed, not packing_list_received', () => {
  it('does NOT treat a lot as confirmed just because packing_list_received is true', async () => {
    mockFetchFor(lotPlReceivedButNotConfirmed);
    render(<SparePartsTab userRole="superadmin" />);

    const table = await expandLotRow('E0000573-SP');

    // G4-guarded field must still be editable (click-to-edit), since the
    // lot is NOT actually confirmed — this is exactly what the old
    // packing_list_received-based check got wrong.
    const partNumberCell = within(table).getByText('PN-001');
    expect(partNumberCell).toHaveAttribute('title', 'Click para editar');

    // qty_physical column stays gated (dash) because reconciliation isn't
    // confirmed yet, regardless of packing_list_received.
    expect(within(table).getAllByText('—').length).toBeGreaterThan(0);
  });

  it('treats a lot as confirmed when reconciliation_confirmed is true, gating G4 fields read-only', async () => {
    mockFetchFor(lotConfirmed);
    render(<SparePartsTab userRole="superadmin" />);

    const table = await expandLotRow('E0000999-SP');

    const partNumberCell = within(table).getByText('PN-001');
    expect(partNumberCell).toHaveAttribute('title', 'Reconciliación confirmada — no editable');

    // Clicking a read-only cell must never turn it into an <input> (no
    // PATCH should ever be attempted).
    fireEvent.click(partNumberCell);
    expect(within(table).queryByRole('textbox')).not.toBeInTheDocument();
  });
});
