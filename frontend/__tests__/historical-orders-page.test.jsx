/**
 * Tests for the Historical Order Entry page, introduced in:
 *   sdd/historical-order-entry, Phase 6 (frontend, PR4)
 *
 * Backend contract (backend/app/api/v1/superadmin_historical_orders.py,
 * backend/app/schemas/historical_order.py, already complete from PR1/PR2):
 *   POST /superadmin/data/historical-orders
 *     -> 201 HistoricalOrderOut {id, tenant_id, vehicle_id, client_id, status,
 *        service_type, created_at, completed_at, delivered_at}
 *     -> 409 {"detail": {"detail": msg, "code": "DUPLICATE_ORDER_WARNING",
 *        "matches": [{order_id, plate, created_at, status}, ...]}}
 *   GET  /tenants                  -> 200 [{id, name}, ...] (taller picker)
 *   GET  /vehicle-models            -> 200 [{id, modelo}, ...] (Modelo catalog)
 *   GET  /vehicles/vin/{vin}        -> 200 {model, year, color} | 404
 *
 * Covers:
 *   - Required-field validation prevents submit (no fetch fired)
 *   - Taller <select> is populated from GET /tenants and required
 *   - VIN lookup (17 chars) autofills model/color/year without manual selection
 *   - Unmatched model from VIN lookup still shows visibly (ModelSelectField's
 *     own guarantee) instead of going blank
 *   - Duplicate warning 409 shows a confirm UI; confirming resubmits with
 *     acknowledge_duplicate: true and succeeds
 *   - Submitted created_at is the Bogotá -> naive-UTC conversion (no trailing Z)
 *   - No cédula/identification input exists anywhere on the page
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
import HistoricalOrdersPage from '../app/historical-orders/page';

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  };
}

const TENANTS = [{ id: 't-1', name: 'Taller Central' }];
const MODELS = [{ id: 'm-1', modelo: 'Renegade 200' }];

// Routes GET calls by URL so every test only has to declare the responses it
// actually cares about (POST + VIN lookup); tenants/models are answered from
// module-level defaults, overridable per test.
let mockTenants = TENANTS;
let mockModels = MODELS;

function queueResponses(...responses) {
  let i = 0;
  mockAuthFetch.mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/tenants')) {
      return Promise.resolve(makeResponse(200, mockTenants));
    }
    if (typeof url === 'string' && url.includes('/vehicle-models')) {
      return Promise.resolve(makeResponse(200, mockModels));
    }
    return Promise.resolve(responses[i++]);
  });
}

function nonCatalogCalls() {
  return mockAuthFetch.mock.calls.filter(
    ([url]) => !(typeof url === 'string' && (url.includes('/tenants') || url.includes('/vehicle-models')))
  );
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.error.mockReset();
  mockToast.success.mockReset();
  mockTenants = TENANTS;
  mockModels = MODELS;
});

async function fillRequiredFields() {
  // The Taller <select> starts with only the placeholder option until
  // GET /tenants resolves -- wait for the real option to actually render,
  // otherwise fireEvent.change silently no-ops (jsdom ignores a value with
  // no matching <option>).
  await waitFor(() => {
    expect(screen.getByText('Taller Central')).toBeInTheDocument();
  });
  fireEvent.change(screen.getByLabelText('Taller'), { target: { value: 't-1' } });
  fireEvent.change(screen.getByLabelText('Placa'), { target: { value: 'ABC123' } });
  fireEvent.change(screen.getByLabelText('Nombre del cliente'), { target: { value: 'Juan Pérez' } });
  fireEvent.change(screen.getByLabelText('Fecha de creación'), { target: { value: '2025-01-10T09:30' } });
  fireEvent.change(screen.getByLabelText('Kilometraje'), { target: { value: '1500' } });
}

describe('HistoricalOrdersPage — required-field validation', () => {
  it('does not submit when required fields are missing', async () => {
    queueResponses();
    render(<HistoricalOrdersPage />);

    await waitFor(() => {
      expect(screen.getByLabelText('Taller')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /crear orden histórica/i }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalled();
    });
    expect(nonCatalogCalls()).toHaveLength(0);
  });

  it('submits once all required fields are filled', async () => {
    queueResponses(makeResponse(201, {
      id: 'order-1', tenant_id: 't-1', vehicle_id: 'v-1', client_id: 'c-1',
      status: 'received', service_type: 'regular',
      created_at: '2025-01-10T14:30:00', completed_at: null, delivered_at: null,
    }));
    render(<HistoricalOrdersPage />);
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear orden histórica/i }));

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(1);
    });
    const [url, options] = nonCatalogCalls()[0];
    expect(url).toBe('/superadmin/data/historical-orders');
    const body = JSON.parse(options.body);
    // Bogotá 2025-01-10T09:30 (UTC-5) -> naive UTC 2025-01-10T14:30:00, no trailing Z
    expect(body.created_at).toBe('2025-01-10T14:30:00');
    expect(body.created_at.endsWith('Z')).toBe(false);
    expect(body.tenant_id).toBe('t-1');
    expect(body.vehicle.plate).toBe('ABC123');
    expect(body.client.name).toBe('Juan Pérez');

    await waitFor(() => {
      expect(screen.getByText(/creada correctamente/i)).toBeInTheDocument();
    });
  });
});

describe('HistoricalOrdersPage — Taller picker', () => {
  it('populates the Taller <select> from GET /tenants', async () => {
    mockTenants = [{ id: 't-9', name: 'Taller Norte' }];
    queueResponses();
    render(<HistoricalOrdersPage />);

    await waitFor(() => {
      expect(screen.getByText('Taller Norte')).toBeInTheDocument();
    });
    const select = screen.getByLabelText('Taller');
    expect(select).toBeRequired();
  });
});

describe('HistoricalOrdersPage — VIN lookup + Modelo select', () => {
  it('autofills model/year/color when the VIN lookup finds a match', async () => {
    queueResponses(makeResponse(200, { model: 'Renegade 200', year: 2023, color: 'Rojo' }));
    render(<HistoricalOrdersPage />);
    await waitFor(() => expect(screen.getByLabelText('VIN')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: '1HGCM82633A004352' } });

    await waitFor(() => {
      expect(screen.getByLabelText('Modelo').value).toBe('Renegade 200');
    });
    expect(screen.getByLabelText('Año').value).toBe('2023');
    expect(screen.getByLabelText('Color').value).toBe('Rojo');
  });

  it('shows an unmatched model as a visible extra option instead of blank', async () => {
    queueResponses(makeResponse(200, { model: 'RENEGADE SPORT 200S', year: 2024, color: 'Negro' }));
    render(<HistoricalOrdersPage />);
    await waitFor(() => expect(screen.getByLabelText('VIN')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: '1HGCM82633A004352' } });

    await waitFor(() => {
      expect(screen.getByLabelText('Modelo').value).toBe('RENEGADE SPORT 200S');
    });
    expect(screen.getByText(/RENEGADE SPORT 200S \(no está en el catálogo estándar\)/i)).toBeInTheDocument();
  });

  it('also autofills brand and client name/phone when the VIN already has a registered vehicle+client', async () => {
    queueResponses(makeResponse(200, {
      model: 'Renegade 200', year: 2023, color: 'Rojo',
      brand: 'UM', client_name: 'Juan Pérez', client_phone: '3001234567',
    }));
    render(<HistoricalOrdersPage />);
    await waitFor(() => expect(screen.getByLabelText('VIN')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: '1HGCM82633A004352' } });

    await waitFor(() => {
      expect(screen.getByLabelText('Modelo').value).toBe('Renegade 200');
    });
    expect(screen.getByLabelText('Marca').value).toBe('UM');
    expect(screen.getByLabelText('Nombre del cliente').value).toBe('Juan Pérez');
    expect(screen.getByLabelText('Teléfono del cliente').value).toBe('3001234567');
  });

  it('leaves brand and client name/phone blank when the VIN has no registered vehicle yet', async () => {
    queueResponses(makeResponse(200, { model: 'Renegade 200', year: 2023, color: 'Rojo' }));
    render(<HistoricalOrdersPage />);
    await waitFor(() => expect(screen.getByLabelText('VIN')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: '1HGCM82633A004352' } });

    await waitFor(() => {
      expect(screen.getByLabelText('Modelo').value).toBe('Renegade 200');
    });
    expect(screen.getByLabelText('Marca').value).toBe('');
    expect(screen.getByLabelText('Nombre del cliente').value).toBe('');
    expect(screen.getByLabelText('Teléfono del cliente').value).toBe('');
  });

  it('keeps whatever was already typed in brand/client name/phone when the lookup has nothing to enrich with', async () => {
    // Same fallback-only-if-empty semantics already used for model/year/color
    // (`data.model || f.model`) -- a lookup response with no brand/client
    // data (VIN not yet registered to a vehicle) must not blank out fields
    // the user already filled in by hand.
    queueResponses(makeResponse(200, { model: 'Renegade 200', year: 2023, color: 'Rojo' }));
    render(<HistoricalOrdersPage />);
    await waitFor(() => expect(screen.getByLabelText('VIN')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('Marca'), { target: { value: 'Yamaha' } });
    fireEvent.change(screen.getByLabelText('Nombre del cliente'), { target: { value: 'Pedro Gómez' } });
    fireEvent.change(screen.getByLabelText('Teléfono del cliente'), { target: { value: '3009999999' } });
    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: '1HGCM82633A004352' } });

    await waitFor(() => {
      expect(screen.getByLabelText('Modelo').value).toBe('Renegade 200');
    });
    expect(screen.getByLabelText('Marca').value).toBe('Yamaha');
    expect(screen.getByLabelText('Nombre del cliente').value).toBe('Pedro Gómez');
    expect(screen.getByLabelText('Teléfono del cliente').value).toBe('3009999999');
  });
});

describe('HistoricalOrdersPage — duplicate warning flow', () => {
  it('shows a confirm UI on 409 DUPLICATE_ORDER_WARNING and succeeds after acknowledging', async () => {
    queueResponses(
      makeResponse(409, {
        detail: {
          detail: 'Ya existe una orden para la placa ABC123 en la fecha 2025-01-10.',
          code: 'DUPLICATE_ORDER_WARNING',
          matches: [{ order_id: 'existing-1', plate: 'ABC123', created_at: '2025-01-10T10:00:00', status: 'delivered' }],
        },
      }),
      makeResponse(201, {
        id: 'order-2', tenant_id: 't-1', vehicle_id: 'v-1', client_id: 'c-1',
        status: 'received', service_type: 'regular',
        created_at: '2025-01-10T14:30:00', completed_at: null, delivered_at: null,
      })
    );
    render(<HistoricalOrdersPage />);
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear orden histórica/i }));

    await waitFor(() => {
      expect(screen.getByText(/ya existe una orden para la placa abc123/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /cargar de todas formas/i }));

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(2);
    });
    const secondBody = JSON.parse(nonCatalogCalls()[1][1].body);
    expect(secondBody.acknowledge_duplicate).toBe(true);

    await waitFor(() => {
      expect(screen.getByText(/creada correctamente/i)).toBeInTheDocument();
    });
  });
});

describe('HistoricalOrdersPage — no cédula/identification field', () => {
  it('never renders a cédula or identification input anywhere on the page', async () => {
    queueResponses();
    render(<HistoricalOrdersPage />);
    await waitFor(() => expect(screen.getByLabelText('Taller')).toBeInTheDocument());

    expect(screen.queryByLabelText(/c[ée]dula/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/identificaci[oó]n/i)).not.toBeInTheDocument();
  });
});
