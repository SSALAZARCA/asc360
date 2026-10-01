/**
 * Motored Fase 4 (F4): the budget cap on the pedido screens (TP-08..TP-14b,
 * TP-24..TP-29, UX-25..UX-29). The tienda page shows the excess banner, the
 * lines to cut (highlighted, with the proposed quantity) and "Aplicar recorte"
 * with a confirmation; a stale proposal (E-CORRIDA-060) shows the fresh one; a
 * closed tienda only informs; the corrida detail shows a banner and a column.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE, CAB_BORRADOR, CAB_CERRADO, CAB_ENVIADO, CAB_PRUEBA,
  L_NORMAL, L_EDITADA, L_FUERA, paginaLineas, lineaEditada, PROPUESTA_TOPE, propuestaInactiva,
  topeTienda, TOPES_CORRIDA, T_FALLIDA,
} from './helpers/pedidosFetch';

let params = { id: 'c1', sucursalId: 's1' };
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  useParams: () => params,
  usePathname: () => '/motored/pedidos/c1',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import PedidoTiendaPage from '../app/motored/pedidos/[id]/[sucursalId]/page';
import CorridaDetallePage from '../app/motored/pedidos/[id]/page';

const RECORTE = '/corridas/c1/sucursales/s1/recorte';
const LINEAS = [L_NORMAL, L_EDITADA, L_FUERA];

const rutas = (over = {}, cabecera = CAB_BORRADOR) => ({
  'GET /corridas/c1/sucursales/s1': jsonRes(cabecera),
  'GET /corridas/c1/lineas': jsonRes(paginaLineas(LINEAS)),
  'GET /corridas/c1': jsonRes(D_DETALLE),
  [`GET ${RECORTE}`]: jsonRes(PROPUESTA_TOPE),
  ...over,
});
const lecturas = (calls, path) => calls.filter((c) => c.method === 'GET' && c.path === path);
const banner = () => screen.findByRole('region', { name: 'Tope de presupuesto' });
// The row of a line in the pedido table (the preview of the cuts repeats the codes in its own table).
const filaDe = async (codigo) => within(await screen.findByRole('table', { name: 'Líneas del pedido' })).getByText(codigo).closest('tr');

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
  params = { id: 'c1', sucursalId: 's1' };
});

describe('banner and highlighted lines (UX-25, TP-09, TP-12)', () => {
  it('states the cap, the value and the excess in COP', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const region = await banner();
    expect(region).toHaveTextContent('Pedido por encima del tope de presupuesto');
    expect(region).toHaveTextContent(/5\.310\.000/);
    expect(region).toHaveTextContent(/5\.400\.000/);
    expect(region).toHaveTextContent(/90\.000/);
  });

  it('marks the lines to cut with the proposed quantity and how much is cut, and leaves the others alone', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    await banner();
    expect(within(await filaDe('55512-A')).getByText('Recorte propuesto: 50 (−10)')).toBeInTheDocument();
    expect(within(await filaDe('00123-AB')).getByText('Recorte propuesto: 24 (−6)')).toBeInTheDocument();
    expect(within(await filaDe('94109-12000S')).queryByText(/Recorte propuesto/)).not.toBeInTheDocument();
  });

  it('lists every cut with its class, from and to quantities and the value freed', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    await banner();
    const lista = screen.getByRole('table', { name: 'Líneas que se recortarían' });
    const fila = within(lista).getByText('00123-AB').closest('tr');
    expect(fila).toHaveTextContent('Pastilla de freno');
    expect(fila).toHaveTextContent('BM');
    expect(fila).toHaveTextContent('30');
    expect(fila).toHaveTextContent('24');
    expect(fila).toHaveTextContent(/90\.000/);
    expect(within(lista).getAllByRole('row')).toHaveLength(3);
  });

  it('says how many lines would be cut and how much value they free', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    const region = await banner();
    expect(region).toHaveTextContent('Se recortarían 2 líneas');
    expect(region).toHaveTextContent(/95\.000/);
  });

  it.each([
    [1, '1 línea sin precio no suma al valor'],
    [4, '4 líneas sin precio no suman al valor'],
  ])('tells the user about %i lines without a price (TP-12)', async (n, texto) => {
    installFetch(rutas({ [`GET ${RECORTE}`]: jsonRes({ ...PROPUESTA_TOPE, lineas_sin_precio: n }) }));
    render(<PedidoTiendaPage />);
    expect(await banner()).toHaveTextContent(texto);
  });

  it('does not mention lines without a price when there are none', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    expect(await banner()).not.toHaveTextContent('sin precio');
  });

  it('warns about the residual excess when the cuts are not enough', async () => {
    installFetch(rutas({ [`GET ${RECORTE}`]: jsonRes({ ...PROPUESTA_TOPE, exceso_residual: '12000.00' }) }));
    render(<PedidoTiendaPage />);
    const region = await banner();
    expect(region).toHaveTextContent(/Aun con el recorte quedaría un exceso de.*12\.000/);
    expect(region).toHaveTextContent('clase A y D');
  });

  it('shows no residual warning when the cuts reach the cap', async () => {
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    expect(await banner()).not.toHaveTextContent('Aun con el recorte');
  });

  it('shows the excess without a button when nothing can be cut', async () => {
    installFetch(rutas({
      [`GET ${RECORTE}`]: jsonRes({ ...PROPUESTA_TOPE, recortes: [], valor_final: '5400000.00', exceso_residual: '90000.00', token: 'tok-vacio' }),
    }));
    render(<PedidoTiendaPage />);
    const region = await banner();
    expect(region).toHaveTextContent('No hay líneas que se puedan recortar');
    expect(within(region).queryByRole('button', { name: 'Aplicar recorte' })).not.toBeInTheDocument();
  });
});

describe('no banner when there is nothing to warn about (TP-08, TP-10, TP-11, UX-27)', () => {
  const sinBanner = async (propuesta) => {
    const calls = installFetch(rutas({ [`GET ${RECORTE}`]: jsonRes(propuesta) }));
    render(<PedidoTiendaPage />);
    await screen.findByRole('textbox', { name: 'Cantidad a pedir de 55512-A' });
    await waitFor(() => expect(lecturas(calls, RECORTE)).toHaveLength(1));
    expect(screen.queryByRole('region', { name: 'Tope de presupuesto' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Aplicar recorte' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Recorte propuesto/)).not.toBeInTheDocument();
  };

  it('under the cap', () => sinBanner({ ...PROPUESTA_TOPE, exceso: '0.00', recortes: [], valor_actual: '5000000.00', token: 'tok-0' }));
  it('with the cap mode off', () => sinBanner(propuestaInactiva('MODO_OFF')));
  it('for a tienda without a cap', () => sinBanner(propuestaInactiva('SIN_TOPE')));
});

describe('Aplicar recorte (TP-24, UX-25)', () => {
  const abrirDialogo = async () => {
    const region = await banner();
    fireEvent.click(within(region).getByRole('button', { name: 'Aplicar recorte' }));
    return screen.findByRole('dialog', { name: 'Aplicar recorte al pedido de Manizales' });
  };

  it.each(['COMPRAS', 'ADMIN'])('is offered to %s', async (rol) => {
    setSession(rol);
    installFetch(rutas());
    render(<PedidoTiendaPage />);
    expect(within(await banner()).getByRole('button', { name: 'Aplicar recorte' })).toBeEnabled();
  });

  it('asks for confirmation with the lines, the value freed and the new total, and sends nothing yet', async () => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    const dialogo = await abrirDialogo();
    expect(dialogo).toHaveTextContent('Se recortarán 2 líneas');
    expect(dialogo).toHaveTextContent(/95\.000/);
    expect(dialogo).toHaveTextContent(/5\.305\.000/);
    expect(dialogo).toHaveTextContent('Después puede seguir ajustando a mano');
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0);
  });

  it('cancels without touching anything', async () => {
    const calls = installFetch(rutas());
    render(<PedidoTiendaPage />);
    const dialogo = await abrirDialogo();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0);
  });

  it('applies with the token the user saw, tells the result and reads everything again', async () => {
    const calls = installFetch(rutas({
      [`POST ${RECORTE}`]: jsonRes({
        corrida_id: 'c1', sucursal_id: 's1', tope: '5310000.00', lineas_recortadas: 2, valor_liberado: '95000.00',
        valor_final: '5305000.00', exceso_residual: '0.00', advertencias: [], totales_tienda: {},
      }),
    }));
    render(<PedidoTiendaPage />);
    const dialogo = await abrirDialogo();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Aplicar recorte' }));
    expect(await screen.findByText(/Recorte aplicado: 2 líneas recortadas/)).toHaveTextContent(/95\.000 liberados/);
    expect(calls.find((c) => c.method === 'POST').body).toEqual({ token: 'tok-1' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(lecturas(calls, RECORTE)).toHaveLength(2));
    await waitFor(() => expect(lecturas(calls, '/corridas/c1/lineas').length).toBeGreaterThan(1));
    await waitFor(() => expect(lecturas(calls, '/corridas/c1/sucursales/s1').length).toBeGreaterThan(1));
  });

  it('keeps the lines editable afterwards (TP-29)', async () => {
    installFetch(rutas({
      [`POST ${RECORTE}`]: jsonRes({ lineas_recortadas: 2, valor_liberado: '95000.00', valor_final: '5305000.00', exceso_residual: '0.00' }),
    }));
    render(<PedidoTiendaPage />);
    const dialogo = await abrirDialogo();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Aplicar recorte' }));
    await screen.findByText(/Recorte aplicado/);
    expect(screen.getByRole('textbox', { name: 'Cantidad a pedir de 55512-A' })).toBeEnabled();
  });
});

describe('stale proposal (E-CORRIDA-060, UX-26, TP-25)', () => {
  const FRESCA = {
    ...PROPUESTA_TOPE, token: 'tok-2', exceso: '40000.00', valor_actual: '5350000.00', valor_final: '5305000.00',
    recortes: [PROPUESTA_TOPE.recortes[1]],
  };
  const stale = () => coded(409, 'E-CORRIDA-060', 'La propuesta cambió mientras la revisaba.', { propuesta: FRESCA });

  // Reads after the first one return `siguiente`, as the server would once the proposal changed.
  async function aplicarVieja({ post = stale(), siguiente = FRESCA } = {}) {
    let lecturasRecorte = 0;
    const calls = installFetch(rutas({
      [`GET ${RECORTE}`]: () => jsonRes((lecturasRecorte += 1) === 1 ? PROPUESTA_TOPE : siguiente),
      [`POST ${RECORTE}`]: post,
    }));
    render(<PedidoTiendaPage />);
    fireEvent.click(within(await banner()).getByRole('button', { name: 'Aplicar recorte' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Aplicar recorte al pedido de Manizales' });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Aplicar recorte' }));
    return { calls, dialogo };
  }

  it('keeps the dialog open with the message, its code and the fresh figures', async () => {
    const { dialogo } = await aplicarVieja();
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('La propuesta cambió mientras la revisaba. (E-CORRIDA-060)');
    expect(dialogo).toHaveTextContent('Se recortará 1 línea');
    expect(dialogo).toHaveTextContent(/90\.000/);
    expect(dialogo).toHaveTextContent('propuesta actualizada');
  });

  it('refreshes the banner and the highlights with the fresh proposal', async () => {
    await aplicarVieja();
    await waitFor(() => expect(screen.queryByText('Recorte propuesto: 50 (−10)')).not.toBeInTheDocument());
    expect(within(await filaDe('00123-AB')).getByText('Recorte propuesto: 24 (−6)')).toBeInTheDocument();
  });

  it('applies the fresh proposal on the next confirmation, with the new token', async () => {
    const { calls, dialogo } = await aplicarVieja();
    await within(dialogo).findByRole('alert');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Aplicar recorte' }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST')).toHaveLength(2));
    expect(calls.filter((c) => c.method === 'POST')[1].body).toEqual({ token: 'tok-2' });
  });

  it('closes the dialog and says so when the fresh proposal has nothing left to cut', async () => {
    const vacia = { ...PROPUESTA_TOPE, token: null, exceso: '0.00', recortes: [], valor_actual: '5300000.00' };
    await aplicarVieja({
      post: coded(409, 'E-CORRIDA-060', 'La propuesta cambió mientras la revisaba.', { propuesta: vacia }), siguiente: vacia,
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByRole('alert')).toHaveTextContent('La propuesta cambió mientras la revisaba. (E-CORRIDA-060)');
    expect(screen.queryByText(/Recorte propuesto/)).not.toBeInTheDocument();
  });

  it('reads the proposal again when the error carries no fresh one', async () => {
    const { calls } = await aplicarVieja({ post: coded(409, 'E-CORRIDA-060', 'La propuesta cambió.') });
    await waitFor(() => expect(lecturas(calls, RECORTE)).toHaveLength(2));
  });
});

describe('other rejections of Aplicar recorte', () => {
  async function aplicarRechazado(error) {
    const calls = installFetch(rutas({ [`POST ${RECORTE}`]: error }));
    render(<PedidoTiendaPage />);
    fireEvent.click(within(await banner()).getByRole('button', { name: 'Aplicar recorte' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Aplicar recorte' }));
    return calls;
  }

  it('shows the message with its code on the screen and reads the pedido again (061: it was closed meanwhile)', async () => {
    const calls = await aplicarRechazado(coded(409, 'E-CORRIDA-061', 'El pedido ya no está en Borrador.'));
    expect(await screen.findByText('El pedido ya no está en Borrador. (E-CORRIDA-061)')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(lecturas(calls, '/corridas/c1/sucursales/s1').length).toBeGreaterThan(1));
  });

  it('shows a 058 (mode switched off meanwhile) the same way', async () => {
    await aplicarRechazado(coded(409, 'E-CORRIDA-058', 'El modo tope está apagado.'));
    expect(await screen.findByText('El modo tope está apagado. (E-CORRIDA-058)')).toBeInTheDocument();
  });
});

describe('closed, sent and scenario pedidos (TP-14b, UX-29)', () => {
  const topesDe = (...tiendas) => jsonRes({ activo: true, corrida_id: 'c1', tiendas });

  it.each([
    ['Cerrado', CAB_CERRADO, 's2', 'Pereira', 'CERRADO'],
    ['Enviado', CAB_ENVIADO, 's3', 'Cali', 'ENVIADO'],
  ])('informs about an excess of a %s pedido and offers no recorte', async (_n, cabecera, sid, nombre, estado) => {
    params = { id: 'c1', sucursalId: sid };
    const calls = installFetch(rutas({
      [`GET /corridas/c1/sucursales/${sid}`]: jsonRes(cabecera),
      'GET /corridas/c1/topes': topesDe(topeTienda({ sucursal_id: sid, nombre, estado_pedido: estado, tope: '3000000.00', valor_a_pedir: '3200000.00', exceso: '200000.00' })),
    }));
    render(<PedidoTiendaPage />);
    const region = await banner();
    expect(region).toHaveTextContent('quedó por encima del tope de presupuesto');
    expect(region).toHaveTextContent(/3\.000\.000/);
    expect(region).toHaveTextContent(/200\.000/);
    expect(region).toHaveTextContent('ya no se puede recortar');
    expect(within(region).queryByRole('button', { name: 'Aplicar recorte' })).not.toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith('/recorte'))).toBe(false);
  });

  it('shows nothing for a closed pedido that is within its cap', async () => {
    params = { id: 'c1', sucursalId: 's2' };
    const calls = installFetch(rutas({
      'GET /corridas/c1/sucursales/s2': jsonRes(CAB_CERRADO),
      'GET /corridas/c1/topes': topesDe(topeTienda({ sucursal_id: 's2', estado_pedido: 'CERRADO', exceso: '0.00' })),
    }));
    render(<PedidoTiendaPage />);
    await waitFor(() => expect(lecturas(calls, '/corridas/c1/topes')).toHaveLength(1));
    expect(screen.queryByRole('region', { name: 'Tope de presupuesto' })).not.toBeInTheDocument();
  });

  it('shows nothing for a closed pedido whose tienda has no cap', async () => {
    params = { id: 'c1', sucursalId: 's2' };
    const calls = installFetch(rutas({
      'GET /corridas/c1/sucursales/s2': jsonRes(CAB_CERRADO),
      'GET /corridas/c1/topes': topesDe(topeTienda({ sucursal_id: 's2', estado_pedido: 'CERRADO', tope: null, exceso: null })),
    }));
    render(<PedidoTiendaPage />);
    await waitFor(() => expect(lecturas(calls, '/corridas/c1/topes')).toHaveLength(1));
    expect(screen.queryByRole('region', { name: 'Tope de presupuesto' })).not.toBeInTheDocument();
  });

  it('asks for no cap data at all on a scenario pedido', async () => {
    const calls = installFetch(rutas({}, CAB_PRUEBA));
    render(<PedidoTiendaPage />);
    await screen.findByRole('table', { name: 'Líneas del pedido' });
    expect(calls.some((c) => c.path.endsWith('/recorte') || c.path.endsWith('/topes'))).toBe(false);
  });
});

describe('the banner follows the edits (TP-14)', () => {
  it('reads the proposal again after a manual edit and shows the new excess', async () => {
    let lecturasRecorte = 0;
    const calls = installFetch(rutas({
      [`GET ${RECORTE}`]: () => {
        lecturasRecorte += 1;
        return jsonRes(lecturasRecorte === 1 ? PROPUESTA_TOPE : { ...PROPUESTA_TOPE, token: 'tok-3', valor_actual: '5700000.00', exceso: '390000.00' });
      },
      'PATCH /corridas/c1/lineas/1': lineaEditada(L_NORMAL, 60),
    }));
    render(<PedidoTiendaPage />);
    expect(await banner()).toHaveTextContent(/90\.000/);
    const input = await screen.findByRole('textbox', { name: 'Cantidad a pedir de 94109-12000S' });
    fireEvent.change(input, { target: { value: '60' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(lecturas(calls, RECORTE)).toHaveLength(2));
    await waitFor(() => expect(screen.getByRole('region', { name: 'Tope de presupuesto' })).toHaveTextContent(/390\.000/));
  });
});

describe('corrida detail: banner and Tope column (UX-25, UX-27)', () => {
  const detalle = (topes = TOPES_CORRIDA) => rutas({ 'GET /corridas/c1/topes': jsonRes(topes) });
  const abrir = async (rutasMock = detalle()) => {
    params = { id: 'c1' };
    const calls = installFetch(rutasMock);
    render(<CorridaDetallePage />);
    await screen.findByText('Manizales');
    return calls;
  };

  it('tells how many tiendas are above their cap', async () => {
    await abrir();
    expect(await screen.findByRole('status', { name: 'Tope de presupuesto' })).toHaveTextContent('Modo tope activo: 1 tienda supera su tope de presupuesto.');
  });

  it('uses the plural when several tiendas are above their cap', async () => {
    await abrir(detalle({ ...TOPES_CORRIDA, tiendas: [topeTienda({}), topeTienda({ sucursal_id: 's2', nombre: 'Pereira', exceso: '10.00' })] }));
    expect(await screen.findByRole('status', { name: 'Tope de presupuesto' })).toHaveTextContent('2 tiendas superan su tope de presupuesto.');
  });

  it('says when every tienda is within its cap', async () => {
    await abrir(detalle({ ...TOPES_CORRIDA, tiendas: [topeTienda({ exceso: '0.00' })] }));
    expect(await screen.findByRole('status', { name: 'Tope de presupuesto' })).toHaveTextContent('Ninguna tienda supera su tope');
  });

  it('adds a Tope column with the excess, within the cap, no cap and no pedido', async () => {
    await abrir();
    const tabla = await screen.findByRole('table');
    await waitFor(() => expect(within(tabla).getByText('Tope')).toBeInTheDocument());
    const columna = [...tabla.querySelectorAll('th')].findIndex((th) => th.textContent.startsWith('Tope'));
    const celdas = [...tabla.querySelectorAll('tbody tr')].map((fila) => fila.querySelectorAll('td')[columna]);
    expect(celdas[0]).toHaveTextContent(/Excede.*2\.400\.000/);
    expect(celdas[1]).toHaveTextContent('Dentro del tope');
    expect(celdas[2]).toHaveTextContent('Sin tope');
    expect(celdas[3]).toHaveTextContent('—');
    expect(celdas[3]).not.toHaveTextContent('tope');
  });

  it('explains the column with a tooltip', async () => {
    await abrir();
    expect(await screen.findByRole('note', { name: /^Tope de presupuesto: / })).toBeInTheDocument();
  });

  it('shows no banner and no column when the mode is off', async () => {
    const calls = await abrir(detalle({ activo: false, corrida_id: 'c1', tiendas: [] }));
    await waitFor(() => expect(lecturas(calls, '/corridas/c1/topes')).toHaveLength(1));
    expect(screen.queryByRole('status', { name: 'Tope de presupuesto' })).not.toBeInTheDocument();
    expect(screen.queryByText('Tope')).not.toBeInTheDocument();
  });

  it('keeps the table working when the cap summary cannot be read', async () => {
    await abrir(rutas({ 'GET /corridas/c1/topes': coded(500, 'E-X', 'Falló.') }));
    expect(screen.getByText('Pereira')).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Tope de presupuesto' })).not.toBeInTheDocument();
  });

  it('reads the summary again after a lifecycle change', async () => {
    const calls = await abrir(rutas({
      'GET /corridas/c1/topes': jsonRes(TOPES_CORRIDA),
      'POST /corridas/c1/sucursales/s2/reabrir': jsonRes({ corrida_id: 'c1', sucursal_id: 's2', estado_pedido: 'BORRADOR' }),
    }));
    fireEvent.click(within(screen.getByText('Pereira').closest('tr')).getByRole('button', { name: 'Reabrir' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Reabrir el pedido de Pereira' });
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'Corrección' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Reabrir pedido' }));
    await waitFor(() => expect(lecturas(calls, '/corridas/c1/topes').length).toBeGreaterThan(1));
  });

  it('shows no cap data for a scenario corrida', async () => {
    params = { id: 'c1' };
    const calls = installFetch(rutas({ 'GET /corridas/c1': jsonRes({ ...D_DETALLE, es_escenario: true, sucursales: [T_FALLIDA] }) }));
    render(<CorridaDetallePage />);
    await screen.findByText('Armenia');
    expect(calls.some((c) => c.path.endsWith('/topes'))).toBe(false);
  });
});
