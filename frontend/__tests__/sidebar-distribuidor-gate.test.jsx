/**
 * Tests for the Distribuidor delivery-registration sidebar entry, introduced in:
 *   sdd/distributor-vehicle-delivery, Phase 7 (frontend, PR7)
 *
 * Mirrors `sidebar-historical-orders-gate.test.jsx`, but exercises the NEW
 * generic `roles: [...]` allowlist mechanism (Design ADR 9) instead of the
 * existing `adminOnly`/`allowAdministrativo` booleans — this same mechanism
 * is meant to be reused, unmodified, by a future parts-sale screen for the
 * same `parts_dealer` role.
 *
 * Updated 2026-07-29 (explicit user decision): a Distribuidor can ONLY see
 * Registro de Motocicletas for now -- Kanban and Gestión de Órdenes (which
 * `parts_dealer` used to see, unrestricted, before this change) are hidden
 * too. The visible id set for `parts_dealer` is EXACTLY {vehicle-delivery}.
 *
 * Updated 2026-07-31 (sdd/distributor-parts-search, PR4): a second `roles:
 * [...]` entry (`parts-search`, "Consulta de Repuestos") has now landed in
 * `ALL_ITEMS` right after `vehicle-delivery` -- see
 * `sidebar-parts-search-gate.test.jsx` for its dedicated coverage. It is
 * TEMPORARILY `roles: ['superadmin']` only (scope adjustment requested by
 * the user this session, while the new screen is polished/tested) -- NOT
 * `parts_dealer`, so the "EXACTLY {vehicle-delivery}" claim below still
 * holds true for `parts_dealer` today. This will need re-verifying (not
 * necessarily changing) once `parts_dealer` is added back to that entry.
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

describe('Sidebar — distribuidor delivery gate', () => {
  it('shows the entry link pointing to /distribuidor/entrega for a parts_dealer user', async () => {
    setUser('parts_dealer');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Registro de Motocicletas/i)).toBeInTheDocument();
    });
    const link = screen.getByText(/Registro de Motocicletas/i).closest('a');
    expect(link).toHaveAttribute('href', '/distribuidor/entrega');
  });

  it('the visible id set for parts_dealer is EXACTLY vehicle-delivery', async () => {
    setUser('parts_dealer');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Registro de Motocicletas/i)).toBeInTheDocument();
    });
    // Kanban and Gestión de Órdenes are hidden too, per the 2026-07-29 decision.
    expect(screen.queryByText(/Tablero Operativo/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Gestión de Órdenes/i)).not.toBeInTheDocument();
    // Every adminOnly/importsOnly entry MUST stay hidden — unchanged.
    expect(screen.queryByText(/Centro de Comando/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Estado Pedidos/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Red de Tiendas/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Personal & Acceso/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Maestro de Partes/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Datos Rápidos/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Orden Histórica/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Configuración/i)).not.toBeInTheDocument();
    // "Consulta de Repuestos" (parts-search, PR4) is temporarily
    // superadmin-only -- a parts_dealer must not see it either.
    expect(screen.queryByText(/Consulta de Repuestos/i)).not.toBeInTheDocument();
  });

  it('shows the entry link for a superadmin user', async () => {
    setUser('superadmin');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Registro de Motocicletas/i)).toBeInTheDocument();
    });
  });

  it('shows the entry link for an administrativo user (2026-08-24: administrativo now matches superadmin here)', async () => {
    setUser('administrativo');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Registro de Motocicletas/i)).toBeInTheDocument();
    });
    const link = screen.getByText(/Registro de Motocicletas/i).closest('a');
    expect(link).toHaveAttribute('href', '/distribuidor/entrega');
  });

  it('hides the entry link for every other role (jefe_taller)', async () => {
    setUser('jefe_taller');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Gestión de Órdenes/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Registro de Motocicletas/i)).not.toBeInTheDocument();
  });
});
