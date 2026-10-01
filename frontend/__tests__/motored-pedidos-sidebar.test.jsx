/**
 * Motored Fase 4 (sdd/motored-pedidos-ui, F1): the "Pedidos" sidebar entry is
 * for ADMIN and COMPRAS only (decision F4-16) and sits first in the menu.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/maestros',
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

beforeEach(() => pushMock.mockClear());

describe('MotoredSidebar - Pedidos entry', () => {
  it.each(['ADMIN', 'COMPRAS'])('shows Pedidos to %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.getByRole('button', { name: 'Pedidos' })).toBeInTheDocument();
  });

  it.each(['CONSULTA', 'SUCURSAL', 'SERVICIO_CLIENTE'])('hides Pedidos from %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.queryByRole('button', { name: 'Pedidos' })).not.toBeInTheDocument();
  });

  it('hides Pedidos while a password change is pending', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'COMPRAS', must_change_password: true }} />);
    expect(screen.queryByRole('button', { name: 'Pedidos' })).not.toBeInTheDocument();
  });

  it('is the first menu entry and navigates to /motored/pedidos', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'COMPRAS' }} />);
    const labels = screen.getAllByRole('button').map((b) => b.textContent);
    expect(labels[0]).toBe('Pedidos');
    fireEvent.click(screen.getByRole('button', { name: 'Pedidos' }));
    expect(pushMock).toHaveBeenCalledWith('/motored/pedidos');
  });

  it('keeps Maestros right after Tablero asesores (which follows Pedidos) for COMPRAS', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'COMPRAS' }} />);
    const labels = screen.getAllByRole('button').map((b) => b.textContent);
    expect(labels.slice(0, 3)).toEqual(['Pedidos', 'Tablero asesores', 'Maestros']);
  });
});
