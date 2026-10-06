import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { installFetch, jsonRes, setSession } from './helpers/pedidosFetch';
import { OPCIONES, VENTAS } from './helpers/kpisVentasFixture';
import { TIENDAS } from './helpers/kpisTiendasFixture';
import { ASESORES } from './helpers/kpisAsesoresFixture';
import { COMISIONES } from './helpers/kpisComisionesFixture';
import { ASESOR_DETALLE, OPCIONES_ASESORES } from './helpers/kpisAsesorDetalleFixture';

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

const K = '/tablero-asesores/kpis';
const BOGOTA = OPCIONES.tiendas[0].id;
const RUTAS = (extra = {}) => ({
  [`GET ${K}/opciones`]: jsonRes(OPCIONES),
  [`GET ${K}/ventas`]: jsonRes(VENTAS),
  [`GET ${K}/tiendas`]: jsonRes(TIENDAS),
  [`GET ${K}/asesores`]: jsonRes(ASESORES),
  [`GET ${K}/comisiones`]: jsonRes(COMISIONES),
  // The list respects the store filter: with one chosen only the Bogotá asesora is left.
  [`GET ${K}/asesores/opciones`]: (url) => jsonRes(
    url.searchParams.get('sucursales') ? { asesores: [OPCIONES_ASESORES.asesores[0]] } : OPCIONES_ASESORES),
  [`GET ${K}/asesores/detalle`]: jsonRes(ASESOR_DETALLE),
  ...extra,
});
const llamadasA = (calls, ruta) => calls.filter((c) => c.path === `${K}/${ruta}`);

async function abrirAsesores(extra) {
  setSession('GERENCIA');
  const calls = installFetch(RUTAS(extra));
  render(<KpisPage />);
  fireEvent.click(await screen.findByRole('tab', { name: 'Asesores' }));
  expect(await screen.findByRole('region', { name: 'Asesores' })).toBeInTheDocument();
  await waitFor(() => expect(llamadasA(calls, 'asesores/opciones')).toHaveLength(1));
  return calls;
}

async function elegir(nombre) {
  fireEvent.click(screen.getByRole('button', { name: /Todos los asesores/ }));
  const dialogo = screen.getByRole('dialog', { name: 'Elegir asesor' });
  fireEvent.click(within(dialogo).getByRole('button', { name: new RegExp(nombre) }));
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('Asesor filter', () => {
  it('is only on the Asesores tab, as "Todos los asesores" with nothing to clear', async () => {
    setSession('ADMIN');
    installFetch(RUTAS());
    render(<KpisPage />);
    await screen.findByRole('tab', { name: 'Ventas' });
    expect(screen.queryByRole('button', { name: /Todos los asesores/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Asesores' }));
    expect(await screen.findByRole('button', { name: /Todos los asesores/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Quitar asesor y volver a todos' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Tiendas' }));
    expect(screen.queryByRole('button', { name: /Todos los asesores/ })).not.toBeInTheDocument();
  });

  it('loads the options for the active store filter and lists "Nombre · Tienda"', async () => {
    const calls = await abrirAsesores();
    expect(llamadasA(calls, 'asesores/opciones')[0].query.has('sucursales')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: /Todos los asesores/ }));
    const dialogo = screen.getByRole('dialog', { name: 'Elegir asesor' });
    expect(within(dialogo).getByText('Gómez Muñoz Paula')).toBeInTheDocument();
    expect(within(dialogo).getByText('Popayán')).toBeInTheDocument();
    expect(within(dialogo).getByText(/12 asesores/)).toBeInTheDocument();
    expect(within(dialogo).getByRole('button', { name: 'Todos los asesores' })).toBeInTheDocument();
  });

  it('searches by name (ignoring accents and case) and by cédula', async () => {
    await abrirAsesores();
    fireEvent.click(screen.getByRole('button', { name: /Todos los asesores/ }));
    const dialogo = screen.getByRole('dialog', { name: 'Elegir asesor' });
    const buscar = within(dialogo).getByRole('searchbox', { name: 'Buscar asesor' });
    fireEvent.change(buscar, { target: { value: 'jimenez' } });
    expect(within(dialogo).getByText('Jiménez Rangel Yulisa')).toBeInTheDocument();
    expect(within(dialogo).queryByText('Gómez Muñoz Paula')).not.toBeInTheDocument();
    fireEvent.change(buscar, { target: { value: 'a8' } });
    expect(within(dialogo).getByText('Gómez Muñoz Paula')).toBeInTheDocument();
    fireEvent.change(buscar, { target: { value: 'zzz' } });
    expect(within(dialogo).getByText('Ningún asesor coincide.')).toBeInTheDocument();
  });

  it('picking one shows her detail with the same filters and the cédula, and the pill names her', async () => {
    const calls = await abrirAsesores();
    await elegir('Gómez Muñoz Paula');
    expect(await screen.findByRole('region', { name: 'Detalle del asesor' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Elegir asesor' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Gómez Muñoz Paula · Popayán' })).toBeInTheDocument();
    const consulta = llamadasA(calls, 'asesores/detalle')[0].query;
    expect(consulta.get('cedula')).toBe('a8');
    expect(consulta.get('hmcl')).toBe('incluir');
    expect(consulta.get('meses')).toBe('2026-01,2026-02,2026-03,2026-04,2026-05,2026-06,2026-07');
    expect(screen.queryByRole('region', { name: 'Asesores' })).not.toBeInTheDocument();
  });

  it('the ✕ goes back to everyone, and so does "Todos los asesores" in the list', async () => {
    await abrirAsesores();
    await elegir('Gómez Muñoz Paula');
    await screen.findByRole('region', { name: 'Detalle del asesor' });
    fireEvent.click(screen.getByRole('button', { name: 'Quitar asesor y volver a todos' }));
    expect(await screen.findByRole('region', { name: 'Asesores' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Detalle del asesor' })).not.toBeInTheDocument();
    await elegir('Gómez Muñoz Paula');
    await screen.findByRole('region', { name: 'Detalle del asesor' });
    fireEvent.click(screen.getByRole('button', { name: /Gómez Muñoz Paula · Popayán/ }));
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Elegir asesor' })).getByRole('button', { name: 'Todos los asesores' }));
    expect(await screen.findByRole('region', { name: 'Asesores' })).toBeInTheDocument();
  });

  it('keeps the asesor when the period changes and asks the detail again for the new months', async () => {
    const calls = await abrirAsesores();
    await elegir('Gómez Muñoz Paula');
    await screen.findByRole('region', { name: 'Detalle del asesor' });
    fireEvent.click(screen.getByRole('button', { name: /Año corrido/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Último mes' }));
    await waitFor(() => expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(2));
    const consulta = llamadasA(calls, 'asesores/detalle')[1].query;
    expect(consulta.get('meses')).toBe('2026-07');
    expect(consulta.get('cedula')).toBe('a8');
    expect(screen.getByRole('button', { name: 'Gómez Muñoz Paula · Popayán' })).toBeInTheDocument();
  });

  it('clears the asesor when the store filter leaves her out, and the list follows the stores', async () => {
    const calls = await abrirAsesores();
    await elegir('Gómez Muñoz Paula');
    await screen.findByRole('region', { name: 'Detalle del asesor' });
    fireEvent.click(screen.getByRole('button', { name: /Toda la red/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('checkbox', { name: /Bogotá Av. Boyacá/ }));
    await waitFor(() => expect(llamadasA(calls, 'asesores/opciones')).toHaveLength(2));
    expect(llamadasA(calls, 'asesores/opciones')[1].query.get('sucursales')).toBe(BOGOTA);
    expect(await screen.findByRole('region', { name: 'Asesores' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Todos los asesores/ })).toBeInTheDocument();
  });

  it('keeps her when the new store filter still includes her', async () => {
    await abrirAsesores();
    await elegir('Jiménez Rangel Yulisa');
    await screen.findByRole('region', { name: 'Detalle del asesor' });
    fireEvent.click(screen.getByRole('button', { name: /Toda la red/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('checkbox', { name: /Bogotá Av. Boyacá/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /Jiménez Rangel Yulisa · Bogotá 1 de Mayo/ })).toBeInTheDocument());
    expect(screen.getByRole('region', { name: 'Detalle del asesor' })).toBeInTheDocument();
  });

  it('styles the list items explicitly so the text shows on the dark theme', async () => {
    await abrirAsesores();
    fireEvent.click(screen.getByRole('button', { name: /Todos los asesores/ }));
    const dialogo = screen.getByRole('dialog', { name: 'Elegir asesor' });
    const item = within(dialogo).getByRole('button', { name: /Gómez Muñoz Paula/ });
    expect(item.style.color).not.toBe('');
    expect(item.style.background).not.toBe('');
  });
});

describe('Todos los asesores', () => {
  it('shows the hint to pick an asesor', async () => {
    await abrirAsesores();
    expect(screen.getByText('Elegí un asesor para ver su detalle')).toBeInTheDocument();
  });

  it('every name of the Top 10, the Bottom 10 and the Tecnired list selects that asesor', async () => {
    const calls = await abrirAsesores();
    const top = screen.getByRole('region', { name: 'Top 10 · venta' });
    fireEvent.click(within(top).getByRole('button', { name: 'Jiménez Rangel Yulisa' }));
    expect(await screen.findByRole('region', { name: 'Detalle del asesor' })).toBeInTheDocument();
    expect(llamadasA(calls, 'asesores/detalle')[0].query.get('cedula')).toBe('a1');
  });

  it('selects from the Bottom 10 and the Tecnired list too', async () => {
    const calls = await abrirAsesores();
    fireEvent.click(within(screen.getByRole('region', { name: 'Bottom 10 · cumplimiento' })).getAllByRole('button')[0]);
    await screen.findByRole('region', { name: 'Detalle del asesor' });
    fireEvent.click(screen.getByRole('button', { name: 'Quitar asesor y volver a todos' }));
    await screen.findByRole('region', { name: 'Asesores' });
    const tecnired = screen.getByRole('region', { name: 'Tecnired por asesor' });
    fireEvent.click(within(tecnired).getAllByTestId('tecnired-fila')[0].querySelector('button'));
    await waitFor(() => expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(2));
    expect(llamadasA(calls, 'asesores/detalle')[1].query.get('cedula')).toMatch(/^a\d+$/);
  });
});

describe('Detail states', () => {
  it('shows a Spanish message when the asesor is not found with the chosen filters', async () => {
    await abrirAsesores({ [`GET ${K}/asesores/detalle`]: jsonRes({ detail: 'Asesor no encontrado' }, 404) });
    await elegir('Gómez Muñoz Paula');
    expect(await screen.findByText('No encontramos a este asesor con los filtros elegidos.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Quitar asesor y volver a todos' })).toBeInTheDocument();
  });

  it('shows the general error when the detail cannot be loaded', async () => {
    await abrirAsesores({ [`GET ${K}/asesores/detalle`]: jsonRes({ detail: 'x' }, 500) });
    await elegir('Gómez Muñoz Paula');
    expect(await screen.findByText(/No pudimos cargar los KPI's/)).toBeInTheDocument();
  });

  it('caches the detail per asesor and filters: going back to the same one does not fetch again', async () => {
    const calls = await abrirAsesores();
    await elegir('Gómez Muñoz Paula');
    await screen.findByRole('region', { name: 'Detalle del asesor' });
    fireEvent.click(screen.getByRole('button', { name: 'Quitar asesor y volver a todos' }));
    await screen.findByRole('region', { name: 'Asesores' });
    await elegir('Gómez Muñoz Paula');
    await screen.findByRole('region', { name: 'Detalle del asesor' });
    expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(1);
    expect(llamadasA(calls, 'asesores')).toHaveLength(1);
  });
});
