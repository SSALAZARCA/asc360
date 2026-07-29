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
 * The regression this test locks down (per spec "Existing parts_dealer
 * Access Unchanged"): for `parts_dealer` the visible id set is EXACTLY
 * {kanban, services, vehicle-delivery} — Kanban and Gestión de Órdenes
 * byte-for-byte unchanged.
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

  it('the visible id set for parts_dealer is EXACTLY kanban + services + vehicle-delivery', async () => {
    setUser('parts_dealer');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Registro de Motocicletas/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Tablero Operativo/i)).toBeInTheDocument();
    expect(screen.getByText(/Gestión de Órdenes/i)).toBeInTheDocument();
    // Every adminOnly/importsOnly entry MUST stay hidden — unchanged.
    expect(screen.queryByText(/Centro de Comando/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Estado Pedidos/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Red de Tiendas/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Personal & Acceso/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Maestro de Partes/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Datos Rápidos/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Orden Histórica/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Configuración/i)).not.toBeInTheDocument();
  });

  it('shows the entry link for a superadmin user', async () => {
    setUser('superadmin');
    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText(/Registro de Motocicletas/i)).toBeInTheDocument();
    });
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
