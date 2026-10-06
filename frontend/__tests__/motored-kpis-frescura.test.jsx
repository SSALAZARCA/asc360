import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { installFetch, jsonRes, setSession } from './helpers/pedidosFetch';
import { OPCIONES, VENTAS } from './helpers/kpisVentasFixture';
import { TIENDAS } from './helpers/kpisTiendasFixture';
import { momentoActualizacion, textoActualizado } from '../components/motored/kpis/frescura';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/tablero-asesores',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});
import KpisPage from '../app/motored/tablero-asesores/page';

const ESTADO = '/tablero-asesores/kpis/estado';
const RECALCULAR = '/tablero-asesores/kpis/recalcular';
const ACTUALIZADO = '2026-10-05T15:30:00+00:00'; // 10:30 in Bogota
const estado = (cambios = {}) => ({
  actualizado_en: ACTUALIZADO, sucio: false, reconstruyendo: false,
  ultima_reconstruccion_total: ACTUALIZADO, usando_resumen: false, ...cambios,
});
const rutas = (ventas = VENTAS, extra = {}) => ({
  'GET /tablero-asesores/kpis/opciones': jsonRes(OPCIONES),
  'GET /tablero-asesores/kpis/ventas': jsonRes(ventas),
  'GET /tablero-asesores/kpis/tiendas': jsonRes(TIENDAS),
  ...extra,
});
const conResumen = { ...VENTAS, usando_resumen: true, datos_actualizados_en: ACTUALIZADO };
const sinResumen = { ...VENTAS, usando_resumen: false, datos_actualizados_en: null };
const llamadasA = (calls, ruta, metodo = 'GET') => calls.filter((c) => c.path === ruta && c.method === metodo);

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});
afterEach(() => jest.useRealTimers());

describe('freshness text', () => {
  const ahora = new Date('2026-10-05T20:00:00Z'); // 15:00 in Bogota

  it('shows only the time for today, in Bogota time', () => {
    expect(textoActualizado(ACTUALIZADO, ahora)).toBe('Datos actualizados a las 10:30');
  });

  it('adds the date when the data is from another day', () => {
    // 03:00 UTC on the 3rd is 22:00 on the 2nd in Bogota.
    expect(textoActualizado('2026-10-03T03:00:00+00:00', ahora)).toBe('Datos actualizados el 02/10 a las 22:00');
    expect(momentoActualizacion('2026-10-03T03:00:00+00:00', ahora)).toBe('el 02/10 a las 22:00');
  });

  it('compares the day in Bogota time, not in UTC', () => {
    const tarde = new Date('2026-10-06T03:00:00Z'); // still Oct 5, 22:00 in Bogota
    expect(textoActualizado(ACTUALIZADO, tarde)).toBe('Datos actualizados a las 10:30');
  });

  it('is empty without a valid timestamp', () => {
    expect(textoActualizado(null, ahora)).toBe('');
    expect(textoActualizado('no es fecha', ahora)).toBe('');
  });
});

describe('freshness in the KPI page', () => {
  it('shows the timestamp to a non-admin when the summary answers', async () => {
    setSession('GERENCIA');
    installFetch(rutas(conResumen));
    render(<KpisPage />);
    expect(await screen.findByText(/Datos actualizados (a las|el)/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Recalcular/ })).not.toBeInTheDocument();
  });

  it('shows nothing to a non-admin when the live query answers, and never asks for the estado', async () => {
    setSession('COMPRAS');
    const calls = installFetch(rutas(sinResumen));
    render(<KpisPage />);
    await waitFor(() => expect(llamadasA(calls, '/tablero-asesores/kpis/ventas')).toHaveLength(1));
    await screen.findByRole('tab', { name: 'Ventas' });
    expect(screen.queryByText(/Datos actualizados/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Resumen precalculado/)).not.toBeInTheDocument();
    expect(llamadasA(calls, ESTADO)).toHaveLength(0);
  });

  it.each([
    ['ready', estado(), 'Resumen precalculado: listo (actualizado a las 10:30) · aún no activo'],
    ['building', estado({ reconstruyendo: true, sucio: true }), 'Resumen precalculado: en construcción · aún no activo'],
    ['pending', estado({ ultima_reconstruccion_total: null, actualizado_en: null, sucio: true }), 'Resumen precalculado: pendiente · aún no activo'],
  ])('tells the admin the state of the summary while it is not active (%s)', async (_n, resp, texto) => {
    jest.useFakeTimers().setSystemTime(new Date('2026-10-05T20:00:00Z'));
    setSession('ADMIN');
    installFetch(rutas(sinResumen, { ['GET ' + ESTADO]: jsonRes(resp) }));
    render(<KpisPage />);
    expect(await screen.findByText(texto)).toBeInTheDocument();
  });

  it('shows the admin the timestamp and the Recalcular button when the summary answers', async () => {
    setSession('ADMIN');
    installFetch(rutas(conResumen, { ['GET ' + ESTADO]: jsonRes(estado({ usando_resumen: true })) }));
    render(<KpisPage />);
    expect(await screen.findByText(/Datos actualizados (a las|el)/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recalcular' })).toBeInTheDocument();
    expect(screen.queryByText(/Resumen precalculado/)).not.toBeInTheDocument();
  });
});

describe('Recalcular', () => {
  it('posts, polls the estado every 10 s until it settles and then refreshes the active tab', async () => {
    jest.useFakeTimers({ doNotFake: ['nextTick', 'setImmediate'] });
    setSession('ADMIN');
    const respuestas = [estado({ sucio: true, usando_resumen: true }), estado({ reconstruyendo: true, sucio: true, usando_resumen: true }), estado({ usando_resumen: true })];
    const calls = installFetch(rutas(conResumen, {
      ['GET ' + ESTADO]: () => jsonRes(respuestas.length > 1 ? respuestas.shift() : respuestas[0]),
      ['POST ' + RECALCULAR]: jsonRes(estado({ sucio: true, usando_resumen: true })),
    }));
    render(<KpisPage />);
    const boton = await screen.findByRole('button', { name: 'Recalcular' });
    await waitFor(() => expect(llamadasA(calls, '/tablero-asesores/kpis/ventas')).toHaveLength(1));

    fireEvent.click(boton);
    expect(await screen.findByText('Recalculando…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recalcular' })).toBeDisabled();
    expect(llamadasA(calls, RECALCULAR, 'POST')).toHaveLength(1);

    const estados = () => llamadasA(calls, ESTADO).length;
    const antes = estados();
    await act(async () => { await jest.advanceTimersByTimeAsync(9000); });
    expect(estados()).toBe(antes);
    await act(async () => { await jest.advanceTimersByTimeAsync(1500); });
    expect(estados()).toBe(antes + 1);
    expect(screen.getByText('Recalculando…')).toBeInTheDocument();

    await act(async () => { await jest.advanceTimersByTimeAsync(10000); });
    await waitFor(() => expect(screen.queryByText('Recalculando…')).not.toBeInTheDocument());
    await waitFor(() => expect(llamadasA(calls, '/tablero-asesores/kpis/ventas')).toHaveLength(2));
    const parados = estados();
    await act(async () => { await jest.advanceTimersByTimeAsync(60000); });
    expect(estados()).toBe(parados);
  });

  it('stops polling after about 15 minutes even if the estado never settles', async () => {
    jest.useFakeTimers({ doNotFake: ['nextTick', 'setImmediate'] });
    setSession('ADMIN');
    const colgado = estado({ reconstruyendo: true, sucio: true, usando_resumen: true });
    const calls = installFetch(rutas(conResumen, {
      ['GET ' + ESTADO]: jsonRes(colgado), ['POST ' + RECALCULAR]: jsonRes(colgado),
    }));
    render(<KpisPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Recalcular' }));
    await screen.findByText('Recalculando…');
    await act(async () => { await jest.advanceTimersByTimeAsync(16 * 60 * 1000); });
    const total = llamadasA(calls, ESTADO).length;
    await act(async () => { await jest.advanceTimersByTimeAsync(5 * 60 * 1000); });
    expect(llamadasA(calls, ESTADO)).toHaveLength(total);
    expect(screen.queryByText('Recalculando…')).not.toBeInTheDocument();
  });

  it('shows the 409 message and goes back to the button', async () => {
    setSession('ADMIN');
    const mensaje = 'Los indicadores se están recalculando; intente de nuevo en unos minutos.';
    installFetch(rutas(conResumen, {
      ['GET ' + ESTADO]: jsonRes(estado({ usando_resumen: true })),
      ['POST ' + RECALCULAR]: jsonRes({ detail: mensaje }, 409),
    }));
    render(<KpisPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Recalcular' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(mensaje);
    expect(screen.getByRole('button', { name: 'Recalcular' })).toBeEnabled();
  });
});
