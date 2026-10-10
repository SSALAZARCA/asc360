/** "Traslados por recibir · tu tienda": the asesor card on the public link and in the staff KPI view, next to the invoices card. */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AsesorDetalle from '../components/motored/kpis/asesores/AsesorDetalle';
import { ASESOR_DETALLE } from './helpers/kpisAsesorDetalleFixture';
import { traslado, RECIBIDO, SIN_CONFIRMAR, NO_LLEGA } from './helpers/trasladosFixture';

jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn(), replace: jest.fn() }), usePathname: () => '/motored/informe/tok123' }));

const respuesta = (status, body = {}) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const bloque = (items) => ({ ultima_carga: '2026-10-09T12:40:00Z', items, resumen: { pendientes: items.length, recibidos_sin_erp: items.filter((i) => i.estado === 'RECIBIDO').length } });
const texto = (t) => (_, el) => el.tagName === 'SPAN' && el.textContent === t;
const tarjeta = () => screen.findByRole('region', { name: 'Traslados por recibir' });
const llamadas = () => global.fetch.mock.calls.map(([url, opts]) => ({ url, opts, body: opts?.body ? JSON.parse(opts.body) : null }));
const delTraslado = () => llamadas().filter((c) => c.url.includes('/traslados'));

/** Routes the fetch by URL: `rutas[fragment]` is a response or a function; unknown URLs get an empty invoices block. */
let rutas;
beforeEach(() => {
  sessionStorage.clear();
  rutas = {};
  global.fetch = jest.fn(async (url) => {
    const clave = Object.keys(rutas).sort((a, b) => b.length - a.length).find((k) => url.includes(k));
    const r = clave ? rutas[clave] : respuesta(200, { verificable_desde: null, items: [] });
    return typeof r === 'function' ? r() : r;
  });
});

describe('traslados card on the public link', () => {
  const montar = () => render(<AsesorDetalle data={ASESOR_DETALLE} enlace={{ token: 'tok123', cedula: '123' }} />);

  it('asks the public endpoint with the cédula and lists the rows', async () => {
    rutas['/traslados'] = respuesta(200, bloque([SIN_CONFIRMAR, RECIBIDO]));
    montar();
    const card = await tarjeta();
    await within(card).findByText(/2 traslados pendientes/);
    expect(within(card).getByText('1 recibidos sin cargar al ERP')).toBeInTheDocument();
    expect(within(card).getByText(texto('79-00000082 · 02/09 · 37 días · 2 und'))).toBeInTheDocument();
    expect(within(card).getByText('Desde Bogotá Av. Caracas')).toBeInTheDocument();
    expect(within(card).getByText(/Carlos Ruiz · 05\/10 10:20/)).toBeInTheDocument();
    expect(within(card).getByText('Sale solo cuando el ERP lo recibe')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Más información' })).toHaveAttribute('title', expect.stringContaining('siguen vivos en el ERP'));
    const [llamada] = delTraslado();
    expect(llamada.url).toMatch(/\/api\/motored\/publico\/informe\/tok123\/traslados$/);
    expect(llamada.opts.method).toBe('POST');
    expect(llamada.body).toEqual({ cedula: '123' });
    expect(JSON.stringify(llamada.opts.headers)).not.toMatch(/authorization/i);
  });

  it('shows the ERP notice only on received rows', async () => {
    rutas['/traslados'] = respuesta(200, bloque([SIN_CONFIRMAR, RECIBIDO, NO_LLEGA]));
    montar();
    const card = await tarjeta();
    await within(card).findByText(/3 traslados pendientes/);
    const filas = within(card).getAllByRole('listitem');
    expect(filas.map((f) => within(f).queryByText('Recíbelo en el ERP') !== null)).toEqual([false, true, false]);
    expect(within(filas[2]).getByRole('button', { name: 'No ha llegado' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('POSTs the answer with the cédula and updates the row', async () => {
    const user = userEvent.setup();
    rutas['/traslados'] = respuesta(200, bloque([SIN_CONFIRMAR]));
    rutas['/traslados/confirmar'] = respuesta(200, { ...SIN_CONFIRMAR, estado: 'RECIBIDO', aviso_erp: true, confirmado_por: 'Paula Gómez', confirmado_en: '2026-10-09T14:00:00Z' });
    montar();
    const card = await tarjeta();
    await user.click(await within(card).findByRole('button', { name: 'Recibido' }));
    const post = delTraslado().find((c) => c.url.endsWith('/traslados/confirmar'));
    expect(post.body).toEqual({ cedula: '123', documento: '79-00000082', bodega_salida: 'B-1', bodega_entrada: 'E-1', estado: 'RECIBIDO' });
    expect(await within(card).findByText('Recíbelo en el ERP')).toBeInTheDocument();
    expect(within(card).getByText(/Paula Gómez/)).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Recibido' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('puts the choice back with the message when the save fails', async () => {
    const user = userEvent.setup();
    rutas['/traslados'] = respuesta(200, bloque([SIN_CONFIRMAR]));
    rutas['/traslados/confirmar'] = respuesta(409);
    montar();
    const card = await tarjeta();
    await user.click(await within(card).findByRole('button', { name: 'No ha llegado' }));
    await waitFor(() => expect(within(card).getByRole('alert')).toHaveTextContent('Este traslado ya no está pendiente.'));
    expect(within(card).getByRole('button', { name: 'No ha llegado' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('shows the empty message when nothing is pending', async () => {
    rutas['/traslados'] = respuesta(200, bloque([]));
    montar();
    expect(await screen.findByText('Sin traslados pendientes')).toBeInTheDocument();
  });

  it('shows a retry message when the load fails and loads again on retry', async () => {
    const user = userEvent.setup();
    rutas['/traslados'] = respuesta(500);
    montar();
    expect(await screen.findByText('No se pudieron cargar los traslados.')).toBeInTheDocument();
    rutas['/traslados'] = respuesta(200, bloque([traslado('79-00000099')]));
    await user.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText(/1 traslados pendientes/)).toBeInTheDocument();
  });

  it('does not ask again when the link object is re-created with the same token and cédula', async () => {
    rutas['/traslados'] = respuesta(200, bloque([SIN_CONFIRMAR]));
    const { rerender } = render(<AsesorDetalle data={ASESOR_DETALLE} enlace={{ token: 'tok123', cedula: '123' }} />);
    await tarjeta();
    const pedidos = () => delTraslado().filter((c) => c.url.endsWith('/traslados')).length;
    expect(pedidos()).toBe(1);
    rerender(<AsesorDetalle data={ASESOR_DETALLE} enlace={{ token: 'tok123', cedula: '123' }} />);
    await tarjeta();
    expect(pedidos()).toBe(1);
    rerender(<AsesorDetalle data={ASESOR_DETALLE} enlace={{ token: 'tok123', cedula: '456' }} />);
    await waitFor(() => expect(pedidos()).toBe(2));
  });

  it('places both cards in one two-column container', async () => {
    rutas['/traslados'] = respuesta(200, bloque([SIN_CONFIRMAR]));
    montar();
    const contenedor = await screen.findByTestId('pendientes-asesor');
    expect(contenedor).toHaveStyle({ display: 'grid' });
    expect(contenedor.style.gridTemplateColumns).toMatch(/auto-fit/);
    expect(await within(contenedor).findByRole('region', { name: 'Traslados por recibir' })).toBeInTheDocument();
  });
});

describe('traslados card in the staff asesor view', () => {
  const entrar = (role) => sessionStorage.setItem('motored_user', JSON.stringify({ role }));
  const staff = () => render(<AsesorDetalle data={ASESOR_DETALLE} />);

  it('reads the store list for the asesor sucursal, next to the invoices card', async () => {
    entrar('ADMIN');
    rutas['/ingresos-facturas/asesor'] = respuesta(200, { verificable_desde: '2026-09-24', items: [], resumen: {} });
    rutas['/traslados/asesor'] = respuesta(200, bloque([SIN_CONFIRMAR]));
    staff();
    const card = await tarjeta();
    expect(await within(card).findByText(texto('79-00000082 · 02/09 · 37 días · 2 und'))).toBeInTheDocument();
    expect(delTraslado()[0].url).toMatch(/\/gestion-repuestos\/traslados\/asesor\?sucursal=s-pop$/);
    const contenedor = screen.getByTestId('pendientes-asesor');
    expect(within(contenedor).getByRole('region', { name: 'Pedidos por ingresar' })).toBeInTheDocument();
  });

  it.each(['COMPRAS', 'GERENCIA'])('is read-only for %s', async (role) => {
    entrar(role);
    rutas['/traslados/asesor'] = respuesta(200, bloque([RECIBIDO]));
    staff();
    const card = await tarjeta();
    await within(card).findByText(/1 traslados pendientes/);
    expect(within(card).queryByRole('button', { name: 'Recibido' })).not.toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: 'No ha llegado' })).not.toBeInTheDocument();
  });

  it.each(['ADMIN', 'COORDINADOR_REPUESTOS', 'ANALISTA_ADMINISTRATIVO'])('%s confirms through the staff endpoint', async (role) => {
    const user = userEvent.setup();
    entrar(role);
    rutas['/traslados/asesor'] = respuesta(200, bloque([SIN_CONFIRMAR]));
    rutas['/traslados/confirmar'] = respuesta(200, { ...SIN_CONFIRMAR, estado: 'NO_HA_LLEGADO', confirmado_por: 'Coord', confirmado_en: '2026-10-09T14:00:00Z' });
    staff();
    const card = await tarjeta();
    await user.click(await within(card).findByRole('button', { name: 'No ha llegado' }));
    const post = delTraslado().find((c) => c.url.endsWith('/gestion-repuestos/traslados/confirmar'));
    expect(post.opts.method).toBe('POST');
    expect(post.body).toEqual({ documento: '79-00000082', bodega_salida: 'B-1', bodega_entrada: 'E-1', estado: 'NO_HA_LLEGADO' });
    await waitFor(() => expect(within(card).getByText(/Coord/)).toBeInTheDocument());
  });

  it('hides the card when the role cannot read it (403) but keeps it on other failures', async () => {
    entrar('SERVICIO_CLIENTE');
    rutas['/traslados/asesor'] = respuesta(403, { detail: 'No tiene permisos para realizar esta acción.' });
    const { unmount } = staff();
    await waitFor(() => expect(delTraslado()).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Traslados por recibir' })).not.toBeInTheDocument());
    unmount();
    rutas['/traslados/asesor'] = respuesta(500);
    staff();
    expect(await screen.findByText('No se pudieron cargar los traslados.')).toBeInTheDocument();
  });
});
