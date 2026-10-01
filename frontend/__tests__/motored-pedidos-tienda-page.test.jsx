/**
 * Motored Fase 4 (F2a): /motored/pedidos/{id}/{sucursalId} - the pedido of ONE
 * tienda, read-only: header with the TIENDA state, sugerido vs a pedir totals,
 * class summary, states without a pedido, and the gate.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE,
  CAB_BORRADOR, CAB_CERRADO, CAB_ENVIADO, CAB_FALLIDA, CAB_PRUEBA,
  L_NORMAL, paginaLineas,
} from './helpers/pedidosFetch';

const pushMock = jest.fn();
let params = { id: 'c1', sucursalId: 's1' };
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useParams: () => params,
  usePathname: () => '/motored/pedidos/c1/s1',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import PedidoTiendaPage from '../app/motored/pedidos/[id]/[sucursalId]/page';

const rutas = (cabecera = CAB_BORRADOR, over = {}) => ({
  [`GET /corridas/c1/sucursales/${cabecera.sucursal_id}`]: jsonRes(cabecera),
  'GET /corridas/c1/lineas': jsonRes(paginaLineas([L_NORMAL])),
  'GET /corridas/c1': jsonRes(D_DETALLE),
  ...over,
});

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  params = { id: 'c1', sucursalId: 's1' };
});

describe('tienda pedido - gate', () => {
  it.each(['SUCURSAL', 'CONSULTA'])('sends %s away without fetching any data', async (role) => {
    setSession(role);
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(calls).toHaveLength(0);
  });
});

describe('tienda pedido - header', () => {
  beforeEach(() => setSession('COMPRAS'));

  it('shows the tienda, SIC, cut date and corrida code', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    expect(await screen.findByRole('heading', { name: 'Manizales' })).toBeInTheDocument();
    expect(screen.getByText('1234')).toBeInTheDocument();
    expect(screen.getByText('01/10/2026')).toBeInTheDocument();
    expect(screen.getByText('PED-2026-S40-001')).toBeInTheDocument();
    expect(screen.getByRole('note', { name: /SIC/ })).toBeInTheDocument();
  });

  it('goes back to the corrida', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    fireEvent.click(await screen.findByRole('button', { name: /Volver a la corrida/ }));
    expect(pushMock).toHaveBeenCalledWith('/motored/pedidos/c1');
  });

  it('shows the state of THIS tienda (UX-19): Borrador with no closed note', async () => {
    installFetch(rutas(CAB_BORRADOR));
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Manizales' });
    expect(screen.getByText('Borrador')).toBeInTheDocument();
    expect(screen.queryByText(/reábralo para ajustar/)).not.toBeInTheDocument();
  });

  it('shows Cerrado with the note and who closed it', async () => {
    params = { id: 'c1', sucursalId: 's2' };
    installFetch(rutas(CAB_CERRADO));
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Pereira' });
    expect(screen.getByText('Cerrado')).toBeInTheDocument();
    expect(screen.getByText('Pedido cerrado: reábralo para ajustar')).toBeInTheDocument();
    expect(screen.getByText(/Cerrado por Compras Uno/)).toHaveTextContent('02/10/2026 09:15');
  });

  it('shows Enviado with the HMCL order number and no adjust note for Cerrado', async () => {
    params = { id: 'c1', sucursalId: 's3' };
    installFetch(rutas(CAB_ENVIADO));
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Cali' });
    expect(screen.getByText('Enviado')).toBeInTheDocument();
    expect(screen.getByText(/Orden 12345/)).toHaveTextContent('02/10/2026');
    expect(screen.getByText('Pedido enviado: ya no se puede ajustar.')).toBeInTheDocument();
    expect(screen.queryByText('Pedido cerrado: reábralo para ajustar')).not.toBeInTheDocument();
  });

  it('shows sugerido versus a pedir totals with their tooltips', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const totales = (await screen.findByText('Totales')).closest('section');
    expect(totales).toHaveTextContent('Sugerido');
    expect(totales).toHaveTextContent('1.000');
    expect(totales).toHaveTextContent(/5\.000\.000/);
    expect(totales).toHaveTextContent('A pedir');
    expect(totales).toHaveTextContent('1.010');
    expect(totales).toHaveTextContent(/5\.400\.000/);
    expect(within(totales).getByRole('note', { name: /Sugerido/ })).toBeInTheDocument();
    expect(within(totales).getByRole('note', { name: /Cantidad a pedir/ })).toBeInTheDocument();
  });

  it('marks a scenario tienda as PRUEBA and read-only', async () => {
    installFetch(rutas(CAB_PRUEBA));
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Manizales' });
    expect(screen.getByText('PRUEBA')).toBeInTheDocument();
    expect(screen.getByText('Escenario de prueba: solo lectura.')).toBeInTheDocument();
  });

  it('renders no lifecycle control that the backend did not allow (F3 draws only what `acciones` says)', async () => {
    params = { id: 'c1', sucursalId: 's2' };
    installFetch(rutas({ ...CAB_CERRADO, acciones: { ...CAB_CERRADO.acciones, reabrir: false, enviar: false, exportar: false } }));
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Pereira' });
    const nombres = screen.getAllByRole('button').map((b) => b.getAttribute('aria-label') || b.textContent);
    expect(nombres.join('|')).not.toMatch(/Cerrar|Reabrir|Exportar|Marcar como enviado|Corregir/);
  });
});

describe('tienda pedido - class summary', () => {
  beforeEach(() => setSession('COMPRAS'));

  it('joins sugerido and a pedir by class for this tienda only', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const tabla = (await screen.findByRole('table', { name: 'Resumen por clase' }));
    const filas = within(tabla).getAllByRole('row').slice(1).map((r) => r.textContent);
    expect(filas).toHaveLength(3);
    expect(filas[0]).toMatch(/AF.*20.*300.*310/);
    expect(filas[1]).toMatch(/CM.*100.*700.*700/);
    expect(filas[2]).toMatch(/TOTAL.*120.*1\.000.*1\.010/);
    expect(tabla).not.toHaveTextContent('800');
  });
});

describe('tienda pedido - tienda without pedido', () => {
  beforeEach(() => setSession('COMPRAS'));

  it('explains a FALLIDA tienda and loads no lines', async () => {
    params = { id: 'c1', sucursalId: 's4' };
    const calls = installFetch(rutas(CAB_FALLIDA));
    render(<PedidoTiendaPage />);
    expect(await screen.findByText(/Esta tienda no tiene pedido/)).toBeInTheDocument();
    expect(screen.getByText(/La tienda no tiene precios cargados\./)).toHaveTextContent('E-CORRIDA-020');
    expect(calls.some((c) => c.path === '/corridas/c1/lineas')).toBe(false);
  });

  it('loads the lines of an OK tienda', async () => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    await screen.findByText('94109-12000S');
    expect(calls.find((c) => c.path === '/corridas/c1/lineas').query.get('sucursal_id')).toBe('s1');
  });
});

describe('tienda pedido - states', () => {
  beforeEach(() => setSession('COMPRAS'));

  it('shows a loading message first', () => {
    installFetch(rutas(CAB_BORRADOR, { 'GET /corridas/c1/sucursales/s1': new Promise(() => {}) }));
    render(<PedidoTiendaPage />);
    expect(screen.getByText('Cargando...')).toBeInTheDocument();
  });

  it('shows the coded error of the server', async () => {
    installFetch(rutas(CAB_BORRADOR, {
      'GET /corridas/c1/sucursales/s1': coded(404, 'E-CORRIDA-001', 'La tienda no está en la corrida.'),
    }));
    render(<PedidoTiendaPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('La tienda no está en la corrida. (E-CORRIDA-001)');
  });
});
