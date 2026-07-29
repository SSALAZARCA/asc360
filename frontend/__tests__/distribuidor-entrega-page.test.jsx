/**
 * Tests for the Distribuidor vehicle-delivery registration page, introduced
 * in: sdd/distributor-vehicle-delivery, Phase 7 (frontend, PR7), converted
 * to a 4-step wizard (Cliente → Vehículo → Entrega → Confirmación) in a
 * post-archive UX follow-up (reversing PR7's flat-form deviation from the
 * original design, which specified this exact wizard).
 *
 * Backend contract (backend/app/api/v1/distributor_deliveries.py,
 * backend/app/schemas/distributor_delivery.py, already complete from
 * PR3/PR4) is UNCHANGED by this restructuring:
 *   POST /distributor/deliveries   multipart/form-data
 *     payload: str (JSON of DeliveryCreate: {client, vehicle, delivery_date})
 *     photo:   File | undefined
 *     -> 201 DeliveryOut {id, plate, vin, model, color, year, engine_number,
 *        delivery_date, delivery_act_url, client_id}
 *   GET  /vehicles/vin/{vin}   -> 200 {model, year, color, engine_number} | 404
 *   GET  /vehicle-models        -> 200 [{id, modelo}, ...]
 *
 * Covers:
 *   - Per-step required-field validation blocks "Siguiente" (no fetch fired,
 *     stays on the same step, same toast.error messages as before)
 *   - VIN lookup (17 chars) autofills model/year/color/engine_number
 *   - delivery_date is submitted as a raw "YYYY-MM-DD" string
 *   - A future delivery_date is blocked at the Entrega step (no fetch fired)
 *   - Photo is mandatory for parts_dealer (blocked at the Entrega step, no
 *     fetch fired), but optional for superadmin
 *   - Final submission (multipart: FormData with `payload` + optional
 *     `photo`) only fires from the Confirmación step's "Registrar Entrega"
 *     button
 *   - Wizard mechanics: stepper renders 4 steps, Atrás preserves entered
 *     data, Confirmación shows a correct read-only summary
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

const clickNext = () => fireEvent.click(screen.getByRole('button', { name: /siguiente/i }));
const clickBack = () => fireEvent.click(screen.getByRole('button', { name: /atrás/i }));
const clickSubmit = () => fireEvent.click(screen.getByRole('button', { name: /registrar entrega/i }));

async function fillClientStep({ name = 'Juan Pérez', identification = '123456789' } = {}) {
  fireEvent.change(screen.getByLabelText('Nombre del cliente'), { target: { value: name } });
  fireEvent.change(screen.getByLabelText('Cédula'), { target: { value: identification } });
}

async function fillVehicleStep({ plate = 'ABC123' } = {}) {
  fireEvent.change(screen.getByLabelText('Placa'), { target: { value: plate } });
}

async function fillDeliveryStep({ delivery_date = '2025-01-10', photo = makeFile() } = {}) {
  fireEvent.change(screen.getByLabelText('Fecha de entrega'), { target: { value: delivery_date } });
  if (photo) {
    await userEvent.upload(screen.getByLabelText(/acta de entrega/i), photo);
  }
}

// Drives the wizard all the way to Confirmación, filling every required
// field for each step along the way. Returns after landing on step 4.
async function goToConfirmation(opts = {}) {
  await fillClientStep(opts.client);
  clickNext();
  await fillVehicleStep(opts.vehicle);
  clickNext();
  await fillDeliveryStep(opts.delivery);
  clickNext();
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.error.mockReset();
  mockToast.success.mockReset();
  mockModels = MODELS;
  sessionStorage.clear();
});

describe('DistribuidorEntregaPage — wizard mechanics', () => {
  it('renders a 4-step stepper starting on Cliente', () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    expect(screen.getByRole('heading', { name: 'Cliente' })).toBeInTheDocument();
    expect(screen.getByLabelText('Nombre del cliente')).toBeInTheDocument();
    // Vehículo/Entrega/Confirmación fields are not mounted yet.
    expect(screen.queryByLabelText('Placa')).not.toBeInTheDocument();
  });

  it('does not advance past Cliente without name+cédula', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    clickNext();

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('El nombre del cliente es obligatorio.');
    });
    expect(screen.getByRole('heading', { name: 'Cliente' })).toBeInTheDocument();
    expect(nonCatalogCalls()).toHaveLength(0);
  });

  it('does not advance past Cliente with a name but no cédula', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    fireEvent.change(screen.getByLabelText('Nombre del cliente'), { target: { value: 'Juan Pérez' } });
    clickNext();

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('La cédula del cliente es obligatoria.');
    });
    expect(screen.getByRole('heading', { name: 'Cliente' })).toBeInTheDocument();
  });

  it('does not advance past Vehículo without a plate', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await fillClientStep();
    clickNext();
    expect(screen.getByRole('heading', { name: 'Vehículo' })).toBeInTheDocument();

    clickNext();

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('La placa es obligatoria.');
    });
    expect(screen.getByRole('heading', { name: 'Vehículo' })).toBeInTheDocument();
  });

  it('Atrás preserves already-entered data', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await fillClientStep({ name: 'Juan Pérez', identification: '123456789' });
    clickNext();
    expect(screen.getByRole('heading', { name: 'Vehículo' })).toBeInTheDocument();

    clickBack();

    expect(screen.getByRole('heading', { name: 'Cliente' })).toBeInTheDocument();
    expect(screen.getByLabelText('Nombre del cliente').value).toBe('Juan Pérez');
    expect(screen.getByLabelText('Cédula').value).toBe('123456789');
  });

  it('shows a correct read-only summary on Confirmación', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await goToConfirmation();

    expect(screen.getByRole('heading', { name: 'Confirmación' })).toBeInTheDocument();
    expect(screen.getByText('Juan Pérez')).toBeInTheDocument();
    expect(screen.getByText('123456789')).toBeInTheDocument();
    expect(screen.getByText('ABC123')).toBeInTheDocument();
    expect(screen.getByText('2025-01-10')).toBeInTheDocument();
    expect(screen.getByText('acta.jpg')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /registrar entrega/i })).toBeInTheDocument();
  });
});

describe('DistribuidorEntregaPage — VIN lookup (Vehículo step)', () => {
  it('fires the VIN lookup at exactly 17 characters and autofills model/year/color/engine_number', async () => {
    setUser('parts_dealer');
    queueResponses(makeResponse(200, { model: 'Renegade 200', year: 2023, color: 'Rojo', engine_number: 'ENG-999' }));
    render(<DistribuidorEntregaPage />);

    await fillClientStep();
    clickNext();

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

    await fillClientStep();
    clickNext();

    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: '1HGCM82633A00435' } }); // 16 chars

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(0);
    });
  });
});

describe('DistribuidorEntregaPage — Entrega step validation', () => {
  it('blocks advancing past Entrega when delivery_date is in the future', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await fillClientStep();
    clickNext();
    await fillVehicleStep();
    clickNext();
    expect(screen.getByRole('heading', { name: 'Entrega' })).toBeInTheDocument();

    const future = new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    await fillDeliveryStep({ delivery_date: future, photo: makeFile() });
    clickNext();

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('La fecha de entrega no puede ser futura.');
    });
    expect(screen.getByRole('heading', { name: 'Entrega' })).toBeInTheDocument();
    expect(nonCatalogCalls()).toHaveLength(0);
  });

  it('blocks advancing past Entrega for parts_dealer with no photo attached', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await fillClientStep();
    clickNext();
    await fillVehicleStep();
    clickNext();
    await fillDeliveryStep({ photo: null });
    clickNext();

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('El acta de entrega firmada es obligatoria.');
    });
    expect(screen.getByRole('heading', { name: 'Entrega' })).toBeInTheDocument();
    expect(nonCatalogCalls()).toHaveLength(0);
  });

  it('allows advancing past Entrega for superadmin with no photo attached', async () => {
    setUser('superadmin');
    queueResponses(makeResponse(201, {
      id: 'v-1', plate: 'ABC123', vin: null, model: null, color: null, year: null,
      engine_number: null, delivery_date: '2025-01-10', delivery_act_url: null, client_id: 'c-1',
    }));
    render(<DistribuidorEntregaPage />);

    await fillClientStep();
    clickNext();
    await fillVehicleStep();
    clickNext();
    await fillDeliveryStep({ photo: null });
    clickNext();

    expect(screen.getByRole('heading', { name: 'Confirmación' })).toBeInTheDocument();

    clickSubmit();

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.getByText(/entrega registrada correctamente/i)).toBeInTheDocument();
    });
  });
});

describe('DistribuidorEntregaPage — successful multipart submission from Confirmación', () => {
  it('submits multipart with a payload field (raw YYYY-MM-DD delivery_date) and a photo field only when Registrar Entrega is clicked', async () => {
    setUser('parts_dealer');
    queueResponses(makeResponse(201, {
      id: 'v-1', plate: 'ABC123', vin: null, model: null, color: null, year: null,
      engine_number: null, delivery_date: '2025-01-10', delivery_act_url: 'https://minio/act.jpg', client_id: 'c-1',
    }));
    render(<DistribuidorEntregaPage />);

    await goToConfirmation();

    // No request fired yet -- only navigation happened so far.
    expect(nonCatalogCalls()).toHaveLength(0);

    clickSubmit();

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
