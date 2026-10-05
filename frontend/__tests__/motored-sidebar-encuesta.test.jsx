import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/maestros',
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

const GROUP = 'Encuestas satisfacción';
const openGroup = (name) => fireEvent.click(screen.getByRole('button', { name }));

beforeEach(() => pushMock.mockClear());

describe('MotoredSidebar — Encuestas satisfacción group', () => {
  it('shows only the survey group and the account page to SERVICIO_CLIENTE', () => {
    render(<MotoredSidebar user={{ nombre: 'Sc', role: 'SERVICIO_CLIENTE' }} />);
    openGroup(GROUP);

    expect(screen.getByText('Cargue de encuestas')).toBeInTheDocument();
    expect(screen.getByText('Gestión de detractores')).toBeInTheDocument();
    ['Pedidos', 'Maestros', 'Configuración', 'Ventas perdidas'].forEach((t) =>
      expect(screen.queryByText(t)).not.toBeInTheDocument()
    );
  });

  it('shows the survey group together with the existing ones to ADMIN', () => {
    render(<MotoredSidebar user={{ nombre: 'Ad', role: 'ADMIN' }} />);
    [GROUP, 'Pedidos', 'Configuración'].forEach(openGroup);

    ['Cargue de encuestas', 'Gestión de detractores', 'Maestros', 'Gestión de usuarios', 'Ventas perdidas'].forEach((t) =>
      expect(screen.getByText(t)).toBeInTheDocument()
    );
  });

  it.each(['COMPRAS', 'SUCURSAL', 'CONSULTA', 'GERENCIA'])('hides the survey group from %s but keeps Maestros', (role) => {
    render(<MotoredSidebar user={{ nombre: 'X', role }} />);

    expect(screen.queryByText(GROUP)).not.toBeInTheDocument();
    openGroup('Pedidos');
    expect(screen.getByText('Maestros')).toBeInTheDocument();
  });

  it('navigates to the survey admin page and the detractors page', () => {
    render(<MotoredSidebar user={{ nombre: 'Ad', role: 'ADMIN' }} />);
    openGroup(GROUP);
    fireEvent.click(screen.getByText('Cargue de encuestas'));
    expect(pushMock).toHaveBeenCalledWith('/motored/encuesta-satisfaccion');
    fireEvent.click(screen.getByText('Gestión de detractores'));
    expect(pushMock).toHaveBeenCalledWith('/motored/detractores');
  });
});
