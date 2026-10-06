/**
 * Motored "Inicio": greeting, "Para hoy" cards per role, "Ir a" links taken
 * from the sidebar, "Estado de los datos" (ADMIN and COMPRAS only), and the
 * loading, error and unavailable states.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';

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
import { menuItemsFor } from '../components/motored/MotoredSidebar';
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

const DATOS = [
  { tipo: 'INVENTARIO', fecha: '2026-09-29', antiguedad_dias: 6, limite_dias: 7, vence: '2026-10-06', vence_cuando: 'manana', estado: 'por_vencer' },
  { tipo: 'BACKORDER', fecha: '2026-09-27', antiguedad_dias: 8, limite_dias: 7, vence: '2026-10-04', vence_cuando: null, estado: 'vencido' },
  { tipo: 'FACTURAS_PEDIDOS', fecha: '2026-10-04', antiguedad_dias: 1, limite_dias: 7, vence: '2026-10-11', vence_cuando: null, estado: 'al_dia' },
  { tipo: 'INGRESOS_FACTURAS', fecha: null, antiguedad_dias: null, limite_dias: 7, vence: null, vence_cuando: null, estado: 'sin_datos' },
  { tipo: 'VENTAS', fecha: '2026-09-30', antiguedad_dias: 5, limite_dias: null, vence: '2026-10-31', vence_cuando: null, estado: 'al_dia' },
];

const SECCIONES = {
  pedidos_borrador: { disponible: true, corrida_id: 'c-1', codigo: 'PED-2026-S41-001', tiendas: 3, total: 5 },
  datos_por_vencer: { disponible: true, cantidad: 3, por_vencer: 1, vencidos: 1, sin_datos: 1, datos: DATOS },
  detractores_sin_gestionar: { disponible: true, cantidad: 7 },
  ultimo_pedido_enviado: { disponible: true, corrida_id: 'c-0', codigo: 'PED-2026-S40-002', enviadas: 4, total: 5 },
  venta_mes: {
    disponible: true, estado: 'ok', mes: '2026-10', venta: 1500000, presupuesto: 2000000, pct: 0.75,
    semaforo: 'violeta', usando_resumen: true, datos_actualizados_en: '2026-10-05T12:30:00+00:00',
  },
  tiendas_verde: { disponible: true, cantidad: 4, total: 9, desde_pct: 100 },
  tiendas_rojo: { disponible: true, cantidad: 2, total: 9, menor_a_pct: 90 },
  encuestas_mes: { disponible: true, cargas: 2, registros: 340, ultima_carga: '2026-10-03T14:00:00+00:00' },
};

const POR_ROL = {
  ADMIN: ['pedidos_borrador', 'datos_por_vencer', 'detractores_sin_gestionar'],
  COMPRAS: ['pedidos_borrador', 'datos_por_vencer', 'ultimo_pedido_enviado'],
  GERENCIA: ['venta_mes', 'tiendas_verde', 'tiendas_rojo'],
  SERVICIO_CLIENTE: ['detractores_sin_gestionar', 'encuestas_mes'],
};

function respuesta(rol, cambios = {}) {
  const secciones = Object.fromEntries(POR_ROL[rol].map((n) => [n, SECCIONES[n]]));
  return { rol, hoy: '2026-10-05', secciones: { ...secciones, ...cambios } };
}

function entrarComo(rol, nombre = 'Ana María Pérez', cambios = {}) {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ nombre, role: rol }));
  mockGetInicio.mockResolvedValue(respuesta(rol, cambios));
  render(<InicioPage />);
}

async function tarjetas() {
  const seccion = await screen.findByRole('region', { name: 'Para hoy' });
  return within(seccion).getAllByRole('link');
}

beforeEach(() => {
  sessionStorage.clear();
  mockGetInicio.mockReset();
  relojEn('2026-10-05T13:00:00Z'); // 08:00 in Bogota
});

afterEach(() => {
  jest.useRealTimers();
});

describe('Inicio - greeting', () => {
  it.each([
    ['2026-10-05T13:00:00Z', 'Buenos días'],
    ['2026-10-05T20:00:00Z', 'Buenas tardes'],
    ['2026-10-06T01:30:00Z', 'Buenas noches'],
  ])('greets by the Bogota hour at %s', async (iso, saludo) => {
    relojEn(iso);
    entrarComo('ADMIN');

    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(`${saludo}, Ana`);
  });

  it('shows the Bogota date in Spanish, not the UTC one', async () => {
    relojEn('2026-10-06T01:30:00Z'); // still Monday 5 in Bogota
    entrarComo('ADMIN');

    expect(await screen.findByText('Lunes, 5 de octubre de 2026')).toBeInTheDocument();
  });

  it('shows the full name, the initials and the role label', async () => {
    entrarComo('SERVICIO_CLIENTE');

    expect(await screen.findByText('Ana María Pérez')).toBeInTheDocument();
    expect(screen.getByText('AP')).toBeInTheDocument();
    expect(screen.getByText('Servicio al cliente')).toBeInTheDocument();
  });

  it('falls back to a neutral greeting without a name', async () => {
    entrarComo('COMPRAS', '');

    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Buenos días');
    expect(screen.getByText('Compras')).toBeInTheDocument();
  });
});

describe('Inicio - "Para hoy" cards per role', () => {
  it('shows ADMIN its three cards with real numbers and links', async () => {
    entrarComo('ADMIN');
    const links = await tarjetas();

    expect(links).toHaveLength(3);
    expect(links[0]).toHaveTextContent('Pedidos en borrador');
    expect(links[0]).toHaveTextContent('3 tiendas');
    expect(links[0]).toHaveTextContent('PED-2026-S41-001');
    expect(links[0]).toHaveAttribute('href', '/motored/pedidos/c-1');
    expect(links[1]).toHaveTextContent('Datos por vencer');
    expect(links[1]).toHaveTextContent('3 cargas');
    expect(links[1]).toHaveTextContent('Backorder está vencido');
    expect(links[1]).toHaveAttribute('href', '/motored/maestros?tab=backorder');
    expect(links[2]).toHaveTextContent('Detractores sin gestionar');
    expect(links[2]).toHaveTextContent('7');
    expect(links[2]).toHaveAttribute('href', '/motored/detractores');
  });

  it('shows COMPRAS the last sent pedido', async () => {
    entrarComo('COMPRAS');
    const links = await tarjetas();

    expect(links.map((a) => a.querySelector('[data-titulo]').textContent)).toEqual([
      'Pedidos en borrador', 'Datos por vencer', 'Último pedido enviado',
    ]);
    expect(links[2]).toHaveTextContent('PED-2026-S40-002');
    expect(links[2]).toHaveTextContent('4 de 5 tiendas enviadas');
    expect(links[2]).toHaveAttribute('href', '/motored/pedidos/c-0');
  });

  it('shows GERENCIA the month against budget and the tiendas by color', async () => {
    entrarComo('GERENCIA');
    const links = await tarjetas();

    expect(links).toHaveLength(3);
    expect(links[0]).toHaveTextContent('Venta del mes');
    expect(links[0]).toHaveTextContent('75% del presupuesto a hoy');
    expect(links[0]).toHaveTextContent('Datos de ventas al 07:30');
    expect(links[0]).toHaveAttribute('href', '/motored/tablero-asesores');
    expect(links[1]).toHaveTextContent('4 de 9');
    expect(links[1]).toHaveTextContent('Cumplimiento igual o mayor al 100%');
    expect(links[2]).toHaveTextContent('Tiendas en rojo');
    expect(links[2]).toHaveTextContent('Cumplimiento menor al 90%');
  });

  it('asks GERENCIA to load the budgets when the month has none', async () => {
    entrarComo('GERENCIA', 'G', {
      venta_mes: { disponible: true, estado: 'sin_presupuesto', mes: '2026-10', venta: 10, usando_resumen: false, datos_actualizados_en: null },
    });
    const links = await tarjetas();

    expect(links[0]).toHaveTextContent('Cargá los presupuestos del mes');
    expect(links[0]).toHaveAttribute('href', '/motored/maestros?tab=presupuestos');
    expect(links[0]).not.toHaveTextContent('Datos de ventas al');
  });

  it('shows SERVICIO_CLIENTE the detractors and the surveys of the month', async () => {
    entrarComo('SERVICIO_CLIENTE');
    const links = await tarjetas();

    expect(links).toHaveLength(2);
    expect(links[0]).toHaveTextContent('Detractores sin gestionar');
    expect(links[1]).toHaveTextContent('Encuestas cargadas este mes');
    expect(links[1]).toHaveTextContent('340');
    expect(links[1]).toHaveTextContent('Última carga: 03/10/2026');
    expect(links[1]).toHaveAttribute('href', '/motored/encuesta-satisfaccion');
  });

  it('shows an unavailable section quietly and keeps the others', async () => {
    entrarComo('ADMIN', 'Ana', { detractores_sin_gestionar: { disponible: false } });
    const links = await tarjetas();

    expect(links).toHaveLength(2);
    const seccion = screen.getByRole('region', { name: 'Para hoy' });
    expect(within(seccion).getByText('Detractores sin gestionar')).toBeInTheDocument();
    expect(within(seccion).getByText('No disponible por ahora')).toBeInTheDocument();
  });
});

describe('Inicio - "Ir a"', () => {
  it.each(Object.keys(POR_ROL))('lists the sidebar entries %s sees, without Inicio or the account page', async (rol) => {
    entrarComo(rol);
    const seccion = await screen.findByRole('region', { name: 'Ir a' });
    const esperados = menuItemsFor({ role: rol })
      .flatMap((i) => i.children || [i])
      .filter((i) => !['inicio', 'mi-cuenta'].includes(i.id));

    const links = within(seccion).getAllByRole('link');
    expect(links.map((a) => a.getAttribute('href'))).toEqual(esperados.map((i) => i.path));
    links.forEach((a, n) => expect(a).toHaveTextContent(esperados[n].name));
  });
});

describe('Inicio - "Estado de los datos"', () => {
  it.each(['ADMIN', 'COMPRAS'])('shows %s one tile per data type with its state', async (rol) => {
    entrarComo(rol);
    const seccion = await screen.findByRole('region', { name: 'Estado de los datos' });
    const tiles = within(seccion).getAllByRole('link');

    expect(tiles.map((t) => t.querySelector('[data-nombre]').textContent)).toEqual([
      'Inventario', 'Backorder', 'Facturas de pedidos', 'Ingresos de facturas', 'Ventas',
    ]);
    expect(tiles[0]).toHaveTextContent('Corte 29/09/2026');
    expect(tiles[0]).toHaveTextContent('Vence mañana');
    expect(tiles[1]).toHaveTextContent('Vencida');
    expect(tiles[2]).toHaveTextContent('Aplicada 04/10/2026');
    expect(tiles[2]).toHaveTextContent('Al día');
    expect(tiles[3]).toHaveTextContent('Sin datos');
    expect(tiles[4]).toHaveTextContent('Hasta septiembre 2026');
    expect(tiles[0]).toHaveAttribute('href', '/motored/maestros?tab=inventario');
  });

  it.each(['GERENCIA', 'SERVICIO_CLIENTE'])('is not shown to %s', async (rol) => {
    entrarComo(rol);
    await screen.findByRole('region', { name: 'Para hoy' });

    expect(screen.queryByRole('region', { name: 'Estado de los datos' })).not.toBeInTheDocument();
  });

  it('says the block is unavailable when the staleness section failed', async () => {
    entrarComo('ADMIN', 'Ana', { datos_por_vencer: { disponible: false } });
    const seccion = await screen.findByRole('region', { name: 'Estado de los datos' });

    expect(within(seccion).getByText('No disponible por ahora')).toBeInTheDocument();
  });
});

describe('Inicio - loading and errors', () => {
  it('shows skeletons while loading', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ nombre: 'Ana', role: 'ADMIN' }));
    mockGetInicio.mockReturnValue(new Promise(() => {}));
    render(<InicioPage />);

    expect(await screen.findByTestId('inicio-cargando')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Buenos días, Ana');
  });

  it('shows a Spanish message when the request fails', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ nombre: 'Ana', role: 'ADMIN' }));
    mockGetInicio.mockRejectedValue(new Error('HTTP 500'));
    render(<InicioPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos cargar tu resumen');
    // The quick links do not depend on the request.
    expect(screen.getByRole('region', { name: 'Ir a' })).toBeInTheDocument();
  });
});
