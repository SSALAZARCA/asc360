/**
 * Tests for the "Exportar Excel" (unidades/VINs) button visibility gate in
 * `MotocicletasTab`, part of the 2026-08-24 `administrativo` role-permission
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

import MotocicletasTab from '../components/imports/MotocicletasTab';

function makeResponse(body) {
  return { ok: true, status: 200, json: jest.fn().mockResolvedValue(body) };
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  // Generic empty response — covers every fetch this component fires on
  // mount (units, locations, observations, model options, distribuidores).
  mockAuthFetch.mockResolvedValue(makeResponse({ items: [], total: 0 }));
});

describe('MotocicletasTab — Exportar Excel (unidades) role gate', () => {
  it('shows the export button for an administrativo user', async () => {
    render(<MotocicletasTab userRole="administrativo" />);

    expect(await screen.findByRole('button', { name: /exportar excel/i })).toBeInTheDocument();
  });

  it('does NOT show the export button for a technician user', async () => {
    render(<MotocicletasTab userRole="technician" />);

    // Wait for the always-rendered toolbar to mount before asserting
    // absence, so the test can't pass simply because nothing rendered yet.
    await screen.findByPlaceholderText('Buscar PI Number...');
    expect(screen.queryByRole('button', { name: /exportar excel/i })).not.toBeInTheDocument();
  });
});
