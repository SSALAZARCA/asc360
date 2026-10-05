/**
 * "Configuración" is a collapsible group in the Motored sidebar holding the
 * settings screen, user management and the login log (it replaced the former
 * "Usuarios" group), so the main menu stays short.
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

describe('MotoredSidebar — Configuración submenu (users)', () => {
  it('starts collapsed outside its pages and expands on click', () => {
    render(<MotoredSidebar user={ADMIN} />);
    const group = screen.getByRole('button', { name: 'Configuración' });
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
    fireEvent.click(screen.getByRole('button', { name: 'Configuración' }));
    fireEvent.click(screen.getByText('Gestión de usuarios'));
    expect(pushMock).toHaveBeenCalledWith('/motored/usuarios');
    fireEvent.click(screen.getByText('Registro de ingresos'));
    expect(pushMock).toHaveBeenCalledWith('/motored/ingresos');
  });

  it.each(['/motored/usuarios', '/motored/ingresos'])('starts collapsed even on %s, marked as current', (path) => {
    mockPathname = path;
    render(<MotoredSidebar user={ADMIN} />);
    const group = screen.getByRole('button', { name: 'Configuración' });
    expect(group).toHaveAttribute('aria-expanded', 'false');
    expect(group).toHaveAttribute('aria-current', 'true');
    expect(screen.queryByText('Registro de ingresos')).toBeNull();
  });

  it.each(['/motored/usuarios', '/motored/ingresos'])('can be collapsed and reopened on %s', (path) => {
    mockPathname = path;
    render(<MotoredSidebar user={ADMIN} />);
    const group = screen.getByRole('button', { name: 'Configuración' });
    fireEvent.click(group);
    expect(group).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Registro de ingresos')).toBeInTheDocument();
    fireEvent.click(group);
    expect(group).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Registro de ingresos')).toBeNull();
  });

  it('collapses again after being opened elsewhere', () => {
    render(<MotoredSidebar user={ADMIN} />);
    const group = screen.getByRole('button', { name: 'Configuración' });
    fireEvent.click(group);
    fireEvent.click(group);
    expect(group).toHaveAttribute('aria-expanded', 'false');
  });

  it('stays collapsed when navigating into one of its pages', () => {
    const { rerender } = render(<MotoredSidebar user={ADMIN} />);
    mockPathname = '/motored/ingresos';
    rerender(<MotoredSidebar user={ADMIN} />);
    expect(screen.getByRole('button', { name: 'Configuración' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('keeps Registro de ingresos out of the top level', () => {
    render(<MotoredSidebar user={ADMIN} />);
    const labels = screen.getAllByRole('button').map((b) => b.textContent);
    expect(labels).not.toContain('Registro de ingresos');
    expect(labels).toContain('Configuración');
  });

  it.each(['COMPRAS', 'SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE'])('is hidden from %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.queryByRole('button', { name: 'Configuración' })).toBeNull();
    expect(screen.queryByText('Registro de ingresos')).toBeNull();
  });
});
