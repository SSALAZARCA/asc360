/**
 * Motored Fase 4 (sdd/motored-pedidos-ui, F1): the corridas list at
 * /motored/pedidos - badges, per-tienda summary chip, filters, anular, gate.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, pagina, setSession, PROGRESO,
  C_CALCULADA, C_CALCULANDO, C_FALLIDA, C_ANULADA, C_PRUEBA, C_PENDIENTE, C_LIMPIA, C_INVALIDADA, C_SOLO_ENVIADAS,
} from './helpers/pedidosFetch';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/pedidos',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import PedidosPage from '../app/motored/pedidos/page';

const TODAS = [
  C_CALCULADA, C_CALCULANDO, C_FALLIDA, C_ANULADA, C_PRUEBA, C_LIMPIA, C_INVALIDADA, C_SOLO_ENVIADAS,
];

function rutas(over = {}) {
  return {
    'GET /corridas': jsonRes(pagina(TODAS)),
    'GET /corridas/c2/progreso': jsonRes(PROGRESO),
    ...over,
  };
}

const fila = async (codigo) => (await screen.findByText(codigo)).closest('tr');
const ultimaLista = (calls) => [...calls].reverse().find((c) => c.path === '/corridas' && c.method === 'GET');

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('Pedidos list - gate', () => {
  it.each(['ADMIN', 'COMPRAS'])('renders the corridas for %s', async (role) => {
    setSession(role);
    installFetch(rutas());
    render(<PedidosPage />);
    expect(await screen.findByText('PED-2026-S40-001')).toBeInTheDocument();
  });

  it.each(['SUCURSAL', 'CONSULTA'])('sends %s away without fetching any data', async (role) => {
    setSession(role);
    const calls = installFetch(rutas());
    render(<PedidosPage />);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/mi-cuenta'));
    expect(calls).toHaveLength(0);
    expect(screen.queryByText('PED-2026-S40-001')).not.toBeInTheDocument();
  });
});

describe('Pedidos list - badges', () => {
  beforeEach(() => {
    setSession();
    installFetch(rutas());
  });

  it('labels each calculation state', async () => {
    render(<PedidosPage />);
    expect(within(await fila('PED-2026-S40-001')).getByText('Calculada')).toBeInTheDocument();
    expect(within(await fila('PED-2026-S40-002')).getByText('Calculando')).toBeInTheDocument();
    expect(within(await fila('PED-2026-S40-003')).getByText('Fallida')).toBeInTheDocument();
    expect(within(await fila('PED-2026-S40-004')).getByText('Anulada')).toBeInTheDocument();
  });

  it('marks a scenario with PRUEBA and a real corrida without it', async () => {
    render(<PedidosPage />);
    expect(within(await fila('ESC-2026-S40-001')).getByText('PRUEBA')).toBeInTheDocument();
    expect(within(await fila('PED-2026-S40-001')).queryByText('PRUEBA')).not.toBeInTheDocument();
  });

  it('shows "3 de 47 enviadas" with the closed and draft counts', async () => {
    render(<PedidosPage />);
    const row = await fila('PED-2026-S40-001');
    expect(within(row).getByText('3 de 47 enviadas')).toBeInTheDocument();
    expect(row).toHaveTextContent('Cerrados 10');
    expect(row).toHaveTextContent('Borrador 34');
  });

  it('shows no summary for a corrida that has no pedidos', async () => {
    render(<PedidosPage />);
    const row = await fila('PED-2026-S40-003');
    expect(within(row).queryByText(/enviadas/)).not.toBeInTheDocument();
  });

  it('warns when the input data of a corrida was invalidated', async () => {
    render(<PedidosPage />);
    expect(within(await fila('PED-2026-S40-008')).getByText('Datos invalidados')).toBeInTheDocument();
    expect(within(await fila('PED-2026-S40-001')).queryByText('Datos invalidados')).not.toBeInTheDocument();
  });

  it('formats the cut date and gives the business tooltips', async () => {
    render(<PedidosPage />);
    const row = await fila('PED-2026-S40-001');
    expect(row).toHaveTextContent('01/10/2026');
    const notas = screen.getAllByRole('note').map((n) => n.getAttribute('aria-label'));
    expect(notas.some((t) => /Estado del pedido/.test(t))).toBe(true);
    expect(notas.some((t) => /PRUEBA/.test(t))).toBe(true);
  });

  it('follows the progress of a corrida being calculated', async () => {
    render(<PedidosPage />);
    const row = await fila('PED-2026-S40-002');
    expect(await within(row).findByText('Sucursal 12 de 47')).toBeInTheDocument();
  });

  it('opens the detail from the code', async () => {
    render(<PedidosPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'PED-2026-S40-001' }));
    expect(pushMock).toHaveBeenCalledWith('/motored/pedidos/c1');
  });
});

describe('Pedidos list - filters and paging', () => {
  it('sends estado, tipo and pedidos filters and returns to page 1', async () => {
    setSession();
    const calls = installFetch(rutas({ 'GET /corridas': jsonRes(pagina(TODAS, { total: 120 })) }));
    render(<PedidosPage />);
    await screen.findByText('PED-2026-S40-001');
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    await waitFor(() => expect(ultimaLista(calls).query.get('offset')).toBe('50'));
    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'BORRADOR' } });
    await waitFor(() => expect(ultimaLista(calls).query.get('estado')).toBe('BORRADOR'));
    expect(ultimaLista(calls).query.get('offset')).toBe('0');
    fireEvent.change(screen.getByLabelText('Tipo'), { target: { value: 'true' } });
    await waitFor(() => expect(ultimaLista(calls).query.get('escenario')).toBe('true'));
    fireEvent.change(screen.getByLabelText('Pedidos'), { target: { value: 'por_enviar' } });
    await waitFor(() => expect(ultimaLista(calls).query.get('pedidos')).toBe('por_enviar'));
  });

  it('sends no filter at first and clears one when set back to Todos', async () => {
    setSession();
    const calls = installFetch(rutas());
    render(<PedidosPage />);
    await screen.findByText('PED-2026-S40-001');
    expect([...ultimaLista(calls).query.keys()].sort()).toEqual(['limite', 'offset']);
    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'FALLIDA' } });
    await waitFor(() => expect(ultimaLista(calls).query.get('estado')).toBe('FALLIDA'));
    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: '' } });
    await waitFor(() => expect(ultimaLista(calls).query.has('estado')).toBe(false));
  });

  it('styles every select option explicitly (dark theme)', async () => {
    setSession();
    installFetch(rutas());
    render(<PedidosPage />);
    await screen.findByText('PED-2026-S40-001');
    const opciones = document.querySelectorAll('select option');
    expect(opciones.length).toBeGreaterThan(8);
    opciones.forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });

  it('pages with limite and offset', async () => {
    setSession();
    const calls = installFetch(rutas({ 'GET /corridas': jsonRes(pagina(TODAS, { total: 120 })) }));
    render(<PedidosPage />);
    await screen.findByText('PED-2026-S40-001');
    expect(screen.getByText(/Página 1 de 3/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    await waitFor(() => expect(ultimaLista(calls).query.get('offset')).toBe('50'));
    expect(ultimaLista(calls).query.get('limite')).toBe('50');
  });
});

describe('Pedidos list - states', () => {
  it('shows the empty message', async () => {
    setSession();
    installFetch(rutas({ 'GET /corridas': jsonRes(pagina([])) }));
    render(<PedidosPage />);
    expect(await screen.findByText('Sin pedidos para mostrar')).toBeInTheDocument();
  });

  it('shows the Spanish error with its code', async () => {
    setSession();
    installFetch(rutas({ 'GET /corridas': coded(409, 'E-CORRIDA-099', 'No se pudo listar.') }));
    render(<PedidosPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo listar. (E-CORRIDA-099)');
  });

  it('shows a loading indicator first', async () => {
    setSession();
    installFetch(rutas());
    render(<PedidosPage />);
    expect(screen.getByText('Cargando...')).toBeInTheDocument();
    await screen.findByText('PED-2026-S40-001');
  });
});

describe('Pedidos list - anular', () => {
  const anular = (row) => within(row).queryByRole('button', { name: 'Anular' });

  it('offers Anular only when no tienda is closed or sent', async () => {
    setSession();
    installFetch(rutas());
    render(<PedidosPage />);
    expect(anular(await fila('PED-2026-S40-001'))).toBeNull();
    expect(anular(await fila('PED-2026-S40-007'))).not.toBeNull();
    expect(anular(await fila('PED-2026-S40-003'))).not.toBeNull();
    expect(anular(await fila('PED-2026-S40-002'))).not.toBeNull();
    expect(anular(await fila('PED-2026-S40-004'))).toBeNull();
    expect(anular(await fila('PED-2026-S40-009'))).toBeNull();
  });

  it('asks for a motivo, explains the protection and anula', async () => {
    setSession();
    const calls = installFetch(rutas({
      'POST /corridas/c7/anular': jsonRes({ id: 'c7', codigo: 'PED-2026-S40-007', estado: 'ANULADA' }),
    }));
    render(<PedidosPage />);
    fireEvent.click(anular(await fila('PED-2026-S40-007')));
    const dialogo = await screen.findByRole('dialog');
    expect(dialogo).toHaveTextContent('PED-2026-S40-007');
    expect(dialogo).toHaveTextContent(/cerradas o enviadas/i);
    const confirmar = within(dialogo).getByRole('button', { name: 'Anular corrida' });
    expect(confirmar).toBeDisabled();
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: '   ' } });
    expect(confirmar).toBeDisabled();
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: ' Datos equivocados ' } });
    fireEvent.click(confirmar);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const post = calls.find((c) => c.method === 'POST');
    expect(post.body).toEqual({ motivo: 'Datos equivocados' });
    const listas = calls.filter((c) => c.path === '/corridas' && c.method === 'GET');
    expect(listas.length).toBeGreaterThanOrEqual(2);
  });

  it('shows the server message when the anulacion is refused (E-CORRIDA-051)', async () => {
    setSession();
    installFetch(rutas({
      'POST /corridas/c7/anular': coded(409, 'E-CORRIDA-051', 'No se puede anular: Pereira (CERRADO) ya tiene su pedido cerrado.'),
    }));
    render(<PedidosPage />);
    fireEvent.click(anular(await fila('PED-2026-S40-007')));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'Prueba' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Anular corrida' }));
    expect(await within(dialogo).findByRole('alert'))
      .toHaveTextContent('No se puede anular: Pereira (CERRADO) ya tiene su pedido cerrado. (E-CORRIDA-051)');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('closes the dialog on Cancelar without calling the API', async () => {
    setSession();
    const calls = installFetch(rutas());
    render(<PedidosPage />);
    fireEvent.click(anular(await fila('PED-2026-S40-007')));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
  });
});
