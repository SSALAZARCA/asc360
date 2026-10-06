/**
 * Motored Fase 4 (F2a): /motored/pedidos/{id} - the corrida detail with its
 * Tiendas table (read-only): per-tienda pedido state, a pedir, last event,
 * order number of the sent ones, FALLIDA/OMITIDA flagged without actions.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, PROGRESO, D_DETALLE, D_PRUEBA,
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

const rutas = (over = {}) => ({ 'GET /corridas/c1': jsonRes(D_DETALLE), ...over });
const fila = async (nombre) => (await screen.findByText(nombre)).closest('tr');

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('corrida detail - gate', () => {
  it.each(['SUCURSAL', 'CONSULTA'])('sends %s away without fetching any data', async (role) => {
    setSession(role);
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(calls).toHaveLength(0);
  });
});

describe('corrida detail - header', () => {
  beforeEach(() => { setSession('COMPRAS'); installFetch(rutas()); });

  it('shows the code, the cut date, the calculation badge and the sent summary', async () => {
    render(<CorridaDetallePage />);
    expect(await screen.findByRole('heading', { name: 'PED-2026-S40-001' })).toBeInTheDocument();
    expect(screen.getByText('01/10/2026')).toBeInTheDocument();
    expect(screen.getByText('Calculada')).toBeInTheDocument();
    expect(screen.getByText('1 de 3 enviadas')).toBeInTheDocument();
  });

  it('goes back to the corridas list', async () => {
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: /Volver a pedidos/ }));
    expect(pushMock).toHaveBeenCalledWith('/motored/pedidos');
  });

  it('keeps the back button at the 44 px tablet touch target', async () => {
    render(<CorridaDetallePage />);
    const volver = await screen.findByRole('button', { name: /Volver a pedidos/ });
    expect(volver.style.minHeight).toBe('44px');
  });

  it('marks a scenario corrida as PRUEBA', async () => {
    installFetch(rutas({ 'GET /corridas/c1': jsonRes(D_PRUEBA) }));
    render(<CorridaDetallePage />);
    expect(await screen.findByText('PRUEBA')).toBeInTheDocument();
  });

  it('flags an invalidated corrida', async () => {
    installFetch(rutas({ 'GET /corridas/c1': jsonRes({ ...D_DETALLE, invalidada: true }) }));
    render(<CorridaDetallePage />);
    expect(await screen.findByText('Datos invalidados')).toBeInTheDocument();
  });
});

describe('corrida detail - data age (UX-06)', () => {
  beforeEach(() => { setSession('COMPRAS'); installFetch(rutas()); });

  it('lists the age of each dataset used', async () => {
    render(<CorridaDetallePage />);
    const antiguedad = (await screen.findByText('Antigüedad de datos')).closest('section');
    expect(within(antiguedad).getByText(/Inventario/)).toHaveTextContent('1 día');
    expect(within(antiguedad).getByText(/Backorder/)).toHaveTextContent('3 días');
  });

  it('warns about a dataset older than its limit and not about the others', async () => {
    render(<CorridaDetallePage />);
    const antiguedad = (await screen.findByText('Antigüedad de datos')).closest('section');
    expect(within(antiguedad).getByText(/Facturas de pedidos/)).toHaveTextContent('supera el límite de 14');
    expect(within(antiguedad).getByText(/Inventario/)).not.toHaveTextContent('supera');
  });

  it('shows the corrida warnings', async () => {
    render(<CorridaDetallePage />);
    expect(await screen.findByText('Sin demanda perdida cargada.')).toBeInTheDocument();
  });
});

describe('corrida detail - Tiendas table', () => {
  beforeEach(() => { setSession('ADMIN'); installFetch(rutas()); });

  it('has the Tiendas columns with their help tooltips', async () => {
    render(<CorridaDetallePage />);
    await screen.findByText('Manizales');
    const cabecera = screen.getAllByRole('columnheader').map((th) => th.textContent);
    ['Tienda', 'Cálculo', 'Pedido', 'A pedir', 'Último evento'].forEach((titulo) => {
      expect(cabecera.some((t) => t.includes(titulo))).toBe(true);
    });
    expect(screen.getByRole('note', { name: /Estado del pedido/ })).toBeInTheDocument();
    expect(screen.getByRole('note', { name: /A pedir/ })).toBeInTheDocument();
  });

  it('shows the pedido state of each tienda and its units and value to order', async () => {
    render(<CorridaDetallePage />);
    const manizales = await fila('Manizales');
    expect(within(manizales).getByText('Borrador')).toBeInTheDocument();
    expect(within(manizales).getByText('1.010')).toBeInTheDocument();
    expect(manizales).toHaveTextContent(/5\.400\.000/);
    expect(within(await fila('Pereira')).getByText('Cerrado')).toBeInTheDocument();
  });

  it('shows who did the last event and when', async () => {
    render(<CorridaDetallePage />);
    const pereira = await fila('Pereira');
    expect(pereira).toHaveTextContent('Cerrado por Compras Uno');
    expect(pereira).toHaveTextContent('02/10/2026 04:15');
    expect(await fila('Manizales')).toHaveTextContent('Sin movimientos');
  });

  it('shows the HMCL order number of a sent tienda', async () => {
    render(<CorridaDetallePage />);
    const cali = await fila('Cali');
    expect(within(cali).getByText('Enviado')).toBeInTheDocument();
    expect(cali).toHaveTextContent('Orden 12345');
    expect(await fila('Pereira')).not.toHaveTextContent('Orden');
  });

  it('flags FALLIDA and OMITIDA tiendas with their message and no actions', async () => {
    render(<CorridaDetallePage />);
    const armenia = await fila('Armenia');
    expect(within(armenia).getByText('Fallida')).toBeInTheDocument();
    expect(armenia).toHaveTextContent('La tienda no tiene precios cargados.');
    expect(armenia).toHaveTextContent('E-CORRIDA-020');
    expect(within(armenia).queryByRole('button')).not.toBeInTheDocument();
    const ibague = await fila('Ibagué');
    expect(within(ibague).getByText('Omitida')).toBeInTheDocument();
    expect(ibague).toHaveTextContent('Tienda sin ventas en el periodo.');
    expect(within(ibague).queryByRole('button')).not.toBeInTheDocument();
  });

  it('opens the tienda pedido page from the row', async () => {
    render(<CorridaDetallePage />);
    const manizales = await fila('Manizales');
    fireEvent.click(within(manizales).getByRole('button', { name: 'Ver pedido' }));
    expect(pushMock).toHaveBeenCalledWith('/motored/pedidos/c1/s1');
  });

  it('renders no lifecycle control that the backend did not allow (F3 draws only what `acciones` says)', async () => {
    const sinAcciones = D_DETALLE.sucursales.map((t) => ({ ...t, acciones: { ...t.acciones, cerrar: false, reabrir: false, enviar: false, corregir_envio: false, exportar: false } }));
    installFetch(rutas({ 'GET /corridas/c1': jsonRes({ ...D_DETALLE, sucursales: sinAcciones.map((t) => (t.estado === 'FALLIDA' ? { ...t, estado: 'OMITIDA' } : t)) }) }));
    render(<CorridaDetallePage />);
    await screen.findByText('Manizales');
    const nombres = screen.getAllByRole('button').map((b) => b.getAttribute('aria-label') || b.textContent);
    expect(nombres.join('|')).not.toMatch(/Cerrar|Reabrir|Exportar|Marcar como enviado|Anular|Recalcular/);
  });

  it('shows no pedido link on a scenario corrida (its tiendas have no pedido)', async () => {
    installFetch(rutas({ 'GET /corridas/c1': jsonRes(D_PRUEBA) }));
    render(<CorridaDetallePage />);
    await screen.findByText('PRUEBA');
    expect(screen.queryByRole('button', { name: 'Ver pedido' })).not.toBeInTheDocument();
  });
});

describe('corrida detail - states', () => {
  beforeEach(() => setSession('COMPRAS'));

  it('shows a loading message first', () => {
    installFetch(rutas({ 'GET /corridas/c1': new Promise(() => {}) }));
    render(<CorridaDetallePage />);
    expect(screen.getByText('Cargando...')).toBeInTheDocument();
  });

  it('shows the coded error of the server', async () => {
    installFetch(rutas({ 'GET /corridas/c1': coded(404, 'E-CORRIDA-001', 'Corrida no encontrada.') }));
    render(<CorridaDetallePage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Corrida no encontrada. (E-CORRIDA-001)');
  });

  it('shows an empty message when the corrida has no tiendas', async () => {
    installFetch(rutas({ 'GET /corridas/c1': jsonRes({ ...D_DETALLE, sucursales: [] }) }));
    render(<CorridaDetallePage />);
    expect(await screen.findByText('Sin pedidos para mostrar')).toBeInTheDocument();
  });

  it('follows the progress of a corrida that is still calculating and reloads at the end', async () => {
    const detalle = { ...D_DETALLE, estado: 'CALCULANDO', sucursales: [], pedidos: null };
    const calls = installFetch(rutas({
      'GET /corridas/c1': jsonRes(detalle),
      'GET /corridas/c1/progreso': jsonRes({ ...PROGRESO, estado: 'BORRADOR', procesadas: 47 }),
    }));
    render(<CorridaDetallePage />);
    await waitFor(() => expect(calls.filter((c) => c.path === '/corridas/c1').length).toBeGreaterThanOrEqual(2));
  });
});
