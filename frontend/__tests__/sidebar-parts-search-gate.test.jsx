/**
 * Tests for the Distribuidor parts-search sidebar entry, introduced in:
 *   sdd/distributor-parts-search, Phase 4 (frontend, PR4)
 *
 * Mirrors `sidebar-distribuidor-gate.test.jsx`'s pattern for the SAME
 * generic `roles: [...]` allowlist mechanism (already used by
 * `vehicle-delivery`) -- no new filter logic needed for this entry either.
 *
 * SCOPE ADJUSTMENT (explicit user decision, this session, 2026-07-31): the
 * tasks doc originally specified `roles: ['parts_dealer', 'superadmin']` for
 * this entry. The user asked to TEMPORARILY restrict it to
 * `roles: ['superadmin']` only -- the screen is still being polished/tested
 * and `parts_dealer` should not see it in their menu yet (they CAN still
 * reach `/distribuidor/repuestos` directly by URL, via the existing
 * `/distribuidor/*` prefix gate -- that route/page restriction is
 * unchanged, see `admin-layout-parts-search-gate.test.jsx`). This file
 * therefore asserts the CURRENT temporary reality (superadmin sees it,
 * parts_dealer and jefe_taller do not) -- NOT the eventual `parts_dealer`
 * visibility from the tasks doc. Re-enabling later is a one-line change to
 * `Sidebar.js`'s `roles` array (see the `// TEMP:` comment there).
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/',
}));

jest.mock('../lib/api', () => ({
  getApiUrl: () => 'https://api.test',
}));

import Sidebar from '../components/Sidebar';

function setUser(role) {
  sessionStorage.setItem('um_user', JSON.stringify({ name: 'Test User', role }));
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  global.fetch = jest.fn().mockResolvedValue({ ok: false });
});

describe('Sidebar — parts-search gate (TEMPORARY: superadmin only)', () => {
  it('shows "Consulta de Repuestos" pointing to /distribuidor/repuestos for a superadmin user', async () => {
    setUser('superadmin');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Consulta de Repuestos/i)).toBeInTheDocument();
    });
    const link = screen.getByText(/Consulta de Repuestos/i).closest('a');
    expect(link).toHaveAttribute('href', '/distribuidor/repuestos');
  });

  it('hides the entry for a parts_dealer user (temporary restriction)', async () => {
    setUser('parts_dealer');
    render(<Sidebar />);

    // parts_dealer still sees its existing entry, proving the sidebar
    // rendered fully and simply chose not to show parts-search.
    await waitFor(() => {
      expect(screen.getByText(/Registro de Motocicletas/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Consulta de Repuestos/i)).not.toBeInTheDocument();
  });

  it('hides the entry for every other role (jefe_taller)', async () => {
    setUser('jefe_taller');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Gestión de Órdenes/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Consulta de Repuestos/i)).not.toBeInTheDocument();
  });
});
