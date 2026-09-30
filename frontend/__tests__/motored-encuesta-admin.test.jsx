/**
 * Survey admin page (T7): public link, customer-base upload, uploads list.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockDescargar = jest.fn();
const mockValidar = jest.fn();
const mockGuardar = jest.fn();
const mockListar = jest.fn();
const pushMock = jest.fn();

jest.mock('../lib/motored/encuestaCargasApi', () => ({
  descargarPlantillaEncuesta: (...a) => mockDescargar(...a),
  validarCargaEncuesta: (...a) => mockValidar(...a),
  guardarCargaEncuesta: (...a) => mockGuardar(...a),
  listCargasEncuesta: (...a) => mockListar(...a),
}));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/encuesta-satisfaccion',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import EncuestaSatisfaccionPage from '../app/motored/encuesta-satisfaccion/page';

const FILE = new File(['x'], 'clientes.xlsx', {
  type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
});
const OTHER = new File(['y'], 'otro.xlsx');

function pick(file) {
  const input = document.querySelector('input[type="file"]');
  fireEvent.change(input, { target: { files: [file] } });
}

async function renderPage(role = 'ADMIN') {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 't');
  render(<EncuestaSatisfaccionPage />);
  await screen.findByText('Enlace de la encuesta');
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  mockListar.mockResolvedValue([]);
  Object.assign(navigator, { clipboard: { writeText: jest.fn().mockResolvedValue() } });
});

describe('Encuesta admin — link', () => {
  it('shows the public survey URL read-only and copies it', async () => {
    await renderPage();
    const field = screen.getByLabelText('Enlace de la encuesta');
    expect(field).toHaveAttribute('readonly');
    expect(field.value).toBe(`${window.location.origin}/motored/encuesta`);
    expect(screen.getByText(/final del mensaje de WhatsApp en Escala/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Copiar enlace' }));
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(`${window.location.origin}/motored/encuesta`)
    );
    expect(await screen.findByText('Enlace copiado')).toBeInTheDocument();
  });
});

describe('Encuesta admin — upload', () => {
  it('allows SERVICIO_CLIENTE on this page', async () => {
    await renderPage('SERVICIO_CLIENTE');
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('downloads the template', async () => {
    mockDescargar.mockResolvedValue();
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Descargar plantilla' }));
    await waitFor(() => expect(mockDescargar).toHaveBeenCalled());
  });

  it('keeps Validar and Guardar disabled without a file', async () => {
    await renderPage();
    expect(screen.getByRole('button', { name: 'Validar' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Guardar carga' })).toBeDisabled();
  });

  it('shows errors table when validation fails and keeps save disabled', async () => {
    mockValidar.mockResolvedValue({
      ok: false, total_filas: 3,
      errores: [{ fila: 2, motivo: 'Cédula vacía' }, { fila: 3, motivo: 'Placa vacía' }],
      advertencias: [],
    });
    await renderPage();
    pick(FILE);
    fireEvent.click(screen.getByRole('button', { name: 'Validar' }));

    expect(await screen.findByText('Cédula vacía')).toBeInTheDocument();
    expect(screen.getByText('Placa vacía')).toBeInTheDocument();
    expect(screen.getByText(/3 filas/)).toBeInTheDocument();
    expect(mockValidar).toHaveBeenCalledWith(FILE);
    expect(screen.getByRole('button', { name: 'Guardar carga' })).toBeDisabled();
  });

  it('enables save after a valid validation, shows warnings, and saves', async () => {
    mockValidar.mockResolvedValue({
      ok: true, total_filas: 5, errores: [],
      advertencias: ['2 registros de Venta se guardaron pero aún no se encuestan'],
    });
    mockGuardar.mockResolvedValue({ ok: true, total_filas: 5, insertados: 5, errores: [], advertencias: [] });
    await renderPage();
    pick(FILE);
    fireEvent.click(screen.getByRole('button', { name: 'Validar' }));
    expect(await screen.findByText(/2 registros de Venta/)).toBeInTheDocument();

    const save = screen.getByRole('button', { name: 'Guardar carga' });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    expect(await screen.findByText(/5 registros guardados/)).toBeInTheDocument();
    expect(mockGuardar).toHaveBeenCalledWith(FILE);
    await waitFor(() => expect(mockListar).toHaveBeenCalledTimes(2));
  });

  it('disables save again when a different file is picked after validating', async () => {
    mockValidar.mockResolvedValue({ ok: true, total_filas: 1, errores: [], advertencias: [] });
    await renderPage();
    pick(FILE);
    fireEvent.click(screen.getByRole('button', { name: 'Validar' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar carga' })).toBeEnabled());

    pick(OTHER);
    expect(screen.getByRole('button', { name: 'Guardar carga' })).toBeDisabled();
  });

  it('shows an error message when saving is rejected with errors', async () => {
    mockValidar.mockResolvedValue({ ok: true, total_filas: 1, errores: [], advertencias: [] });
    mockGuardar.mockResolvedValue({ ok: false, total_filas: 1, errores: [{ fila: 2, motivo: 'Duplicado' }] });
    await renderPage();
    pick(FILE);
    fireEvent.click(screen.getByRole('button', { name: 'Validar' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar carga' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Guardar carga' }));
    expect(await screen.findByText('Duplicado')).toBeInTheDocument();
  });
});

describe('Encuesta admin — template columns and list', () => {
  it('explains the template columns with a SIC tooltip', async () => {
    await renderPage();
    const region = screen.getByText('Columnas de la plantilla').closest('section');
    ['Nombre', 'Cédula', 'Celular', 'Línea', 'Placa', 'Centro de servicio', 'Tipo'].forEach((c) =>
      expect(within(region).getAllByText(new RegExp(`^${c}`)).length).toBeGreaterThan(0)
    );
    expect(within(region).getByRole('note', { name: /HMCL/ })).toBeInTheDocument();
  });

  it('renders the uploads table with respondidas and percentage', async () => {
    mockListar.mockResolvedValue([
      { id: '1', nombre_archivo: 'mayo.xlsx', total_registros: 200, respondidos: 50,
        created_at: '2026-05-04T15:30:00', usuario: 'Ana' },
      { id: '2', nombre_archivo: 'vacia.xlsx', total_registros: 0, respondidos: 0,
        created_at: '2026-05-05T15:30:00', usuario: null },
    ]);
    await renderPage();
    const row = (await screen.findByText('mayo.xlsx')).closest('tr');
    expect(within(row).getByText('Ana')).toBeInTheDocument();
    expect(within(row).getByText('200')).toBeInTheDocument();
    expect(within(row).getByText('50 (25%)')).toBeInTheDocument();
    const empty = screen.getByText('vacia.xlsx').closest('tr');
    expect(within(empty).getByText('0 (0%)')).toBeInTheDocument();
    ['Archivo', 'Fecha', 'Cargado por', 'Registros', 'Respondidas'].forEach((h) =>
      expect(screen.getByRole('columnheader', { name: h })).toBeInTheDocument()
    );
  });

  it('renders an empty state', async () => {
    await renderPage();
    expect(await screen.findByText('Todavía no hay cargas de clientes.')).toBeInTheDocument();
  });

  it('renders a load error', async () => {
    mockListar.mockRejectedValue(new Error('boom'));
    await renderPage();
    expect(await screen.findByText(/boom/)).toBeInTheDocument();
  });
});
