/**
 * Tests for the Superadmin Data Editor page, introduced in:
 *   sdd/superadmin-data-editor, Phase 6 (frontend)
 *
 * Backend contract (backend/app/api/v1/superadmin_data.py, Phases 1-5,
 * already complete):
 *   GET  /superadmin/data/vehicles?plate=       -> 200 vehicle | 404
 *   PUT  /superadmin/data/vehicles/{id}          -> 200 vehicle | 404 | 409 (string detail)
 *   GET  /superadmin/data/orders?plate=&order_id= -> 200 order | 404
 *   PUT  /superadmin/data/orders/{id}            -> 200 order | 404 | 422 (string detail)
 *                                                    | 409 {"detail": {"detail": msg, "code": "CONFIRM_DELETE_EVENT"}}
 *
 * Covers:
 *   - Two-tab rendering (Vehículo / Orden)
 *   - Vehículo: search populates form; PUT sends ONLY whitelisted fields;
 *     404/409 surfaced via toast
 *   - Orden: search populates form (dates + mileage_km + service_type);
 *     404/422 surfaced via toast
 *   - Orden: 409 CONFIRM_DELETE_EVENT opens ConfirmModal with the event/plate
 *     message; confirming resubmits with confirm_delete_event=true; canceling
 *     sends no further request
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));
jest.mock('../lib/api', () => ({
  getApiUrl: () => 'https://api.test',
}));
jest.mock('../lib/toast', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

jest.mock('../app/admin-layout', () => {
  const MockAdminLayout = ({ children }) => <div>{children}</div>;
  MockAdminLayout.displayName = 'MockAdminLayout';
  return MockAdminLayout;
});

import { toast as mockToast } from '../lib/toast';
import SuperadminDataPage from '../app/superadmin-data/page';

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  };
}

const VEHICLE = {
  id: 'v-1',
  plate: 'ABC123',
  vin: 'VIN0001',
  brand: 'UM',
  model: 'Renegade 200',
  color: 'Rojo',
  year: 2023,
  mileage: 5000,
};

const ORDER = {
  id: 'o-1',
  plate: 'ABC123',
  status: 'completed',
  service_type: 'km_review',
  created_at: '2026-07-01T00:00:00',
  delivered_at: '2026-07-03T00:00:00',
  mileage_km: '15000.00',
};

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.error.mockReset();
  mockToast.success.mockReset();
});

describe('SuperadminDataPage — tab structure', () => {
  it('renders both the Vehículo and Orden tab controls', () => {
    render(<SuperadminDataPage />);
    expect(screen.getByRole('button', { name: 'Vehículo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Orden' })).toBeInTheDocument();
  });
});

describe('SuperadminDataPage — Vehículo tab', () => {
  it('populates the form with the found vehicle on a successful search', async () => {
    mockAuthFetch.mockResolvedValueOnce(makeResponse(200, VEHICLE));

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

    await waitFor(() => {
      expect(screen.getByLabelText('VIN')).toHaveValue('VIN0001');
    });
    expect(screen.getByLabelText('Marca')).toHaveValue('UM');
    expect(screen.getByLabelText('Modelo')).toHaveValue('Renegade 200');
    expect(mockAuthFetch).toHaveBeenCalledWith(expect.stringContaining('/superadmin/data/vehicles?plate=ABC123'));
  });

  it('shows an error toast and no form when the plate is not found (404)', async () => {
    mockAuthFetch.mockResolvedValueOnce(makeResponse(404, { detail: 'Vehículo no encontrado' }));

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ZZZ999' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Vehículo no encontrado');
    });
    expect(screen.queryByLabelText('VIN')).not.toBeInTheDocument();
  });

  it('PUTs only the whitelisted vehicle fields on save and shows a success toast', async () => {
    mockAuthFetch.mockResolvedValueOnce(makeResponse(200, VEHICLE));
    mockAuthFetch.mockResolvedValueOnce(makeResponse(200, { ...VEHICLE, plate: 'XYZ789' }));

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => expect(screen.getByLabelText('VIN')).toHaveValue('VIN0001'));

    fireEvent.change(screen.getByLabelText('Placa'), { target: { value: 'XYZ789' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(mockToast.success).toHaveBeenCalled();
    });

    const [url, options] = mockAuthFetch.mock.calls[1];
    expect(url).toContain('/superadmin/data/vehicles/v-1');
    expect(options.method).toBe('PUT');
    const sentBody = JSON.parse(options.body);
    expect(Object.keys(sentBody).sort()).toEqual(['brand', 'color', 'mileage', 'model', 'plate', 'vin', 'year'].sort());
    expect(sentBody.plate).toBe('XYZ789');
  });

  it('shows the 409 duplicate-plate message via toast without clearing the loaded form', async () => {
    mockAuthFetch.mockResolvedValueOnce(makeResponse(200, VEHICLE));
    mockAuthFetch.mockResolvedValueOnce(makeResponse(409, { detail: 'La placa ya está registrada en otro vehículo' }));

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => expect(screen.getByLabelText('VIN')).toHaveValue('VIN0001'));

    fireEvent.change(screen.getByLabelText('Placa'), { target: { value: 'DUP001' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('La placa ya está registrada en otro vehículo');
    });
  });
});

describe('SuperadminDataPage — Orden tab', () => {
  async function goToOrderTab() {
    fireEvent.click(screen.getByRole('button', { name: 'Orden' }));
  }

  it('populates dates, mileage_km and service_type on a successful search', async () => {
    mockAuthFetch.mockResolvedValueOnce(makeResponse(200, ORDER));

    render(<SuperadminDataPage />);
    await goToOrderTab();
    fireEvent.change(screen.getByLabelText('Valor de búsqueda de orden'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

    await waitFor(() => {
      expect(screen.getByLabelText('Fecha de creación')).toHaveValue('2026-07-01');
    });
    expect(screen.getByLabelText('Fecha de entrega')).toHaveValue('2026-07-03');
    expect(screen.getByLabelText('Kilometraje de orden')).toHaveValue(15000);
    expect(screen.getByLabelText('Tipo de servicio')).toHaveValue('km_review');
  });

  it('shows a picker when the plate matches multiple orders, and selecting one loads its form', async () => {
    const older = { ...ORDER, id: 'o-old', created_at: '2026-01-01T00:00:00', delivered_at: null, service_type: 'regular' };
    const newer = { ...ORDER, id: 'o-new' };
    mockAuthFetch.mockResolvedValueOnce(makeResponse(200, { multiple_matches: true, matches: [newer, older] }));

    render(<SuperadminDataPage />);
    await goToOrderTab();
    fireEvent.change(screen.getByLabelText('Valor de búsqueda de orden'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

    await waitFor(() => {
      expect(screen.getByText(/varias órdenes/i)).toBeInTheDocument();
    });
    expect(screen.queryByLabelText('Fecha de creación')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /o-old/ }));

    await waitFor(() => {
      expect(screen.getByLabelText('Fecha de creación')).toHaveValue('2026-01-01');
    });
    expect(screen.queryByText(/varias órdenes/i)).not.toBeInTheDocument();
  });

  it('shows an error toast when the order is not found (404)', async () => {
    mockAuthFetch.mockResolvedValueOnce(makeResponse(404, { detail: 'Orden no encontrada' }));

    render(<SuperadminDataPage />);
    await goToOrderTab();
    fireEvent.change(screen.getByLabelText('Valor de búsqueda de orden'), { target: { value: 'ZZZ999' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Orden no encontrada');
    });
  });

  it('shows the 422 date-order block message via toast', async () => {
    mockAuthFetch.mockResolvedValueOnce(makeResponse(200, ORDER));
    mockAuthFetch.mockResolvedValueOnce(makeResponse(422, {
      detail: 'La fecha de entrega no puede ser anterior a la fecha de creación',
    }));

    render(<SuperadminDataPage />);
    await goToOrderTab();
    fireEvent.change(screen.getByLabelText('Valor de búsqueda de orden'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => expect(screen.getByLabelText('Fecha de creación')).toHaveValue('2026-07-01'));

    fireEvent.change(screen.getByLabelText('Fecha de entrega'), { target: { value: '2026-06-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('La fecha de entrega no puede ser anterior a la fecha de creación');
    });
  });

  it('opens ConfirmModal on 409 CONFIRM_DELETE_EVENT and resubmits with confirm_delete_event=true on confirm', async () => {
    mockAuthFetch.mockResolvedValueOnce(makeResponse(200, ORDER));
    mockAuthFetch.mockResolvedValueOnce(makeResponse(409, {
      detail: {
        detail: 'Esta corrección eliminará el evento MANTENIMIENTO (id E2) del historial del vehículo ABC123.',
        code: 'CONFIRM_DELETE_EVENT',
      },
    }));
    mockAuthFetch.mockResolvedValueOnce(makeResponse(200, { ...ORDER, service_type: 'regular' }));

    render(<SuperadminDataPage />);
    await goToOrderTab();
    fireEvent.change(screen.getByLabelText('Valor de búsqueda de orden'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => expect(screen.getByLabelText('Tipo de servicio')).toHaveValue('km_review'));

    fireEvent.change(screen.getByLabelText('Tipo de servicio'), { target: { value: 'regular' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(screen.getByText(/eliminará el evento MANTENIMIENTO/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Sí, eliminar/ }));

    await waitFor(() => {
      expect(mockToast.success).toHaveBeenCalled();
    });

    const [, confirmedOptions] = mockAuthFetch.mock.calls[2];
    const confirmedBody = JSON.parse(confirmedOptions.body);
    expect(confirmedBody.confirm_delete_event).toBe(true);
    expect(screen.queryByText(/eliminará el evento MANTENIMIENTO/)).not.toBeInTheDocument();
  });

  it('sends no further request when the ConfirmModal is canceled', async () => {
    mockAuthFetch.mockResolvedValueOnce(makeResponse(200, ORDER));
    mockAuthFetch.mockResolvedValueOnce(makeResponse(409, {
      detail: {
        detail: 'Esta corrección eliminará el evento MANTENIMIENTO (id E2) del historial del vehículo ABC123.',
        code: 'CONFIRM_DELETE_EVENT',
      },
    }));

    render(<SuperadminDataPage />);
    await goToOrderTab();
    fireEvent.change(screen.getByLabelText('Valor de búsqueda de orden'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => expect(screen.getByLabelText('Tipo de servicio')).toHaveValue('km_review'));

    fireEvent.change(screen.getByLabelText('Tipo de servicio'), { target: { value: 'regular' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(screen.getByText(/eliminará el evento MANTENIMIENTO/)).toBeInTheDocument();
    });

    const callsBeforeCancel = mockAuthFetch.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));

    await waitFor(() => {
      expect(screen.queryByText(/eliminará el evento MANTENIMIENTO/)).not.toBeInTheDocument();
    });
    expect(mockAuthFetch.mock.calls.length).toBe(callsBeforeCancel);
  });
});
