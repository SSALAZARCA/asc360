/**
 * Dry-run panel of a raw ERP VENTAS carga (VALIDADO, before Aplicar), shown
 * in the Resumen tab: the discard counters of `log`, the "Referencias sin
 * línea" table where per-row and bulk picks stay pending until ONE bulk
 * "Guardar asignaciones" PUT (ADMIN and COMPRAS only; the single-row PUT is
 * never called), the Aplicar block while any ref has no line or a pick is
 * unsaved, and the compact lists
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
const mockAplicar = jest.fn();

jest.mock('../lib/motored/api', () => ({
  getInformeCarga: (...args) => mockGetInforme(...args),
  aplicarCarga: (...args) => mockAplicar(...args),
  anularCarga: jest.fn(),
  getReferenciasSinLinea: (...args) => mockGetSinLinea(...args),
  asignarLineaReferencia: (...args) => mockAsignarUna(...args),
  asignarLineasReferencias: (...args) => mockAsignarVarias(...args),
  getParametroVigente: (...args) => mockGetParametro(...args),
  getVaciadoPrevisto: (...args) => mockVaciado(...args),
}));

import ResumenTab from '../components/motored/cargas/ResumenTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';
import { codedError } from '../lib/motored/httpErrors';

const LOG = { filas_tipo_excluido: 1234, filas_fuera_de_linea: 56, filas_sin_linea: 7, filas_co_vacio: 1 };
const informe = (log = LOG) => ({
  id: 'carga-1', estado: 'VALIDADO', filas_leidas: 2000, filas_validas: 700, filas_rechazadas: 0,
  periodo_desde: '2026-09-01', periodo_hasta: '2026-09-30', log, variacion_pct_vs_carga_anterior: null,
});

const REF_A = { referencia_id: 'r-a', codigo: 'A-100', nombre: 'Filtro aire', filas: 3, unidades: 5, valor: '150000.00' };
const REF_B = { referencia_id: 'r-b', codigo: 'B-200', nombre: 'Pastilla freno', filas: 4, unidades: 8, valor: '1250000' };
const REF_C = { referencia_id: 'r-c', codigo: 'C-300', nombre: 'Guaya', filas: 9, unidades: 9, valor: '150000' };
const OPCIONES = [
  { valor: 'REPUESTOS', etiqueta: 'Repuestos' },
  { valor: 'LLANTAS', etiqueta: 'Llantas' },
  { valor: 'GPS', etiqueta: 'GPS' },
  { valor: 'NO COMERCIAL', etiqueta: 'No es de repuestos (descartar)' },
];
const payload = (sinLinea = [REF_A, REF_B, REF_C], extra = {}) => ({
  opciones_linea: OPCIONES,
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

describe('VENTAS dry-run panel -- line selects', () => {
  it('offers the opciones_linea of the payload in both selects, every option styled', async () => {
    await renderizar();
    await tabla();
    ['Línea de B-200', 'Línea para las seleccionadas'].forEach((etiqueta) => {
      const opciones = within(screen.getByLabelText(etiqueta)).getAllByRole('option');
      expect(opciones.map((o) => o.value)).toEqual(['', 'REPUESTOS', 'LLANTAS', 'GPS', 'NO COMERCIAL']);
      expect(opciones.map((o) => o.textContent).slice(1)).toEqual(OPCIONES.map((o) => o.etiqueta));
      opciones.forEach((o) => expect(o.getAttribute('style')).toMatch(/color/));
    });
    expect(mockGetParametro).not.toHaveBeenCalled();
  });

  it('falls back to the seven default lines plus the discard option when opciones_linea is absent', async () => {
    const { opciones_linea: _, ...sinOpciones } = payload();
    mockGetSinLinea.mockResolvedValue(sinOpciones);
    await renderizar();
    await tabla();
    const select = screen.getByLabelText('Línea de B-200');
    const valores = within(select).getAllByRole('option').map((o) => o.value);
    expect(valores).toEqual(['', 'REPUESTOS', 'ACCESORIOS', 'LLANTAS', 'LUBRICANTES', 'BATERIAS', 'GPS', 'CASCOS', 'NO COMERCIAL']);
    expect(within(select).getByRole('option', { name: 'No es de repuestos (descartar)' })).toBeInTheDocument();
    expect(mockGetParametro).not.toHaveBeenCalled();
  });
});

describe('VENTAS dry-run panel -- pending assignments', () => {
  const elegir = (codigo, linea) => fireEvent.change(screen.getByLabelText(`Línea de ${codigo}`), { target: { value: linea } });
  const guardar = () => screen.getByRole('button', { name: /^Guardar asignaciones/ });

  it('records the per-row choices locally and sends no request', async () => {
    await renderizar();
    await tabla();
    expect(guardar()).toHaveTextContent('Guardar asignaciones (0)');
    expect(guardar()).toBeDisabled();
    elegir('B-200', 'LLANTAS');
    elegir('A-100', 'NO COMERCIAL');
    expect(screen.getByLabelText('Línea de B-200')).toHaveValue('LLANTAS');
    expect(guardar()).toHaveTextContent('Guardar asignaciones (2)');
    expect(screen.getByText('2 asignaciones sin guardar')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Asignar línea a / })).not.toBeInTheDocument();
    expect(mockAsignarVarias).not.toHaveBeenCalled();
    expect(mockAsignarUna).not.toHaveBeenCalled();
  });

  it('un-picking a row drops its pending choice', async () => {
    await renderizar();
    await tabla();
    elegir('B-200', 'LLANTAS');
    elegir('B-200', '');
    expect(guardar()).toHaveTextContent('Guardar asignaciones (0)');
  });

  it('sends every pending choice in ONE bulk PUT and replaces the table with the response', async () => {
    const nuevas = [{ valor: 'CASCOS', etiqueta: 'Cascos' }, OPCIONES[3]];
    mockAsignarVarias.mockResolvedValue(payload([REF_C], { opciones_linea: nuevas }));
    await renderizar();
    await tabla();
    elegir('A-100', 'NO COMERCIAL');
    elegir('B-200', 'LLANTAS');
    fireEvent.click(guardar());
    await waitFor(() => expect(filasDe(screen.getByRole('table', { name: 'Referencias sin línea' }))).toHaveLength(1));
    expect(mockAsignarVarias).toHaveBeenCalledTimes(1);
    expect(mockAsignarVarias).toHaveBeenCalledWith('carga-1', [
      { referencia_id: 'r-b', linea_comercial: 'LLANTAS' },
      { referencia_id: 'r-a', linea_comercial: 'NO COMERCIAL' },
    ]);
    expect(guardar()).toHaveTextContent('Guardar asignaciones (0)');
    expect(within(screen.getByLabelText('Línea de C-300')).getAllByRole('option').map((o) => o.value))
      .toEqual(['', 'CASCOS', 'NO COMERCIAL']);
    expect(screen.getByText('Hay 1 referencias sin línea: asígnelas antes de aplicar')).toBeInTheDocument();
    expect(mockAsignarUna).not.toHaveBeenCalled();
  });

  it('keeps the pending choices and shows the detail on a 409', async () => {
    mockAsignarVarias.mockRejectedValue(conflicto(409, 'Una referencia ya no está en la lista.'));
    await renderizar();
    await tabla();
    elegir('B-200', 'GPS');
    elegir('C-300', 'REPUESTOS');
    fireEvent.click(guardar());
    expect(await screen.findByText('Una referencia ya no está en la lista.')).toBeInTheDocument();
    await waitFor(() => expect(guardar()).toBeEnabled());
    expect(guardar()).toHaveTextContent('Guardar asignaciones (2)');
    expect(screen.getByLabelText('Línea de B-200')).toHaveValue('GPS');
    expect(screen.getByLabelText('Línea de C-300')).toHaveValue('REPUESTOS');
  });

  it('shows a Spanish message for a 422 and keeps the choices', async () => {
    mockAsignarVarias.mockRejectedValue(conflicto(422, 'HTTP 422'));
    await renderizar();
    await tabla();
    elegir('B-200', 'GPS');
    fireEvent.click(guardar());
    expect(await screen.findByText('La línea elegida no es válida. Elija otra de la lista.')).toBeInTheDocument();
    expect(screen.getByLabelText('Línea de B-200')).toHaveValue('GPS');
  });

  it('blocks Aplicar while there are unsaved choices', async () => {
    await renderizar();
    await tabla();
    elegir('B-200', 'GPS');
    expect(screen.getByText('Guarde las asignaciones antes de aplicar')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Aplicar' })).toBeDisabled();
  });
});

describe('VENTAS dry-run panel -- bulk selection', () => {
  const usarEnSeleccionadas = (linea) => {
    fireEvent.change(screen.getByLabelText('Línea para las seleccionadas'), { target: { value: linea } });
    fireEvent.click(screen.getByRole('button', { name: 'Usar línea en seleccionadas' }));
  };

  it('fills the pending choices of the checked rows without a request', async () => {
    await renderizar();
    await tabla();
    fireEvent.click(screen.getByLabelText('Seleccionar C-300'));
    expect(screen.getByText('1 seleccionada')).toBeInTheDocument();
    usarEnSeleccionadas('GPS');
    expect(screen.getByLabelText('Línea de C-300')).toHaveValue('GPS');
    expect(screen.getByLabelText('Línea de B-200')).toHaveValue('');
    expect(screen.getByLabelText('Seleccionar C-300')).not.toBeChecked();
    expect(mockAsignarVarias).not.toHaveBeenCalled();
  });

  it('selects all, fills every row and saves them in one bulk PUT', async () => {
    mockAsignarVarias.mockResolvedValue(payload([]));
    await renderizar();
    await tabla();
    fireEvent.click(screen.getByLabelText('Seleccionar todas'));
    usarEnSeleccionadas('REPUESTOS');
    fireEvent.click(screen.getByRole('button', { name: 'Guardar asignaciones (3)' }));
    await screen.findByText('Todas las referencias del archivo tienen línea.');
    expect(mockAsignarVarias).toHaveBeenCalledTimes(1);
    expect(mockAsignarVarias).toHaveBeenCalledWith('carga-1', [
      { referencia_id: 'r-b', linea_comercial: 'REPUESTOS' },
      { referencia_id: 'r-c', linea_comercial: 'REPUESTOS' },
      { referencia_id: 'r-a', linea_comercial: 'REPUESTOS' },
    ]);
    expect(mockAsignarUna).not.toHaveBeenCalled();
  });
});
describe('VENTAS dry-run panel -- gating', () => {
  it.each(['GERENCIA', 'CONSULTA'])('requests nothing and shows only the summary for %s', async (role) => {
    await renderizar({ role });
    await screen.findByText('Filas válidas');
    expect(screen.queryByText(/Referencias sin línea/)).not.toBeInTheDocument();
    expect(screen.queryByText(/descartadas por tipo/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Se van a borrar/)).not.toBeInTheDocument();
    expect(mockGetSinLinea).not.toHaveBeenCalled();
    expect(mockVaciado).not.toHaveBeenCalled();
  });

  it('lets ADMIN review and assign too', async () => {
    await renderizar({ role: 'ADMIN' });
    await tabla();
    expect(screen.getByLabelText('Línea de B-200')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Guardar asignaciones (0)' })).toBeInTheDocument();
    expect(mockGetSinLinea).toHaveBeenCalledWith('carga-1');
    expect(mockVaciado).toHaveBeenCalledWith('carga-1');
  });

  it('shows the period-rejection detail of a 409 on Aplicar verbatim', async () => {
    const detalle = 'RECHAZO: el 35 % de las líneas del archivo son de otro mes (tolerancia 5 %).';
    mockGetSinLinea.mockResolvedValue(payload([]));
    mockAplicar.mockRejectedValue(codedError(409, { detail: detalle }, 'HTTP 409'));
    await renderizar();
    await screen.findByText('Todas las referencias del archivo tienen línea.');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Aplicar' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar' }));
    expect(await screen.findByText(detalle)).toBeInTheDocument();
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
