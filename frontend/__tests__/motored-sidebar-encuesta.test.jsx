import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/maestros',
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

beforeEach(() => pushMock.mockClear());

describe('MotoredSidebar — Encuesta satisfacción entry', () => {
  it('shows only the survey entry to SERVICIO_CLIENTE', () => {
    render(<MotoredSidebar user={{ nombre: 'Sc', role: 'SERVICIO_CLIENTE' }} />);

    expect(screen.getByText('Encuesta satisfacción')).toBeInTheDocument();
    expect(screen.queryByText('Maestros')).not.toBeInTheDocument();
    expect(screen.queryByText('Usuarios')).not.toBeInTheDocument();
    expect(screen.queryByText('Ventas perdidas')).not.toBeInTheDocument();
  });

  it('shows the survey entry together with the existing ones to ADMIN', () => {
    render(<MotoredSidebar user={{ nombre: 'Ad', role: 'ADMIN' }} />);

    ['Encuesta satisfacción', 'Maestros', 'Usuarios', 'Ventas perdidas'].forEach((t) =>
      expect(screen.getByText(t)).toBeInTheDocument()
    );
  });

  it.each(['COMPRAS', 'SUCURSAL', 'CONSULTA'])('hides the survey entry from %s but keeps Maestros', (role) => {
    render(<MotoredSidebar user={{ nombre: 'X', role }} />);

    expect(screen.queryByText('Encuesta satisfacción')).not.toBeInTheDocument();
    expect(screen.getByText('Maestros')).toBeInTheDocument();
  });

  it('navigates to the survey admin page on click', () => {
    render(<MotoredSidebar user={{ nombre: 'Ad', role: 'ADMIN' }} />);
    fireEvent.click(screen.getByText('Encuesta satisfacción'));
    expect(pushMock).toHaveBeenCalledWith('/motored/encuesta-satisfaccion');
  });
});
