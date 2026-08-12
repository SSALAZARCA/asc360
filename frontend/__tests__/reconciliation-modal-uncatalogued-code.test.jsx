/**
 * Wiring of the not-yet-cataloged-code superadmin flow into
 * ReconciliationModal's `description_es` `EditableReconciliationCell`
 * (`sdd/parts-description-source-of-truth` PR3, task 3.6). A 409
 * `PART_NOT_IN_CATALOG` on save opens `CodeCandidateModal`, scoped to the
 * edited result's own `part_number` / `model_applicable`.
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

const mockCodeCandidateModal = jest.fn(() => null);
jest.mock('../components/imports/CodeCandidateModal', () => (props) => mockCodeCandidateModal(props));

import ReconciliationModal from '../components/imports/ReconciliationModal';

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  };
}

function makeResult({ id = 'r-1', part_number = 'P1', model_applicable = 'MODELX', confirmed_at = null } = {}) {
  return {
    id, part_number, description_es: 'Repuesto', model_applicable,
    qty_ordered: 10, qty_in_packing: 10, result: 'COMPLETE', confirmed_at,
  };
}

const lot = { id: 'lot-1', lot_identifier: 'E0000573-SP' };

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockCodeCandidateModal.mockClear();
});

describe('ReconciliationModal — uncatalogued-code flow (superadmin only)', () => {
  it('opens CodeCandidateModal scoped to the result on a 409 PART_NOT_IN_CATALOG', async () => {
    mockAuthFetch.mockImplementation((url, opts) => {
      if (url.includes('/reconciliation') && !opts) return Promise.resolve(makeResponse(200, [makeResult()]));
      if (url.includes('/reconciliation-results/r-1') && opts?.method === 'PATCH') {
        return Promise.resolve(makeResponse(409, {
          detail: { detail: 'El código no está en el catálogo', code: 'PART_NOT_IN_CATALOG' },
        }));
      }
      return Promise.resolve(makeResponse(200, [makeResult()]));
    });

    render(<ReconciliationModal lot={lot} userRole="superadmin" onClose={() => {}} />);

    const cell = await screen.findByText('Repuesto');
    const table = cell.closest('table');
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

  it('refetches results when the modal resolves', async () => {
    mockAuthFetch.mockImplementation((url, opts) => {
      if (url.includes('/reconciliation-results/r-1') && opts?.method === 'PATCH') {
        return Promise.resolve(makeResponse(409, {
          detail: { detail: 'El código no está en el catálogo', code: 'PART_NOT_IN_CATALOG' },
        }));
      }
      return Promise.resolve(makeResponse(200, [makeResult()]));
    });

    render(<ReconciliationModal lot={lot} userRole="superadmin" onClose={() => {}} />);

    const cell = await screen.findByText('Repuesto');
    const table = cell.closest('table');
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
