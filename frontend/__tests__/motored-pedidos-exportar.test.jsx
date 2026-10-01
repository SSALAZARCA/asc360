/**
 * Motored Fase 4 (F3): exporting the HMCL files (F4-1, EX-01, EX-02, EX-12,
 * UX-23): one xlsx per tienda, the zip of the closed and sent tiendas with
 * the skipped ones listed from `X-Tiendas-Omitidas`, and the coded 055, 056
 * and 057 messages. Downloads are stubbed: no test navigates.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, installDescargas, fileRes, jsonRes, coded, setSession,
  D_DETALLE, D_PRUEBA, CAB_CERRADO, CAB_ENVIADO,
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

import CorridaDetallePage from '../app/motored/pedidos/[id]/page';
import PedidoTiendaPage from '../app/motored/pedidos/[id]/[sucursalId]/page';

const XLSX = (nombre) => fileRes({ 'content-disposition': `attachment; filename="${nombre}"` });
const OMITIDAS = [
  { sucursal_id: 's1', nombre: 'Manizales', codigo: 'BORRADOR', motivo: 'Su pedido sigue en Borrador.' },
  { sucursal_id: 's4', nombre: 'Armenia', codigo: 'SIN_PEDIDO', motivo: 'No tiene pedido (su cálculo falló).' },
];
const ZIP = (omitidas = []) => fileRes({
  'content-disposition': 'attachment; filename="Pedidos_PED-2026-S40-001_2026-10-01.zip"',
  'x-tiendas-omitidas': encodeURIComponent(JSON.stringify(omitidas)),
});

let descargas;
const fila = async (nombre) => (await screen.findByText(nombre)).closest('tr');

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
  params = { id: 'c1' };
  descargas = installDescargas();
});
afterEach(() => jest.restoreAllMocks());

describe('exportar una tienda (EX-01, EX-12)', () => {
  it('downloads the xlsx of a closed tienda under the name the server gives', async () => {
    const calls = installFetch({
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'GET /corridas/c1/sucursales/s2/exportar': XLSX('Pedido_SIC5678_Pereira_2026-10-01.xlsx'),
    });
    render(<CorridaDetallePage />);
    fireEvent.click(within(await fila('Pereira')).getByRole('button', { name: 'Exportar' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Se descargó Pedido_SIC5678_Pereira_2026-10-01.xlsx.');
    expect(descargas).toEqual(['Pedido_SIC5678_Pereira_2026-10-01.xlsx']);
    expect(calls.filter((c) => c.path.endsWith('/exportar'))).toHaveLength(1);
  });

  it('lets a sent tienda be exported again (A5)', async () => {
    installFetch({
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'GET /corridas/c1/sucursales/s3/exportar': XLSX('Pedido_SIC9012_Cali_2026-10-01.xlsx'),
    });
    render(<CorridaDetallePage />);
    fireEvent.click(within(await fila('Cali')).getByRole('button', { name: 'Exportar' }));
    await waitFor(() => expect(descargas).toEqual(['Pedido_SIC9012_Cali_2026-10-01.xlsx']));
  });

  it('does not offer Exportar on a draft', async () => {
    installFetch({ 'GET /corridas/c1': jsonRes(D_DETALLE) });
    render(<CorridaDetallePage />);
    expect(within(await fila('Manizales')).queryByRole('button', { name: 'Exportar' })).not.toBeInTheDocument();
  });

  it.each([
    ['E-CORRIDA-055', 'No se puede exportar: el pedido de Pereira sigue en Borrador.'],
    ['E-CORRIDA-056', 'Pereira no tiene nada que pedir (todas sus cantidades son 0): no hay nada que exportar.'],
    ['E-CORRIDA-057', 'Pereira no tiene SIC cargado: no se puede exportar.'],
  ])('shows the %s message with its code and downloads nothing', async (code, mensaje) => {
    installFetch({
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'GET /corridas/c1/sucursales/s2/exportar': coded(409, code, mensaje),
    });
    render(<CorridaDetallePage />);
    fireEvent.click(within(await fila('Pereira')).getByRole('button', { name: 'Exportar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(`${mensaje} (${code})`);
    expect(descargas).toEqual([]);
  });

  it('replaces the previous notice with the new one', async () => {
    installFetch({
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'GET /corridas/c1/sucursales/s2/exportar': XLSX('a.xlsx'),
      'GET /corridas/c1/sucursales/s3/exportar': coded(409, 'E-CORRIDA-057', 'Cali no tiene SIC.'),
    });
    render(<CorridaDetallePage />);
    fireEvent.click(within(await fila('Pereira')).getByRole('button', { name: 'Exportar' }));
    await screen.findByRole('status');
    fireEvent.click(within(await fila('Cali')).getByRole('button', { name: 'Exportar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Cali no tiene SIC. (E-CORRIDA-057)');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

describe('exportar cerradas (.zip) (EX-02, UX-23)', () => {
  it('downloads the zip and lists the tiendas the server skipped, with the reason', async () => {
    const calls = installFetch({
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'GET /corridas/c1/exportar': ZIP(OMITIDAS),
    });
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Exportar cerradas (.zip)' }));
    const aviso = await screen.findByRole('status');
    expect(aviso).toHaveTextContent('Se descargó Pedidos_PED-2026-S40-001_2026-10-01.zip.');
    expect(aviso).toHaveTextContent('2 tiendas no se incluyeron');
    expect(within(aviso).getByText(/Manizales/)).toHaveTextContent('Su pedido sigue en Borrador.');
    expect(within(aviso).getByText(/Armenia/)).toHaveTextContent('No tiene pedido (su cálculo falló).');
    expect(descargas).toEqual(['Pedidos_PED-2026-S40-001_2026-10-01.zip']);
    expect(calls.find((c) => c.path === '/corridas/c1/exportar').query.getAll('sucursal_id')).toEqual([]);
  });

  it('lists nothing when no tienda was skipped', async () => {
    installFetch({ 'GET /corridas/c1': jsonRes(D_DETALLE), 'GET /corridas/c1/exportar': ZIP([]) });
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Exportar cerradas (.zip)' }));
    const aviso = await screen.findByRole('status');
    expect(aviso).toHaveTextContent('Se descargó Pedidos_PED-2026-S40-001_2026-10-01.zip.');
    expect(aviso).not.toHaveTextContent('no se incluyeron');
  });

  it('uses the singular for one skipped tienda', async () => {
    installFetch({ 'GET /corridas/c1': jsonRes(D_DETALLE), 'GET /corridas/c1/exportar': ZIP([OMITIDAS[0]]) });
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Exportar cerradas (.zip)' }));
    expect(await screen.findByRole('status')).toHaveTextContent('1 tienda no se incluyó');
  });

  it('shows the coded error when nothing can be exported (055/056)', async () => {
    installFetch({
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'GET /corridas/c1/exportar': coded(409, 'E-CORRIDA-056', 'Ninguna de las tiendas tiene cantidades para exportar.'),
    });
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Exportar cerradas (.zip)' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Ninguna de las tiendas tiene cantidades para exportar. (E-CORRIDA-056)');
    expect(descargas).toEqual([]);
  });

  it('is offered only when some tienda can be exported, and never on a scenario', async () => {
    installFetch({ 'GET /corridas/c1': jsonRes({ ...D_DETALLE, sucursales: [D_DETALLE.sucursales[0]] }) });
    const { unmount } = render(<CorridaDetallePage />);
    await screen.findByText('Manizales');
    expect(screen.queryByRole('button', { name: 'Exportar cerradas (.zip)' })).not.toBeInTheDocument();
    unmount();
    installFetch({ 'GET /corridas/c1': jsonRes(D_PRUEBA) });
    render(<CorridaDetallePage />);
    await screen.findByText('PRUEBA');
    expect(screen.queryByRole('button', { name: 'Exportar cerradas (.zip)' })).not.toBeInTheDocument();
  });
});

describe('exportar - desde la página de la tienda', () => {
  const pagina = jsonRes({ items: [], total: 0, limite: 50, offset: 0 });

  it('downloads the xlsx of the tienda from the header', async () => {
    params = { id: 'c1', sucursalId: 's2' };
    installFetch({
      'GET /corridas/c1/sucursales/s2': jsonRes(CAB_CERRADO),
      'GET /corridas/c1/lineas': pagina,
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'GET /corridas/c1/sucursales/s2/exportar': XLSX('Pedido_SIC5678_Pereira_2026-10-01.xlsx'),
    });
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Pereira' });
    fireEvent.click(screen.getByRole('button', { name: 'Exportar' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Se descargó Pedido_SIC5678_Pereira_2026-10-01.xlsx.');
    expect(descargas).toEqual(['Pedido_SIC5678_Pereira_2026-10-01.xlsx']);
  });

  it('can export a sent tienda again', async () => {
    params = { id: 'c1', sucursalId: 's3' };
    installFetch({
      'GET /corridas/c1/sucursales/s3': jsonRes(CAB_ENVIADO),
      'GET /corridas/c1/lineas': pagina,
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'GET /corridas/c1/sucursales/s3/exportar': XLSX('Pedido_SIC9012_Cali_2026-10-01.xlsx'),
    });
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Cali' });
    fireEvent.click(screen.getByRole('button', { name: 'Exportar' }));
    await waitFor(() => expect(descargas).toEqual(['Pedido_SIC9012_Cali_2026-10-01.xlsx']));
  });
});
