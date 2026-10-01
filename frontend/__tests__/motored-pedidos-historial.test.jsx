/**
 * Motored Fase 4 (F2a): the Historial drawer - the timeline of the tienda
 * pedido (cerrado, reabierto, enviado...) and the edit history of one line.
 */
import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE, CAB_BORRADOR,
  L_NORMAL, L_EDITADA, paginaLineas,
} from './helpers/pedidosFetch';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  useParams: () => ({ id: 'c1', sucursalId: 's1' }),
  usePathname: () => '/motored/pedidos/c1/s1',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import PedidoTiendaPage from '../app/motored/pedidos/[id]/[sucursalId]/page';

const EVENTOS = [
  { id: 1, evento: 'CERRADO', motivo: null, detalle: null, usuario_id: 'u1', usuario: 'Compras Uno', creado_en: '2026-10-02T09:15:00' },
  { id: 2, evento: 'REABIERTO', motivo: 'Corrección de cantidades', detalle: null, usuario_id: 'u1', usuario: 'Compras Uno', creado_en: '2026-10-02T09:40:00' },
  { id: 3, evento: 'ENVIADO', motivo: null, detalle: { numero: '12345' }, usuario_id: 'u2', usuario: 'Ana Gómez', creado_en: '2026-10-02T11:00:00' },
  { id: 4, evento: 'ENVIO_CORREGIDO', motivo: null, detalle: { antes: '12345', despues: '12399' }, usuario_id: 'u2', usuario: 'Ana Gómez', creado_en: '2026-10-02T12:00:00' },
];
const HISTORIAL = [
  { id: 1, linea_id: 2, campo: 'pedido_final', valor_anterior: '50.00', valor_nuevo: '60.00', motivo: 'MANUAL', detalle: null, usuario_id: 'u1', usuario: 'Compras Uno', creado_en: '2026-10-02T10:15:00' },
  { id: 2, linea_id: 2, campo: 'pedido_final', valor_anterior: '60.00', valor_nuevo: '55.00', motivo: 'RECORTE_PRESUPUESTO', detalle: { tope: '80000000' }, usuario_id: 'u1', usuario: 'Compras Uno', creado_en: '2026-10-02T10:30:00' },
];

const rutas = (over = {}) => ({
  'GET /corridas/c1/sucursales/s1': jsonRes(CAB_BORRADOR),
  'GET /corridas/c1/lineas': jsonRes(paginaLineas([L_NORMAL, L_EDITADA])),
  'GET /corridas/c1': jsonRes(D_DETALLE),
  'GET /corridas/c1/sucursales/s1/eventos': jsonRes(EVENTOS),
  'GET /corridas/c1/lineas/2/historial': jsonRes(HISTORIAL),
  ...over,
});

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
});

describe('Historial drawer - tienda timeline', () => {
  it('stays closed and fetches nothing until it is opened', async () => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Manizales' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith('/eventos'))).toBe(false);
  });

  it('lists every event with who, when and its details', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Historial del pedido' }));
    const panel = await screen.findByRole('dialog', { name: 'Historial del pedido' });
    const items = await within(panel).findAllByRole('listitem');
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveTextContent('Cerrado');
    expect(items[0]).toHaveTextContent('Compras Uno');
    expect(items[0]).toHaveTextContent('02/10/2026 09:15');
    expect(items[1]).toHaveTextContent('Reabierto');
    expect(items[1]).toHaveTextContent('Corrección de cantidades');
    expect(items[2]).toHaveTextContent('Orden 12345');
    expect(items[3]).toHaveTextContent('12345 → 12399');
  });

  it('closes', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Historial del pedido' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar historial' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('says so when the tienda has no events', async () => {
    installFetch(rutas({ 'GET /corridas/c1/sucursales/s1/eventos': jsonRes([]) }));
    render(<PedidoTiendaPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Historial del pedido' }));
    expect(await screen.findByText('Sin movimientos')).toBeInTheDocument();
  });

  it('shows the coded error of the server', async () => {
    installFetch(rutas({ 'GET /corridas/c1/sucursales/s1/eventos': coded(404, 'E-CORRIDA-001', 'No existe.') }));
    render(<PedidoTiendaPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Historial del pedido' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No existe. (E-CORRIDA-001)');
  });
});

describe('Historial drawer - one line', () => {
  it('offers the history only on edited lines', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    await screen.findByText('55512-A');
    expect(screen.getAllByRole('button', { name: /Historial de la línea/ })).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Historial de la línea 55512-A' })).toBeInTheDocument();
  });

  it('lists the edits oldest first with before, after, reason, who and when', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Historial de la línea 55512-A' }));
    const panel = await screen.findByRole('dialog', { name: 'Historial de 55512-A' });
    const items = await within(panel).findAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('50 → 60');
    expect(items[0]).toHaveTextContent('Manual');
    expect(items[0]).toHaveTextContent('Compras Uno');
    expect(items[0]).toHaveTextContent('02/10/2026 10:15');
    expect(items[1]).toHaveTextContent('60 → 55');
    expect(items[1]).toHaveTextContent('Recorte por presupuesto');
  });
});
