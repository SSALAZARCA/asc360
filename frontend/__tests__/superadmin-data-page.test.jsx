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
 *   GET  /vehicle-models                          -> 200 [{id, modelo}, ...] (fetched on mount by the Vehículo tab)
 *   GET  /vehicles/vin/{vin}                      -> 200 {model, year, color} | 404
 *
 * Covers:
 *   - Two-tab rendering (Vehículo / Orden)
 *   - Vehículo: search populates form; PUT sends ONLY whitelisted fields;
 *     404/409 surfaced via toast
 *   - Vehículo: Modelo renders as a catalog <select>; VIN blur looks up the
 *     VIN master and fills model/year/color, or shows a not-found hint
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

// The Vehículo tab always fires GET /vehicle-models on mount (its Modelo
// catalog), regardless of which tab is showing -- SuperadminDataPage mounts
// the Vehículo tab first by default. Real test scenarios only care about the
// OTHER calls (search/save/VIN lookup), so the mock routes by URL instead of
// by call position: `/vehicle-models` always answers from `mockVehicleModels`
// (defaults to an empty catalog, overridable per test), and every other call
// consumes the given `responses` queue in order.
let mockVehicleModels = [];

function queueResponses(...responses) {
  let i = 0;
  mockAuthFetch.mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/vehicle-models')) {
      return Promise.resolve(makeResponse(200, mockVehicleModels));
    }
    return Promise.resolve(responses[i++]);
  });
}

function nonCatalogCalls() {
  return mockAuthFetch.mock.calls.filter(([url]) => !(typeof url === 'string' && url.includes('/vehicle-models')));
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockVehicleModels = [];
  queueResponses();
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
    queueResponses(makeResponse(200, VEHICLE));

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
    queueResponses(makeResponse(404, { detail: 'Vehículo no encontrado' }));

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ZZZ999' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Vehículo no encontrado');
    });
    expect(screen.queryByLabelText('VIN')).not.toBeInTheDocument();
  });

  it('PUTs only the whitelisted vehicle fields on save and shows a success toast', async () => {
    queueResponses(makeResponse(200, VEHICLE), makeResponse(200, { ...VEHICLE, plate: 'XYZ789' }));

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => expect(screen.getByLabelText('VIN')).toHaveValue('VIN0001'));

    fireEvent.change(screen.getByLabelText('Placa'), { target: { value: 'XYZ789' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(mockToast.success).toHaveBeenCalled();
    });

    const [url, options] = nonCatalogCalls()[1];
    expect(url).toContain('/superadmin/data/vehicles/v-1');
    expect(options.method).toBe('PUT');
    const sentBody = JSON.parse(options.body);
    expect(Object.keys(sentBody).sort()).toEqual(['brand', 'color', 'model', 'plate', 'vin', 'year'].sort());
    expect(sentBody.plate).toBe('XYZ789');
  });

  it('shows the 409 duplicate-plate message via toast without clearing the loaded form', async () => {
    queueResponses(
      makeResponse(200, VEHICLE),
      makeResponse(409, { detail: 'La placa ya está registrada en otro vehículo' }),
    );

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

describe('SuperadminDataPage — Vehículo tab — catálogo de modelos y lookup de VIN', () => {
  it('renders Modelo as a <select> fed by GET /vehicle-models once the catalog loads', async () => {
    mockVehicleModels = [{ id: 'm1', modelo: 'Renegade 200' }, { id: 'm2', modelo: 'NKD 125' }];
    queueResponses(makeResponse(200, VEHICLE));

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

    await waitFor(() => expect(screen.getByLabelText('Modelo').tagName).toBe('SELECT'));
    expect(screen.getByLabelText('Modelo')).toHaveValue('Renegade 200');
  });

  it('falls back to a free-text Modelo input when the catalog fails to load', async () => {
    queueResponses(makeResponse(200, VEHICLE));

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

    await waitFor(() => expect(screen.getByLabelText('VIN')).toHaveValue('VIN0001'));
    expect(screen.getByLabelText('Modelo').tagName).toBe('INPUT');
  });

  it('looking up a 17-character VIN on blur fills model/year/color from the VIN master', async () => {
    queueResponses(
      makeResponse(200, { ...VEHICLE, model: '', color: '', year: '' }),
      makeResponse(200, { model: 'Renegade 200', year: 2024, color: 'Rojo' }),
    );

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => expect(screen.getByLabelText('VIN')).toHaveValue('VIN0001'));

    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: 'SD5CCML06TL000359' } });
    fireEvent.blur(screen.getByLabelText('VIN'));

    await waitFor(() => expect(screen.getByLabelText('Color')).toHaveValue('Rojo'));
    expect(screen.getByLabelText('Modelo')).toHaveValue('Renegade 200');
    expect(screen.getByLabelText('Año')).toHaveValue(2024);
    expect(screen.getByText(/Datos encontrados/)).toBeInTheDocument();

    const [url] = nonCatalogCalls()[1];
    expect(url).toContain('/vehicles/vin/SD5CCML06TL000359');
  });

  it('shows a not-found hint and leaves the form untouched when the VIN has no match', async () => {
    queueResponses(makeResponse(200, VEHICLE), makeResponse(404, {}));

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => expect(screen.getByLabelText('VIN')).toHaveValue('VIN0001'));

    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: 'ZZZZZZZZZZZZZZZZZ' } });
    fireEvent.blur(screen.getByLabelText('VIN'));

    await waitFor(() => {
      expect(screen.getByText(/No está en el maestro/)).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Modelo')).toHaveValue('Renegade 200');
  });

  it('does not trigger a VIN lookup for a partial (non-17-char) VIN', async () => {
    queueResponses(makeResponse(200, VEHICLE));

    render(<SuperadminDataPage />);
    fireEvent.change(screen.getByLabelText('Buscar vehículo por placa'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => expect(screen.getByLabelText('VIN')).toHaveValue('VIN0001'));

    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: 'SD5CCML06TL' } });
    fireEvent.blur(screen.getByLabelText('VIN'));

    expect(nonCatalogCalls()).toHaveLength(1);
  });
});

describe('SuperadminDataPage — Orden tab', () => {
  async function goToOrderTab() {
    fireEvent.click(screen.getByRole('button', { name: 'Orden' }));
  }

  it('populates dates, mileage_km and service_type on a successful search', async () => {
    queueResponses(makeResponse(200, ORDER));

    render(<SuperadminDataPage />);
    await goToOrderTab();
    fireEvent.change(screen.getByLabelText('Valor de búsqueda de orden'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

    // ORDER's dates are UTC ("...T00:00:00"); the form must show Bogotá
    // wall-clock time (UTC-5), so they land on the PREVIOUS calendar day.
    await waitFor(() => {
      expect(screen.getByLabelText('Fecha de creación')).toHaveValue('2026-06-30T19:00');
    });
    expect(screen.getByLabelText('Fecha de entrega')).toHaveValue('2026-07-02T19:00');
    expect(screen.getByLabelText('Kilometraje de orden')).toHaveValue(15000);
    expect(screen.getByLabelText('Tipo de servicio')).toHaveValue('km_review');
  });

  it('shows a picker when the plate matches multiple orders, and selecting one re-fetches the full order by id (so fields like mileage_km trimmed from the list come back accurate)', async () => {
    // The multiple_matches list is intentionally lightweight (no mileage_km) —
    // selecting an entry must re-fetch by order_id rather than trusting it.
    const older = { ...ORDER, id: 'o-old', created_at: '2026-01-01T00:00:00', delivered_at: null, service_type: 'regular', mileage_km: null };
    const newer = { ...ORDER, id: 'o-new', mileage_km: null };
    queueResponses(
      makeResponse(200, { multiple_matches: true, matches: [newer, older] }),
      makeResponse(200, { ...older, mileage_km: '9000.00' }),
    );

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
      expect(screen.getByLabelText('Fecha de creación')).toHaveValue('2025-12-31T19:00');
    });
    expect(screen.getByLabelText('Kilometraje de orden')).toHaveValue(9000);
    expect(nonCatalogCalls()[1][0]).toContain('order_id=o-old');
    expect(screen.queryByText(/varias órdenes/i)).not.toBeInTheDocument();
  });

  it('shows an error toast when the order is not found (404)', async () => {
    queueResponses(makeResponse(404, { detail: 'Orden no encontrada' }));

    render(<SuperadminDataPage />);
    await goToOrderTab();
    fireEvent.change(screen.getByLabelText('Valor de búsqueda de orden'), { target: { value: 'ZZZ999' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Orden no encontrada');
    });
  });

  it('shows the 422 date-order block message via toast', async () => {
    queueResponses(
      makeResponse(200, ORDER),
      makeResponse(422, {
        detail: 'La fecha de entrega no puede ser anterior a la fecha de creación',
      }),
    );

    render(<SuperadminDataPage />);
    await goToOrderTab();
    fireEvent.change(screen.getByLabelText('Valor de búsqueda de orden'), { target: { value: 'ABC123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => expect(screen.getByLabelText('Fecha de creación')).toHaveValue('2026-06-30T19:00'));

    fireEvent.change(screen.getByLabelText('Fecha de entrega'), { target: { value: '2026-06-01T00:00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('La fecha de entrega no puede ser anterior a la fecha de creación');
    });
  });

  it('opens ConfirmModal on 409 CONFIRM_DELETE_EVENT and resubmits with confirm_delete_event=true on confirm', async () => {
    queueResponses(
      makeResponse(200, ORDER),
      makeResponse(409, {
        detail: {
          detail: 'Esta corrección eliminará el evento MANTENIMIENTO (id E2) del historial del vehículo ABC123.',
          code: 'CONFIRM_DELETE_EVENT',
        },
      }),
      makeResponse(200, { ...ORDER, service_type: 'regular' }),
    );

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

    const [, confirmedOptions] = nonCatalogCalls()[2];
    const confirmedBody = JSON.parse(confirmedOptions.body);
    expect(confirmedBody.confirm_delete_event).toBe(true);
    expect(screen.queryByText(/eliminará el evento MANTENIMIENTO/)).not.toBeInTheDocument();
  });

  it('sends no further request when the ConfirmModal is canceled', async () => {
    queueResponses(
      makeResponse(200, ORDER),
      makeResponse(409, {
        detail: {
          detail: 'Esta corrección eliminará el evento MANTENIMIENTO (id E2) del historial del vehículo ABC123.',
          code: 'CONFIRM_DELETE_EVENT',
        },
      }),
    );

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
