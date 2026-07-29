/**
 * Tests for the Distribuidor vehicle-delivery registration page, introduced
 * in: sdd/distributor-vehicle-delivery, Phase 7 (frontend, PR7)
 *
 * Backend contract (backend/app/api/v1/distributor_deliveries.py,
 * backend/app/schemas/distributor_delivery.py, already complete from
 * PR3/PR4):
 *   POST /distributor/deliveries   multipart/form-data
 *     payload: str (JSON of DeliveryCreate: {client, vehicle, delivery_date})
 *     photo:   File | undefined
 *     -> 201 DeliveryOut {id, plate, vin, model, color, year, engine_number,
 *        delivery_date, delivery_act_url, client_id}
 *   GET  /vehicles/vin/{vin}   -> 200 {model, year, color, engine_number} | 404
 *   GET  /vehicle-models        -> 200 [{id, modelo}, ...]
 *
 * Covers:
 *   - Required-field validation prevents submit (no fetch fired)
 *   - VIN lookup (17 chars) autofills model/year/color/engine_number
 *   - delivery_date is submitted as a raw "YYYY-MM-DD" string
 *   - A future delivery_date is blocked client-side (no fetch fired)
 *   - Photo is mandatory for parts_dealer (blocked client-side, no fetch
 *     fired), but optional for superadmin (submits successfully with no
 *     photo attached)
 *   - Submission is multipart: FormData with a `payload` field (JSON
 *     string) and, when present, a `photo` file field
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

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
import DistribuidorEntregaPage from '../app/distribuidor/entrega/page';

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  };
}

const MODELS = [{ id: 'm-1', modelo: 'Renegade 200' }];
let mockModels = MODELS;

function queueResponses(...responses) {
  let i = 0;
  mockAuthFetch.mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/vehicle-models')) {
      return Promise.resolve(makeResponse(200, mockModels));
    }
    return Promise.resolve(responses[i++]);
  });
}

function nonCatalogCalls() {
  return mockAuthFetch.mock.calls.filter(
    ([url]) => !(typeof url === 'string' && url.includes('/vehicle-models'))
  );
}

function setUser(role) {
  sessionStorage.setItem('um_user', JSON.stringify({ name: 'Test User', role }));
}

function makeFile(name = 'acta.jpg', type = 'image/jpeg') {
  return new File(['fake-bytes'], name, { type });
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.error.mockReset();
  mockToast.success.mockReset();
  mockModels = MODELS;
  sessionStorage.clear();
});

async function fillRequiredFields({ delivery_date = '2025-01-10' } = {}) {
  fireEvent.change(screen.getByLabelText('Nombre del cliente'), { target: { value: 'Juan Pérez' } });
  fireEvent.change(screen.getByLabelText('Cédula'), { target: { value: '123456789' } });
  fireEvent.change(screen.getByLabelText('Placa'), { target: { value: 'ABC123' } });
  fireEvent.change(screen.getByLabelText('Fecha de entrega'), { target: { value: delivery_date } });
}

describe('DistribuidorEntregaPage — required-field validation', () => {
  it('does not submit when required fields are missing', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    fireEvent.click(screen.getByRole('button', { name: /registrar entrega/i }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalled();
    });
    expect(nonCatalogCalls()).toHaveLength(0);
  });
});

describe('DistribuidorEntregaPage — VIN lookup', () => {
  it('fires the VIN lookup at exactly 17 characters and autofills model/year/color/engine_number', async () => {
    setUser('parts_dealer');
    queueResponses(makeResponse(200, { model: 'Renegade 200', year: 2023, color: 'Rojo', engine_number: 'ENG-999' }));
    render(<DistribuidorEntregaPage />);

    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: '1HGCM82633A004352' } });

    await waitFor(() => {
      expect(screen.getByLabelText('Modelo').value).toBe('Renegade 200');
    });
    expect(screen.getByLabelText('Año').value).toBe('2023');
    expect(screen.getByLabelText('Color').value).toBe('Rojo');
    expect(screen.getByLabelText('Número de motor').value).toBe('ENG-999');
  });

  it('does not fire the lookup before 17 characters', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: '1HGCM82633A00435' } }); // 16 chars

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(0);
    });
  });
});

describe('DistribuidorEntregaPage — future delivery date blocked client-side', () => {
  it('blocks submission when delivery_date is in the future', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    const future = new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    await fillRequiredFields({ delivery_date: future });
    const file = makeFile();
    await userEvent.upload(screen.getByLabelText(/acta de entrega/i), file);

    fireEvent.click(screen.getByRole('button', { name: /registrar entrega/i }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalled();
    });
    expect(nonCatalogCalls()).toHaveLength(0);
  });
});

describe('DistribuidorEntregaPage — photo requirement is role-conditional', () => {
  it('blocks submission for parts_dealer with no photo attached', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /registrar entrega/i }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalled();
    });
    expect(nonCatalogCalls()).toHaveLength(0);
  });

  it('allows submission for superadmin with no photo attached', async () => {
    setUser('superadmin');
    queueResponses(makeResponse(201, {
      id: 'v-1', plate: 'ABC123', vin: null, model: null, color: null, year: null,
      engine_number: null, delivery_date: '2025-01-10', delivery_act_url: null, client_id: 'c-1',
    }));
    render(<DistribuidorEntregaPage />);
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /registrar entrega/i }));

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.getByText(/entrega registrada correctamente/i)).toBeInTheDocument();
    });
  });
});

describe('DistribuidorEntregaPage — successful multipart submission', () => {
  it('submits multipart with a payload field (raw YYYY-MM-DD delivery_date) and a photo field', async () => {
    setUser('parts_dealer');
    queueResponses(makeResponse(201, {
      id: 'v-1', plate: 'ABC123', vin: null, model: null, color: null, year: null,
      engine_number: null, delivery_date: '2025-01-10', delivery_act_url: 'https://minio/act.jpg', client_id: 'c-1',
    }));
    render(<DistribuidorEntregaPage />);
    await fillRequiredFields();

    const file = makeFile();
    await userEvent.upload(screen.getByLabelText(/acta de entrega/i), file);

    fireEvent.click(screen.getByRole('button', { name: /registrar entrega/i }));

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(1);
    });
    const [url, options] = nonCatalogCalls()[0];
    expect(url).toBe('/distributor/deliveries');
    expect(options.body).toBeInstanceOf(FormData);

    const payload = JSON.parse(options.body.get('payload'));
    expect(payload.delivery_date).toBe('2025-01-10');
    expect(payload.client.name).toBe('Juan Pérez');
    expect(payload.client.identification).toBe('123456789');
    expect(payload.vehicle.plate).toBe('ABC123');
    expect(options.body.get('photo')).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText(/entrega registrada correctamente/i)).toBeInTheDocument();
    });
  });
});
