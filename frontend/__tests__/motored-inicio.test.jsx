/**
 * Motored "Inicio": one page, the same for every role that reaches it. The
 * greeting, then four stat boxes (the KPI sales total of the last month and
 * of the year, puntos de venta, asesores with sales last month) with their
 * tooltips, and the loading,
 * unavailable and error states. No links or buttons in the body.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { formatCOP } from '../lib/motored/formatCOP';

// Testing Library normalizes the received text; Intl puts a no-break space after the sign.
const cop = (valor) => formatCOP(valor).replace(/\s/g, ' ');

const mockGetInicio = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/inicio',
}));
jest.mock('../app/motored/motored-layout', () => {
  const Layout = ({ children }) => <div>{children}</div>;
  Layout.displayName = 'MockMotoredLayout';
  return Layout;
});
jest.mock('../lib/motored/inicioApi', () => ({
  getInicio: (...a) => mockGetInicio(...a),
}));

import InicioPage from '../app/motored/inicio/page';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

// Only `Date` is faked, so React and Testing Library keep real timers.
const SOLO_FECHA = {
  doNotFake: [
    'hrtime', 'nextTick', 'performance', 'queueMicrotask', 'requestAnimationFrame',
    'cancelAnimationFrame', 'requestIdleCallback', 'cancelIdleCallback', 'setImmediate',
    'clearImmediate', 'setInterval', 'clearInterval', 'setTimeout', 'clearTimeout',
  ],
};

function relojEn(iso) {
  jest.useFakeTimers({ ...SOLO_FECHA, now: new Date(iso) });
}

const ROLES = ['ADMIN', 'COMPRAS', 'GERENCIA', 'SERVICIO_CLIENTE'];
const MES = 'Ventas del último mes';
const ANIO = 'Ventas acumuladas del año';
const LINEAS = 'Total de las líneas comerciales (repuestos, accesorios, llantas, lubricantes, baterías, GPS y cascos)';
const PUNTOS = 'Puntos de venta';
const ASESORES = 'Asesores';

const RESPUESTA = {
  hoy: '2026-10-06',
  ventas_mes: { disponible: true, valor: 152340000.4, mes: '2026-09' },
  ventas_anio: { disponible: true, valor: 1234567890, desde: '2026-01', hasta: '2026-09' },
  puntos_venta: { disponible: true, cantidad: 12 },
  asesores: { disponible: true, cantidad: 1234, mes: '2026-09' },
};

function entrarComo(rol, nombre = 'Ana María Pérez', cambios = {}) {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ nombre, role: rol }));
  mockGetInicio.mockResolvedValue({ ...RESPUESTA, ...cambios });
  return render(<InicioPage />);
}

async function caja(titulo) {
  await screen.findByTestId('inicio-cifras'); // loaded, not the skeletons
  return screen.getByRole('region', { name: titulo });
}
const ayuda = (region) => within(region).getByRole('note').getAttribute('aria-label');

beforeEach(() => {
  sessionStorage.clear();
  mockGetInicio.mockReset();
  relojEn('2026-10-06T13:00:00Z'); // 08:00 in Bogota
});

afterEach(() => {
  jest.useRealTimers();
});

describe('Inicio - greeting', () => {
  it.each([
    ['2026-10-06T13:00:00Z', 'Buenos días'],
    ['2026-10-06T20:00:00Z', 'Buenas tardes'],
    ['2026-10-07T01:30:00Z', 'Buenas noches'],
  ])('greets by the Bogota hour at %s', async (iso, saludo) => {
    relojEn(iso);
    entrarComo('ADMIN');

    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(`${saludo}, Ana`);
  });

  it('shows the Bogota date in Spanish, not the UTC one', async () => {
    relojEn('2026-10-07T01:30:00Z'); // still Tuesday 6 in Bogota
    entrarComo('ADMIN');

    expect(await screen.findByText('Martes, 6 de octubre de 2026')).toBeInTheDocument();
  });

  it.each([
    ['ADMIN', 'Administrador'],
    ['COMPRAS', 'Compras'],
    ['GERENCIA', 'Gerencia'],
    ['SERVICIO_CLIENTE', 'Servicio al cliente'],
  ])('shows the full name, the initials and the role label of %s', async (rol, etiqueta) => {
    entrarComo(rol);

    expect(await screen.findByText('Ana María Pérez')).toBeInTheDocument();
    expect(screen.getByText('AP')).toBeInTheDocument();
    expect(screen.getByText(etiqueta)).toBeInTheDocument();
  });

  it('falls back to a neutral greeting without a name', async () => {
    entrarComo('COMPRAS', '');

    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Buenos días');
  });
});

describe('Inicio - the four boxes', () => {
  it('shows the KPI sales total of the last complete month in pesos', async () => {
    entrarComo('GERENCIA');

    const region = await caja(MES);
    expect(within(region).getByRole('heading', { level: 2 })).toHaveTextContent(MES);
    expect(region).toHaveTextContent(cop(152340000.4));
    expect(region).toHaveTextContent('Septiembre 2026');
    expect(ayuda(region)).toBe(
      `${LINEAS} en septiembre de 2026, todas las tiendas. Es la misma venta que muestra KPIs.`);
  });

  it('shows the KPI sales total of the "Año corrido" in pesos', async () => {
    entrarComo('ADMIN');

    const region = await caja(ANIO);
    expect(region).toHaveTextContent(cop(1234567890));
    expect(region).toHaveTextContent('Enero a septiembre 2026');
    expect(ayuda(region)).toBe(
      `${LINEAS} de enero a septiembre de 2026, todas las tiendas. Es la misma venta del "Año corrido" de KPIs.`);
  });

  it('names a single month when the year has only January', async () => {
    entrarComo('ADMIN', 'Ana', { ventas_anio: { disponible: true, valor: 5, desde: '2027-01', hasta: '2027-01' } });

    const region = await caja(ANIO);
    expect(region).toHaveTextContent('Enero 2027');
    expect(ayuda(region)).toBe(
      `${LINEAS} en enero de 2027, todas las tiendas. Es la misma venta del "Año corrido" de KPIs.`);
  });

  it('shows the asesores with sales in the last complete month', async () => {
    entrarComo('ADMIN');

    const region = await caja(ASESORES);
    expect(region).toHaveTextContent('Con ventas en septiembre 2026');
    expect(ayuda(region)).toBe(
      'Asesores con venta en septiembre de 2026, los mismos que cuenta KPIs › Asesores.');
  });

  it('shows the counts as plain integers with Colombian separators', async () => {
    entrarComo('COMPRAS');

    const puntos = await caja(PUNTOS);
    expect(within(puntos).getByText('12')).toBeInTheDocument();
    expect(ayuda(puntos)).toMatch(/principales activas/);
    const asesores = await caja(ASESORES);
    expect(within(asesores).getByText('1.234')).toBeInTheDocument();
    expect(ayuda(asesores)).toMatch(/con venta en septiembre de 2026/);
  });

  it('has exactly four level-2 headings, in order', async () => {
    entrarComo('ADMIN');

    await caja(MES);
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual(
      [MES, ANIO, PUNTOS, ASESORES]);
  });

  it('has no links or buttons in the body', async () => {
    entrarComo('ADMIN');

    await caja(MES);
    expect(screen.queryAllByRole('link')).toHaveLength(0);
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('renders the same boxes for every role', async () => {
    const vistas = [];
    for (const rol of ROLES) {
      const { unmount } = entrarComo(rol);
      vistas.push((await screen.findByTestId('inicio-cifras')).innerHTML);
      unmount();
      sessionStorage.clear();
    }

    expect(new Set(vistas).size).toBe(1);
  });
});

describe('Inicio - loading, unavailable and errors', () => {
  it('shows skeletons while loading, with the greeting already there', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ nombre: 'Ana', role: 'ADMIN' }));
    mockGetInicio.mockReturnValue(new Promise(() => {}));
    render(<InicioPage />);

    expect(await screen.findByTestId('inicio-cargando')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Buenos días, Ana');
    expect(screen.queryByText(cop(152340000.4))).not.toBeInTheDocument();
  });

  it('shows an unavailable figure quietly and keeps the others', async () => {
    entrarComo('ADMIN', 'Ana', { ventas_mes: { disponible: false } });

    const region = await caja(MES);
    expect(region).toHaveTextContent('No disponible por ahora');
    expect(ayuda(region)).toBe(
      `${LINEAS} del último mes completo, todas las tiendas. Es la misma venta que muestra KPIs.`);
    expect(await caja(ANIO)).toHaveTextContent(cop(1234567890));
  });

  it('explains the unavailable year and asesores without a month', async () => {
    entrarComo('ADMIN', 'Ana', { ventas_anio: { disponible: false }, asesores: { disponible: false } });

    expect(ayuda(await caja(ANIO))).toBe(
      `${LINEAS} de enero al último mes con ventas, todas las tiendas. Es la misma venta del "Año corrido" de KPIs.`);
    const asesores = await caja(ASESORES);
    expect(asesores).not.toHaveTextContent('Con ventas en');
    expect(ayuda(asesores)).toBe(
      'Asesores con venta en el último mes completo, los mismos que cuenta KPIs › Asesores.');
  });

  it('shows every box as unavailable when the request fails', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ nombre: 'Ana', role: 'ADMIN' }));
    mockGetInicio.mockRejectedValue(new Error('HTTP 500'));
    render(<InicioPage />);

    for (const titulo of [MES, ANIO, PUNTOS, ASESORES]) {
      expect(await caja(titulo)).toHaveTextContent('No disponible por ahora');
    }
  });
});
