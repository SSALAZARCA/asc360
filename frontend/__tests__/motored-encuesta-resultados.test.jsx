/**
 * Survey admin: expandable per-carga detail, quick filters, categoria chips
 * and the two Excel downloads (per carga and by date range).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockDetalle = jest.fn();
const mockExcelCarga = jest.fn();
const mockExcelRango = jest.fn();

jest.mock('../lib/motored/encuestaCargasApi', () => ({
  getDetalleCargaEncuesta: (...a) => mockDetalle(...a),
  descargarExcelCargaEncuesta: (...a) => mockExcelCarga(...a),
  descargarResultadosEncuesta: (...a) => mockExcelRango(...a),
}));

import CargasRealizadas from '../components/motored/encuesta-admin/CargasRealizadas';
import { rangoMesActual } from '../lib/motored/encuestaRango';

const CARGAS = [
  { id: 'c1', nombre_archivo: 'mayo.xlsx', total_registros: 4, created_at: '2026-10-01T03:00:00+00:00', usuario: 'Agente', respondidos: 3 },
  { id: 'c2', nombre_archivo: 'junio.xlsx', total_registros: 1, created_at: '2026-10-02T15:00:00+00:00', usuario: 'Agente', respondidos: 0 },
];
const FILAS = [
  { cliente: 'Ana Perez', cedula: '1', telefono: '3001112233', tienda: 'Cali Norte', estado: 'RESPONDIDA', nota: 5, categoria: 'SATISFECHO', comentario: 'Excelente', fecha_respuesta: '2026-10-02T15:00:00+00:00' },
  { cliente: 'Beto Ruiz', cedula: '2', telefono: '3002223344', tienda: 'Cali Sur', estado: 'RESPONDIDA', nota: 2, categoria: 'DETRACTOR', comentario: 'Mal servicio', fecha_respuesta: '2026-10-03T04:00:00+00:00' },
  { cliente: 'Dora Gil', cedula: '4', telefono: null, tienda: 'Cali Sur', estado: 'SIN_RESPONDER', nota: null, categoria: null, comentario: null, fecha_respuesta: null },
];

function renderTabla(props = {}) {
  return render(<CargasRealizadas cargas={CARGAS} loading={false} error="" {...props} />);
}

beforeEach(() => {
  jest.clearAllMocks();
  mockDetalle.mockResolvedValue(FILAS);
  mockExcelCarga.mockResolvedValue({});
  mockExcelRango.mockResolvedValue({});
});

describe('rangoMesActual', () => {
  it('returns the first and last day of the month in Bogota time', () => {
    expect(rangoMesActual(new Date('2026-10-08T15:00:00Z'))).toEqual({ desde: '2026-10-01', hasta: '2026-10-31' });
    // 02:00 UTC on Nov 1 is still Oct 31 in Bogota
    expect(rangoMesActual(new Date('2026-11-01T02:00:00Z'))).toEqual({ desde: '2026-10-01', hasta: '2026-10-31' });
    expect(rangoMesActual(new Date('2028-02-10T12:00:00Z'))).toEqual({ desde: '2028-02-01', hasta: '2028-02-29' });
  });
});

describe('Expandable detail', () => {
  it('starts collapsed, fetches lazily on expand and collapses again', async () => {
    renderTabla();
    const chevron = screen.getByRole('button', { name: 'Ver detalle de mayo.xlsx' });
    expect(chevron).toHaveAttribute('aria-expanded', 'false');
    expect(mockDetalle).not.toHaveBeenCalled();
    fireEvent.click(chevron);
    expect(chevron).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Cargando detalle...')).toBeInTheDocument();
    expect(await screen.findByText('Ana Perez')).toBeInTheDocument();
    expect(mockDetalle).toHaveBeenCalledWith('c1', 'todas');
    const region = screen.getByRole('region', { name: 'Detalle de mayo.xlsx' });
    for (const col of ['Cliente', 'Teléfono', 'Tienda', 'Estado', 'Nota', 'Categoría', 'Comentario', 'Fecha de respuesta']) {
      expect(within(region).getByRole('columnheader', { name: col })).toBeInTheDocument();
    }
    fireEvent.click(chevron);
    expect(chevron).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Ana Perez')).not.toBeInTheDocument();
  });

  it('shows the fetch error', async () => {
    mockDetalle.mockRejectedValue(new Error('Sin conexión'));
    renderTabla();
    fireEvent.click(screen.getByRole('button', { name: 'Ver detalle de mayo.xlsx' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Sin conexión');
  });

  it('renders estado, nota, comentario and the Bogota response date, with a dash when empty', async () => {
    renderTabla();
    fireEvent.click(screen.getByRole('button', { name: 'Ver detalle de mayo.xlsx' }));
    await screen.findByText('Ana Perez');
    const ana = screen.getByText('Ana Perez').closest('tr');
    expect(within(ana).getByText('Respondida')).toBeInTheDocument();
    expect(within(ana).getByText('Excelente')).toBeInTheDocument();
    expect(within(ana).getByText('02/10/2026 10:00')).toBeInTheDocument();
    const dora = screen.getByText('Dora Gil').closest('tr');
    expect(within(dora).getByText('Sin responder')).toBeInTheDocument();
  });

  it('colors the categoria chip with the traffic-light tones', async () => {
    renderTabla();
    fireEvent.click(screen.getByRole('button', { name: 'Ver detalle de mayo.xlsx' }));
    await screen.findByText('Ana Perez');
    expect(screen.getByText('Satisfecho')).toHaveAttribute('data-tono', 'good');
    expect(screen.getByText('Detractor')).toHaveAttribute('data-tono', 'bad');
    expect(screen.getAllByTestId('categoria-chip')).toHaveLength(2);
  });

  it('refetches with the quick filter and marks the active pill', async () => {
    renderTabla();
    fireEvent.click(screen.getByRole('button', { name: 'Ver detalle de mayo.xlsx' }));
    await screen.findByText('Ana Perez');
    expect(screen.getByRole('button', { name: 'Todas' })).toHaveAttribute('aria-pressed', 'true');
    for (const [label, valor] of [['Respondidas', 'respondidas'], ['Sin responder', 'sin_responder'], ['Detractores', 'detractores']]) {
      fireEvent.click(screen.getByRole('button', { name: label }));
      await waitFor(() => expect(mockDetalle).toHaveBeenLastCalledWith('c1', valor));
      expect(screen.getByRole('button', { name: label })).toHaveAttribute('aria-pressed', 'true');
    }
  });

  it('keeps each carga detail independent', async () => {
    renderTabla();
    fireEvent.click(screen.getByRole('button', { name: 'Ver detalle de mayo.xlsx' }));
    fireEvent.click(screen.getByRole('button', { name: 'Ver detalle de junio.xlsx' }));
    await waitFor(() => expect(mockDetalle).toHaveBeenCalledWith('c2', 'todas'));
    expect(screen.getByRole('region', { name: 'Detalle de mayo.xlsx' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Detalle de junio.xlsx' })).toBeInTheDocument();
  });

  it('has an inner scroll container', async () => {
    renderTabla();
    fireEvent.click(screen.getByRole('button', { name: 'Ver detalle de mayo.xlsx' }));
    await screen.findByText('Ana Perez');
    expect(screen.getByTestId('detalle-scroll')).toHaveStyle({ maxHeight: '360px', overflowY: 'auto' });
  });
});

describe('Excel per carga', () => {
  it('downloads the carga and shows the busy state', async () => {
    let fin;
    mockExcelCarga.mockReturnValue(new Promise((r) => { fin = r; }));
    renderTabla();
    const boton = screen.getByRole('button', { name: 'Descargar Excel de mayo.xlsx' });
    fireEvent.click(boton);
    expect(mockExcelCarga).toHaveBeenCalledWith('c1', 'mayo.xlsx');
    await waitFor(() => expect(boton).toBeDisabled());
    fin({});
    await waitFor(() => expect(boton).not.toBeDisabled());
  });

  it('shows the download error', async () => {
    mockExcelCarga.mockRejectedValue(new Error('HTTP 500'));
    renderTabla();
    fireEvent.click(screen.getByRole('button', { name: 'Descargar Excel de mayo.xlsx' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 500');
  });
});

describe('Descargar resultados (date range)', () => {
  it('defaults to the current month, filtered by send date, with a tooltip', () => {
    renderTabla();
    const { desde, hasta } = rangoMesActual();
    expect(screen.getByLabelText('Desde')).toHaveValue(desde);
    expect(screen.getByLabelText('Hasta')).toHaveValue(hasta);
    expect(screen.getByRole('button', { name: 'Fecha de envío' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Fecha de respuesta' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getAllByText(/el mes del servicio/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/cuándo contestó el cliente/).length).toBeGreaterThan(0);
  });

  it('downloads with the chosen dates and por=envio by default', async () => {
    renderTabla();
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-09-30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Descargar resultados' }));
    await waitFor(() => expect(mockExcelRango).toHaveBeenCalledWith({ desde: '2026-09-01', hasta: '2026-09-30', por: 'envio' }));
  });

  it('sends por=respuesta when the toggle is switched', async () => {
    renderTabla();
    fireEvent.click(screen.getByRole('button', { name: 'Fecha de respuesta' }));
    expect(screen.getByRole('button', { name: 'Fecha de respuesta' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Descargar resultados' }));
    await waitFor(() => expect(mockExcelRango).toHaveBeenCalledWith(expect.objectContaining({ por: 'respuesta' })));
  });

  it('disables the button when desde is after hasta, or a date is empty', () => {
    renderTabla();
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-10-10' } });
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-10-01' } });
    expect(screen.getByRole('button', { name: 'Descargar resultados' })).toBeDisabled();
    expect(screen.getByText('La fecha desde no puede ser posterior a la fecha hasta.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '' } });
    expect(screen.getByRole('button', { name: 'Descargar resultados' })).toBeDisabled();
    expect(mockExcelRango).not.toHaveBeenCalled();
  });

  it('shows the download error', async () => {
    mockExcelRango.mockRejectedValue(new Error('El rango no puede superar 366 días'));
    renderTabla();
    fireEvent.click(screen.getByRole('button', { name: 'Descargar resultados' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El rango no puede superar 366 días');
  });

  it('is available even when there are no cargas yet', () => {
    renderTabla({ cargas: [] });
    expect(screen.getByRole('button', { name: 'Descargar resultados' })).toBeInTheDocument();
  });
});
