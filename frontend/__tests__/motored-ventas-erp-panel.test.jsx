/**
 * Dry-run panel of a raw ERP VENTAS carga (VALIDADO, before Aplicar), shown
 * in the Resumen tab: the discard counters of `log`, the "Referencias sin
 * línea" table with per-row and bulk line assignment (ADMIN and COMPRAS
 * only), the Aplicar block while any ref has no line, and the compact lists
 * of rows outside the parts lines and refs missing from the catalog.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockGetInforme = jest.fn();
const mockGetSinLinea = jest.fn();
const mockAsignarUna = jest.fn();
const mockAsignarVarias = jest.fn();
const mockGetParametro = jest.fn();
const mockVaciado = jest.fn();

jest.mock('../lib/motored/api', () => ({
  getInformeCarga: (...args) => mockGetInforme(...args),
  aplicarCarga: jest.fn(),
  anularCarga: jest.fn(),
  getReferenciasSinLinea: (...args) => mockGetSinLinea(...args),
  asignarLineaReferencia: (...args) => mockAsignarUna(...args),
  asignarLineasReferencias: (...args) => mockAsignarVarias(...args),
  getParametroVigente: (...args) => mockGetParametro(...args),
  getVaciadoPrevisto: (...args) => mockVaciado(...args),
}));

import ResumenTab from '../components/motored/cargas/ResumenTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const LOG = { filas_tipo_excluido: 1234, filas_fuera_de_linea: 56, filas_sin_linea: 7, filas_co_vacio: 1 };
const informe = (log = LOG) => ({
  id: 'carga-1', estado: 'VALIDADO', filas_leidas: 2000, filas_validas: 700, filas_rechazadas: 0,
  periodo_desde: '2026-09-01', periodo_hasta: '2026-09-30', log, variacion_pct_vs_carga_anterior: null,
});

const REF_A = { referencia_id: 'r-a', codigo: 'A-100', nombre: 'Filtro aire', filas: 3, unidades: 5, valor: '150000.00' };
const REF_B = { referencia_id: 'r-b', codigo: 'B-200', nombre: 'Pastilla freno', filas: 4, unidades: 8, valor: '1250000' };
const REF_C = { referencia_id: 'r-c', codigo: 'C-300', nombre: 'Guaya', filas: 9, unidades: 9, valor: '150000' };
const payload = (sinLinea = [REF_A, REF_B, REF_C], extra = {}) => ({
  sin_linea: sinLinea,
  fuera_de_linea: [{ linea: 'MOTOS', filas: 40 }, { linea: 'SERVICIOS', filas: 16 }],
  no_encontradas: [{ codigo: 'ZZ-1', filas: 10 }, { codigo: 'ZZ-2', filas: 5 }],
  ...extra,
});

const CARGA = { id: 'carga-1', tipo: 'VENTAS', estado: 'VALIDADO' };

function conflicto(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

async function renderizar({ role = 'COMPRAS', carga = CARGA } = {}) {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role }));
  render(<ResumenTab carga={carga} />);
  await screen.findByText('Filas leídas');
}

const tabla = () => screen.findByRole('table', { name: 'Referencias sin línea' });
const filasDe = (t) => within(t).getAllByRole('row').slice(1);

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  mockGetInforme.mockResolvedValue(informe());
  mockGetSinLinea.mockResolvedValue(payload());
  mockGetParametro.mockResolvedValue({ clave: 'lineas_comerciales', valor: ['Repuestos', 'Llantas', 'GPS'] });
  mockVaciado.mockResolvedValue([]);
});

describe('VENTAS dry-run panel -- summary and lists', () => {
  it('summarizes the discard counters in plain Spanish', async () => {
    await renderizar();
    expect(await screen.findByText('1.234 filas descartadas por tipo (motos, SOAT…)')).toBeInTheDocument();
    expect(screen.getByText('56 filas fuera de las líneas de repuestos')).toBeInTheDocument();
    expect(screen.getByText('7 filas de referencias sin línea')).toBeInTheDocument();
    expect(screen.getByText('1 fila con el C.O. vacío')).toBeInTheDocument();
  });

  it('sorts the table by valor desc with filas as tie-break and shows COP', async () => {
    await renderizar();
    const filas = filasDe(await tabla());
    expect(filas.map((f) => within(f).getAllByRole('cell')[1].textContent)).toEqual(['B-200', 'C-300', 'A-100']);
    expect(within(filas[0]).getByText('$ 1.250.000')).toBeInTheDocument();
    expect(within(filas[0]).getByText('Pastilla freno')).toBeInTheDocument();
  });

  it('lists the rows outside the parts lines and the refs missing from the catalog', async () => {
    await renderizar();
    await tabla();
    expect(screen.getByText('MOTOS: 40 filas')).toBeInTheDocument();
    expect(screen.getByText('ZZ-1: 10 filas')).toBeInTheDocument();
    expect(screen.getByText(
      '15 filas de 2 referencias que no están en el catálogo no se cargan; si son repuestos, agréguelas al catálogo y vuelva a validar.',
    )).toBeInTheDocument();
  });

  it('says so when every ref has a line', async () => {
    mockGetSinLinea.mockResolvedValue(payload([]));
    await renderizar();
    expect(await screen.findByText('Todas las referencias del archivo tienen línea.')).toBeInTheDocument();
  });

  it('shows an error with a retry when the report fails', async () => {
    mockGetSinLinea.mockRejectedValueOnce(new Error('caído'));
    await renderizar();
    expect(await screen.findByText(/No se pudo revisar las referencias sin línea/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
    await tabla();
    expect(mockGetSinLinea).toHaveBeenCalledTimes(2);
  });
});

describe('VENTAS dry-run panel -- Aplicar block', () => {
  it('disables Aplicar while refs have no line', async () => {
    await renderizar();
    expect(await screen.findByText('Hay 3 referencias sin línea: asígnelas antes de aplicar')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Aplicar' })).toBeDisabled();
  });

  it('keeps Aplicar enabled when only catalog-missing refs remain', async () => {
    mockGetSinLinea.mockResolvedValue(payload([]));
    await renderizar();
    await screen.findByText(/no están en el catálogo no se cargan/);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Aplicar' })).toBeEnabled());
  });
});

describe('VENTAS dry-run panel -- per-row assignment', () => {
  it('offers the configured lines plus the discard option, every option styled', async () => {
    await renderizar();
    await tabla();
    const select = screen.getByLabelText('Línea de B-200');
    const opciones = within(select).getAllByRole('option');
    expect(opciones.map((o) => o.value)).toEqual(['', 'REPUESTOS', 'LLANTAS', 'GPS', 'NO COMERCIAL']);
    expect(within(select).getByRole('option', { name: 'No es de repuestos (descartar)' })).toBeInTheDocument();
    opciones.forEach((o) => expect(o.getAttribute('style')).toMatch(/color/));
  });

  it('falls back to the seven default lines when the config cannot be read', async () => {
    mockGetParametro.mockRejectedValue(conflicto(404, 'Sin versión vigente'));
    await renderizar();
    await tabla();
    const valores = within(screen.getByLabelText('Línea de B-200')).getAllByRole('option').map((o) => o.value);
    expect(valores).toEqual(['', 'REPUESTOS', 'ACCESORIOS', 'LLANTAS', 'LUBRICANTES', 'BATERIAS', 'GPS', 'CASCOS', 'NO COMERCIAL']);
  });

  it('assigns one line and replaces the table with the response', async () => {
    mockAsignarUna.mockResolvedValue(payload([REF_A]));
    await renderizar();
    await tabla();
    fireEvent.change(screen.getByLabelText('Línea de B-200'), { target: { value: 'LLANTAS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Asignar línea a B-200' }));
    await waitFor(() => expect(filasDe(screen.getByRole('table', { name: 'Referencias sin línea' }))).toHaveLength(1));
    expect(mockAsignarUna).toHaveBeenCalledWith('carga-1', 'r-b', 'LLANTAS');
    expect(screen.getByText('Hay 1 referencias sin línea: asígnelas antes de aplicar')).toBeInTheDocument();
  });

  it('sends the NO COMERCIAL sentinel for the discard option', async () => {
    mockAsignarUna.mockResolvedValue(payload([REF_A, REF_C]));
    await renderizar();
    await tabla();
    fireEvent.change(screen.getByLabelText('Línea de B-200'), { target: { value: 'NO COMERCIAL' } });
    fireEvent.click(screen.getByRole('button', { name: 'Asignar línea a B-200' }));
    await waitFor(() => expect(mockAsignarUna).toHaveBeenCalledWith('carga-1', 'r-b', 'NO COMERCIAL'));
  });

  it('shows the 409 message inline and refreshes the table', async () => {
    mockAsignarUna.mockRejectedValue(conflicto(409, 'La referencia ya tiene línea.'));
    await renderizar();
    await tabla();
    fireEvent.change(screen.getByLabelText('Línea de B-200'), { target: { value: 'GPS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Asignar línea a B-200' }));
    expect(await screen.findByText('La referencia ya tiene línea.')).toBeInTheDocument();
    await waitFor(() => expect(mockGetSinLinea).toHaveBeenCalledTimes(2));
  });

  it('shows a Spanish message for a 422', async () => {
    mockAsignarUna.mockRejectedValue(conflicto(422, 'HTTP 422'));
    await renderizar();
    await tabla();
    fireEvent.change(screen.getByLabelText('Línea de B-200'), { target: { value: 'GPS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Asignar línea a B-200' }));
    expect(await screen.findByText('La línea elegida no es válida. Elija otra de la lista.')).toBeInTheDocument();
  });
});

describe('VENTAS dry-run panel -- bulk assignment', () => {
  async function seleccionarTodasYAsignar(linea) {
    await renderizar();
    await tabla();
    fireEvent.click(screen.getByLabelText('Seleccionar todas'));
    fireEvent.change(screen.getByLabelText('Línea para las seleccionadas'), { target: { value: linea } });
    fireEvent.click(screen.getByRole('button', { name: 'Asignar línea a seleccionadas' }));
  }

  it('sends one bulk PUT with every selected ref and replaces the table', async () => {
    mockAsignarVarias.mockResolvedValue(payload([]));
    await seleccionarTodasYAsignar('REPUESTOS');
    await screen.findByText('Todas las referencias del archivo tienen línea.');
    expect(mockAsignarVarias).toHaveBeenCalledWith('carga-1', [
      { referencia_id: 'r-b', linea_comercial: 'REPUESTOS' },
      { referencia_id: 'r-c', linea_comercial: 'REPUESTOS' },
      { referencia_id: 'r-a', linea_comercial: 'REPUESTOS' },
    ]);
    expect(mockAsignarUna).not.toHaveBeenCalled();
  });

  it('assigns only the checked rows', async () => {
    mockAsignarVarias.mockResolvedValue(payload([REF_A, REF_B]));
    await renderizar();
    await tabla();
    fireEvent.click(screen.getByLabelText('Seleccionar C-300'));
    expect(screen.getByText('1 seleccionada')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Línea para las seleccionadas'), { target: { value: 'GPS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Asignar línea a seleccionadas' }));
    await waitFor(() => expect(mockAsignarVarias).toHaveBeenCalledWith('carga-1', [
      { referencia_id: 'r-c', linea_comercial: 'GPS' },
    ]));
  });

  it('shows the error and keeps the selection when the bulk PUT fails', async () => {
    mockAsignarVarias.mockRejectedValue(conflicto(409, 'Una referencia ya no está en la lista.'));
    await seleccionarTodasYAsignar('GPS');
    expect(await screen.findByText('Una referencia ya no está en la lista.')).toBeInTheDocument();
    expect(screen.getByLabelText('Seleccionar B-200')).toBeChecked();
    expect(screen.getByLabelText('Seleccionar todas')).toBeChecked();
  });
});

describe('VENTAS dry-run panel -- gating', () => {
  it('shows read-only text for roles that cannot assign', async () => {
    await renderizar({ role: 'CONSULTA' });
    const t = await tabla();
    expect(within(t).queryByRole('combobox')).not.toBeInTheDocument();
    expect(within(t).queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Asignar/ })).not.toBeInTheDocument();
    expect(within(filasDe(t)[0]).getByText('Sin línea')).toBeInTheDocument();
  });

  it('lets ADMIN assign too', async () => {
    await renderizar({ role: 'ADMIN' });
    await tabla();
    expect(screen.getByRole('button', { name: 'Asignar línea a B-200' })).toBeInTheDocument();
  });

  it.each([
    ['a non-VENTAS carga', { id: 'carga-1', tipo: 'INVENTARIO', estado: 'VALIDADO' }],
    ['an applied VENTAS carga', { id: 'carga-1', tipo: 'VENTAS', estado: 'APLICADA' }],
  ])('never calls the new endpoints for %s', async (_, carga) => {
    await renderizar({ carga });
    expect(screen.queryByText(/Referencias sin línea/)).not.toBeInTheDocument();
    expect(mockGetSinLinea).not.toHaveBeenCalled();
    expect(mockVaciado).not.toHaveBeenCalled();
    expect(mockGetParametro).not.toHaveBeenCalled();
  });
});
