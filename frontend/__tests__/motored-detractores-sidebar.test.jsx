import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/maestros',
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

beforeEach(() => pushMock.mockClear());

const GROUP = 'Encuestas satisfacción';
const ENTRY = 'Gestión de detractores';

describe('MotoredSidebar — Gestión de detractores entry', () => {
  it.each(['ADMIN', 'SERVICIO_CLIENTE'])('shows Gestión de detractores to %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    fireEvent.click(screen.getByRole('button', { name: GROUP }));
    expect(screen.getByText(ENTRY)).toBeInTheDocument();
  });

  it.each(['COMPRAS', 'SUCURSAL', 'CONSULTA', 'GERENCIA'])('hides Gestión de detractores from %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.queryByText(GROUP)).not.toBeInTheDocument();
    expect(screen.queryByText(ENTRY)).not.toBeInTheDocument();
  });

  it('places Gestión de detractores right after Cargue de encuestas and navigates on click', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'ADMIN' }} />);
    fireEvent.click(screen.getByRole('button', { name: GROUP }));
    const labels = screen.getAllByRole('button').map((b) => b.textContent);
    const i = labels.indexOf('Cargue de encuestas');
    expect(labels[i + 1]).toBe(ENTRY);
    fireEvent.click(screen.getByText(ENTRY));
    expect(pushMock).toHaveBeenCalledWith('/motored/detractores');
  });
});
