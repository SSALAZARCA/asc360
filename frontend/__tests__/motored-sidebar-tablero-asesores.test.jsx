/**
 * "KPI's" sidebar entry (route /motored/tablero-asesores):
 * ADMIN, COMPRAS and GERENCIA, placed first in the menu.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/maestros',
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

describe('MotoredSidebar - KPIs', () => {
  it.each(['ADMIN', 'COMPRAS', 'GERENCIA'])('lo muestra a %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.getByText("KPI's")).toBeInTheDocument();
  });

  it.each(['SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE'])('lo oculta a %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.queryByText("KPI's")).not.toBeInTheDocument();
  });

  it('is the first entry, right before the Pedidos group', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'ADMIN' }} />);
    const nombres = screen.getAllByRole('button').map((b) => b.textContent);
    expect(nombres.slice(0, 2)).toEqual(["KPI's", 'Pedidos']);
  });
});
