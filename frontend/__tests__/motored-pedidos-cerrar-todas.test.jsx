/**
 * Motored Fase 4 (F3): closing several pedidos at once (CI-06, CI-07, UX-11):
 * "Cerrar todas las listas" and "Cerrar seleccionadas", both all or nothing.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE, D_PRUEBA, T_BORRADOR, T_CERRADO, T_ENVIADO, otraTienda,
} from './helpers/pedidosFetch';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useParams: () => ({ id: 'c1' }),
  usePathname: () => '/motored/pedidos/c1',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import CorridaDetallePage from '../app/motored/pedidos/[id]/page';

const BOGOTA = otraTienda(T_BORRADOR, 's6', 'Bogotá', 6);
const CUCUTA = otraTienda(T_BORRADOR, 's7', 'Cúcuta', 7);
const TRES_BORRADORES = {
  ...D_DETALLE,
  sucursales: [T_BORRADOR, BOGOTA, CUCUTA, T_CERRADO, T_ENVIADO],
};

const rutas = (over = {}) => ({
  'GET /corridas/c1': jsonRes(TRES_BORRADORES),
  'POST /corridas/c1/cerrar': jsonRes({ id: 'c1', codigo: 'PED-2026-S40-001', estado: 'BORRADOR', cerradas: ['s1', 's6', 's7'], ya_cerradas: 2 }),
  ...over,
});
const posts = (calls) => calls.filter((c) => c.method === 'POST');
const fila = async (nombre) => (await screen.findByText(nombre)).closest('tr');
const marcar = async (nombre) => fireEvent.click(within(await fila(nombre)).getByRole('checkbox'));

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
});

describe('Cerrar todas las listas', () => {
  it('confirms with the number of drafts and how many were already closed or sent', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar todas las listas' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Cerrar los pedidos en Borrador' });
    expect(dialogo).toHaveTextContent('Se cerrarán 3 pedidos en Borrador.');
    expect(dialogo).toHaveTextContent('2 pedidos ya estaban cerrados o enviados.');
    expect(dialogo).toHaveTextContent('todo o nada');
  });

  it('uses the singular when there is a single draft', async () => {
    installFetch(rutas({ 'GET /corridas/c1': jsonRes(D_DETALLE) }));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar todas las listas' }));
    const dialogo = await screen.findByRole('dialog');
    expect(dialogo).toHaveTextContent('Se cerrará 1 pedido en Borrador.');
  });

  it('posts the batch close with no body, reloads and reports what was closed', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar todas las listas' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar pedidos' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(posts(calls)).toHaveLength(1);
    expect(posts(calls)[0]).toMatchObject({ path: '/corridas/c1/cerrar', body: null });
    expect(await screen.findByRole('status')).toHaveTextContent('Se cerraron 3 pedidos.');
    await waitFor(() => expect(calls.filter((c) => c.method === 'GET' && c.path === '/corridas/c1')).toHaveLength(2));
  });

  it('shows the tienda that blocks the all-or-nothing close and changes nothing (CI-07)', async () => {
    const calls = installFetch(rutas({
      'POST /corridas/c1/cerrar': coded(409, 'E-CORRIDA-064', 'No se puede cerrar: el pedido de Bogotá no está en Borrador.'),
    }));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar todas las listas' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar pedidos' }));
    expect(await within(dialogo).findByRole('alert'))
      .toHaveTextContent('No se puede cerrar: el pedido de Bogotá no está en Borrador. (E-CORRIDA-064)');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(calls.filter((c) => c.method === 'GET' && c.path === '/corridas/c1')).toHaveLength(1);
  });

  it('is not offered when no pedido is in draft', async () => {
    installFetch(rutas({ 'GET /corridas/c1': jsonRes({ ...D_DETALLE, sucursales: [T_CERRADO, T_ENVIADO] }) }));
    render(<CorridaDetallePage />);
    await screen.findByText('Pereira');
    expect(screen.queryByRole('button', { name: 'Cerrar todas las listas' })).not.toBeInTheDocument();
  });

  it('is not offered on a scenario corrida', async () => {
    installFetch(rutas({ 'GET /corridas/c1': jsonRes(D_PRUEBA) }));
    render(<CorridaDetallePage />);
    await screen.findByText('PRUEBA');
    expect(screen.queryByRole('button', { name: 'Cerrar todas las listas' })).not.toBeInTheDocument();
  });
});

describe('Cerrar seleccionadas', () => {
  it('names the selected tiendas in the request, in table order', async () => {
    const calls = installFetch(rutas({
      'POST /corridas/c1/cerrar': jsonRes({ id: 'c1', codigo: 'PED-2026-S40-001', estado: 'BORRADOR', cerradas: ['s1', 's7'], ya_cerradas: 0 }),
    }));
    render(<CorridaDetallePage />);
    await marcar('Cúcuta');
    await marcar('Manizales');
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar seleccionadas (2)' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Cerrar los pedidos seleccionados' });
    expect(dialogo).toHaveTextContent('Se cerrarán 2 pedidos');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar pedidos' }));
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    expect(posts(calls)[0].body).toEqual({ sucursal_ids: ['s1', 's7'] });
    expect(await screen.findByRole('status')).toHaveTextContent('Se cerraron 2 pedidos.');
  });

  it('is absent until something is selected and clears the selection after closing', async () => {
    const calls = installFetch(rutas({
      'POST /corridas/c1/sucursales/s1/cerrar': jsonRes({ corrida_id: 'c1', sucursal_id: 's1', estado_pedido: 'CERRADO' }),
    }));
    render(<CorridaDetallePage />);
    await screen.findByText('Manizales');
    expect(screen.queryByRole('button', { name: /Cerrar seleccionadas/ })).not.toBeInTheDocument();
    await marcar('Manizales');
    expect(screen.getByRole('button', { name: 'Cerrar seleccionadas (1)' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar seleccionadas (1)' }));
    // A single tienda gets the single-tienda confirmation (with its pack warning) and endpoint.
    const dialogo = await screen.findByRole('dialog', { name: 'Cerrar el pedido de Manizales' });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar pedido' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(posts(calls).map((c) => c.path)).toEqual(['/corridas/c1/sucursales/s1/cerrar']);
    expect(screen.queryByRole('button', { name: /Cerrar seleccionadas/ })).not.toBeInTheDocument();
  });

  it('is disabled while the selection mixes a draft with a tienda that cannot be closed', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await marcar('Manizales');
    await marcar('Pereira');
    expect(screen.getByRole('button', { name: 'Cerrar seleccionadas (2)' })).toBeDisabled();
  });

  it('gives no checkbox to a tienda with nothing to do (sent) nor to read-only rows', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    expect(within(await fila('Manizales')).getByRole('checkbox', { name: 'Seleccionar Manizales' })).toBeInTheDocument();
    expect(within(await fila('Cali')).queryByRole('checkbox')).not.toBeInTheDocument();
  });
});
