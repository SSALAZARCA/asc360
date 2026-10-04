/**
 * /motored/configuracion: ADMIN-only page with the seven section tabs.
 * Every section but Topes renders its own notice (Topes links to its own screen).
 */
import React from 'react';
import { render, screen, renderHook, waitFor, fireEvent } from '@testing-library/react';
import { installFetch, jsonRes, coded, setSession } from './helpers/pedidosFetch';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/configuracion',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import useConfiguracionGate, { CONFIGURACION_ROLES } from '../components/motored/configuracion/useConfiguracionGate';
import ConfiguracionPage from '../app/motored/configuracion/page';

const SECCIONES = ['pedido', 'avisos', 'cargas', 'limpieza', 'indicadores', 'comisiones', 'topes']
  .map((seccion) => ({ seccion, grupos: [] }));
const CONFIG = { secciones: SECCIONES };
const ETIQUETAS = ['Pedido', 'Avisos', 'Cargas', 'Limpieza', 'Indicadores', 'Comisiones', 'Topes'];

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('useConfiguracionGate', () => {
  it('is ADMIN only', () => {
    expect(CONFIGURACION_ROLES).toEqual(['ADMIN']);
  });

  it('lets an ADMIN in', async () => {
    setSession('ADMIN');
    const { result } = renderHook(() => useConfiguracionGate());
    await waitFor(() => expect(result.current).toBe(true));
    expect(pushMock).not.toHaveBeenCalled();
  });

  it.each(['COMPRAS', 'SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE'])('sends %s to Maestros', async (role) => {
    setSession(role);
    const { result } = renderHook(() => useConfiguracionGate());
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(result.current).toBe(false);
  });

  it('sends a visitor without a session to Maestros', async () => {
    renderHook(() => useConfiguracionGate());
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
  });
});

describe('ConfiguracionPage', () => {
  it('does not load anything for a non-ADMIN', async () => {
    setSession('COMPRAS');
    const calls = installFetch({ 'GET /parametros/configuracion': jsonRes(CONFIG) });
    render(<ConfiguracionPage />);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(calls).toHaveLength(0);
    expect(screen.queryByRole('heading', { name: 'Configuración' })).not.toBeInTheDocument();
  });

  it('shows the seven tabs in order with Pedido selected', async () => {
    setSession('ADMIN');
    installFetch({ 'GET /parametros/configuracion': jsonRes(CONFIG) });
    render(<ConfiguracionPage />);
    expect(await screen.findByRole('heading', { name: 'Configuración' })).toBeInTheDocument();
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(ETIQUETAS);
    expect(screen.getByRole('tab', { name: 'Pedido' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText(/Los cambios aplican a los pedidos nuevos/)).toBeInTheDocument();
  });

  it('asks the API for the configuration once', async () => {
    setSession('ADMIN');
    const calls = installFetch({ 'GET /parametros/configuracion': jsonRes(CONFIG) });
    render(<ConfiguracionPage />);
    await screen.findByRole('tab', { name: 'Pedido' });
    await waitFor(() => expect(calls.filter((c) => c.path === '/parametros/configuracion')).toHaveLength(1));
  });

  it('switches tabs', async () => {
    setSession('ADMIN');
    installFetch({ 'GET /parametros/configuracion': jsonRes(CONFIG) });
    render(<ConfiguracionPage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Avisos' }));
    expect(screen.getByRole('tab', { name: 'Avisos' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Pedido' })).toHaveAttribute('aria-selected', 'false');
  });

  it('Topes links to the budget caps screen', async () => {
    setSession('ADMIN');
    installFetch({ 'GET /parametros/configuracion': jsonRes(CONFIG) });
    render(<ConfiguracionPage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Topes' }));
    fireEvent.click(screen.getByRole('button', { name: /Ir a Topes por tienda/ }));
    expect(pushMock).toHaveBeenCalledWith('/motored/pedidos/topes');
  });

  it('shows the server message when the configuration cannot be loaded', async () => {
    setSession('ADMIN');
    installFetch({ 'GET /parametros/configuracion': coded(500, 'E-X', 'Falló la lectura') });
    render(<ConfiguracionPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Falló la lectura');
  });
});
