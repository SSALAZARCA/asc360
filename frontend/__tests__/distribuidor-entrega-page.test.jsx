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

// The client Ciudad/Departamento fields are DIVIPOLA-backed cascading
// selects (`GET /tenants/divipola/departments`, `GET /tenants/divipola/
// cities?departamento=...`), same catalog/UX as `frontend/app/tenants/
// page.js` -- fetched via plain global `fetch` (public, no auth), not
// `authFetch`. Treated as boilerplate infra, same precedent as
// `/vehicle-models`: every test gets a default catalog so tests that don't
// care about geography aren't affected.
const mockFetch = jest.fn();
global.fetch = (...args) => mockFetch(...args);
const DEFAULT_DEPARTMENTS = ['Cundinamarca', 'Antioquia'];
const DEFAULT_CITIES = { Cundinamarca: ['Bogotá'], Antioquia: ['Medellín'] };
function queueGeoResponses() {
  mockFetch.mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/tenants/divipola/departments')) {
      return Promise.resolve(makeResponse(200, DEFAULT_DEPARTMENTS));
    }
    if (typeof url === 'string' && url.includes('/tenants/divipola/cities')) {
      const dpto = decodeURIComponent(url.split('departamento=')[1] || '');
      return Promise.resolve(makeResponse(200, DEFAULT_CITIES[dpto] || []));
    }
    return Promise.resolve(makeResponse(200, []));
  });
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

// GET /distributor/deliveries/{id} (full-detail fetch, follow-up fix
// 2026-07-30) -- fired when the "Editar Registro" modal opens, distinct from
// the PATCH on the SAME url (matched by method, same precedent as the two
// other GET-vs-mutation disambiguations above). Treated as boilerplate too:
// defaults to a full record consistent with `ROW_DISTRIBUIDOR` below so
// existing edit-dialog tests that don't care about the detail fetch keep
// their original pre-fill assertions; set `mockDeliveryDetail = null` to
// simulate a failed fetch (404).
const DEFAULT_DELIVERY_DETAIL = {
  id: 'd-1',
  plate: 'ABC123',
  vin: 'VIN1234567890XYZ',
  model: 'Renegade 200',
  color: null,
  year: null,
  engine_number: null,
  delivery_date: '2025-01-10',
  client_name: 'Juan Pérez',
  client_identification: null,
  client_birth_date: null,
  client_city: null,
  client_department: null,
  client_address: null,
  client_phone: null,
  client_email: null,
};
let mockDeliveryDetail = DEFAULT_DELIVERY_DETAIL;
function isDeliveryDetailGet(url, opts) {
  return typeof url === 'string' && /^\/distributor\/deliveries\/[^/]+$/.test(url)
    && (!opts || !opts.method || opts.method === 'GET');
}

// GET /tenants -- superadmin's "Tienda" select (create wizard AND the edit
// modal). Fetched via `authFetch`, only when the actor is superadmin
// (`useTenants(enabled)`). Treated as boilerplate too, same precedent as
// `/vehicle-models`: defaults to a single tenant so every superadmin flow
// test can select one without wiring its own response.
let mockTenants = [{ id: 't-1', name: 'Moto Total S.A.S' }];
function isTenantsListGet(url, opts) {
  return typeof url === 'string' && url === '/tenants' && (!opts || !opts.method || opts.method === 'GET');
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
    if (isDeliveryDetailGet(url, opts)) {
      return Promise.resolve(
        mockDeliveryDetail ? makeResponse(200, mockDeliveryDetail) : makeResponse(404, {})
      );
    }
    if (isTenantsListGet(url, opts)) {
      return Promise.resolve(makeResponse(200, mockTenants));
    }
    return Promise.resolve(responses[i++]);
  });
}

function nonCatalogCalls() {
  return mockAuthFetch.mock.calls.filter(
    ([url, opts]) => !(typeof url === 'string' && url.includes('/vehicle-models'))
      && !isDeliveriesListGet(url, opts)
      && !isVinLookupGet(url)
      && !isDeliveryDetailGet(url, opts)
      && !isTenantsListGet(url, opts)
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

// `tienda` only applies when the "Tienda" field is the superadmin `<select>`
// variant (a Distribuidor's is a read-only, non-`<select>` `<input>` --
// nothing to pick). Defaults to the first mocked tenant so every existing
// superadmin flow keeps working without each test wiring its own selection;
// waits for the fetched options first, same "wait before acting" discipline
// as `fillVehicleStep`'s VIN-lookup wait.
async function fillDeliveryStep({ delivery_date = '2025-01-10', photo = makeFile(), tienda } = {}) {
  fireEvent.change(screen.getByLabelText('Fecha de entrega'), { target: { value: delivery_date } });
  const tiendaField = screen.queryByLabelText('Tienda');
  if (tiendaField && tiendaField.tagName === 'SELECT') {
    await waitFor(() => {
      expect(within(tiendaField).getAllByRole('option').length).toBeGreaterThan(1);
    });
    fireEvent.change(tiendaField, { target: { value: tienda ?? mockTenants[0]?.id ?? '' } });
  }
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
  mockFetch.mockReset();
  queueGeoResponses();
  mockToast.error.mockReset();
  mockToast.success.mockReset();
  mockModels = MODELS;
  mockDeliveries = [];
  mockVinLookupResult = { model: 'Renegade 200', year: 2023, color: 'Rojo', engine_number: 'ENG-999' };
  mockDeliveryDetail = DEFAULT_DELIVERY_DETAIL;
  mockTenants = [{ id: 't-1', name: 'Moto Total S.A.S' }];
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
      expect(mockToast.success).toHaveBeenCalledWith('Entrega registrada correctamente.');
    });
    expect(screen.getByRole('heading', { name: 'Cliente' })).toBeInTheDocument();
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
  client_identification: '900555111',
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

  // Bugfix (2026-07-30): `delivery_act_url` is a raw `localhost:9000` MinIO
  // URL that only resolves on the SERVER, never the browser -- the download
  // control now calls the authenticated proxy endpoint
  // (`GET /distributor/deliveries/{vehicle_id}/act-file`) via `authFetch`
  // and opens the returned blob, instead of linking to the raw URL directly.
  it('clicking the download control fetches the act-file proxy endpoint (not the raw delivery_act_url) and opens the blob', async () => {
    setUser('parts_dealer');
    mockDeliveries = [{ ...ROW_DISTRIBUIDOR, delivery_act_url: 'https://minio.example/act-123.jpg' }];
    queueResponses();
    const fakeBlob = new Blob(['fake-bytes'], { type: 'image/jpeg' });
    const originalCreateObjectURL = global.URL.createObjectURL;
    global.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
    const originalOpen = window.open;
    window.open = jest.fn();

    mockAuthFetch.mockImplementation((url, opts) => {
      if (typeof url === 'string' && url === `/distributor/deliveries/${ROW_DISTRIBUIDOR.id}/act-file`) {
        return Promise.resolve({ ok: true, status: 200, blob: () => Promise.resolve(fakeBlob) });
      }
      if (typeof url === 'string' && url.includes('/vehicle-models')) {
        return Promise.resolve(makeResponse(200, mockModels));
      }
      if (isDeliveriesListGet(url, opts)) {
        return Promise.resolve(makeResponse(200, mockDeliveries));
      }
      return Promise.resolve(makeResponse(200, {}));
    });

    render(<DistribuidorEntregaPage />);
    await screen.findByText('Juan Pérez');

    fireEvent.click(screen.getByRole('button', { name: /descargar acta de entrega/i }));

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(`/distributor/deliveries/${ROW_DISTRIBUIDOR.id}/act-file`);
    });
    await waitFor(() => {
      expect(window.open).toHaveBeenCalledWith('blob:mock-url', '_blank', 'noopener,noreferrer');
    });
    expect(global.URL.createObjectURL).toHaveBeenCalledWith(fakeBlob);
    // Never links (or fetches) the raw stored URL directly.
    expect(screen.queryByRole('link', { name: /descargar acta de entrega/i })).not.toBeInTheDocument();
    expect(mockAuthFetch).not.toHaveBeenCalledWith('https://minio.example/act-123.jpg', expect.anything());

    global.URL.createObjectURL = originalCreateObjectURL;
    window.open = originalOpen;
  });

  it('does not render a download control for a row without delivery_act_url', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR]; // no delivery_act_url
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');

    expect(screen.queryByRole('button', { name: /descargar acta de entrega/i })).not.toBeInTheDocument();
  });

  it('shows the download control for a superadmin row too (not gated by isSuperadmin)', async () => {
    setUser('superadmin');
    mockDeliveries = [{ ...ROW_DISTRIBUIDOR, registered_by_tenant_name: 'Moto Total S.A.S', delivery_act_url: 'https://minio.example/act-456.jpg' }];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');

    expect(screen.getByRole('button', { name: /descargar acta de entrega/i })).toBeInTheDocument();
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
      expect(mockToast.success).toHaveBeenCalledWith('Entrega registrada correctamente.');
    });
    await waitFor(() => {
      expect(screen.queryByText(/todavía no hay registros/i)).not.toBeInTheDocument();
    });
    expect(await screen.findByText(/ABC123/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Cliente' })).toBeInTheDocument();
  });
});

const ROW_B = {
  id: 'd-2',
  plate: 'XYZ999',
  vin: 'VIN0987654321ABC',
  model: 'Xpeed 150',
  delivery_date: '2025-02-01',
  client_name: 'Ana Gómez',
  client_identification: '111222333',
  registered_by_tenant_name: null,
};

describe('DistribuidorEntregaPage — Registros Realizados search + counter', () => {
  it('shows the total record count even with no search active', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR, ROW_B];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    expect(screen.getByText('2 registros')).toBeInTheDocument();
  });

  it('filters by a cédula substring', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR, ROW_B];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.change(screen.getByLabelText(/buscar por cédula, vin o placa/i), { target: { value: '900555' } });

    expect(screen.getByText('Juan Pérez')).toBeInTheDocument();
    expect(screen.queryByText('Ana Gómez')).not.toBeInTheDocument();
    expect(screen.getByText('Mostrando 1 de 2 registros')).toBeInTheDocument();
  });

  it('filters by a VIN substring, case-insensitively', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR, ROW_B];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.change(screen.getByLabelText(/buscar por cédula, vin o placa/i), { target: { value: 'vin0987' } });

    expect(screen.getByText('Ana Gómez')).toBeInTheDocument();
    expect(screen.queryByText('Juan Pérez')).not.toBeInTheDocument();
  });

  it('filters by a placa substring', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR, ROW_B];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.change(screen.getByLabelText(/buscar por cédula, vin o placa/i), { target: { value: 'XYZ999' } });

    expect(screen.getByText('Ana Gómez')).toBeInTheDocument();
    expect(screen.queryByText('Juan Pérez')).not.toBeInTheDocument();
  });

  it('shows a distinct empty-state message when the search matches nothing, without hiding the total count', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR, ROW_B];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.change(screen.getByLabelText(/buscar por cédula, vin o placa/i), { target: { value: 'nada-existe' } });

    expect(screen.getByText(/sin resultados para tu búsqueda/i)).toBeInTheDocument();
    expect(screen.queryByText(/todavía no hay registros/i)).not.toBeInTheDocument();
    expect(screen.getByText('Mostrando 0 de 2 registros')).toBeInTheDocument();
  });

  it('clearing the search restores the full list', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR, ROW_B];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    const input = screen.getByLabelText(/buscar por cédula, vin o placa/i);
    fireEvent.change(input, { target: { value: 'XYZ999' } });
    expect(screen.queryByText('Juan Pérez')).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: '' } });
    expect(screen.getByText('Juan Pérez')).toBeInTheDocument();
    expect(screen.getByText('Ana Gómez')).toBeInTheDocument();
    expect(screen.getByText('2 registros')).toBeInTheDocument();
  });
});

// GET /distributor/deliveries/export -- mirrors the act-file download
// test's mocking convention above (a dedicated `mockAuthFetch`
// implementation, not added to the shared `queueResponses` boilerplate,
// same precedent as `/distributor/deliveries/{id}/act-file`).
describe('DistribuidorEntregaPage — Registros Realizados Excel export', () => {
  it('clicking "Exportar Excel" fetches the export endpoint and downloads the returned blob', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    const fakeBlob = new Blob(['fake-xlsx-bytes'], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const originalCreateObjectURL = global.URL.createObjectURL;
    const originalRevokeObjectURL = global.URL.revokeObjectURL;
    global.URL.createObjectURL = jest.fn(() => 'blob:mock-export-url');
    global.URL.revokeObjectURL = jest.fn();

    mockAuthFetch.mockImplementation((url, opts) => {
      if (url === '/distributor/deliveries/export') {
        return Promise.resolve({ ok: true, status: 200, blob: () => Promise.resolve(fakeBlob) });
      }
      if (typeof url === 'string' && url.includes('/vehicle-models')) {
        return Promise.resolve(makeResponse(200, mockModels));
      }
      if (isDeliveriesListGet(url, opts)) {
        return Promise.resolve(makeResponse(200, mockDeliveries));
      }
      return Promise.resolve(makeResponse(200, {}));
    });

    render(<DistribuidorEntregaPage />);
    await screen.findByText('Juan Pérez');

    fireEvent.click(screen.getByRole('button', { name: /exportar excel/i }));

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith('/distributor/deliveries/export');
    });
    await waitFor(() => {
      expect(global.URL.createObjectURL).toHaveBeenCalledWith(fakeBlob);
    });
    expect(global.URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-export-url');

    global.URL.createObjectURL = originalCreateObjectURL;
    global.URL.revokeObjectURL = originalRevokeObjectURL;
  });

  it('is available to a Distribuidor, not just superadmin', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    expect(screen.getByRole('button', { name: /exportar excel/i })).toBeInTheDocument();
  });

  it('disables the button and shows a loading label while the export is in flight', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    let resolveExport;
    const exportPromise = new Promise((resolve) => { resolveExport = resolve; });
    const fakeBlob = new Blob(['fake-xlsx-bytes']);
    const originalCreateObjectURL = global.URL.createObjectURL;
    const originalRevokeObjectURL = global.URL.revokeObjectURL;
    global.URL.createObjectURL = jest.fn(() => 'blob:mock-export-url');
    global.URL.revokeObjectURL = jest.fn();

    mockAuthFetch.mockImplementation((url, opts) => {
      if (url === '/distributor/deliveries/export') return exportPromise;
      if (typeof url === 'string' && url.includes('/vehicle-models')) {
        return Promise.resolve(makeResponse(200, mockModels));
      }
      if (isDeliveriesListGet(url, opts)) {
        return Promise.resolve(makeResponse(200, mockDeliveries));
      }
      return Promise.resolve(makeResponse(200, {}));
    });

    render(<DistribuidorEntregaPage />);
    await screen.findByText('Juan Pérez');

    fireEvent.click(screen.getByRole('button', { name: /exportar excel/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /exportando/i })).toBeDisabled();
    });

    resolveExport({ ok: true, status: 200, blob: () => Promise.resolve(fakeBlob) });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /exportar excel/i })).not.toBeDisabled();
    });

    global.URL.createObjectURL = originalCreateObjectURL;
    global.URL.revokeObjectURL = originalRevokeObjectURL;
  });

  it('shows an error toast and re-enables the button when the export request fails', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    mockAuthFetch.mockImplementation((url, opts) => {
      if (url === '/distributor/deliveries/export') {
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
      }
      if (typeof url === 'string' && url.includes('/vehicle-models')) {
        return Promise.resolve(makeResponse(200, mockModels));
      }
      if (isDeliveriesListGet(url, opts)) {
        return Promise.resolve(makeResponse(200, mockDeliveries));
      }
      return Promise.resolve(makeResponse(200, {}));
    });

    render(<DistribuidorEntregaPage />);
    await screen.findByText('Juan Pérez');

    fireEvent.click(screen.getByRole('button', { name: /exportar excel/i }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('No se pudieron exportar los registros.');
    });
    expect(screen.getByRole('button', { name: /exportar excel/i })).not.toBeDisabled();
  });

  it('does not interfere with the search box or the delivery-list boilerplate call', async () => {
    setUser('parts_dealer');
    mockDeliveries = [ROW_DISTRIBUIDOR, ROW_B];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.change(screen.getByLabelText(/buscar por cédula, vin o placa/i), { target: { value: 'XYZ999' } });

    expect(screen.getByText('Ana Gómez')).toBeInTheDocument();
    expect(screen.queryByText('Juan Pérez')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /exportar excel/i })).toBeInTheDocument();
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
    expect(await within(dialog).findByLabelText('Nombre del cliente')).toHaveValue('Juan Pérez');
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
    await within(dialog).findByLabelText('Nombre del cliente');
    const future = new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    fireEvent.change(within(dialog).getByLabelText('Fecha de entrega'), { target: { value: future } });
    fireEvent.click(within(dialog).getByRole('button', { name: /guardar/i }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('La fecha de entrega no puede ser futura.');
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  // Bugfix (2026-07-30): the modal used to derive its "original" values from
  // the sparse `DeliveryListItemOut` list row, which never carried most of
  // these fields -- they showed blank even though the data already existed
  // in the DB. It now fetches `GET /distributor/deliveries/{id}` on open and
  // prefills EVERY field from that response.
  it('fetches the detail endpoint on open and pre-fills EVERY field from its response, not just what the list row had', async () => {
    setUser('superadmin');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    mockDeliveryDetail = {
      id: 'd-1',
      plate: 'ABC123',
      vin: 'VIN1234567890XYZ',
      model: 'Renegade 200',
      color: 'Rojo',
      year: 2022,
      engine_number: 'ENG-100',
      delivery_date: '2025-01-10',
      client_name: 'Juan Pérez',
      client_identification: '900111222',
      client_birth_date: '1990-05-15',
      client_city: 'Bogotá',
      client_department: 'Cundinamarca',
      client_address: 'Calle 1 # 2-3',
      client_phone: '3001234567',
      client_email: 'juan@example.com',
    };
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.click(screen.getByRole('button', { name: /editar/i }));

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith('/distributor/deliveries/d-1');
    });
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByLabelText('Cédula');

    expect(within(dialog).getByLabelText('Nombre del cliente').value).toBe('Juan Pérez');
    expect(within(dialog).getByLabelText('Cédula').value).toBe('900111222');
    expect(within(dialog).getByLabelText('Fecha de nacimiento').value).toBe('1990-05-15');
    expect(within(dialog).getByLabelText('Teléfono del cliente').value).toBe('3001234567');
    expect(within(dialog).getByLabelText('Email').value).toBe('juan@example.com');
    // Ciudad/Departamento are DIVIPOLA selects -- their options load
    // asynchronously (own catalog fetch), so their values settle after the
    // synchronous fields above already do.
    await waitFor(() => {
      expect(within(dialog).getByLabelText('Departamento').value).toBe('Cundinamarca');
    });
    await waitFor(() => {
      expect(within(dialog).getByLabelText('Ciudad').value).toBe('Bogotá');
    });
    expect(within(dialog).getByLabelText('Dirección').value).toBe('Calle 1 # 2-3');
    expect(within(dialog).getByLabelText('Placa').value).toBe('ABC123');
    expect(within(dialog).getByLabelText('VIN').value).toBe('VIN1234567890XYZ');
    expect(within(dialog).getByLabelText('Modelo').value).toBe('Renegade 200');
    expect(within(dialog).getByLabelText('Color').value).toBe('Rojo');
    expect(within(dialog).getByLabelText('Año').value).toBe('2022');
    expect(within(dialog).getByLabelText('Número de motor').value).toBe('ENG-100');
    expect(within(dialog).getByLabelText('Fecha de entrega').value).toBe('2025-01-10');
  });

  it('shows a toast error and closes the dialog when the detail fetch fails', async () => {
    setUser('superadmin');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    mockDeliveryDetail = null; // simulates the GET returning a non-2xx
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.click(screen.getByRole('button', { name: /editar/i }));

    await screen.findByRole('dialog');
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('No se pudo cargar el registro.');
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('clicking the backdrop closes the dialog without saving; clicking inside the dialog box does not', async () => {
    setUser('superadmin');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.click(screen.getByRole('button', { name: /editar/i }));

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByLabelText('Nombre del cliente');

    // Click inside the box -- must NOT close.
    fireEvent.click(within(dialog).getByText('Editar Registro'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // Click the backdrop itself (the dialog's parent, outside the box) -- must close.
    fireEvent.click(dialog.parentElement);

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(nonCatalogCalls()).toHaveLength(0);
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
    await within(dialog).findByLabelText('Nombre del cliente');

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
    await within(dialog).findByLabelText('Nombre del cliente');

    fireEvent.change(within(dialog).getByLabelText('Cédula'), { target: { value: '900111222' } });
    // Ciudad is a cascading select disabled until a Departamento is picked
    // (Cundinamarca's cities load from the mocked DIVIPOLA catalog).
    fireEvent.change(within(dialog).getByLabelText('Departamento'), { target: { value: 'Cundinamarca' } });
    await waitFor(() => {
      expect(within(dialog).getByLabelText('Ciudad')).not.toBeDisabled();
    });
    fireEvent.change(within(dialog).getByLabelText('Ciudad'), { target: { value: 'Bogotá' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /guardar/i }));

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(1);
    });
    const [, options] = nonCatalogCalls()[0];
    expect(JSON.parse(options.body)).toEqual({
      client_identification: '900111222',
      client_department: 'Cundinamarca',
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
      expect(mockToast.success).toHaveBeenCalledWith('Entrega registrada correctamente.');
    });
    expect(screen.getByRole('heading', { name: 'Cliente' })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// "Tienda" field (which Distribuidora made the sale) -- read-only for a
// tenant user (their own store, implicit), a required editable select for
// superadmin (GET /tenants, no tenant of their own).
// ---------------------------------------------------------------------------
describe('DistribuidorEntregaPage — Tienda field on the Entrega step', () => {
  it("shows the tenant user's own store, read-only", async () => {
    sessionStorage.setItem('um_user', JSON.stringify({ name: 'Test User', role: 'parts_dealer', tenant_name: 'Moto Total S.A.S' }));
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await fillClientStep();
    clickNext();
    await fillVehicleStep();
    clickNext();

    const tiendaField = screen.getByLabelText('Tienda');
    expect(tiendaField.tagName).toBe('INPUT');
    expect(tiendaField).toBeDisabled();
    expect(tiendaField).toHaveValue('Moto Total S.A.S');
  });

  it('shows a required editable select of network tenants for superadmin', async () => {
    setUser('superadmin');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await fillClientStep();
    clickNext();
    await fillVehicleStep();
    clickNext();

    const tiendaField = screen.getByLabelText('Tienda');
    expect(tiendaField.tagName).toBe('SELECT');
    await waitFor(() => {
      expect(within(tiendaField).getAllByRole('option').length).toBeGreaterThan(1);
    });
    expect(within(tiendaField).getByText('Moto Total S.A.S')).toBeInTheDocument();
  });

  it('blocks advancing past Entrega for superadmin with no tienda selected', async () => {
    setUser('superadmin');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await fillClientStep();
    clickNext();
    await fillVehicleStep();
    clickNext();
    fireEvent.change(screen.getByLabelText('Fecha de entrega'), { target: { value: '2025-01-10' } });
    clickNext();

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Debe seleccionar la tienda que realizó la venta.');
    });
    expect(screen.getByRole('heading', { name: 'Entrega' })).toBeInTheDocument();
    expect(nonCatalogCalls()).toHaveLength(0);
  });

  it("includes the selected tienda's id in the create payload for superadmin", async () => {
    setUser('superadmin');
    queueResponses(makeResponse(201, {
      id: 'v-1', plate: 'ABC123', vin: null, model: null, color: null, year: null,
      engine_number: null, delivery_date: '2025-01-10', delivery_act_url: null, client_id: 'c-1',
    }));
    render(<DistribuidorEntregaPage />);

    await goToConfirmation();
    clickSubmit();

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(1);
    });
    const [, options] = nonCatalogCalls()[0];
    const payload = JSON.parse(options.body.get('payload'));
    expect(payload.registered_by_tenant_id).toBe('t-1');
  });

  it('shows the resolved Tienda name on the Confirmación summary', async () => {
    setUser('superadmin');
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await goToConfirmation();

    expect(screen.getByText('Moto Total S.A.S')).toBeInTheDocument();
  });

  it('the edit modal shows an editable Tienda select, prefilled, and PATCHes only when changed', async () => {
    setUser('superadmin');
    mockDeliveries = [ROW_DISTRIBUIDOR];
    mockTenants = [
      { id: 't-1', name: 'Vieja Distribuidora' },
      { id: 't-2', name: 'Nueva Distribuidora' },
    ];
    mockDeliveryDetail = { ...DEFAULT_DELIVERY_DETAIL, registered_by_tenant_id: 't-1' };
    queueResponses();
    render(<DistribuidorEntregaPage />);

    await screen.findByText('Juan Pérez');
    fireEvent.click(screen.getByRole('button', { name: /editar/i }));
    const dialog = await screen.findByRole('dialog');
    const tiendaSelect = await within(dialog).findByLabelText('Tienda');
    await waitFor(() => {
      expect(tiendaSelect).toHaveValue('t-1');
    });

    fireEvent.change(tiendaSelect, { target: { value: 't-2' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /guardar/i }));

    await waitFor(() => {
      expect(nonCatalogCalls()).toHaveLength(1);
    });
    const [, options] = nonCatalogCalls()[0];
    expect(JSON.parse(options.body)).toEqual({ registered_by_tenant_id: 't-2' });
  });
});
