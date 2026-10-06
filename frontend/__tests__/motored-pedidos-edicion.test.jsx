/**
 * Motored Fase 4 (F2b): inline edit of "Cantidad a pedir" on the tienda pedido
 * (UX-13, UX-14, UX-15, UX-17; ED-01..ED-14): Enter or blur saves, Escape
 * cancels, whole numbers only, the row is locked while saving, optimistic
 * value with rollback and the coded Spanish error, 066 refreshes the line,
 * the pack warning, and plain text when the pedido cannot be edited.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE,
  CAB_BORRADOR, CAB_CERRADO, CAB_ENVIADO, CAB_PRUEBA,
  L_NORMAL, L_EDITADA, L_FUERA, L_EXCLUIDA, paginaLineas, lineaEditada,
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

const CAB_ACTUALIZADA = {
  ...CAB_BORRADOR,
  totales: { unidades_a_pedir: '1022.00', valor_a_pedir: '5580000.00', unidades_sugerido: '1000.00', valor_sugerido: '5000000.00' },
};

const rutas = (over = {}, cabecera = CAB_BORRADOR, lineas = [L_NORMAL, L_EDITADA, L_FUERA, L_EXCLUIDA]) => ({
  'GET /corridas/c1/sucursales/s1': jsonRes(cabecera),
  'GET /corridas/c1/lineas': jsonRes(paginaLineas(lineas)),
  'GET /corridas/c1': jsonRes(D_DETALLE),
  ...over,
});

const entrada = async (codigo) => screen.findByRole('textbox', { name: `Cantidad a pedir de ${codigo}` });
const escribir = (input, texto) => fireEvent.change(input, { target: { value: texto } });
const enter = (input) => fireEvent.keyDown(input, { key: 'Enter' });
const patches = (calls) => calls.filter((c) => c.method === 'PATCH');
const lecturas = (calls, path) => calls.filter((c) => c.method === 'GET' && c.path === path);

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
});

describe('inline edit - who gets an input', () => {
  it('gives an input to every orderable line of an editable pedido, started on the saved quantity', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    expect(await entrada('94109-12000S')).toHaveValue('48');
    expect(await entrada('55512-A')).toHaveValue('60');
    expect(await entrada('00123-AB')).toHaveValue('30');
  });

  it('keeps the input labelled with the line code (reachable by a screen reader)', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    expect(input).toHaveAttribute('inputmode', 'numeric');
  });

  it('shows an excluded line as plain text, with no input', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    await entrada('94109-12000S');
    expect(screen.queryByRole('textbox', { name: 'Cantidad a pedir de 77700-X' })).not.toBeInTheDocument();
    expect(within(screen.getByText('77700-X').closest('tr')).getByText('Excluida: Sustituida')).toBeInTheDocument();
  });

  it.each([['Cerrado', CAB_CERRADO], ['Enviado', CAB_ENVIADO], ['escenario', CAB_PRUEBA]])(
    'shows plain text, with no input, for a %s pedido (UX-15)', async (_nombre, cabecera) => {
      installFetch(rutas({}, cabecera));
      render(<PedidoTiendaPage />);
      const tabla = await screen.findByRole('table', { name: 'Líneas del pedido' });
      expect(within(tabla).queryAllByRole('textbox')).toHaveLength(0);
      expect(within(screen.getByText('55512-A').closest('tr')).getByText('60')).toBeInTheDocument();
    },
  );
});

describe('inline edit - saving', () => {
  it('saves on Enter with the value the screen saw, and shows the refreshed line (UX-13)', async () => {
    const calls = installFetch(rutas({ 'PATCH /corridas/c1/lineas/1': lineaEditada(L_NORMAL, 60) }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '60');
    enter(input);
    await waitFor(() => expect(patches(calls)).toHaveLength(1));
    expect(patches(calls)[0].path).toBe('/corridas/c1/lineas/1');
    expect(patches(calls)[0].body).toEqual({ pedido_final: 60, esperado: '48.00' });
    const fila = screen.getByText('94109-12000S').closest('tr');
    await waitFor(() => expect(within(fila).getByRole('note', { name: 'Editado por Compras Uno el 02/10/2026 05:15' })).toBeInTheDocument());
    expect(within(fila).getByRole('textbox')).toHaveValue('60');
    expect(fila).toHaveTextContent(/900\.000/);
  });

  it('saves when the input loses focus', async () => {
    const calls = installFetch(rutas({ 'PATCH /corridas/c1/lineas/1': lineaEditada(L_NORMAL, 72) }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '72');
    fireEvent.blur(input);
    await waitFor(() => expect(patches(calls)).toHaveLength(1));
    expect(patches(calls)[0].body).toEqual({ pedido_final: 72, esperado: '48.00' });
  });

  it('cancels on Escape: nothing is sent and the saved quantity comes back', async () => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '99');
    expect(input).toHaveValue('99');
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(input).toHaveValue('48');
    fireEvent.blur(input);
    expect(patches(calls)).toHaveLength(0);
  });

  it('does not call the server when the quantity did not change', async () => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '48');
    enter(input);
    fireEvent.blur(input);
    escribir(input, '048');
    fireEvent.blur(input);
    expect(patches(calls)).toHaveLength(0);
    expect(input).toHaveValue('48');
  });

  it('saves a zero (ED-04)', async () => {
    const calls = installFetch(rutas({ 'PATCH /corridas/c1/lineas/1': lineaEditada(L_NORMAL, 0) }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '0');
    enter(input);
    await waitFor(() => expect(patches(calls)).toHaveLength(1));
    expect(patches(calls)[0].body.pedido_final).toBe(0);
  });

  it('refreshes the totals and the class summary after a save', async () => {
    let guardado = false;
    const calls = installFetch(rutas({
      'PATCH /corridas/c1/lineas/1': () => { guardado = true; return lineaEditada(L_NORMAL, 60); },
      'GET /corridas/c1/sucursales/s1': () => jsonRes(guardado ? CAB_ACTUALIZADA : CAB_BORRADOR),
    }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    expect(screen.getByText('1.010 uds')).toBeInTheDocument();
    escribir(input, '60');
    enter(input);
    expect(await screen.findByText('1.022 uds')).toBeInTheDocument();
    expect(lecturas(calls, '/corridas/c1/sucursales/s1').length).toBeGreaterThanOrEqual(2);
    expect(lecturas(calls, '/corridas/c1').length).toBeGreaterThanOrEqual(2);
  });
});

describe('inline edit - whole numbers only', () => {
  it.each([
    ['2.5', /números enteros/],
    ['abc', /números enteros/],
    ['-1', /números enteros/],
    ['', /Escriba la cantidad/],
    ['10000000', /máximo es 9\.999\.999/],
  ])('rejects %j on the screen, without calling the server', async (texto, mensaje) => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, texto);
    enter(input);
    expect(await screen.findByRole('alert')).toHaveTextContent(mensaje);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveValue(texto);
    expect(patches(calls)).toHaveLength(0);
  });

  it('clears the message and the saved quantity returns on Escape', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '2.5');
    enter(input);
    await screen.findByRole('alert');
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(input).toHaveValue('48');
    expect(input).not.toHaveAttribute('aria-invalid', 'true');
  });

  it('accepts the quantity once it is fixed', async () => {
    const calls = installFetch(rutas({ 'PATCH /corridas/c1/lineas/1': lineaEditada(L_NORMAL, 25) }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '2.5');
    enter(input);
    await screen.findByRole('alert');
    escribir(input, '25');
    enter(input);
    await waitFor(() => expect(patches(calls)).toHaveLength(1));
    expect(patches(calls)[0].body.pedido_final).toBe(25);
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });
});

describe('inline edit - row locked while saving, optimistic value', () => {
  const lento = () => {
    const control = {};
    control.respuesta = new Promise((resolver) => { control.resolver = resolver; });
    return control;
  };

  it('shows the new value at once, locks the row, and ignores typing and a second save', async () => {
    const control = lento();
    const calls = installFetch(rutas({ 'PATCH /corridas/c1/lineas/1': () => control.respuesta }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '60');
    enter(input);
    await waitFor(() => expect(input).toHaveAttribute('aria-busy', 'true'));
    expect(input).toHaveAttribute('readonly');
    expect(input).toHaveValue('60');
    escribir(input, '99');
    enter(input);
    fireEvent.blur(input);
    expect(input).toHaveValue('60');
    expect(patches(calls)).toHaveLength(1);
    await act(async () => { control.resolver(lineaEditada(L_NORMAL, 60)); });
    await waitFor(() => expect(input).not.toHaveAttribute('aria-busy', 'true'));
    expect(input).not.toHaveAttribute('readonly');
  });

  it('only locks the row being saved', async () => {
    const control = lento();
    installFetch(rutas({ 'PATCH /corridas/c1/lineas/1': () => control.respuesta }));
    render(<PedidoTiendaPage />);
    const primera = await entrada('94109-12000S');
    const otra = await entrada('55512-A');
    escribir(primera, '60');
    enter(primera);
    await waitFor(() => expect(primera).toHaveAttribute('aria-busy', 'true'));
    expect(otra).not.toHaveAttribute('readonly');
    expect(otra).not.toHaveAttribute('aria-busy', 'true');
    await act(async () => { control.resolver(lineaEditada(L_NORMAL, 60)); });
  });
});

describe('inline edit - server rejections', () => {
  it.each([
    ['E-CORRIDA-053', 422, 'La cantidad debe estar entre 0 y 9.999.999.'],
    ['E-CORRIDA-054', 409, 'La línea está excluida y no se puede editar.'],
  ])('rolls back and shows the message with its code for %s', async (codigo, status, mensaje) => {
    installFetch(rutas({ 'PATCH /corridas/c1/lineas/1': coded(status, codigo, mensaje) }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '60');
    enter(input);
    expect(await screen.findByRole('alert')).toHaveTextContent(`${mensaje} (${codigo})`);
    expect(input).toHaveValue('48');
    expect(input).not.toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('94109-12000S').closest('tr')).toHaveTextContent(/720\.000/);
  });

  it('on 052 (the pedido is not a draft any more) rolls back, says why and reloads the header', async () => {
    let cerrado = false;
    const calls = installFetch(rutas({
      'PATCH /corridas/c1/lineas/1': () => {
        cerrado = true;
        return coded(409, 'E-CORRIDA-052', 'El pedido de la tienda no está en borrador.');
      },
      'GET /corridas/c1/sucursales/s1': () => jsonRes(cerrado ? CAB_CERRADO : CAB_BORRADOR),
    }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '60');
    enter(input);
    await waitFor(() => expect(lecturas(calls, '/corridas/c1/sucursales/s1').length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.queryAllByRole('textbox')).toHaveLength(0));
    const fila = screen.getByText('94109-12000S').closest('tr');
    expect(within(fila).getAllByText('48')).toHaveLength(2);
    expect(within(fila).getByRole('alert')).toHaveTextContent('El pedido de la tienda no está en borrador. (E-CORRIDA-052)');
  });

  it('on 066 (stale quantity) shows the server message and refreshes the line from the server', async () => {
    let lecturasDeLineas = 0;
    installFetch(rutas({
      'PATCH /corridas/c1/lineas/1': coded(409, 'E-CORRIDA-066', 'La cantidad cambió mientras la editaba. Se muestra el valor actual.'),
      'GET /corridas/c1/lineas': () => {
        lecturasDeLineas += 1;
        const primera = { ...L_NORMAL };
        const fresca = { ...L_NORMAL, pedido_final: '55.00', valor_pedido: '825000.00' };
        return jsonRes(paginaLineas([lecturasDeLineas === 1 ? primera : fresca, L_EDITADA]));
      },
    }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '60');
    enter(input);
    expect(await screen.findByRole('alert')).toHaveTextContent('La cantidad cambió mientras la editaba. Se muestra el valor actual. (E-CORRIDA-066)');
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Cantidad a pedir de 94109-12000S' })).toHaveValue('55'));
    expect(lecturasDeLineas).toBe(2);
  });

  it('on a network failure rolls back and shows a generic message', async () => {
    installFetch(rutas({ 'PATCH /corridas/c1/lineas/1': () => { throw new TypeError('Failed to fetch'); } }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '60');
    enter(input);
    expect(await screen.findByRole('alert')).toHaveTextContent(/No se pudo guardar la cantidad/);
    expect(input).toHaveValue('48');
  });

  it('clears the previous error when the user starts a new save', async () => {
    let intento = 0;
    installFetch(rutas({
      'PATCH /corridas/c1/lineas/1': () => {
        intento += 1;
        return intento === 1 ? coded(422, 'E-CORRIDA-053', 'Cantidad inválida.') : lineaEditada(L_NORMAL, 60);
      },
    }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    escribir(input, '60');
    enter(input);
    await screen.findByRole('alert');
    escribir(input, '60');
    enter(input);
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(input).toHaveValue('60');
  });
});

describe('inline edit - pack warning (UX-17) and edit marks', () => {
  it('shows the warning after saving a quantity that is not a pack multiple', async () => {
    installFetch(rutas({
      'PATCH /corridas/c1/lineas/1': lineaEditada(L_NORMAL, 30),
    }));
    render(<PedidoTiendaPage />);
    const input = await entrada('94109-12000S');
    const fila = screen.getByText('94109-12000S').closest('tr');
    expect(within(fila).queryByText(/No es múltiplo/)).not.toBeInTheDocument();
    escribir(input, '30');
    enter(input);
    expect(await within(fila).findByText('No es múltiplo del empaque (12)')).toBeInTheDocument();
  });

  it('keeps showing the warning of a line the server already flagged, next to its input', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const input = await entrada('00123-AB');
    expect(input).toHaveValue('30');
    expect(within(input.closest('tr')).getByText('No es múltiplo del empaque (12)')).toBeInTheDocument();
  });

  it('removes the warning when the quantity becomes a multiple', async () => {
    installFetch(rutas({ 'PATCH /corridas/c1/lineas/3': lineaEditada(L_FUERA, 36) }));
    render(<PedidoTiendaPage />);
    const input = await entrada('00123-AB');
    escribir(input, '36');
    enter(input);
    await waitFor(() => expect(within(input.closest('tr')).queryByText(/No es múltiplo/)).not.toBeInTheDocument());
  });

  it('keeps the Historial button of an edited line and opens its history', async () => {
    installFetch(rutas({
      'GET /corridas/c1/lineas/2/historial': jsonRes([]),
    }));
    render(<PedidoTiendaPage />);
    const input = await entrada('55512-A');
    fireEvent.click(within(input.closest('tr')).getByRole('button', { name: 'Historial de la línea 55512-A' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });
});
