/** "Gestión repuestos > Traslados": cards, per-store table, filters, detail with history and confirm buttons. */
import React from 'react';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ITEMS, ULTIMA_CARGA, RECIBIDO, SIN_CONFIRMAR } from './helpers/trasladosFixture';

jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }), usePathname: () => '/motored/gestion-repuestos/traslados' }));

const mockApi = { getTrasladosDetalle: jest.fn(), getTrasladosHistorial: jest.fn(), confirmarTraslado: jest.fn() };
jest.mock('../lib/motored/gestionRepuestosApi', () => ({
  getTrasladosDetalle: (...a) => mockApi.getTrasladosDetalle(...a),
  getTrasladosHistorial: (...a) => mockApi.getTrasladosHistorial(...a),
  confirmarTraslado: (...a) => mockApi.confirmarTraslado(...a),
}));

import TrasladosContainer from '../components/motored/gestion-repuestos/TrasladosContainer';

beforeEach(() => {
  sessionStorage.clear();
  Object.values(mockApi).forEach((f) => f.mockReset());
  mockApi.getTrasladosDetalle.mockResolvedValue({ ultima_carga: ULTIMA_CARGA, items: ITEMS });
  mockApi.getTrasladosHistorial.mockResolvedValue({ historial: [] });
});

const entrar = async (role = 'ADMIN') => {
  sessionStorage.setItem('motored_user', JSON.stringify({ role }));
  render(<TrasladosContainer />);
  await screen.findByRole('table', { name: 'Detalle' });
};
const tarjeta = (nombre) => screen.getByRole('group', { name: nombre });
const filasDetalle = () => within(screen.getByRole('table', { name: 'Detalle' })).getAllByRole('row').slice(1);
const documentos = () => filasDetalle().map((f) => within(f).getAllByRole('cell')[0].textContent);

describe('Traslados panel', () => {
  it('shows the title and the last load time in Bogota', async () => {
    await entrar();
    expect(screen.getByRole('heading', { level: 1, name: 'Traslados' })).toBeInTheDocument();
    expect(screen.getByText(/última carga: 09\/10\/2026 07:40/)).toBeInTheDocument();
  });

  it('asks for the first load when there is none', async () => {
    mockApi.getTrasladosDetalle.mockResolvedValue({ ultima_carga: null, items: [] });
    sessionStorage.setItem('motored_user', JSON.stringify({ role: 'ADMIN' }));
    render(<TrasladosContainer />);
    expect(await screen.findByText('Carga traslados para empezar el seguimiento')).toBeInTheDocument();
  });

  it('shows the five cards derived from the items', async () => {
    await entrar();
    expect(within(tarjeta('Pendientes')).getByText('3')).toBeInTheDocument();
    expect(within(tarjeta('Pendientes')).getByText(/4 líneas/)).toBeInTheDocument();
    expect(within(tarjeta('Recibidos sin cargar al ERP')).getByText('1')).toBeInTheDocument();
    expect(within(tarjeta('Sin confirmar')).getByText('1')).toBeInTheDocument();
    expect(within(tarjeta('Aún no llegan')).getByText('1')).toBeInTheDocument();
    expect(within(tarjeta('Más antiguo')).getByText('67 días')).toBeInTheDocument();
    expect(within(tarjeta('Más antiguo')).getByText('79-00000067 · Bogotá Venecia')).toBeInTheDocument();
  });

  it('highlights the received-not-loaded card in amber with a tooltip', async () => {
    await entrar();
    const card = tarjeta('Recibidos sin cargar al ERP');
    expect(card).toHaveAttribute('title', expect.stringContaining('sigue vivo en el ERP'));
    expect(card).toHaveStyle({ border: '2px solid #B45309' });
  });

  it('lists one row per store ordered by received-not-loaded', async () => {
    await entrar();
    const filas = within(screen.getByRole('table', { name: 'Por tienda' })).getAllByRole('row').slice(1);
    expect(filas.map((f) => within(f).getAllByRole('cell')[0].textContent)).toEqual(['Bogotá Venecia', 'Bogotá Campin', 'Popayán']);
    expect(within(filas[0]).getAllByRole('cell').map((c) => c.textContent)).toEqual(['Bogotá Venecia', '1', '1', '0', '0', '67', '2']);
  });

  it('lists the transfers oldest first with sale, arrival, state and last change', async () => {
    await entrar();
    expect(documentos()).toEqual(['79-00000067', '79-00000082', '79-00000170']);
    const celdas = within(filasDetalle()[0]).getAllByRole('cell').map((c) => c.textContent);
    expect(celdas.slice(0, 5)).toEqual(['79-00000067', 'Bodega 1 de Mayo Tres', 'Bogotá Venecia', '03/08/2026', '67']);
    expect(celdas).toContain('Recibido sin cargar al ERP');
    expect(celdas).toContain('Carlos Ruiz · 05/10/2026 10:20');
    expect(screen.getByText('Mostrando 3 de 3')).toBeInTheDocument();
  });

  it('shows the footer note', async () => {
    await entrar();
    expect(screen.getByText(/dejan de aparecer en el archivo de traslados/)).toBeInTheDocument();
  });
});

describe('Traslados filters apply to every section', () => {
  it('filters by estado', async () => {
    const user = userEvent.setup();
    await entrar();
    await user.click(screen.getByRole('button', { name: 'Aún no llega' }));
    expect(documentos()).toEqual(['79-00000170']);
    expect(within(tarjeta('Pendientes')).getByText('1')).toBeInTheDocument();
    const filas = within(screen.getByRole('table', { name: 'Por tienda' })).getAllByRole('row').slice(1);
    expect(filas).toHaveLength(1);
    expect(screen.getByText('Mostrando 1 de 3')).toBeInTheDocument();
  });

  it.each([
    ['Hasta 7 días', ['79-00000170']],
    ['8 a 15 días', []],
    ['Más de 15 días', ['79-00000067', '79-00000082']],
  ])('filters by the %s band', async (banda, esperado) => {
    const user = userEvent.setup();
    await entrar();
    await user.click(screen.getByRole('button', { name: banda }));
    expect(documentos()).toEqual(esperado);
    if (!esperado.length) expect(screen.getByText('No hay traslados con estos filtros.')).toBeInTheDocument();
  });

  it('filters by the receiving store from the select and from a row click', async () => {
    const user = userEvent.setup();
    await entrar();
    await user.selectOptions(screen.getByLabelText('Tienda que recibe'), 's-pop');
    expect(documentos()).toEqual(['79-00000170']);
    await user.selectOptions(screen.getByLabelText('Tienda que recibe'), '');
    await user.click(within(screen.getByRole('table', { name: 'Por tienda' })).getByText('Bogotá Campin'));
    expect(documentos()).toEqual(['79-00000082']);
    expect(screen.getByLabelText('Tienda que recibe')).toHaveValue('s-cam');
    expect(within(tarjeta('Pendientes')).getByText('1')).toBeInTheDocument();
  });

  it('styles every select option and clears the filters', async () => {
    const user = userEvent.setup();
    await entrar();
    screen.getAllByRole('option').forEach((o) => expect(o).toHaveStyle({ color: '#1a1a18', background: '#ffffff' }));
    await user.click(screen.getByRole('button', { name: 'Sin confirmar' }));
    expect(screen.getByText(/Filtros activos: Sin confirmar/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Limpiar' }));
    expect(documentos()).toHaveLength(3);
  });
});

describe('Traslados history and confirmation', () => {
  it('expands the reference lines and then the history chain', async () => {
    const user = userEvent.setup();
    mockApi.getTrasladosHistorial.mockResolvedValue({ historial: [
      { estado: 'RECIBIDO', por: 'Juan Pérez', canal: 'APP', en: '2026-09-04T14:15:00Z' },
      { estado: 'NO_HA_LLEGADO', por: 'Ana Gómez', canal: 'ENLACE', en: '2026-09-03T21:02:00Z' },
    ] });
    await entrar();
    await user.click(within(filasDetalle()[1]).getByRole('button', { name: 'Historial' }));
    expect(mockApi.getTrasladosHistorial).toHaveBeenCalledWith('79-00000082', 'B-1');
    expect(await screen.findByText('Referencias de 79-00000082')).toBeInTheDocument();
    expect(screen.getByText('3360B-ABW-201S')).toBeInTheDocument();
    expect(screen.getByText(/Direccional der\. del\. · 1 und/)).toBeInTheDocument();
    const cadena = (await screen.findByText('Historial de 79-00000082')).nextElementSibling;
    expect(within(cadena).getAllByRole('listitem').map((li) => li.textContent.replace('→', ''))).toEqual([
      '03/09/2026 16:02Ana Gómez:Aún no llega', '04/09/2026 09:15Juan Pérez:Recibido',
    ]);
    await user.click(within(filasDetalle()[1]).getByRole('button', { name: 'Ocultar' }));
    expect(screen.queryByText('Referencias de 79-00000082')).not.toBeInTheDocument();
  });

  it('says nobody answered yet when the history is empty', async () => {
    const user = userEvent.setup();
    await entrar();
    await user.click(within(filasDetalle()[1]).getByRole('button', { name: 'Historial' }));
    expect(await screen.findByText('Nadie ha respondido todavía.')).toBeInTheDocument();
  });

  it.each(['ADMIN', 'COORDINADOR_REPUESTOS', 'ANALISTA_ADMINISTRATIVO'])('%s confirms through the API and the row updates', async (role) => {
    const user = userEvent.setup();
    const nuevo = { ...SIN_CONFIRMAR, estado: 'RECIBIDO', aviso_erp: true, confirmado_por: 'Coord', confirmado_en: '2026-10-09T13:00:00Z' };
    mockApi.confirmarTraslado.mockResolvedValue(nuevo);
    mockApi.getTrasladosDetalle.mockResolvedValueOnce({ ultima_carga: ULTIMA_CARGA, items: ITEMS })
      .mockResolvedValue({ ultima_carga: ULTIMA_CARGA, items: [RECIBIDO, nuevo, ITEMS[2]] }); // the reload after saving
    await entrar(role);
    await user.click(within(filasDetalle()[1]).getByRole('button', { name: 'Recibido' }));
    expect(mockApi.confirmarTraslado).toHaveBeenCalledWith({ documento: '79-00000082', bodega_salida: 'B-1', estado: 'RECIBIDO' });
    await waitFor(() => expect(within(filasDetalle()[1]).getByText(/Coord/)).toBeInTheDocument());
    await user.click(within(filasDetalle()[2]).getByRole('button', { name: 'No ha llegado' }));
    expect(mockApi.confirmarTraslado).toHaveBeenLastCalledWith({ documento: '79-00000170', bodega_salida: 'B-2', estado: 'NO_HA_LLEGADO' });
  });

  it.each(['COMPRAS', 'GERENCIA'])('%s reads without confirm buttons', async (role) => {
    await entrar(role);
    expect(screen.queryByRole('button', { name: 'Recibido' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'No ha llegado' })).not.toBeInTheDocument();
    expect(RECIBIDO.documento).toBe('79-00000067');
  });

  it('shows the backend message when saving fails', async () => {
    const user = userEvent.setup();
    mockApi.confirmarTraslado.mockRejectedValue(new Error('El traslado ya no está pendiente.'));
    await entrar();
    await user.click(within(filasDetalle()[1]).getByRole('button', { name: 'Recibido' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El traslado ya no está pendiente.');
  });
});
