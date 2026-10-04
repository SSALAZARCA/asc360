/**
 * Motored: early warning banner when pedido input data is about to go stale
 * (`GET /avisos-antiguedad`), on the Pedidos list and the corrida detail.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import {
  installFetch, jsonRes, pagina, setSession, C_CALCULADA, D_DETALLE,
} from './helpers/pedidosFetch';

const pushMock = jest.fn();
let params = { id: 'c1' };
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useParams: () => params,
  usePathname: () => '/motored/pedidos',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import PedidosPage from '../app/motored/pedidos/page';
import CorridaDetallePage from '../app/motored/pedidos/[id]/page';

const MANANA = {
  dataset: 'inventario', nombre: 'inventario', vence: 'manana',
  fecha_carga: '2026-09-26', fecha_vencimiento: '2026-10-03',
};
const HOY = {
  dataset: 'facturas', nombre: 'facturas de pedidos', vence: 'hoy',
  fecha_carga: '2026-09-25', fecha_vencimiento: '2026-10-02',
};

const avisos = (...items) => jsonRes({ avisos: items });

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
  params = { id: 'c1' };
});

describe('banner on the Pedidos list', () => {
  const rutas = (aviso) => ({
    'GET /corridas': jsonRes(pagina([C_CALCULADA])),
    'GET /avisos-antiguedad': aviso,
  });

  it('warns the day before with the load date and asks to upload', async () => {
    installFetch(rutas(avisos(MANANA)));
    render(<PedidosPage />);

    const banner = await screen.findByRole('status', { name: 'Datos por vencer' });
    expect(banner).toHaveTextContent('El inventario vence mañana (cargado el 26/09).');
    expect(banner).toHaveTextContent('Súbalo antes de lanzar el pedido.');
  });

  it('says "hoy" and uses the plural for facturas', async () => {
    installFetch(rutas(avisos(HOY)));
    render(<PedidosPage />);

    const banner = await screen.findByRole('status', { name: 'Datos por vencer' });
    expect(banner).toHaveTextContent('Las facturas de pedidos vencen hoy (cargado el 25/09).');
    expect(banner).toHaveTextContent('Súbalas antes de lanzar el pedido.');
  });

  it('lists every dataset that is about to expire', async () => {
    installFetch(rutas(avisos(MANANA, HOY)));
    render(<PedidosPage />);

    const banner = await screen.findByRole('status', { name: 'Datos por vencer' });
    expect(banner).toHaveTextContent('El inventario vence mañana');
    expect(banner).toHaveTextContent('Las facturas de pedidos vencen hoy');
  });

  it('renders nothing when no data is about to expire', async () => {
    installFetch(rutas(avisos()));
    render(<PedidosPage />);

    expect(await screen.findByText('PED-2026-S40-001')).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Datos por vencer' })).toBeNull();
  });

  it('stays silent and keeps the screen working when the warning fails', async () => {
    installFetch(rutas(jsonRes({ detail: 'boom' }, 500)));
    render(<PedidosPage />);

    expect(await screen.findByText('PED-2026-S40-001')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByRole('status', { name: 'Datos por vencer' })).toBeNull();
  });

  it('can be dismissed with a 44 px control', async () => {
    installFetch(rutas(avisos(MANANA)));
    render(<PedidosPage />);

    await screen.findByRole('status', { name: 'Datos por vencer' });
    const boton = screen.getByRole('button', { name: 'Descartar aviso de datos por vencer' });
    expect(boton.style.minHeight).toBe('44px');
    boton.click();
    await waitFor(() => expect(screen.queryByRole('status', { name: 'Datos por vencer' })).toBeNull());
  });
});

describe('banner on the corrida detail', () => {
  it('shows the same warning', async () => {
    installFetch({
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'GET /avisos-antiguedad': avisos(MANANA),
    });
    render(<CorridaDetallePage />);

    const banner = await screen.findByRole('status', { name: 'Datos por vencer' });
    expect(banner).toHaveTextContent('El inventario vence mañana (cargado el 26/09).');
  });
});
