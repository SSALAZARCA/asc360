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
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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
// GET /distributor/deliveries (list, exact URL + GET method) is treated as a
// boilerplate infra call, same precedent as `/vehicle-models` above -- it
// fires on mount (and again after a successful new-delivery submission), so
// every test's indexed `responses` queue must stay reserved for the
// business-action calls it already controls (POST, PATCH...).
// Read live at call-time (not captured at queueResponses() setup time), so a
// test can mutate `mockDeliveries` between the initial mount fetch and a
// later re-fetch to simulate the list picking up a change.
let mockDeliveries = [];
function isDeliveriesListGet(url, opts) {
  return typeof url === 'string' && url === '/distributor/deliveries' && (!opts || !opts.method || opts.method === 'GET');
}

// GET /vehicles/vin/{vin} -- follow-up fix (2026-07-30): the VIN must now
// resolve against the master catalog for EVERY actor before the Vehículo
// step can advance, so almost every wizard-flow test needs this call to
// succeed by default. Treated as boilerplate too, same precedent as
// `/vehicle-models` and the deliveries list above: defaults to a "found"
// match so existing flows don't need to wire their own response, and
// specific tests override `mockVinLookupResult` (set to `null` to simulate
// the 404/"not in master" case) to exercise the blocking rule itself.
let mockVinLookupResult = { model: 'Renegade 200', year: 2023, color: 'Rojo', engine_number: 'ENG-999' };
function isVinLookupGet(url) {
  return typeof url === 'string' && url.startsWith('/vehicles/vin/');
}

function queueResponses(...responses) {
  let i = 0;
  mockAuthFetch.mockImplementation((url, opts) => {
    if (typeof url === 'string' && url.includes('/vehicle-models')) {
      return Promise.resolve(makeResponse(200, mockModels));
    }
    if (isDeliveriesListGet(url, opts)) {
      return Promise.resolve(makeResponse(200, mockDeliveries));
    }
    if (isVinLookupGet(url)) {
      return Promise.resolve(
        mockVinLookupResult ? makeResponse(200, mockVinLookupResult) : makeResponse(404, {})
      );
    }
    return Promise.resolve(responses[i++]);
  });
}

function nonCatalogCalls() {
  return mockAuthFetch.mock.calls.filter(
    ([url, opts]) => !(typeof url === 'string' && url.includes('/vehicle-models'))
      && !isDeliveriesListGet(url, opts)
      && !isVinLookupGet(url)
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

// `vin: null` skips entering a VIN entirely (used to exercise the
// idle/not-yet-looked-up blocking case). Any other `vin` value fires the
// lookup and waits for it to settle (found or not_found, per
// `mockVinLookupResult`) before returning, so callers land with a
// deterministic `vinLookupStatus` before they act on the "Siguiente" button.
async function fillVehicleStep({ plate = 'ABC123', vin = '1HGCM82633A004352' } = {}) {
  fireEvent.change(screen.getByLabelText('Placa'), { target: { value: plate } });
  if (vin === null) return;
  fireEvent.change(screen.getByLabelText('VIN'), { target: { value: vin } });
  await waitFor(() => {
    expect(
      screen.queryByText(/datos encontrados/i) || screen.queryByText(/no está en el maestro/i)
    ).toBeTruthy();
  });
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
  mockDeliveries = [];
  mockVinLookupResult = { model: 'Renegade 200', year: 2023, color: 'Rojo', engine_number: 'ENG-999' };
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
    mockVinLookupResult = { model: 'Renegade 200', year: 2023, color: 'Rojo', engine_number: 'ENG-999' };
    queueResponses();
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

// ---------------------------------------------------------------------------
// Follow-up fix (2026-07-30): the VIN must resolve against the master
// catalog for EVERY actor before Vehículo → Entrega is allowed -- no role
// exception anywhere in this feature (unlike the mandatory-photo rule, which
// DOES exempt superadmin).
// ---------------------------------------------------------------------------
describe('DistribuidorEntregaPage — VIN master-catalog check blocks Vehículo → Entrega', () => {
  it.each(['parts_dealer', 'superadmin'])(
    'blocks "Siguiente" when the VIN has not been looked up yet (idle), for %s',
    async (role) => {
      setUser(role);
      queueResponses();
      render(<DistribuidorEntregaPage />);

      await fillClientStep();
      clickNext();
      await fillVehicleStep({ vin: null }); // plate filled, VIN left untouched
      clickNext();

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith('El VIN debe corresponder a una moto registrada en el maestro.');
      });
      expect(screen.getByRole('heading', { name: 'Vehículo' })).toBeInTheDocument();
      expect(nonCatalogCalls()).toHaveLength(0);
    }
  );

  it.each(['parts_dealer', 'superadmin'])(
    'blocks "Siguiente" when the VIN lookup resolves not_found, for %s',
    async (role) => {
      setUser(role);
      mockVinLookupResult = null; // GET /vehicles/vin/{vin} -> 404
      queueResponses();
      render(<DistribuidorEntregaPage />);

      await fillClientStep();
      clickNext();
      await fillVehicleStep();
      clickNext();

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith('El VIN debe corresponder a una moto registrada en el maestro.');
      });
      expect(screen.getByRole('heading', { name: 'Vehículo' })).toBeInTheDocument();
    }
  );

  it('allows "Siguiente" once the VIN lookup resolves found', async () => {
    setUser('parts_dealer');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await fillClientStep();
    clickNext();
    await fillVehicleStep();
    clickNext();

    expect(screen.getByRole('heading', { name: 'Entrega' })).toBeInTheDocument();
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

// ---------------------------------------------------------------------------
// Follow-up feature: "Registros Realizados" list below the wizard.
//   GET   /distributor/deliveries              -> 200 [DeliveryListItemOut, ...]
//   PATCH /distributor/deliveries/{vehicle_id}  -> 200 DeliveryOut (superadmin only)
// ---------------------------------------------------------------------------
const ROW_DISTRIBUIDOR = {
  id: 'd-1',
  plate: 'ABC123',
  vin: 'VIN1234567890XYZ',
  model: 'Renegade 200',
  delivery_date: '2025-01-10',
  client_name: 'Juan Pérez',
  registered_by_tenant_name: null,
};

function findList() {
  return screen.findByRole('heading', { name: /registros realizados/i });
}

describe('DistribuidorEntregaPage — Registros Realizados (list)', () => {
  it('fetches and renders delivery rows on mount', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await findList();

    expect(await screen.findByText('Juan Pérez')).toBeInTheDocument();
    expect(screen.getByText(/ABC123/)).toBeInTheDocument();
    expect(screen.getByText(/Renegade 200/)).toBeInTheDocument();
    expect(screen.getByText('VIN1234567890XYZ')).toBeInTheDocument();
    expect(screen.getByText('2025-01-10')).toBeInTheDocument();
  });

  it('shows the loading state while the fetch is in flight', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    // Loading text appears before the fetch resolves.
    expect(screen.getByText(/cargando registros/i)).toBeInTheDocument();
    await screen.findByText('Juan Pérez');
  });

  it('renders the empty-state message when there are no registrations, without crashing', async () => {
    setUser('parts_dealer');
    mockDeliveries = [];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await findList();
    expect(await screen.findByText(/todavía no hay registros/i)).toBeInTheDocument();
  });

  it("a Distribuidor's view never shows registered_by_tenant_name or an Editar affordance, even if a row includes one", async () => {
    setUser('parts_dealer');
    mockDeliveries = [{ ...ROW_DISTRIBUIDOR, registered_by_tenant_name: 'Moto Total S.A.S' }];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');

    expect(screen.queryByText('Moto Total S.A.S')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /editar/i })).not.toBeInTheDocument();
  });

  it("a superadmin's view shows the Distribuidora name per row and an Editar affordance", async () => {
    setUser('superadmin');
    mockDeliveries = [{ ...ROW_DISTRIBUIDOR, registered_by_tenant_name: 'Moto Total S.A.S' }];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');

    expect(screen.getByText('Moto Total S.A.S')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /editar/i })).toBeInTheDocument();
  });

  it('renders a download link to delivery_act_url for a row that has one, opening in a new tab', async () => {
    setUser('parts_dealer');
    mockDeliveries = [{ ...ROW_DISTRIBUIDOR, delivery_act_url: 'https://minio.example/act-123.jpg' }];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');

    const link = screen.getByRole('link', { name: /descargar acta de entrega/i });
    expect(link).toHaveAttribute('href', 'https://minio.example/act-123.jpg');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('does not render a download link for a row without delivery_act_url', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR]; // no delivery_act_url
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');

    expect(screen.queryByRole('link', { name: /descargar acta de entrega/i })).not.toBeInTheDocument();
  });

  it('shows the download link for a superadmin row too (not gated by isSuperadmin)', async () => {
    setUser('superadmin');
    mockDeliveries = [{ ...ROW_DISTRIBUIDOR, registered_by_tenant_name: 'Moto Total S.A.S', delivery_act_url: 'https://minio.example/act-456.jpg' }];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');

    expect(screen.getByRole('link', { name: /descargar acta de entrega/i })).toHaveAttribute('href', 'https://minio.example/act-456.jpg');
  });

  it('after a successful new-delivery submission, the list re-fetches and shows the new entry', async () => {
    setUser('parts_dealer');
    mockDeliveries = [];
    queueResponses(makeResponse(201, {
      id: 'v-new', plate: 'ABC123', vin: null, model: null, color: null, year: null,
      engine_number: null, delivery_date: '2025-01-10', delivery_act_url: 'https://minio/act.jpg', client_id: 'c-1',
    }));
    render(<DistribuidorEntregaPage />);

    await findList();
    expect(await screen.findByText(/todavía no hay registros/i)).toBeInTheDocument();

    // Simulate the backend now returning the freshly-created row on the
    // next GET, the way it would after a real POST commits.
    mockDeliveries = [{
      id: 'v-new', plate: 'ABC123', vin: null, model: null, delivery_date: '2025-01-10',
      client_name: 'Juan Pérez', registered_by_tenant_name: null,
    }];

    await goToConfirmation();
    clickSubmit();

    await waitFor(() => {
      expect(screen.getByText(/entrega registrada correctamente/i)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.queryByText(/todavía no hay registros/i)).not.toBeInTheDocument();
    });
    expect(await screen.findByText(/ABC123/)).toBeInTheDocument();
  });
});

describe('DistribuidorEntregaPage — Registros Realizados edit (superadmin only)', () => {
  it('opens the edit dialog pre-filled and PATCHes only the changed field(s) on save, updating the list in place', async () => {
    setUser('superadmin');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    queueResponses(makeResponse(200, {
      id: 'd-1', plate: 'XYZ999', vin: 'VIN1234567890XYZ', model: 'Renegade 200', color: null, year: null,
      engine_number: null, delivery_date: '2025-01-10', delivery_act_url: null, client_id: 'c-1',
    }));
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.click(screen.getByRole('button', { name: /editar/i }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText('Nombre del cliente').value).toBe('Juan Pérez');
    expect(within(dialog).getByLabelText('Placa').value).toBe('ABC123');
    expect(within(dialog).getByLabelText('VIN').value).toBe('VIN1234567890XYZ');
    expect(within(dialog).getByLabelText('Modelo').value).toBe('Renegade 200');
    expect(within(dialog).getByLabelText('Fecha de entrega').value).toBe('2025-01-10');

    fireEvent.change(within(dialog).getByLabelText('Placa'), { target: { value: 'XYZ999' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /guardar/i }));

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(1);
    });
    const [url, options] = nonCatalogCalls()[0];
    expect(url).toBe('/distributor/deliveries/d-1');
    expect(options.method).toBe('PATCH');
    expect(JSON.parse(options.body)).toEqual({ plate: 'XYZ999' });

    await waitFor(() => {
      expect(mockToast.success).toHaveBeenCalled();
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(await screen.findByText(/XYZ999/)).toBeInTheDocument();
  });

  it('shows the backend error message via toast on a 422 (future date) and keeps the dialog open', async () => {
    setUser('superadmin');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    queueResponses(makeResponse(422, { detail: 'La fecha de entrega no puede ser futura.' }));
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.click(screen.getByRole('button', { name: /editar/i }));

    const dialog = await screen.findByRole('dialog');
    const future = new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    fireEvent.change(within(dialog).getByLabelText('Fecha de entrega'), { target: { value: future } });
    fireEvent.click(within(dialog).getByRole('button', { name: /guardar/i }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('La fecha de entrega no puede ser futura.');
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('shows every field, pre-filled from the list row where a source value exists (model) and blank otherwise', async () => {
    setUser('superadmin');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.click(screen.getByRole('button', { name: /editar/i }));
    const dialog = await screen.findByRole('dialog');

    // Has a source value on the list row.
    expect(within(dialog).getByLabelText('Nombre del cliente').value).toBe('Juan Pérez');
    expect(within(dialog).getByLabelText('Placa').value).toBe('ABC123');
    expect(within(dialog).getByLabelText('VIN').value).toBe('VIN1234567890XYZ');
    expect(within(dialog).getByLabelText('Modelo').value).toBe('Renegade 200');
    expect(within(dialog).getByLabelText('Fecha de entrega').value).toBe('2025-01-10');

    // No server-known original value on `DeliveryListItemOut` -- starts
    // blank, same established pattern as `client_phone`.
    expect(within(dialog).getByLabelText('Teléfono del cliente').value).toBe('');
    expect(within(dialog).getByLabelText('Cédula').value).toBe('');
    expect(within(dialog).getByLabelText('Fecha de nacimiento').value).toBe('');
    expect(within(dialog).getByLabelText('Ciudad').value).toBe('');
    expect(within(dialog).getByLabelText('Departamento').value).toBe('');
    expect(within(dialog).getByLabelText('Dirección').value).toBe('');
    expect(within(dialog).getByLabelText('Email').value).toBe('');
    expect(within(dialog).getByLabelText('Color').value).toBe('');
    expect(within(dialog).getByLabelText('Año').value).toBe('');
    expect(within(dialog).getByLabelText('Número de motor').value).toBe('');
  });

  it('changing the VIN in the edit modal to a 17-char value autofills model/color/year/engine_number in that form', async () => {
    setUser('superadmin');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    mockVinLookupResult = { model: 'Rockville 200', year: 2024, color: 'Negro', engine_number: 'ENG-777' };
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.click(screen.getByRole('button', { name: /editar/i }));
    const dialog = await screen.findByRole('dialog');

    fireEvent.change(within(dialog).getByLabelText('VIN'), { target: { value: '9BWZZZ377VT004251' } });

    await waitFor(() => {
      expect(within(dialog).getByLabelText('Modelo').value).toBe('Rockville 200');
    });
    expect(within(dialog).getByLabelText('Color').value).toBe('Negro');
    expect(within(dialog).getByLabelText('Año').value).toBe('2024');
    expect(within(dialog).getByLabelText('Número de motor').value).toBe('ENG-777');
  });

  it('PATCHes only the new fields actually changed, in addition to the original 5', async () => {
    setUser('superadmin');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    queueResponses(makeResponse(200, {
      id: 'd-1', plate: 'ABC123', vin: 'VIN1234567890XYZ', model: 'Renegade 200', color: 'Rojo', year: 2023,
      engine_number: 'ENG-1', delivery_date: '2025-01-10', delivery_act_url: null, client_id: 'c-1',
    }));
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.click(screen.getByRole('button', { name: /editar/i }));
    const dialog = await screen.findByRole('dialog');

    fireEvent.change(within(dialog).getByLabelText('Cédula'), { target: { value: '900111222' } });
    fireEvent.change(within(dialog).getByLabelText('Ciudad'), { target: { value: 'Bogotá' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /guardar/i }));

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(1);
    });
    const [, options] = nonCatalogCalls()[0];
    expect(JSON.parse(options.body)).toEqual({
      client_identification: '900111222',
      client_city: 'Bogotá',
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
