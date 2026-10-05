/**
 * Tests for the "Ventas Perdidas" sidebar entry, introduced in:
 *   sdd/motored-ventas-perdidas-panel, Phase 8 (S8), task 8.1
 *
 * Same `adminOnly: true` gate as "Gestión de usuarios" (`MotoredSidebar.js`'s
 * `ALL_ITEMS`): visible for role === 'ADMIN', hidden for any other role. The
 * entry lives inside the collapsible "Pedidos" group.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/maestros',
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

const openPedidos = () => fireEvent.click(screen.getByRole('button', { name: 'Pedidos' }));

describe('MotoredSidebar — Ventas perdidas entry', () => {
  it('renders "Ventas perdidas" for an ADMIN user', () => {
    render(<MotoredSidebar user={{ nombre: 'Admin', role: 'ADMIN' }} />);
    openPedidos();

    expect(screen.getByText('Ventas perdidas')).toBeInTheDocument();
  });

  it('hides "Ventas perdidas" for a non-ADMIN user', () => {
    render(<MotoredSidebar user={{ nombre: 'Asesor', role: 'ASESOR_MOSTRADOR' }} />);
    openPedidos();

    expect(screen.queryByText('Ventas perdidas')).not.toBeInTheDocument();
  });

  it('hides "Ventas perdidas" when there is no user at all', () => {
    render(<MotoredSidebar user={null} />);

    expect(screen.queryByText('Ventas perdidas')).not.toBeInTheDocument();
  });

  it('still shows "Maestros" (non-admin item) for a non-ADMIN user', () => {
    render(<MotoredSidebar user={{ nombre: 'Asesor', role: 'ASESOR_MOSTRADOR' }} />);
    openPedidos();

    expect(screen.getByText('Maestros')).toBeInTheDocument();
  });
});
