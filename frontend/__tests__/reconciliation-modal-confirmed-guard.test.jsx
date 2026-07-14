/**
 * Tests for the G1/G2 frontend guard in ReconciliationModal, introduced in:
 *   feat(imports): gate ReconciliationModal UI on reconciliation_confirmed
 *   (sdd/packing-list-reupload-requires-rollback, Phase 7)
 *
 * Backend guards G1 (upload) and G2 (field-scoped edit) already reject these
 * actions with a 409 once a lot's reconciliation is confirmed. This locks in
 * the UI-side guard that PREVENTS the interaction upfront instead of letting
 * the user hit the 409 after a round-trip:
 *   - Upload/replace label is replaced by a rollback-required message once
 *     every fetched result is confirmed.
 *   - Declared-field cells (part_number, description_es, model_applicable,
 *     qty_in_packing) become read-only (no click-to-edit) once confirmed.
 *   - Everything behaves exactly as before when NOT confirmed (regression
 *     guard for the existing editable/upload behavior).
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

import ReconciliationModal from '../components/imports/ReconciliationModal';

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  };
}

function makeResult({ id, confirmed_at = null, part_number = 'PN-001' } = {}) {
  return {
    id: id || `r-${part_number}`,
    part_number,
    description_es: 'Repuesto',
    model_applicable: 'M1',
    qty_ordered: 10,
    qty_in_packing: 10,
    result: 'COMPLETE',
    confirmed_at,
  };
}

const lot = { id: 'lot-1', lot_identifier: 'E0000573-SP' };

beforeEach(() => {
  mockAuthFetch.mockReset();
});

describe('ReconciliationModal — confirmed-lot guard (G1 upload UI)', () => {
  it('shows the upload/replace label when no result is confirmed yet', async () => {
    mockAuthFetch.mockResolvedValue(
      makeResponse(200, [makeResult({ confirmed_at: null })])
    );

    render(<ReconciliationModal lot={lot} onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText('Reemplazar Packing List')).toBeInTheDocument();
    });
    expect(screen.queryByText(/primero debe ejecutarse un rollback/)).not.toBeInTheDocument();
  });

  it('hides the upload/replace label and shows the rollback message once every result is confirmed', async () => {
    mockAuthFetch.mockResolvedValue(
      makeResponse(200, [makeResult({ confirmed_at: '2026-07-13T00:00:00Z' })])
    );

    render(<ReconciliationModal lot={lot} onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText(/primero debe ejecutarse un rollback/)).toBeInTheDocument();
    });
    expect(screen.queryByText('Reemplazar Packing List')).not.toBeInTheDocument();
    expect(screen.queryByText('Subir Packing List')).not.toBeInTheDocument();
  });
});

describe('ReconciliationModal — confirmed-lot guard (G2 field-edit UI)', () => {
  it('keeps declared-field cells click-to-edit when not confirmed', async () => {
    mockAuthFetch.mockResolvedValue(
      makeResponse(200, [makeResult({ confirmed_at: null })])
    );

    render(<ReconciliationModal lot={lot} onClose={() => {}} />);

    const cell = await screen.findByText('PN-001');
    expect(cell).toHaveAttribute('title', 'Click para editar');
  });

  it('makes declared-field cells read-only once the result is confirmed', async () => {
    mockAuthFetch.mockResolvedValue(
      makeResponse(200, [makeResult({ confirmed_at: '2026-07-13T00:00:00Z' })])
    );

    render(<ReconciliationModal lot={lot} onClose={() => {}} />);

    const cell = await screen.findByText('PN-001');
    expect(cell).toHaveAttribute('title', 'Reconciliación confirmada — no editable');

    // Clicking must NOT turn the cell into an <input> (no PATCH should ever
    // be attempted from a read-only cell) — scoped to the results table to
    // avoid the modal's own (unrelated) search textbox.
    fireEvent.click(cell);
    const table = cell.closest('table');
    expect(within(table).queryByRole('textbox')).not.toBeInTheDocument();
  });
});
