/**
 * Tablero de asesores (feature motored-tablero-asesores, T4): the screen at
 * /motored/tablero-asesores (ADMIN and COMPRAS only).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { installFetch, jsonRes, setSession } from './helpers/pedidosFetch';
import { TABLERO, conSinLinea } from './helpers/tableroAsesoresFetch';

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

import TableroAsesoresPage from '../components/motored/tablero-asesores/TableroAsesoresContent';
import { rangoPorDefecto, validarRango } from '../components/motored/tablero-asesores/rango';

const RUTA = 'GET /tablero-asesores';
const ultima = (calls) => [...calls].reverse().find((c) => c.path === '/tablero-asesores');

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('Tablero de asesores - acceso', () => {
  it.each(['ADMIN', 'COMPRAS'])('muestra el tablero a %s', async (role) => {
    setSession(role);
    installFetch({ [RUTA]: jsonRes(TABLERO) });
    render(<TableroAsesoresPage />);
    expect(await screen.findByText('Ana Pérez')).toBeInTheDocument();
    expect(screen.getByText('Beto Ruiz')).toBeInTheDocument();
    expect(screen.getByText('RESTO COMPAÑÍA (3 vendedores)')).toBeInTheDocument();
    expect(screen.getByText('TOTAL')).toBeInTheDocument();
  });

  it.each(['SUCURSAL', 'CONSULTA'])('manda a %s a Maestros sin pedir datos', async (role) => {
    setSession(role);
    const calls = installFetch({ [RUTA]: jsonRes(TABLERO) });
    render(<TableroAsesoresPage />);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(calls).toHaveLength(0);
    expect(screen.queryByText('Ana Pérez')).not.toBeInTheDocument();
  });
});

describe('Tablero de asesores - tabla', () => {
  beforeEach(() => {
    setSession('ADMIN');
    installFetch({ [RUTA]: jsonRes(TABLERO) });
  });

  it('agrupa las columnas bajo los 8 encabezados', async () => {
    render(<TableroAsesoresPage />);
    await screen.findByText('Ana Pérez');
    const encabezados = screen.getAllByRole('columnheader').map((th) => th.textContent);
    ['Venta', 'Mix', 'Costo', 'Tendencia', 'Facturas', 'Descuentos', 'Clientes', 'Ranking'].forEach((grupo) => {
      expect(encabezados.some((t) => t.startsWith(grupo))).toBe(true);
    });
  });

  it('muestra punto de venta, nombre y cargo de cada persona', async () => {
    render(<TableroAsesoresPage />);
    const fila = (await screen.findByText('Ana Pérez')).closest('tr');
    expect(within(fila).getByText('CALI NORTE')).toBeInTheDocument();
    expect(within(fila).getByText('ASESOR DE REPUESTOS')).toBeInTheDocument();
  });

  it('da formato a pesos, porcentajes y conteos', async () => {
    render(<TableroAsesoresPage />);
    const fila = (await screen.findByText('Ana Pérez')).closest('tr');
    const texto = fila.textContent;
    expect(texto).toMatch(/\$\s?3\.500/); // venta total en pesos
    expect(texto).toMatch(/57,1\s?%/); // % HMCL
    expect(texto).toMatch(/40,0\s?%/); // % margen
    expect(texto).toMatch(/0,88/); // índice contra el promedio
  });

  it('un valor sin dato (None) se ve como raya y no como cero', async () => {
    installFetch({ [RUTA]: jsonRes({ ...TABLERO, filas: [{ ...TABLERO.filas[0], tendencia: { ultimos_3m: null, previos_3m: null, diferencia: null, pct: null } }] }) });
    render(<TableroAsesoresPage />);
    const fila = (await screen.findByText('Ana Pérez')).closest('tr');
    expect(within(fila).getAllByText('—').length).toBeGreaterThanOrEqual(3);
  });

  it('la tabla va dentro del contenedor con desplazamiento horizontal', async () => {
    const { container } = render(<TableroAsesoresPage />);
    await screen.findByText('Ana Pérez');
    expect(container.querySelector('.motored-table-scroll table')).not.toBeNull();
  });

  it('las primeras tres columnas quedan fijas al desplazarse', async () => {
    render(<TableroAsesoresPage />);
    const fila = (await screen.findByText('Ana Pérez')).closest('tr');
    const fijas = [...fila.children].slice(0, 3).map((td) => td.style.position);
    expect(fijas).toEqual(['sticky', 'sticky', 'sticky']);
  });

  describe('en pantallas estrechas (tablet de 768px)', () => {
    const original = window.matchMedia;
    afterEach(() => { window.matchMedia = original; });

    it('solo el asesor queda fijo y va primero, para dejar espacio a los datos', async () => {
      window.matchMedia = jest.fn().mockImplementation((query) => ({
        matches: query === '(max-width: 1023px)', media: query,
        addEventListener: jest.fn(), removeEventListener: jest.fn(),
      }));
      render(<TableroAsesoresPage />);
      const fila = (await screen.findByText('Ana Pérez')).closest('tr');
      const celdas = [...fila.children].slice(0, 3);
      expect(celdas.map((td) => td.textContent)).toEqual(['Ana Pérez', 'CALI NORTE', 'ASESOR DE REPUESTOS']);
      expect(celdas.map((td) => td.style.position)).toEqual(['sticky', '', '']);
      const anchoFijo = Number.parseInt(celdas[0].style.width, 10);
      expect(anchoFijo).toBeLessThanOrEqual(160);
    });
  });

  it('cada encabezado no obvio explica su fórmula en un tooltip', async () => {
    render(<TableroAsesoresPage />);
    await screen.findByText('Ana Pérez');
    const notas = screen.getAllByRole('note').map((n) => n.getAttribute('aria-label'));
    expect(notas.some((t) => /utilidad.*venta con costo/i.test(t))).toBe(true); // % margen
    expect(notas.some((t) => /últimos 3 meses/i.test(t))).toBe(true); // tendencia
    expect(notas.some((t) => /5 clientes/i.test(t))).toBe(true); // % top 5
  });
});

describe('Tablero de asesores - avisos', () => {
  it('avisa cuando hay venta sin línea comercial reconocida', async () => {
    setSession('ADMIN');
    installFetch({ [RUTA]: jsonRes(conSinLinea(700, 0.0769)) });
    render(<TableroAsesoresPage />);
    const aviso = await screen.findByRole('alert');
    expect(aviso).toHaveTextContent(/7,7% de la venta no tiene línea comercial reconocida y no se incluye/);
    expect(aviso.textContent).toMatch(/\$\s?700/);
  });

  it('no avisa cuando toda la venta tiene línea', async () => {
    setSession('ADMIN');
    installFetch({ [RUTA]: jsonRes(TABLERO) });
    render(<TableroAsesoresPage />);
    await screen.findByText('Ana Pérez');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('informa la fecha del inventario usada para los costos', async () => {
    setSession('ADMIN');
    installFetch({ [RUTA]: jsonRes(TABLERO) });
    render(<TableroAsesoresPage />);
    expect(await screen.findByText(/costos.*inventario del 03\/09\/2026/i)).toBeInTheDocument();
  });

  it('dice que no hay costos cuando no hay inventario cargado', async () => {
    setSession('ADMIN');
    installFetch({ [RUTA]: jsonRes({ ...TABLERO, fecha_corte_costos: null }) });
    render(<TableroAsesoresPage />);
    expect(await screen.findByText(/no hay inventario cargado/i)).toBeInTheDocument();
  });

  it('muestra el motivo cuando el servidor rechaza el rango', async () => {
    setSession('ADMIN');
    installFetch({ [RUTA]: jsonRes({ detail: 'El rango no puede pasar de 12 meses.' }, 422) });
    render(<TableroAsesoresPage />);
    expect(await screen.findByText('El rango no puede pasar de 12 meses.')).toBeInTheDocument();
  });

  it('sin ventas en el rango lo dice en lugar de mostrar una tabla vacía', async () => {
    setSession('ADMIN');
    installFetch({ [RUTA]: jsonRes({ ...TABLERO, filas: [] }) });
    render(<TableroAsesoresPage />);
    expect(await screen.findByText(/no hay ventas/i)).toBeInTheDocument();
  });
});

describe('Tablero de asesores - filtros', () => {
  beforeEach(() => setSession('COMPRAS'));

  it('la primera consulta usa los últimos 6 meses y HMCL incluido', async () => {
    const calls = installFetch({ [RUTA]: jsonRes(TABLERO) });
    render(<TableroAsesoresPage />);
    await screen.findByText('Ana Pérez');
    const q = calls[0].query;
    expect(q.get('hmcl')).toBe('incluir');
    expect(q.get('desde')).toMatch(/^\d{4}-\d{2}$/);
    expect(validarRango(q.get('desde'), q.get('hasta'))).toBeNull();
  });

  it('cambiar el mes final o HMCL vuelve a consultar con esos parámetros', async () => {
    const calls = installFetch({ [RUTA]: jsonRes(TABLERO) });
    render(<TableroAsesoresPage />);
    await screen.findByText('Ana Pérez');

    // Both ends are set explicitly: the default range depends on today's date.
    fireEvent.change(screen.getByLabelText('Mes desde'), { target: { value: '2026-03' } });
    fireEvent.change(screen.getByLabelText('Mes hasta'), { target: { value: '2026-08' } });
    await waitFor(() => {
      expect(ultima(calls).query.get('desde')).toBe('2026-03');
      expect(ultima(calls).query.get('hasta')).toBe('2026-08');
    });
    fireEvent.change(screen.getByLabelText('HMCL'), { target: { value: 'solo' } });
    await waitFor(() => expect(ultima(calls).query.get('hmcl')).toBe('solo'));
    expect(ultima(calls).query.get('desde')).toBe('2026-03');
  });

  it('si el rango pasa a ser inválido con una consulta en vuelo, deja de decir "Cargando"', async () => {
    installFetch({ [RUTA]: () => new Promise(() => {}) }); // never answers
    render(<TableroAsesoresPage />);
    expect(await screen.findByText('Cargando...')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Mes desde'), { target: { value: '2099-12' } });

    expect(await screen.findByText(/no puede ser posterior/i)).toBeInTheDocument();
    expect(screen.queryByText('Cargando...')).not.toBeInTheDocument();
  });

  it('al volver a un rango válido consulta de nuevo y muestra el resultado', async () => {
    let respuesta = () => new Promise(() => {});
    const calls = installFetch({ [RUTA]: () => respuesta() });
    render(<TableroAsesoresPage />);
    await screen.findByText('Cargando...');
    const desdeOriginal = screen.getByLabelText('Mes desde').value;

    fireEvent.change(screen.getByLabelText('Mes desde'), { target: { value: '2099-12' } });
    await screen.findByText(/no puede ser posterior/i);
    respuesta = async () => jsonRes(TABLERO);
    fireEvent.change(screen.getByLabelText('Mes desde'), { target: { value: desdeOriginal } });

    expect(await screen.findByText('Ana Pérez')).toBeInTheDocument();
    expect(calls.length).toBeGreaterThanOrEqual(2);
  });

  it('un rango invertido se explica sin consultar al servidor', async () => {
    const calls = installFetch({ [RUTA]: jsonRes(TABLERO) });
    render(<TableroAsesoresPage />);
    await screen.findByText('Ana Pérez');
    const antes = calls.length;

    fireEvent.change(screen.getByLabelText('Mes desde'), { target: { value: '2099-12' } });

    expect(await screen.findByText(/no puede ser posterior/i)).toBeInTheDocument();
    expect(calls).toHaveLength(antes);
  });

  it('todas las opciones del selector HMCL llevan el color explícito del tema oscuro', async () => {
    installFetch({ [RUTA]: jsonRes(TABLERO) });
    render(<TableroAsesoresPage />);
    await screen.findByText('Ana Pérez');
    const opciones = within(screen.getByLabelText('HMCL')).getAllByRole('option');
    expect(opciones.map((o) => o.value)).toEqual(['incluir', 'excluir', 'solo']);
    opciones.forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });
});

describe('rango', () => {
  it('por defecto son los 6 meses que terminan en el mes dado', () => {
    expect(rangoPorDefecto(new Date(2026, 9, 1))).toEqual({ desde: '2026-05', hasta: '2026-10' });
    expect(rangoPorDefecto(new Date(2026, 2, 15))).toEqual({ desde: '2025-10', hasta: '2026-03' });
  });

  it('valida orden y máximo de 12 meses', () => {
    expect(validarRango('2026-01', '2026-12')).toBeNull();
    expect(validarRango('2026-05', '2026-04')).toMatch(/posterior/);
    expect(validarRango('2025-01', '2026-01')).toMatch(/12 meses/);
    expect(validarRango('', '2026-01')).toMatch(/Elija/);
  });
});
