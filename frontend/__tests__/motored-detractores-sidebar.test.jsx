import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/maestros',
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

beforeEach(() => pushMock.mockClear());

describe('MotoredSidebar — Detractores entry', () => {
  it.each(['ADMIN', 'SERVICIO_CLIENTE'])('shows Detractores to %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.getByText('Detractores')).toBeInTheDocument();
  });

  it.each(['COMPRAS', 'SUCURSAL', 'CONSULTA'])('hides Detractores from %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.queryByText('Detractores')).not.toBeInTheDocument();
  });

  it('places Detractores right after Encuesta satisfacción and navigates on click', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'ADMIN' }} />);
    const labels = screen.getAllByRole('button').map((b) => b.textContent);
    const i = labels.indexOf('Encuesta satisfacción');
    expect(labels[i + 1]).toBe('Detractores');
    fireEvent.click(screen.getByText('Detractores'));
    expect(pushMock).toHaveBeenCalledWith('/motored/detractores');
  });
});
