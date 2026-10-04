/**
 * Maestros > Presupuestos (budgets, T3): month selector, month grouped by
 * tienda with totals, manual edit/add/remove (each one a new version),
 * version history, and the explicit option style the dark theme needs.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MES, LISTA, TIENDAS, VERSIONES } from './helpers/presupuestosFixtures';

const mockApi = {
  listarMesesPresupuesto: jest.fn(),
  listarTiendasPresupuesto: jest.fn(),
  getMesPresupuesto: jest.fn(),
  getVersionesPresupuesto: jest.fn(),
  getVersionPresupuesto: jest.fn(),
  guardarAsesorPresupuesto: jest.fn(),
  quitarAsesorPresupuesto: jest.fn(),
  descargarPlantillaPresupuestos: jest.fn(),
  validarPresupuestos: jest.fn(),
  aplicarPresupuestos: jest.fn(),
};
jest.mock('../lib/motored/presupuestosApi', () => new Proxy({}, { get: (_t, n) => (...a) => mockApi[n](...a) }));

import PresupuestosTab from '../components/motored/maestros/PresupuestosTab';

beforeEach(() => {
  Object.values(mockApi).forEach((f) => f.mockReset());
  mockApi.listarMesesPresupuesto.mockResolvedValue(LISTA);
  mockApi.listarTiendasPresupuesto.mockResolvedValue(TIENDAS);
  mockApi.getMesPresupuesto.mockResolvedValue(MES);
  mockApi.getVersionesPresupuesto.mockResolvedValue(VERSIONES);
  mockApi.guardarAsesorPresupuesto.mockResolvedValue({ mes: '2026-10', version: 3 });
  mockApi.quitarAsesorPresupuesto.mockResolvedValue({ mes: '2026-10', version: 3 });
});

const pesos = (n) => new RegExp(String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '\\.'));

describe('month list', () => {
  it('shows an empty state with an upload call to action', async () => {
    mockApi.listarMesesPresupuesto.mockResolvedValue([]);
    render(<PresupuestosTab />);

    expect(await screen.findByText('Aún no hay presupuestos cargados')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Cargar presupuestos' }).length).toBeGreaterThan(0);
  });

  it('selects the newest month and offers every month, newest first', async () => {
    render(<PresupuestosTab />);
    const select = await screen.findByLabelText('Mes');

    await waitFor(() => expect(mockApi.getMesPresupuesto).toHaveBeenCalledWith('2026-10'));
    expect([...select.options].map((o) => o.value)).toEqual(['2026-10', '2026-09']);
  });

  it('loads another month when selected', async () => {
    render(<PresupuestosTab />);
    fireEvent.change(await screen.findByLabelText('Mes'), { target: { value: '2026-09' } });

    await waitFor(() => expect(mockApi.getMesPresupuesto).toHaveBeenCalledWith('2026-09'));
  });
});

describe('month view', () => {
  it('shows version, origin, grand total, and budgets grouped by tienda with totals', async () => {
    render(<PresupuestosTab />);

    const caliGrupo = (await screen.findByRole('region', { name: /Cali/ }));
    expect(within(caliGrupo).getByText(pesos(2500000))).toBeInTheDocument();
    expect(within(caliGrupo).getByText('Ana Gómez')).toBeInTheDocument();
    expect(within(caliGrupo).getByText('111')).toBeInTheDocument();
    expect(within(caliGrupo).getByText(pesos(1500000))).toBeInTheDocument();
    const bogota = screen.getByRole('region', { name: /Bogotá/ });
    expect(within(bogota).getByText('Carla Díaz')).toBeInTheDocument();
    expect(screen.getByTestId('presupuesto-total')).toHaveTextContent(pesos(4500000));
    expect(screen.getByTestId('presupuesto-total')).toHaveTextContent(/3 asesores/);
    expect(screen.getByText(/Versión 2/)).toBeInTheDocument();
    expect(screen.getByTestId('presupuesto-origen')).toHaveTextContent('Manual');
  });

  it('explains version and origin with tooltips', async () => {
    render(<PresupuestosTab />);
    await screen.findByRole('region', { name: /Cali/ });

    expect(screen.getByRole('note', { name: /última versión/i })).toBeInTheDocument();
    expect(screen.getByRole('note', { name: /Excel|manual/i })).toBeInTheDocument();
  });
});

describe('manual edits', () => {
  it('says that every change creates a new version', async () => {
    render(<PresupuestosTab />);
    expect(await screen.findByText(/Cada cambio crea una nueva versión del mes/)).toBeInTheDocument();
  });

  it('edits an asesor with the optional note and refreshes', async () => {
    render(<PresupuestosTab />);
    const fila = (await screen.findByText('Ana Gómez')).closest('tr');
    fireEvent.click(within(fila).getByRole('button', { name: /Editar/ }));

    fireEvent.change(screen.getByLabelText('Monto'), { target: { value: '1800000' } });
    fireEvent.change(screen.getByLabelText('Tienda'), { target: { value: 's2' } });
    fireEvent.change(screen.getByLabelText(/Nota/), { target: { value: 'ajuste' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambio' }));

    await waitFor(() => expect(mockApi.guardarAsesorPresupuesto).toHaveBeenCalledWith(
      '2026-10', '111', { sucursal_id: 's2', monto: 1800000, nota: 'ajuste' }));
    await waitFor(() => expect(mockApi.getMesPresupuesto).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/versión 3/)).toBeInTheDocument();
  });

  it('adds an asesor by cédula, tienda and monto', async () => {
    render(<PresupuestosTab />);
    fireEvent.click(await screen.findByRole('button', { name: 'Agregar asesor' }));

    fireEvent.change(screen.getByLabelText('Cédula'), { target: { value: '444' } });
    fireEvent.change(screen.getByLabelText('Tienda'), { target: { value: 's1' } });
    fireEvent.change(screen.getByLabelText('Monto'), { target: { value: '900000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambio' }));

    await waitFor(() => expect(mockApi.guardarAsesorPresupuesto).toHaveBeenCalledWith(
      '2026-10', '444', { sucursal_id: 's1', monto: 900000 }));
  });

  it('removes an asesor with the optional note', async () => {
    render(<PresupuestosTab />);
    const fila = (await screen.findByText('Beto Ruiz')).closest('tr');
    fireEvent.click(within(fila).getByRole('button', { name: /Quitar/ }));
    fireEvent.change(screen.getByLabelText(/Nota/), { target: { value: 'baja' } });
    fireEvent.click(screen.getByRole('button', { name: 'Quitar asesor' }));

    await waitFor(() => expect(mockApi.quitarAsesorPresupuesto).toHaveBeenCalledWith('2026-10', '222', 'baja'));
  });

  it('shows the server message when the save fails', async () => {
    mockApi.guardarAsesorPresupuesto.mockRejectedValue(new Error('Otra persona está modificando este presupuesto.'));
    render(<PresupuestosTab />);
    fireEvent.click(await screen.findByRole('button', { name: 'Agregar asesor' }));
    fireEvent.change(screen.getByLabelText('Cédula'), { target: { value: '444' } });
    fireEvent.change(screen.getByLabelText('Tienda'), { target: { value: 's1' } });
    fireEvent.change(screen.getByLabelText('Monto'), { target: { value: '900000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambio' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Otra persona está modificando');
  });

  it('gives every tienda option an explicit style (dark theme hides the text otherwise)', async () => {
    render(<PresupuestosTab />);
    fireEvent.click(await screen.findByRole('button', { name: 'Agregar asesor' }));

    const opciones = screen.getByLabelText('Tienda').querySelectorAll('option');
    expect(opciones.length).toBeGreaterThanOrEqual(TIENDAS.length);
    opciones.forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });

  it('styles the month selector options too', async () => {
    render(<PresupuestosTab />);
    const select = await screen.findByLabelText('Mes');

    select.querySelectorAll('option').forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });
});

describe('version history', () => {
  it('lists the versions and shows a chosen one read-only', async () => {
    mockApi.getVersionPresupuesto.mockResolvedValue({ ...MES, id: 'v1', version: 1, origen: 'EXCEL', lineas: [MES.lineas[0]], asesores: 1, total: 1500000 });
    render(<PresupuestosTab />);
    fireEvent.click(await screen.findByRole('button', { name: 'Historial de versiones' }));

    expect(await screen.findByText('ajuste Ana')).toBeInTheDocument();
    expect(screen.getByText('oct.xlsx')).toBeInTheDocument();
    expect(screen.getByText('Gerente Uno')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ver versión 1' }));

    await waitFor(() => expect(mockApi.getVersionPresupuesto).toHaveBeenCalledWith('v1'));
    const panel = await screen.findByRole('region', { name: /Versión 1 \(solo lectura\)/ });
    expect(within(panel).getByText('Ana Gómez')).toBeInTheDocument();
    expect(within(panel).queryByRole('button', { name: /Editar|Quitar/ })).toBeNull();
  });
});

describe('tablet layout', () => {
  it('keeps tables inside a scroll container', async () => {
    const { container } = render(<PresupuestosTab />);
    await screen.findByText('Ana Gómez');

    container.querySelectorAll('table').forEach((t) => {
      expect(t.closest('.motored-table-scroll')).not.toBeNull();
    });
  });
});
