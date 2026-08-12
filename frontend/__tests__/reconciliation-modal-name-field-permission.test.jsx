/**
 * Field-level superadmin gate for the part's Spanish name on
 * ReconciliationModal's `EditableReconciliationCell` — `sdd/parts-
 * description-source-of-truth` PR2 (design D8/D9/D10, spec's "Field-Level
 * Permission Split on Repuestos/Reconciliación Endpoints" requirement).
 *
 * `ReconciliationModal` had NO `userRole` prop before this change (flagged
 * design risk) — it now receives it from `SparePartsTab`. `description_es`
 * becomes read-only for any non-superadmin, with a tooltip distinct from
 * the pre-existing confirmed-lot freeze tooltip
 * (`reconciliation-modal-confirmed-guard.test.jsx` covers that one). Other
 * declared fields (`part_number`, `model_applicable`, `qty_in_packing`)
 * are unaffected — still gated only by the confirmed-lot freeze.
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

describe('ReconciliationModal — description_es cell is superadmin-only', () => {
  it('superadmin sees description_es as click-to-edit on an unconfirmed result', async () => {
    mockAuthFetch.mockResolvedValue(makeResponse(200, [makeResult({ confirmed_at: null })]));

    render(<ReconciliationModal lot={lot} userRole="superadmin" onClose={() => {}} />);

    const cell = await screen.findByText('Repuesto');
    expect(cell).toHaveAttribute('title', 'Click para editar');
  });

  it('a non-superadmin editor sees description_es read-only with a permission-specific tooltip, distinct from the confirmed-lot one', async () => {
    mockAuthFetch.mockResolvedValue(makeResponse(200, [makeResult({ confirmed_at: null })]));

    render(<ReconciliationModal lot={lot} userRole="administrativo" onClose={() => {}} />);

    const cell = await screen.findByText('Repuesto');
    expect(cell).toHaveAttribute('title', 'Solo superadmin puede editar el nombre del repuesto');

    fireEvent.click(cell);
    const table = cell.closest('table');
    expect(within(table).queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('a non-superadmin editor still edits non-name fields like part_number on an unconfirmed result', async () => {
    mockAuthFetch.mockResolvedValue(makeResponse(200, [makeResult({ confirmed_at: null })]));

    render(<ReconciliationModal lot={lot} userRole="administrativo" onClose={() => {}} />);

    const cell = await screen.findByText('PN-001');
    expect(cell).toHaveAttribute('title', 'Click para editar');
  });

  it('defaults to read-only (deny by default) when userRole is not provided', async () => {
    mockAuthFetch.mockResolvedValue(makeResponse(200, [makeResult({ confirmed_at: null })]));

    render(<ReconciliationModal lot={lot} onClose={() => {}} />);

    const cell = await screen.findByText('Repuesto');
    expect(cell).toHaveAttribute('title', 'Solo superadmin puede editar el nombre del repuesto');
  });

  it('shows the confirmed-lot tooltip (not the permission one) once the result is confirmed, even for superadmin', async () => {
    mockAuthFetch.mockResolvedValue(makeResponse(200, [makeResult({ confirmed_at: '2026-07-13T00:00:00Z' })]));

    render(<ReconciliationModal lot={lot} userRole="superadmin" onClose={() => {}} />);

    const cell = await screen.findByText('Repuesto');
    expect(cell).toHaveAttribute('title', 'Reconciliación confirmada — no editable');
  });
});
