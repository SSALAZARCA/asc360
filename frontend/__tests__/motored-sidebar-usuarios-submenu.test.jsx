/**
 * "Usuarios" is a collapsible group in the Motored sidebar holding the user
 * management screen and the login log, so the main menu stays short.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/motored/maestros';
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

const ADMIN = { nombre: 'U', role: 'ADMIN' };

beforeEach(() => {
  pushMock.mockClear();
  mockPathname = '/motored/maestros';
});

describe('MotoredSidebar — Usuarios submenu', () => {
  it('starts collapsed outside its pages and expands on click', () => {
    render(<MotoredSidebar user={ADMIN} />);
    const group = screen.getByRole('button', { name: 'Usuarios' });
    expect(group).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Registro de ingresos')).toBeNull();

    fireEvent.click(group);
    expect(group).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Gestión de usuarios')).toBeInTheDocument();
    expect(screen.getByText('Registro de ingresos')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('navigates from each child entry', () => {
    render(<MotoredSidebar user={ADMIN} />);
    fireEvent.click(screen.getByRole('button', { name: 'Usuarios' }));
    fireEvent.click(screen.getByText('Gestión de usuarios'));
    expect(pushMock).toHaveBeenCalledWith('/motored/usuarios');
    fireEvent.click(screen.getByText('Registro de ingresos'));
    expect(pushMock).toHaveBeenCalledWith('/motored/ingresos');
  });

  it.each(['/motored/usuarios', '/motored/ingresos'])('is open on %s', (path) => {
    mockPathname = path;
    render(<MotoredSidebar user={ADMIN} />);
    expect(screen.getByRole('button', { name: 'Usuarios' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Registro de ingresos')).toBeInTheDocument();
  });

  it('keeps Registro de ingresos out of the top level', () => {
    render(<MotoredSidebar user={ADMIN} />);
    const labels = screen.getAllByRole('button').map((b) => b.textContent);
    expect(labels).not.toContain('Registro de ingresos');
    expect(labels).toContain('Usuarios');
  });

  it.each(['COMPRAS', 'SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE'])('is hidden from %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.queryByRole('button', { name: 'Usuarios' })).toBeNull();
    expect(screen.queryByText('Registro de ingresos')).toBeNull();
  });
});
