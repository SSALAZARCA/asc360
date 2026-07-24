/**
 * Tests for the Superadmin Data Editor sidebar entry, introduced in:
 *   sdd/superadmin-data-editor, Phase 6 (frontend)
 *
 * The sidebar entry pointing to `/superadmin-data` must follow the exact
 * existing `adminOnly` pattern already used by `/users` and `/settings`:
 * visible only to `role === 'superadmin'`, hidden for every other role.
 * This is cosmetic UX only — the real access control lives on the backend
 * (`is_superadmin` guard) — but the frontend gate must still behave
 * correctly so non-superadmins never see the entry point.
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

describe('Sidebar — superadmin data quick-fix entry gate', () => {
  it('shows the entry link pointing to /superadmin-data for a superadmin user', async () => {
    setUser('superadmin');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Datos Rápidos/i)).toBeInTheDocument();
    });
    const link = screen.getByText(/Datos Rápidos/i).closest('a');
    expect(link).toHaveAttribute('href', '/superadmin-data');
  });

  it('hides the entry link for a non-superadmin (jefe_taller) user', async () => {
    setUser('jefe_taller');
    render(<Sidebar />);

    // Sanity: a non-adminOnly item is present, proving the menu actually rendered.
    await waitFor(() => {
      expect(screen.getByText(/Gestión de Órdenes/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Datos Rápidos/i)).not.toBeInTheDocument();
  });

  it('hides the entry link for an administrativo user (adminOnly, not allowAdministrativo)', async () => {
    setUser('administrativo');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Gestión de Órdenes/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Datos Rápidos/i)).not.toBeInTheDocument();
  });
});
