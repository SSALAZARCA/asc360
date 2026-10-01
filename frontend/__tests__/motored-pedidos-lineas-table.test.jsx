/**
 * Motored Fase 4 (F2a): the line table of the tienda pedido (read-only):
 * columns, edited marker, pack warning, filters that reset the paging,
 * excluded lines, pagination sizes and states.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE, CAB_BORRADOR,
  L_NORMAL, L_EDITADA, L_FUERA, L_EXCLUIDA, paginaLineas,
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

const TRES = [L_NORMAL, L_EDITADA, L_FUERA];
const rutas = (lineas = jsonRes(paginaLineas(TRES))) => ({
  'GET /corridas/c1/sucursales/s1': jsonRes(CAB_BORRADOR),
  'GET /corridas/c1/lineas': lineas,
  'GET /corridas/c1': jsonRes(D_DETALLE),
});
const ultimas = (calls) => [...calls].reverse().find((c) => c.path === '/corridas/c1/lineas');
const tablaLineas = async () => screen.findByRole('table', { name: 'Líneas del pedido' });
const fila = async (codigo) => (await screen.findByText(codigo)).closest('tr');

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
});

describe('lines table - columns and content', () => {
  it('shows exactly the pedido columns, with no Z / ajuste column', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const tabla = await tablaLineas();
    const titulos = within(tabla).getAllByRole('columnheader').map((th) => th.textContent);
    ['Código', 'Nombre', 'Clase', 'Empaque', 'Precio', 'Sugerido', 'Cantidad a pedir', 'Valor', 'Quiebre'].forEach((t) => {
      expect(titulos.some((x) => x.includes(t))).toBe(true);
    });
    expect(titulos).toHaveLength(9);
    expect(tabla).not.toHaveTextContent(/ajuste/i);
  });

  it('has help tooltips on the non-obvious column titles', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const tabla = await tablaLineas();
    ['Clase', 'Empaque', 'Sugerido', 'Cantidad a pedir', 'Valor', 'Quiebre'].forEach((nombre) => {
      expect(within(tabla).getByRole('note', { name: new RegExp(nombre) })).toBeInTheDocument();
    });
  });

  it('renders each line with its code, name, class, pack, price, quantities and stock state', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const f = await fila('94109-12000S');
    expect(f).toHaveTextContent('Filtro de aceite');
    expect(f).toHaveTextContent('AF');
    expect(f).toHaveTextContent(/12/);
    expect(f).toHaveTextContent(/15\.000/);
    expect(f).toHaveTextContent(/720\.000/);
    expect(f).toHaveTextContent('Normal');
    expect(within(await fila('00123-AB')).getByText('Quiebre total')).toBeInTheDocument();
  });

  it('shows the quantity to order as plain text (no input)', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const tabla = await tablaLineas();
    expect(within(tabla).queryAllByRole('textbox')).toHaveLength(0);
    expect(within(tabla).queryAllByRole('spinbutton')).toHaveLength(0);
    expect(within(await fila('55512-A')).getByText('60')).toBeInTheDocument();
  });

  it('marks an edited line with who and when, and leaves the others unmarked', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const editada = await fila('55512-A');
    expect(within(editada).getByRole('note', { name: 'Editado por Compras Uno el 02/10/2026 10:15' })).toBeInTheDocument();
    expect(within(await fila('94109-12000S')).queryByRole('note', { name: /Editado por/ })).not.toBeInTheDocument();
  });

  it('warns when the quantity is not a multiple of the pack, only on that line', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    expect(within(await fila('00123-AB')).getByText('No es múltiplo del empaque (12)')).toBeInTheDocument();
    expect(within(await fila('94109-12000S')).queryByText(/No es múltiplo/)).not.toBeInTheDocument();
  });
});

describe('lines table - filters', () => {
  it('asks only for non-excluded lines by default and shows the excluded ones on request', async () => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    await tablaLineas();
    expect(ultimas(calls).query.has('incluir_excluidas')).toBe(false);
    fireEvent.click(screen.getByLabelText('Mostrar excluidas'));
    await waitFor(() => expect(ultimas(calls).query.get('incluir_excluidas')).toBe('true'));
  });

  it('shows why an excluded line is excluded, read-only', async () => {
    installFetch(rutas(jsonRes(paginaLineas([L_NORMAL, L_EXCLUIDA]))));
    render(<PedidoTiendaPage />);
    const f = await fila('77700-X');
    expect(f).toHaveTextContent('Excluida: Sustituida');
  });

  it('filters by class and quiebre state', async () => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    await tablaLineas();
    fireEvent.change(screen.getByLabelText('Clase'), { target: { value: 'AF' } });
    await waitFor(() => expect(ultimas(calls).query.get('clase')).toBe('AF'));
    fireEvent.change(screen.getByLabelText('Quiebre'), { target: { value: 'BAJO_MINIMO' } });
    await waitFor(() => expect(ultimas(calls).query.get('estado_quiebre')).toBe('BAJO_MINIMO'));
    expect(ultimas(calls).query.get('clase')).toBe('AF');
  });

  it('searches by code or name after the typing pauses (debounced)', async () => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    await tablaLineas();
    const antes = calls.length;
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'fil' } });
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'filtro' } });
    expect(calls.length).toBe(antes);
    await waitFor(() => expect(ultimas(calls).query.get('q')).toBe('filtro'));
    expect(calls.filter((c) => c.path === '/corridas/c1/lineas' && c.query.get('q') === 'fil')).toHaveLength(0);
  });

  it('shows only edited lines on request', async () => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    await tablaLineas();
    fireEvent.click(screen.getByLabelText('Solo editadas'));
    await waitFor(() => expect(ultimas(calls).query.get('solo_editadas')).toBe('true'));
  });

  it('goes back to the first page whenever a filter changes', async () => {
    const calls = installFetch(rutas(jsonRes(paginaLineas(TRES, { total: 120 }))));
    render(<PedidoTiendaPage />);
    await tablaLineas();
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    await waitFor(() => expect(ultimas(calls).query.get('offset')).toBe('50'));
    fireEvent.change(screen.getByLabelText('Clase'), { target: { value: 'CM' } });
    await waitFor(() => expect(ultimas(calls).query.get('clase')).toBe('CM'));
    expect(ultimas(calls).query.get('offset')).toBe('0');
  });

  it('styles every select option explicitly (dark theme)', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    await tablaLineas();
    const opciones = document.querySelectorAll('select option');
    expect(opciones.length).toBeGreaterThan(15);
    opciones.forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });
});

describe('lines table - pagination', () => {
  it('pages 50 lines at a time with limite and offset and counts the lines', async () => {
    const calls = installFetch(rutas(jsonRes(paginaLineas(TRES, { total: 120 }))));
    render(<PedidoTiendaPage />);
    await tablaLineas();
    expect(screen.getByText('Página 1 de 3')).toBeInTheDocument();
    expect(screen.getByText('120 líneas')).toBeInTheDocument();
    expect(ultimas(calls).query.get('limite')).toBe('50');
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    await waitFor(() => expect(ultimas(calls).query.get('offset')).toBe('50'));
  });

  it('offers 50, 100, 200 and 500 per page and goes back to page 1 when it changes', async () => {
    const calls = installFetch(rutas(jsonRes(paginaLineas(TRES, { total: 600 }))));
    render(<PedidoTiendaPage />);
    await tablaLineas();
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    await waitFor(() => expect(ultimas(calls).query.get('offset')).toBe('50'));
    const tamanos = screen.getByLabelText('Por página');
    expect(within(tamanos).getAllByRole('option').map((o) => o.textContent)).toEqual(['50', '100', '200', '500']);
    fireEvent.change(tamanos, { target: { value: '100' } });
    await waitFor(() => expect(ultimas(calls).query.get('limite')).toBe('100'));
    expect(ultimas(calls).query.get('offset')).toBe('0');
  });
});

describe('lines table - states', () => {
  it('shows the empty message when no line matches', async () => {
    installFetch(rutas(jsonRes(paginaLineas([]))));
    render(<PedidoTiendaPage />);
    expect(await screen.findByText('Sin pedidos para mostrar')).toBeInTheDocument();
  });

  it('shows the coded error of the server', async () => {
    installFetch(rutas(coded(409, 'E-CORRIDA-040', 'La corrida no admite lectura.')));
    render(<PedidoTiendaPage />);
    expect(await screen.findByText('La corrida no admite lectura. (E-CORRIDA-040)')).toBeInTheDocument();
  });

  it('shows a loading message while the lines load', async () => {
    installFetch(rutas(new Promise(() => {})));
    render(<PedidoTiendaPage />);
    await screen.findByRole('heading', { name: 'Manizales' });
    expect(screen.getByText('Cargando líneas...')).toBeInTheDocument();
  });
});
