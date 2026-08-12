/**
 * Wiring of the not-yet-cataloged-code superadmin flow into SparePartsTab's
 * `description_es` `EditableCell` (`sdd/parts-description-source-of-truth`
 * PR3, task 3.6). A 409 `PART_NOT_IN_CATALOG` on save opens
 * `CodeCandidateModal`, scoped to the edited item's own `part_number` /
 * `model_applicable`, carrying the description the superadmin was trying
 * to save. Non-superadmins never reach this -- the cell is already
 * read-only for them (PR2).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';

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

const mockCodeCandidateModal = jest.fn(() => null);
jest.mock('../components/imports/CodeCandidateModal', () => (props) => mockCodeCandidateModal(props));

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
  id: 'item-1', lot_id: 'lot-1', part_number: 'P1', description_es: 'Repuesto',
  description: 'Spare part', model_applicable: 'MODELX', qty_ordered: 10, qty_received: 10,
  qty_physical: null, qty_pending: 0, status: 'RECEIVED', unit_price: null,
  amount: null, fob_pi: null, rotation_class: null,
};

function mockFetchFor() {
  mockAuthFetch.mockImplementation((url, opts) => {
    if (url.includes('/spare-part-lots/stats')) return Promise.resolve(makeResponse(200, { unique_refs: 1, declared_refs: 1 }));
    if (url.includes('/backorders?')) return Promise.resolve(makeResponse(200, []));
    if (url.includes(`/spare-part-lots/${lot.id}/items`)) return Promise.resolve(makeResponse(200, [item]));
    if (url.includes('/spare-part-lots?')) return Promise.resolve(makeResponse(200, [lot]));
    if (url.includes('/spare-part-items/item-1') && opts?.method === 'PATCH') {
      return Promise.resolve(makeResponse(409, {
        detail: { detail: 'El código no está en el catálogo', code: 'PART_NOT_IN_CATALOG' },
      }));
    }
    return Promise.resolve(makeResponse(200, []));
  });
}

async function expandLotRow() {
  const row = await screen.findByText('E0000573-SP');
  fireEvent.click(row);
  const partNumberCell = await screen.findByText('P1');
  return partNumberCell.closest('table');
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockCodeCandidateModal.mockClear();
});

describe('SparePartsTab — uncatalogued-code flow (superadmin only)', () => {
  it('opens CodeCandidateModal scoped to the item on a 409 PART_NOT_IN_CATALOG', async () => {
    mockFetchFor();
    render(<SparePartsTab userRole="superadmin" />);

    const table = await expandLotRow();
    const cell = within(table).getByText('Repuesto');
    fireEvent.click(cell);
    const input = within(table).getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Filtro nuevo' } });
    fireEvent.blur(input);

    await waitFor(() => expect(mockCodeCandidateModal).toHaveBeenCalled());
    const props = mockCodeCandidateModal.mock.calls.at(-1)[0];
    expect(props.partNumber).toBe('P1');
    expect(props.modelApplicable).toBe('MODELX');
    expect(props.pendingDescription).toBe('Filtro nuevo');
  });

  it('does not show a generic error toast for the 409 -- the modal replaces it', async () => {
    mockFetchFor();
    const { toast } = require('../lib/toast');
    render(<SparePartsTab userRole="superadmin" />);

    const table = await expandLotRow();
    const cell = within(table).getByText('Repuesto');
    fireEvent.click(cell);
    const input = within(table).getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Filtro nuevo' } });
    fireEvent.blur(input);

    await waitFor(() => expect(mockCodeCandidateModal).toHaveBeenCalled());
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('closing the modal via onClose removes it and refetches on onResolved', async () => {
    mockFetchFor();
    render(<SparePartsTab userRole="superadmin" />);

    const table = await expandLotRow();
    const cell = within(table).getByText('Repuesto');
    fireEvent.click(cell);
    const input = within(table).getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Filtro nuevo' } });
    fireEvent.blur(input);

    await waitFor(() => expect(mockCodeCandidateModal).toHaveBeenCalled());
    const props = mockCodeCandidateModal.mock.calls.at(-1)[0];
    const callsBefore = mockAuthFetch.mock.calls.length;
    act(() => { props.onResolved(); });

    await waitFor(() => expect(mockAuthFetch.mock.calls.length).toBeGreaterThan(callsBefore));
  });
});
