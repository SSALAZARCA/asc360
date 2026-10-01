/**
 * Motored Fase 4 (F3): closing the pedido of ONE tienda (CI-05, ED-15, UX-08):
 * an accessible confirmation that shows the pack-warning count, the coded
 * rejection kept inside the dialog, and the same action on the tienda page.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE, CAB_BORRADOR, L_FUERA, paginaLineas,
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

const CERRADA_OK = jsonRes({ corrida_id: 'c1', sucursal_id: 's1', estado_pedido: 'CERRADO' });

/** Lines endpoint: the pack-warning count of the closing dialog is the `total` of a one-row page. */
const lineasFuera = (total) => (url) => {
  const q = url.searchParams;
  const esConteo = q.get('sucursal_id') === 's1' && q.get('solo_fuera_empaque') === 'true' && q.get('limite') === '1';
  return jsonRes(paginaLineas(esConteo && total > 0 ? [L_FUERA] : [], { total: esConteo ? total : 0 }));
};

const rutas = (over = {}) => ({
  'GET /corridas/c1': jsonRes(D_DETALLE),
  'GET /corridas/c1/lineas': lineasFuera(3),
  'POST /corridas/c1/sucursales/s1/cerrar': CERRADA_OK,
  ...over,
});

const detalleCargas = (calls) => calls.filter((c) => c.method === 'GET' && c.path === '/corridas/c1');
const abrirDialogo = async () => {
  const fila = (await screen.findByText('Manizales')).closest('tr');
  fireEvent.click(within(fila).getByRole('button', { name: 'Cerrar' }));
  return screen.findByRole('dialog', { name: 'Cerrar el pedido de Manizales' });
};

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
  params = { id: 'c1' };
});

describe('cerrar una tienda - confirmación accesible', () => {
  it('opens a modal dialog named after the tienda and described by its summary', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    expect(dialogo).toHaveAttribute('aria-modal', 'true');
    const descripcion = document.getElementById(dialogo.getAttribute('aria-describedby'));
    expect(descripcion).toHaveTextContent('Manizales');
    expect(descripcion).toHaveTextContent('1.010');
  });

  it('moves the focus into the dialog and gives it back to the trigger on cancel', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const fila = (await screen.findByText('Manizales')).closest('tr');
    const disparador = within(fila).getByRole('button', { name: 'Cerrar' });
    act(() => disparador.focus());
    fireEvent.click(disparador);
    const dialogo = await screen.findByRole('dialog');
    expect(dialogo.contains(document.activeElement)).toBe(true);
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(disparador);
  });

  it('closes with Escape without sending anything', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    fireEvent.keyDown(dialogo, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0);
  });
});

describe('cerrar una tienda - el foco no se pierde con el botón deshabilitado (verificado en el navegador)', () => {
  // A browser drops the focus of a button the moment it is disabled (while the request is in flight);
  // jsdom keeps it, so the loss is simulated by moving the focus to a control outside the dialog.
  const perderFoco = () => act(() => screen.getByRole('button', { name: /Volver a pedidos/ }).focus());

  it('closes with Escape even when the focus is on the page body', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirDialogo();
    perderFoco();
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('puts the focus back inside the dialog when the request fails', async () => {
    let rechazar;
    installFetch(rutas({
      'POST /corridas/c1/sucursales/s1/cerrar': () => new Promise((_, no) => { rechazar = () => no(Object.assign(new Error('Falla.'), { status: 409, code: 'E-CORRIDA-041' })); }),
    }));
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar pedido' }));
    await waitFor(() => expect(within(dialogo).getByRole('button', { name: 'Cancelar' })).toBeDisabled());
    perderFoco();
    expect(dialogo.contains(document.activeElement)).toBe(false);
    await act(async () => { rechazar(); });
    expect(await within(dialogo).findByRole('alert')).toBeInTheDocument();
    expect(dialogo.contains(document.activeElement)).toBe(true);
  });

  it('keeps Tab inside the dialog when the focus had been lost', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    perderFoco();
    fireEvent.keyDown(document.body, { key: 'Tab' });
    expect(dialogo.contains(document.activeElement)).toBe(true);
  });
});

describe('cerrar una tienda - líneas fuera de empaque (ED-15)', () => {
  it('shows how many lines are not a multiple of the pack', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    expect(await within(dialogo).findByText(/3 líneas no son múltiplo del empaque/)).toBeInTheDocument();
    const conteo = calls.find((c) => c.path === '/corridas/c1/lineas');
    expect(conteo.query.get('solo_fuera_empaque')).toBe('true');
  });

  it('uses the singular for one line', async () => {
    installFetch(rutas({ 'GET /corridas/c1/lineas': lineasFuera(1) }));
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    expect(await within(dialogo).findByText(/1 línea no es múltiplo del empaque/)).toBeInTheDocument();
  });

  it('says so when every line fits the pack', async () => {
    installFetch(rutas({ 'GET /corridas/c1/lineas': lineasFuera(0) }));
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    expect(await within(dialogo).findByText(/Ninguna línea está fuera del empaque/)).toBeInTheDocument();
  });

  it('still lets the user close when the count cannot be read', async () => {
    installFetch(rutas({ 'GET /corridas/c1/lineas': coded(500, 'E-X', 'falla') }));
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    await waitFor(() => expect(within(dialogo).getByRole('button', { name: 'Cerrar pedido' })).toBeEnabled());
    expect(within(dialogo).queryByText(/múltiplo del empaque/)).not.toBeInTheDocument();
  });
});

describe('cerrar una tienda - confirmar', () => {
  it('posts the close of that tienda, closes the dialog and reloads the corrida', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar pedido' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual(['/corridas/c1/sucursales/s1/cerrar']);
    await waitFor(() => expect(detalleCargas(calls)).toHaveLength(2));
  });

  it('keeps the dialog open with the coded message when the server rejects (E-CORRIDA-041)', async () => {
    const calls = installFetch(rutas({
      'POST /corridas/c1/sucursales/s1/cerrar': coded(409, 'E-CORRIDA-041', 'La corrida usa una carga anulada.'),
    }));
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar pedido' }));
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('La corrida usa una carga anulada. (E-CORRIDA-041)');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(detalleCargas(calls)).toHaveLength(1);
  });

  it('disables the buttons while the request is in flight', async () => {
    let liberar;
    installFetch(rutas({ 'POST /corridas/c1/sucursales/s1/cerrar': () => new Promise((ok) => { liberar = () => ok(CERRADA_OK); }) }));
    render(<CorridaDetallePage />);
    const dialogo = await abrirDialogo();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar pedido' }));
    await waitFor(() => expect(within(dialogo).getByRole('button', { name: 'Cancelar' })).toBeDisabled());
    expect(within(dialogo).getByRole('button', { name: 'Cerrar pedido' })).toBeDisabled();
    fireEvent.keyDown(dialogo, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    liberar();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});

describe('cerrar una tienda - desde la página de la tienda', () => {
  beforeEach(() => { params = { id: 'c1', sucursalId: 's1' }; });

  it('closes from the header and reloads the header', async () => {
    const calls = installFetch(rutas({ 'GET /corridas/c1/sucursales/s1': jsonRes(CAB_BORRADOR) }));
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Manizales' });
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Cerrar el pedido de Manizales' });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar pedido' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(calls.filter((c) => c.path === '/corridas/c1/sucursales/s1' && c.method === 'GET')).toHaveLength(2));
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual(['/corridas/c1/sucursales/s1/cerrar']);
  });
});
