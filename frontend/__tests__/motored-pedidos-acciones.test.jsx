/**
 * Motored Fase 4 (F3): which lifecycle controls each screen renders (UX-08,
 * UX-10, UX-12, SC-05) and "Recalcular fallidas" (F4-6, CI-12, CI-13).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE, D_PRUEBA, T_BORRADOR, T_CERRADO, T_FALLIDA,
  CAB_BORRADOR, CAB_CERRADO, CAB_ENVIADO, CAB_FALLIDA, CAB_PRUEBA,
} from './helpers/pedidosFetch';

const pushMock = jest.fn();
let params = { id: 'c1' };
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useParams: () => params,
  usePathname: () => '/motored/pedidos/c1',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

// The default send date is today in Bogota: pin it so the tests do not depend on the clock.
jest.mock('../components/motored/pedidos/acciones', () => ({
  ...jest.requireActual('../components/motored/pedidos/acciones'),
  hoyBogota: () => '2026-10-05',
}));

import CorridaDetallePage from '../app/motored/pedidos/[id]/page';
import PedidoTiendaPage from '../app/motored/pedidos/[id]/[sucursalId]/page';

const CICLO = ['Cerrar', 'Reabrir', 'Exportar', 'Marcar como enviado', 'Corregir número'];
const fila = async (nombre) => (await screen.findByText(nombre)).closest('tr');
const accionesDe = (contenedor) => CICLO.filter((nombre) => within(contenedor).queryByRole('button', { name: new RegExp(`^${nombre}`) }));

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
  params = { id: 'c1' };
});

describe('acciones por fila de la corrida (UX-08, UX-10)', () => {
  beforeEach(() => installFetch({ 'GET /corridas/c1': jsonRes(D_DETALLE) }));

  it.each([
    ['Manizales', 'Borrador', ['Cerrar']],
    ['Pereira', 'Cerrado', ['Reabrir', 'Exportar', 'Marcar como enviado']],
    ['Cali', 'Enviado', ['Exportar', 'Corregir número']],
    ['Armenia', 'Fallida', []],
    ['Ibagué', 'Omitida', []],
  ])('%s (%s) shows exactly %p', async (nombre, _estado, esperadas) => {
    render(<CorridaDetallePage />);
    expect(accionesDe(await fila(nombre))).toEqual(esperadas);
  });

  it('keeps Ver pedido on every tienda that has a pedido', async () => {
    render(<CorridaDetallePage />);
    expect(within(await fila('Pereira')).getByRole('button', { name: 'Ver pedido' })).toBeInTheDocument();
    expect(within(await fila('Armenia')).queryByRole('button', { name: 'Ver pedido' })).not.toBeInTheDocument();
  });

  it('gives each row action a 44 px touch target', async () => {
    render(<CorridaDetallePage />);
    const boton = within(await fila('Pereira')).getByRole('button', { name: 'Reabrir' });
    expect(boton.style.minHeight).toBe('44px');
  });

  it('draws no checkbox on FALLIDA or OMITIDA rows', async () => {
    render(<CorridaDetallePage />);
    expect(within(await fila('Armenia')).queryByRole('checkbox')).not.toBeInTheDocument();
    expect(within(await fila('Ibagué')).queryByRole('checkbox')).not.toBeInTheDocument();
  });
});

describe('acciones en una corrida de prueba (SC-05)', () => {
  it('renders no lifecycle control nor header action', async () => {
    installFetch({ 'GET /corridas/c1': jsonRes(D_PRUEBA) });
    render(<CorridaDetallePage />);
    const fila1 = await fila('Manizales');
    expect(accionesDe(fila1)).toEqual([]);
    expect(within(fila1).queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Cerrar todas|Exportar cerradas|Recalcular/ })).not.toBeInTheDocument();
  });
});

describe('Recalcular fallidas (CI-12, CI-13)', () => {
  const FALLIDAS = { ...D_DETALLE, sucursales: [T_BORRADOR, T_CERRADO, T_FALLIDA, { ...T_FALLIDA, sucursal_id: 's8', nombre: 'Pasto' }] };
  const NUEVA = jsonRes({ id: 'c9', codigo: 'PED-2026-S40-009', estado: 'PENDIENTE' });

  it('is hidden when no tienda failed', async () => {
    installFetch({ 'GET /corridas/c1': jsonRes({ ...D_DETALLE, sucursales: [T_BORRADOR, T_CERRADO] }) });
    render(<CorridaDetallePage />);
    await screen.findByText('Manizales');
    expect(screen.queryByRole('button', { name: 'Recalcular fallidas' })).not.toBeInTheDocument();
  });

  it('confirms and creates a corrida with exactly the failed tiendas and the same fecha de corte', async () => {
    const calls = installFetch({ 'GET /corridas/c1': jsonRes(FALLIDAS), 'POST /corridas': NUEVA });
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Recalcular fallidas' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Recalcular las tiendas fallidas' });
    expect(dialogo).toHaveTextContent('2 tiendas');
    expect(dialogo).toHaveTextContent('Armenia');
    expect(dialogo).toHaveTextContent('Pasto');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Recalcular' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const post = calls.find((c) => c.method === 'POST');
    expect(post.path).toBe('/corridas');
    expect(post.body).toEqual({
      fecha_corte: '2026-10-01', sucursal_ids: ['s4', 's8'], nota: 'Recálculo de fallidas de PED-2026-S40-001',
    });
  });

  it('offers a link to the new corrida and leaves the original one alone', async () => {
    const calls = installFetch({ 'GET /corridas/c1': jsonRes(FALLIDAS), 'POST /corridas': NUEVA });
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Recalcular fallidas' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Recalcular' }));
    const aviso = await screen.findByRole('status');
    expect(aviso).toHaveTextContent('Corrida PED-2026-S40-009 creada: se está calculando.');
    fireEvent.click(within(aviso).getByRole('button', { name: 'Ver corrida' }));
    expect(pushMock).toHaveBeenCalledWith('/motored/pedidos/c9');
    expect(calls.filter((c) => c.method !== 'GET')).toHaveLength(1);
  });

  it('shows the coded error of the launch and keeps the dialog', async () => {
    installFetch({
      'GET /corridas/c1': jsonRes(FALLIDAS),
      'POST /corridas': coded(422, 'E-CORRIDA-001', 'Ya hay una corrida calculando.'),
    });
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Recalcular fallidas' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Recalcular' }));
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('Ya hay una corrida calculando. (E-CORRIDA-001)');
  });
});

describe('acciones en la página de la tienda (UX-19)', () => {
  const lineas = jsonRes({ items: [], total: 0, limite: 50, offset: 0 });
  const abrirPagina = async (cabecera, detalle = D_DETALLE) => {
    params = { id: 'c1', sucursalId: cabecera.sucursal_id };
    installFetch({
      [`GET /corridas/c1/sucursales/${cabecera.sucursal_id}`]: jsonRes(cabecera),
      'GET /corridas/c1/lineas': lineas,
      'GET /corridas/c1': jsonRes(detalle),
    });
    render(<PedidoTiendaPage />);
    return (await screen.findByRole('heading', { name: cabecera.nombre })).closest('header');
  };

  it.each([
    ['borrador', CAB_BORRADOR, ['Cerrar']],
    ['cerrado', CAB_CERRADO, ['Reabrir', 'Exportar', 'Marcar como enviado']],
    ['enviado', CAB_ENVIADO, ['Exportar', 'Corregir número']],
    ['fallida', CAB_FALLIDA, []],
    ['de prueba', CAB_PRUEBA, []],
  ])('a %s tienda shows its actions in the header', async (_nombre, cabecera, esperadas) => {
    expect(accionesDe(await abrirPagina(cabecera))).toEqual(esperadas);
  });

  it('disables Marcar como enviado in the header when there is nothing to order (A1)', async () => {
    const cab = { ...CAB_CERRADO, totales: { ...CAB_CERRADO.totales, unidades_a_pedir: '0.00' } };
    const encabezado = await abrirPagina(cab);
    expect(within(encabezado).getByRole('button', { name: /Marcar como enviado: .*nada que pedir/ })).toBeDisabled();
  });

  it('sends the tienda from the header with its number and date', async () => {
    params = { id: 'c1', sucursalId: 's2' };
    const calls = installFetch({
      'GET /corridas/c1/sucursales/s2': jsonRes(CAB_CERRADO),
      'GET /corridas/c1/lineas': lineas,
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'POST /corridas/c1/sucursales/s2/enviar': jsonRes({}),
    });
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Pereira' });
    fireEvent.click(screen.getByRole('button', { name: 'Marcar como enviado' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Marcar como enviado el pedido de Pereira' });
    fireEvent.change(within(dialogo).getByLabelText('Número de orden de Pereira'), { target: { value: '555' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Marcar como enviado' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const post = calls.find((c) => c.method === 'POST');
    expect(post.path).toBe('/corridas/c1/sucursales/s2/enviar');
    expect(post.body.numero_pedido_proveedor).toBe('555');
  });
});
