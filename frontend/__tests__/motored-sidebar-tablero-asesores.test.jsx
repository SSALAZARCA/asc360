/**
 * "Tablero asesores" sidebar entry (feature motored-tablero-asesores, T4):
 * ADMIN and COMPRAS only, placed right after "Pedidos".
 */
import React from 'react';
import { render, screen } from '@testing-library/react';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/maestros',
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

describe('MotoredSidebar - Tablero asesores', () => {
  it.each(['ADMIN', 'COMPRAS'])('lo muestra a %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.getByText('Tablero asesores')).toBeInTheDocument();
  });

  it.each(['SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE'])('lo oculta a %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.queryByText('Tablero asesores')).not.toBeInTheDocument();
  });

  it('va justo después de Pedidos', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'ADMIN' }} />);
    const nombres = screen.getAllByRole('button').map((b) => b.textContent);
    expect(nombres.indexOf('Tablero asesores')).toBe(nombres.indexOf('Pedidos') + 1);
  });
});
