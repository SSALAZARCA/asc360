/**
 * Motored Fase 4 (sdd/motored-pedidos-ui, F1): the "Registro de pedidos"
 * sidebar entry (inside the "Pedidos" group) is for ADMIN and COMPRAS only
 * (decision F4-16); "Configuración parámetros" (inside "Configuración") is
 * for ADMIN only.
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

const openGroup = (name) => fireEvent.click(screen.getByRole('button', { name }));
const PEDIDOS = 'Registro de pedidos';
const CONFIG = 'Configuración parámetros';

describe('MotoredSidebar - Registro de pedidos entry', () => {
  it.each(['ADMIN', 'COMPRAS'])('shows Registro de pedidos to %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    openGroup('Pedidos');
    expect(screen.getByRole('button', { name: PEDIDOS })).toBeInTheDocument();
  });

  it.each(['CONSULTA', 'SUCURSAL', 'GERENCIA'])('hides Registro de pedidos from %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    openGroup('Pedidos');
    expect(screen.queryByRole('button', { name: PEDIDOS })).not.toBeInTheDocument();
  });

  it('hides the whole Pedidos group from SERVICIO_CLIENTE', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'SERVICIO_CLIENTE' }} />);
    expect(screen.queryByRole('button', { name: 'Pedidos' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: PEDIDOS })).not.toBeInTheDocument();
  });

  it('hides Pedidos while a password change is pending', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'COMPRAS', must_change_password: true }} />);
    expect(screen.queryByRole('button', { name: 'Pedidos' })).not.toBeInTheDocument();
  });

  it('is the first entry of the Pedidos group and navigates to /motored/pedidos', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'COMPRAS' }} />);
    openGroup('Pedidos');
    const labels = screen.getAllByRole('button').map((b) => b.textContent);
    expect(labels.slice(0, 4)).toEqual(["KPI's", 'Pedidos', PEDIDOS, 'Maestros']);
    fireEvent.click(screen.getByRole('button', { name: PEDIDOS }));
    expect(pushMock).toHaveBeenCalledWith('/motored/pedidos');
  });
});

describe('MotoredSidebar - Configuración parámetros entry', () => {
  it('is shown to ADMIN only', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'ADMIN' }} />);
    openGroup('Configuración');
    expect(screen.getByRole('button', { name: CONFIG })).toBeInTheDocument();
  });

  it.each(['COMPRAS', 'CONSULTA', 'SUCURSAL', 'SERVICIO_CLIENTE', 'GERENCIA'])('is hidden from %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.queryByRole('button', { name: 'Configuración' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: CONFIG })).not.toBeInTheDocument();
  });

  it('is hidden while a password change is pending', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'ADMIN', must_change_password: true }} />);
    expect(screen.queryByRole('button', { name: 'Configuración' })).not.toBeInTheDocument();
  });

  it('opens first in the Configuración group and navigates to /motored/configuracion', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'ADMIN' }} />);
    openGroup('Configuración');
    const etiquetas = screen.getAllByRole('button').map((b) => b.textContent);
    expect(etiquetas[etiquetas.indexOf('Configuración') + 1]).toBe(CONFIG);
    fireEvent.click(screen.getByRole('button', { name: CONFIG }));
    expect(pushMock).toHaveBeenCalledWith('/motored/configuracion');
  });
});
