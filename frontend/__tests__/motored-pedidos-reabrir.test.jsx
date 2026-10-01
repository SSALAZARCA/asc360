/**
 * Motored Fase 4 (F3): reopening ONE closed pedido (F4-10, CI-15..CI-20,
 * UX-09, UX-20): the motivo is required and the dialog warns that the HMCL
 * file downloaded before becomes invalid.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE, CAB_CERRADO, CAB_ENVIADO,
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

const REABIERTO = jsonRes({ corrida_id: 'c1', sucursal_id: 's2', estado_pedido: 'BORRADOR' });
const rutas = (over = {}) => ({
  'GET /corridas/c1': jsonRes(D_DETALLE),
  'POST /corridas/c1/sucursales/s2/reabrir': REABIERTO,
  ...over,
});
const posts = (calls) => calls.filter((c) => c.method === 'POST');

async function abrir() {
  const fila = (await screen.findByText('Pereira')).closest('tr');
  fireEvent.click(within(fila).getByRole('button', { name: 'Reabrir' }));
  return screen.findByRole('dialog', { name: 'Reabrir el pedido de Pereira' });
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
  params = { id: 'c1' };
});

describe('reabrir - motivo obligatorio (CI-17, UX-20)', () => {
  it('keeps the confirm button disabled until the motivo has text', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrir();
    const confirmar = within(dialogo).getByRole('button', { name: 'Reabrir pedido' });
    expect(confirmar).toBeDisabled();
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: '    ' } });
    expect(confirmar).toBeDisabled();
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'Corrección de cantidades' } });
    expect(confirmar).toBeEnabled();
  });

  it('warns that the HMCL file already downloaded becomes invalid', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrir();
    expect(dialogo).toHaveTextContent('El archivo HMCL que descargó antes queda inválido');
    expect(dialogo).toHaveTextContent('vuelva a exportar después de cerrar');
  });

  it('limits the motivo to 500 characters', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrir();
    expect(within(dialogo).getByLabelText('Motivo')).toHaveAttribute('maxlength', '500');
  });

  it('starts from an empty motivo every time it opens', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    let dialogo = await abrir();
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'algo' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }));
    dialogo = await abrir();
    expect(within(dialogo).getByLabelText('Motivo')).toHaveValue('');
  });
});

describe('reabrir - confirmar', () => {
  it('posts the trimmed motivo for that tienda and reloads the corrida', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrir();
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: '  Corrección de cantidades ' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Reabrir pedido' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(posts(calls)).toHaveLength(1);
    expect(posts(calls)[0]).toMatchObject({ path: '/corridas/c1/sucursales/s2/reabrir', body: { motivo: 'Corrección de cantidades' } });
    await waitFor(() => expect(calls.filter((c) => c.method === 'GET' && c.path === '/corridas/c1')).toHaveLength(2));
  });

  it.each([
    ['E-CORRIDA-045', 'Pereira ya está enviado (orden 12345): no se puede reabrir.'],
    ['E-CORRIDA-046', 'Escriba el motivo para reabrir el pedido.'],
  ])('shows the server rejection %s with its code and keeps the dialog', async (code, mensaje) => {
    installFetch(rutas({ 'POST /corridas/c1/sucursales/s2/reabrir': coded(code === 'E-CORRIDA-046' ? 422 : 409, code, mensaje) }));
    render(<CorridaDetallePage />);
    const dialogo = await abrir();
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'x' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Reabrir pedido' }));
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent(`${mensaje} (${code})`);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('only touches the tienda that was reopened (the others keep their state)', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrir();
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'x' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Reabrir pedido' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(posts(calls).map((c) => c.path)).toEqual(['/corridas/c1/sucursales/s2/reabrir']);
  });
});

describe('reabrir - no se ofrece', () => {
  it('is not offered for a sent tienda', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const fila = (await screen.findByText('Cali')).closest('tr');
    expect(within(fila).queryByRole('button', { name: 'Reabrir' })).not.toBeInTheDocument();
  });
});

describe('reabrir - desde la página de la tienda', () => {
  it('reopens from the header', async () => {
    params = { id: 'c1', sucursalId: 's2' };
    const calls = installFetch({
      'GET /corridas/c1/sucursales/s2': jsonRes(CAB_CERRADO),
      'GET /corridas/c1/lineas': jsonRes({ items: [], total: 0, limite: 50, offset: 0 }),
      'GET /corridas/c1': jsonRes(D_DETALLE),
      'POST /corridas/c1/sucursales/s2/reabrir': REABIERTO,
    });
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Pereira' });
    fireEvent.click(screen.getByRole('button', { name: 'Reabrir' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Reabrir el pedido de Pereira' });
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'Ajuste' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Reabrir pedido' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(posts(calls)[0].body).toEqual({ motivo: 'Ajuste' });
    await waitFor(() => expect(calls.filter((c) => c.method === 'GET' && c.path === '/corridas/c1/sucursales/s2')).toHaveLength(2));
  });

  it('does not offer Reabrir on a sent tienda', async () => {
    params = { id: 'c1', sucursalId: 's3' };
    installFetch({
      'GET /corridas/c1/sucursales/s3': jsonRes(CAB_ENVIADO),
      'GET /corridas/c1/lineas': jsonRes({ items: [], total: 0, limite: 50, offset: 0 }),
      'GET /corridas/c1': jsonRes(D_DETALLE),
    });
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Cali' });
    expect(screen.queryByRole('button', { name: 'Reabrir' })).not.toBeInTheDocument();
  });
});
