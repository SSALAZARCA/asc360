import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/maestros',
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

describe('MotoredSidebar — Cambiar mi contraseña', () => {
  it.each(['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE'])('is visible to %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.getByText('Cambiar mi contraseña')).toBeInTheDocument();
  });

  it('navigates to the account page', () => {
    pushMock.mockClear();
    render(<MotoredSidebar user={{ nombre: 'U', role: 'COMPRAS' }} />);
    fireEvent.click(screen.getByText('Cambiar mi contraseña'));
    expect(pushMock).toHaveBeenCalledWith('/motored/mi-cuenta');
  });
});
