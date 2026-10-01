/** Motored Fase 4 (F1): launching a corrida from /motored/pedidos (UX-03, UX-07). */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, pagina, setSession, SUCURSALES, C_CALCULADA,
} from './helpers/pedidosFetch';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/pedidos',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import PedidosPage from '../app/motored/pedidos/page';

const CREADA = { id: 'n1', codigo: 'PED-2026-S41-001', estado: 'PENDIENTE', es_escenario: false };

function rutas(over = {}) {
  return {
    'GET /corridas': jsonRes(pagina([C_CALCULADA])),
    'GET /maestros/sucursales': jsonRes(SUCURSALES),
    'POST /corridas': jsonRes(CREADA, 202),
    ...over,
  };
}

const posts = (calls) => calls.filter((c) => c.method === 'POST' && c.path === '/corridas');

async function abrirFormulario() {
  render(<PedidosPage />);
  await screen.findByText('PED-2026-S40-001');
  return screen.getByRole('form', { name: 'Nueva corrida' });
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
});

describe('Lanzar corrida', () => {
  it('keeps the button disabled until a fecha de corte is chosen', async () => {
    installFetch(rutas());
    const form = await abrirFormulario();
    const boton = within(form).getByRole('button', { name: 'Calcular corrida' });
    expect(boton).toBeDisabled();
    fireEvent.change(within(form).getByLabelText('Fecha de corte'), { target: { value: '2026-10-08' } });
    expect(boton).toBeEnabled();
  });

  it('launches for every tienda and reloads the list', async () => {
    const calls = installFetch(rutas());
    const form = await abrirFormulario();
    fireEvent.change(within(form).getByLabelText('Fecha de corte'), { target: { value: '2026-10-08' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Calcular corrida' }));
    expect(await screen.findByText(/PED-2026-S41-001/)).toBeInTheDocument();
    expect(posts(calls)[0].body).toEqual({ fecha_corte: '2026-10-08' });
    const listas = calls.filter((c) => c.path === '/corridas' && c.method === 'GET');
    expect(listas.length).toBeGreaterThanOrEqual(2);
  });

  it('sends the nota trimmed and only when it is not blank', async () => {
    const calls = installFetch(rutas());
    const form = await abrirFormulario();
    fireEvent.change(within(form).getByLabelText('Fecha de corte'), { target: { value: '2026-10-08' } });
    fireEvent.change(within(form).getByLabelText('Nota (opcional)'), { target: { value: '  Pedido de octubre ' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Calcular corrida' }));
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    expect(posts(calls)[0].body).toEqual({ fecha_corte: '2026-10-08', nota: 'Pedido de octubre' });
  });

  it('lets the user pick tiendas, listing only the active ones', async () => {
    const calls = installFetch(rutas());
    const form = await abrirFormulario();
    fireEvent.change(within(form).getByLabelText('Fecha de corte'), { target: { value: '2026-10-08' } });
    fireEvent.click(within(form).getByLabelText('Selección de tiendas'));
    expect(await within(form).findByLabelText('Manizales')).toBeInTheDocument();
    expect(within(form).getByLabelText('Pereira')).toBeInTheDocument();
    expect(within(form).queryByLabelText('Cerrada vieja')).not.toBeInTheDocument();
    const boton = within(form).getByRole('button', { name: 'Calcular corrida' });
    expect(boton).toBeDisabled();
    fireEvent.click(within(form).getByLabelText('Pereira'));
    expect(boton).toBeEnabled();
    fireEvent.click(boton);
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    expect(posts(calls)[0].body).toEqual({ fecha_corte: '2026-10-08', sucursal_ids: ['s2'] });
  });

  it('shows the coded 422 in Spanish and keeps what the user typed', async () => {
    installFetch(rutas({
      'POST /corridas': coded(422, 'E-CORRIDA-021', 'Los datos de VENTAS tienen 45 días y el máximo permitido es 40.'),
    }));
    const form = await abrirFormulario();
    fireEvent.change(within(form).getByLabelText('Fecha de corte'), { target: { value: '2026-10-08' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Calcular corrida' }));
    expect(await within(form).findByRole('alert'))
      .toHaveTextContent('Los datos de VENTAS tienen 45 días y el máximo permitido es 40. (E-CORRIDA-021)');
    expect(within(form).getByLabelText('Fecha de corte')).toHaveValue('2026-10-08');
    expect(within(form).getByRole('button', { name: 'Calcular corrida' })).toBeEnabled();
  });

  it('shows an error when the tiendas cannot be loaded', async () => {
    installFetch(rutas({ 'GET /maestros/sucursales': jsonRes({ detail: 'Sin conexión' }, 500) }));
    const form = await abrirFormulario();
    fireEvent.click(within(form).getByLabelText('Selección de tiendas'));
    expect(await within(form).findByRole('alert')).toHaveTextContent('Sin conexión');
  });
});
