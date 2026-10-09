import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AsesorDetalle from '../components/motored/kpis/asesores/AsesorDetalle';
import InformeContainer from '../components/motored/informe/InformeContainer';
import { cuandoDe, valorCorto } from '../components/motored/kpis/asesores/pendientes';
import { ASESOR_DETALLE } from './helpers/kpisAsesorDetalleFixture';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  usePathname: () => '/motored/informe/tok123',
}));

const item = (numero, extra = {}) => ({
  prefijo_rh: 'RH', numero_rh: numero, factura: `RH ${numero}`, sucursal_id: 's-pop', tienda: 'Popayán',
  fecha: '2026-09-28', dias: 12, unidades: 3, valor: 1200000, estado: 'SIN_CONFIRMAR', confirmado_por: null, confirmado_en: null, ...extra,
});
const bloque = (items, desde = '2026-09-24') => ({
  verificable_desde: desde, items,
  resumen: { pendientes: items.length, llegaron_sin_ingresar: items.filter((i) => i.estado === 'LLEGO').length },
});
const respuesta = (status, body = {}) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const tarjeta = () => screen.findByRole('region', { name: 'Pedidos por ingresar' });

const conBloque = (b) => ({ ...ASESOR_DETALLE, pendientes_ingreso: b });
const llamadas = () => global.fetch.mock.calls.map(([url, opts]) => ({ url, opts, body: opts?.body ? JSON.parse(opts.body) : null }));

beforeEach(() => {
  global.fetch = jest.fn();
  sessionStorage.clear();
});

describe('pending invoices card on the public link', () => {
  const montar = (b) => render(<AsesorDetalle data={conBloque(b)} enlace={{ token: 'tok123', cedula: '123' }} />);

  it('lists the rows as one-line summaries with the totals and the footer', async () => {
    montar(bloque([item(482915), item(478301, { estado: 'LLEGO', confirmado_por: 'Juan Pérez', confirmado_en: '2026-09-30T14:15:00Z', valor: 642000, dias: 1, fecha: '2026-10-07' })]));
    const card = await tarjeta();
    expect(within(card).getByText(/2 facturas pendientes/)).toBeInTheDocument();
    expect(within(card).getByText('1 llegaron sin ingresar')).toBeInTheDocument();
    expect(within(card).getByText('RH 482915 · 28/09 · 12 días · $1,2 M')).toBeInTheDocument();
    expect(within(card).getByText('RH 478301 · 07/10 · 1 día · $642 mil')).toBeInTheDocument();
    expect(within(card).getByText(/Juan Pérez · 30\/09 09:15/)).toBeInTheDocument();
    expect(within(card).getByText(/Verificable desde 24\/09 · sale sola al ingresarse/)).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Más información' })).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('marks the selected answer as pressed', async () => {
    montar(bloque([item(1, { estado: 'NO_HA_LLEGADO', confirmado_por: 'Ana', confirmado_en: '2026-10-01T12:00:00Z' })]));
    const card = await tarjeta();
    expect(within(card).getByRole('button', { name: 'No ha llegado' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(card).getByRole('button', { name: 'Llegó' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('POSTs the answer to the public endpoint with the cédula and updates the row', async () => {
    const user = userEvent.setup();
    global.fetch.mockResolvedValue(respuesta(200, item(482915, { estado: 'LLEGO', confirmado_por: 'Paula Gómez', confirmado_en: '2026-10-08T14:00:00Z' })));
    montar(bloque([item(482915)]));
    const card = await tarjeta();
    await user.click(within(card).getByRole('button', { name: 'Llegó' }));
    await waitFor(() => expect(within(card).getByText('1 llegaron sin ingresar')).toBeInTheDocument());
    const [llamada] = llamadas();
    expect(llamada.url).toMatch(/\/api\/motored\/publico\/informe\/tok123\/pendientes$/);
    expect(llamada.opts.method).toBe('POST');
    expect(llamada.body).toEqual({ cedula: '123', factura: 'RH 482915', estado: 'LLEGO' });
    expect(JSON.stringify(llamada.opts.headers)).not.toMatch(/authorization/i);
    expect(within(card).getByRole('button', { name: 'Llegó' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(card).getByText(/Paula Gómez/)).toBeInTheDocument();
  });

  it('shows the choice at once and puts it back with a message when the save fails', async () => {
    const user = userEvent.setup();
    let fallar;
    global.fetch.mockReturnValue(new Promise((_, rechazar) => { fallar = rechazar; }));
    montar(bloque([item(482915)]));
    const card = await tarjeta();
    await user.click(within(card).getByRole('button', { name: 'No ha llegado' }));
    expect(within(card).getByRole('button', { name: 'No ha llegado' })).toHaveAttribute('aria-pressed', 'true');
    fallar(new TypeError('network'));
    await waitFor(() => expect(within(card).getByRole('button', { name: 'No ha llegado' })).toHaveAttribute('aria-pressed', 'false'));
    expect(within(card).getByRole('alert')).toHaveTextContent('No pudimos guardar tu respuesta. Intenta de nuevo.');
  });

  it.each([
    [401, 'Enlace o cédula no válidos.'],
    [429, 'Demasiados intentos. Intenta de nuevo en unos minutos.'],
    [409, 'Esta factura ya no está pendiente.'],
  ])('maps a %i answer to its message and reverts', async (status, mensaje) => {
    const user = userEvent.setup();
    global.fetch.mockResolvedValue(respuesta(status));
    montar(bloque([item(482915)]));
    const card = await tarjeta();
    await user.click(within(card).getByRole('button', { name: 'Llegó' }));
    await waitFor(() => expect(within(card).getByRole('alert')).toHaveTextContent(mensaje));
    expect(within(card).getByRole('button', { name: 'Llegó' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('shows the empty message when nothing is pending but data is verifiable', async () => {
    montar(bloque([]));
    expect(await screen.findByText('No tienes facturas pendientes por ingresar.')).toBeInTheDocument();
  });

  it('hides the card when nothing can be verified or the block is missing', () => {
    const { unmount } = montar(bloque([], null));
    expect(screen.queryByRole('region', { name: 'Pedidos por ingresar' })).not.toBeInTheDocument();
    unmount();
    render(<AsesorDetalle data={ASESOR_DETALLE} enlace={{ token: 't', cedula: '1' }} />);
    expect(screen.queryByRole('region', { name: 'Pedidos por ingresar' })).not.toBeInTheDocument();
  });

  it('InformeContainer keeps the cédula in state, passes it on and writes no storage', async () => {
    const user = userEvent.setup();
    const setItem = jest.spyOn(Storage.prototype, 'setItem');
    global.fetch
      .mockResolvedValueOnce(respuesta(200, conBloque(bloque([item(482915)]))))
      .mockResolvedValueOnce(respuesta(200, item(482915, { estado: 'LLEGO', confirmado_por: 'Paula', confirmado_en: '2026-10-08T14:00:00Z' })));
    render(<InformeContainer token="tok123" />);
    await user.type(screen.getByLabelText('Tu cédula'), '123456');
    await user.click(screen.getByRole('button', { name: 'Ver mi informe' }));
    const card = await tarjeta();
    await user.click(within(card).getByRole('button', { name: 'Llegó' }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
    expect(llamadas()[1].body).toEqual({ cedula: '123456', factura: 'RH 482915', estado: 'LLEGO' });
    expect(setItem).not.toHaveBeenCalled();
    expect(document.cookie).toBe('');
    setItem.mockRestore();
  });
});

describe('pending invoices card in the staff asesor view', () => {
  const entrar = (role) => sessionStorage.setItem('motored_user', JSON.stringify({ role }));
  const staff = () => render(<AsesorDetalle data={ASESOR_DETALLE} />);

  it('reads the store pending list for the asesor sucursal', async () => {
    entrar('ADMIN');
    global.fetch.mockResolvedValue(respuesta(200, bloque([item(482915)])));
    staff();
    const card = await tarjeta();
    expect(within(card).getByText('RH 482915 · 28/09 · 12 días · $1,2 M')).toBeInTheDocument();
    expect(llamadas()[0].url).toMatch(/\/gestion-repuestos\/ingresos-facturas\/asesor\?sucursal=s-pop$/);
  });

  it.each(['COMPRAS', 'GERENCIA'])('is read-only for %s (no buttons)', async (role) => {
    entrar(role);
    global.fetch.mockResolvedValue(respuesta(200, bloque([item(482915, { estado: 'LLEGO', confirmado_por: 'Ana', confirmado_en: '2026-10-01T12:00:00Z' })])));
    staff();
    const card = await tarjeta();
    expect(within(card).queryByRole('button', { name: 'Llegó' })).not.toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: 'No ha llegado' })).not.toBeInTheDocument();
    expect(within(card).getByText(/Ana/)).toBeInTheDocument();
  });

  it.each(['ADMIN', 'COORDINADOR_REPUESTOS'])('%s gets the buttons and confirms through the staff endpoint', async (role) => {
    const user = userEvent.setup();
    entrar(role);
    global.fetch
      .mockResolvedValueOnce(respuesta(200, bloque([item(482915)])))
      .mockResolvedValueOnce(respuesta(200, item(482915, { estado: 'NO_HA_LLEGADO', confirmado_por: 'Coord', confirmado_en: '2026-10-08T14:00:00Z' })));
    staff();
    const card = await tarjeta();
    await user.click(within(card).getByRole('button', { name: 'No ha llegado' }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
    const post = llamadas()[1];
    expect(post.url).toMatch(/\/gestion-repuestos\/ingresos-facturas\/confirmar$/);
    expect(post.opts.method).toBe('POST');
    expect(post.body).toEqual({ factura: 'RH 482915', sucursal_id: 's-pop', estado: 'NO_HA_LLEGADO' });
    await waitFor(() => expect(within(card).getByText(/Coord/)).toBeInTheDocument());
  });

  it('reverts and explains when the staff confirmation fails', async () => {
    const user = userEvent.setup();
    entrar('COORDINADOR_REPUESTOS');
    global.fetch
      .mockResolvedValueOnce(respuesta(200, bloque([item(482915)])))
      .mockResolvedValueOnce(respuesta(409, { detail: 'Esta factura ya no está pendiente de ingreso.' }));
    staff();
    const card = await tarjeta();
    await user.click(within(card).getByRole('button', { name: 'Llegó' }));
    await waitFor(() => expect(within(card).getByRole('alert')).toHaveTextContent('Esta factura ya no está pendiente'));
    expect(within(card).getByRole('button', { name: 'Llegó' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('hides the card when the role is not allowed (403) or nothing is verifiable', async () => {
    entrar('SERVICIO_CLIENTE');
    global.fetch.mockResolvedValue(respuesta(403, { detail: 'No tiene permisos para realizar esta acción.' }));
    const { unmount } = staff();
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Pedidos por ingresar' })).not.toBeInTheDocument());
    unmount();
    global.fetch.mockResolvedValue(respuesta(200, bloque([], null)));
    staff();
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('region', { name: 'Pedidos por ingresar' })).not.toBeInTheDocument();
  });
});

describe('pending card formats', () => {
  const ahora = new Date('2026-10-08T20:00:00Z'); // 15:00 in Bogota
  it('says hoy, ayer or the date for when it was answered', () => {
    expect(cuandoDe('2026-10-08T14:15:00Z', ahora)).toBe('hoy 09:15');
    expect(cuandoDe('2026-10-07T22:40:00Z', ahora)).toBe('ayer 17:40');
    expect(cuandoDe('2026-10-01T12:00:00Z', ahora)).toBe('01/10 07:00');
    expect(cuandoDe(null, ahora)).toBeNull();
  });
  it('shortens the value', () => {
    expect(valorCorto(1200000)).toBe('$1,2 M');
    expect(valorCorto(642000)).toBe('$642 mil');
    expect(valorCorto(null)).toBe('—');
  });
});
