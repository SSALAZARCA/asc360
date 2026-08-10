/**
 * Tests for the reception mini-app chat flow, introduced in:
 *   sdd/vehicle-tenant-checkin-release, Phase 4 (frontend, PR4)
 *
 * A vehicle's "owner" is now a derived, temporary claim (an open ServiceOrder),
 * never a permanent column on Vehicle (PR1/PR2/PR3, already shipped). This
 * file locks down four PR4 fixes in `app/tg/reception/page.js`:
 *
 *   1. Tenant-precedence inversion (~:529) -- the vehicle's own stored data
 *      MUST NEVER win over the logged-in user's active taller when deciding
 *      who a new order/client/vehicle belongs to. Regression covered by
 *      resuming a stale sessionStorage draft that still carries a foreign
 *      `vehicleData.tenant_id` (the exact shape a pre-fix draft could have
 *      left behind) and asserting every outgoing body still carries the
 *      logged-in user's own tenant.
 *   2. Draft persistence (~:116) -- the auto-save snapshot of `vehicleData`
 *      must never re-introduce a `tenant_id` key.
 *   3. Conflict messaging on lookup (~:243-245) -- when `GET
 *      /orders/mini-app/vehicle/{plate}` reports an `active_order`, the chat
 *      must name the holding taller (name + city) instead of a generic
 *      "ya tiene una orden activa" with no detail.
 *   4. Structured 409 rendering at order-submission (~:586) -- the backend's
 *      conflict guard (PR3) returns `{"detail": {"detail": "...", "code":
 *      "..."}}`; the chat must render the nested string, not
 *      "[object Object]".
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const pushMock    = jest.fn();
const replaceMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock, back: jest.fn() }),
  usePathname: () => '/tg/reception',
}));

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));

import TgReception from '../app/tg/reception/page';

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  };
}

const STORAGE_KEY = 'reception_draft';

let vehicleLookupResponse;
let orderCreateResponse;
let motiveResponse;

function nonCatalogCalls() {
  return mockAuthFetch.mock.calls.filter(([url]) => !(typeof url === 'string' && url.includes('/vehicle-models')));
}

function callsTo(path, method) {
  return nonCatalogCalls().filter(([url, options]) =>
    url === path && (!method || (options?.method || 'GET') === method)
  );
}

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  replaceMock.mockClear();
  mockAuthFetch.mockReset();

  vehicleLookupResponse = makeResponse(200, {});
  orderCreateResponse   = makeResponse(201, { id: 'order-1', reception: { reception_pdf_url: null } });
  motiveResponse        = makeResponse(200, { motivos: ['Ruido en el motor'], service_type: 'regular' });

  mockAuthFetch.mockImplementation((url, options = {}) => {
    const method = options.method || 'GET';
    if (typeof url === 'string' && url.includes('/vehicle-models')) {
      return Promise.resolve(makeResponse(200, []));
    }
    if (typeof url === 'string' && url.startsWith('/orders/mini-app/vehicle/')) {
      return Promise.resolve(vehicleLookupResponse);
    }
    if (url === '/mini-app/ai/extract-motive' && method === 'POST') {
      return Promise.resolve(motiveResponse);
    }
    if (url === '/orders/' && method === 'POST') {
      return Promise.resolve(orderCreateResponse);
    }
    if (url === '/users/' && method === 'POST') {
      return Promise.resolve(makeResponse(200, { id: 'c-new' }));
    }
    if (url === '/vehicles/' && method === 'POST') {
      return Promise.resolve(makeResponse(200, { id: 'v-new', plate: 'XYZ99D', brand: 'UM', model: 'DSR 150' }));
    }
    return Promise.resolve(makeResponse(200, {}));
  });
});

function setSession(user) {
  sessionStorage.setItem('um_user', JSON.stringify(user));
  sessionStorage.setItem('um_token', 'tok-123');
}

async function typeAndEnter(text) {
  const box = screen.getByRole('textbox');
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: 'Enter', code: 'Enter' });
}

// Walks the chat from the KM step (right after a vehicle has been
// accepted/confirmed) through to the final CONFIRM summary screen. Shared by
// every test that needs to reach order submission, regardless of how the
// vehicle was found (fresh lookup vs. a resumed draft).
async function walkKMToConfirm() {
  await waitFor(() => screen.getByText(/cuántos kilómetros/i));
  await typeAndEnter('15000');

  await waitFor(() => screen.getByText(/cuánta gasolina/i));
  fireEvent.click(screen.getByRole('button', { name: 'Lleno' }));

  await waitFor(() => screen.getByText(/fotos de daños/i));
  fireEvent.click(screen.getByRole('button', { name: /sin fotos/i }));

  await waitFor(() => screen.getByText(/dejó accesorios/i));
  fireEvent.click(screen.getByRole('button', { name: 'Ninguno' }));

  await waitFor(() => screen.getByText(/motivo de la visita/i));
  await typeAndEnter('Se cae el rendimiento del motor');

  await waitFor(() => screen.getByText(/es correcto\?/i));
  fireEvent.click(screen.getByRole('button', { name: /confirmar ✓/i }));

  await waitFor(() => screen.getByText(/pregunta 1\/1/i));
  await typeAndEnter('Terreno urbano');

  await waitFor(() => screen.getByText(/alguna observación general/i));
  fireEvent.click(screen.getByRole('button', { name: 'Saltar' }));

  await waitFor(() => screen.getByText(/revisá el resumen/i));
}

async function submitOrder() {
  fireEvent.click(screen.getByRole('button', { name: /confirmar recepción/i }));
}

describe('TgReception — tenant-precedence inversion (task 4.1/4.2)', () => {
  it('never lets a foreign vehicleData.tenant_id win over the logged-in user\'s own taller', async () => {
    // Simulates resuming a draft saved before this fix shipped: vehicleData
    // still carries a stale/foreign tenant_id ("A"), while the logged-in
    // user's own active taller is "B". Every outgoing body created from this
    // point on (client, vehicle, order) MUST carry "B", never "A".
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      step: 'KM',
      ocrData: null,
      vehicleId: null,
      isNew: true,
      newVeh: { brand: 'UM', model: 'DSR 150', year: '2022', color: 'Rojo', vin: '' },
      clientPhone: '3001234567',
      formData: { plate: 'XYZ99D', km: '', gas: '', notes: '', motivos: [], serviceType: 'regular', accessories: [], observations: '', intakeAnswers: [], pdfUrl: null },
      vehicleData: { plate: 'XYZ99D', brand: 'UM', model: 'DSR 150', year: '2022', id: null, tenant_id: 'A', client_id: null },
      evidenceItems: [],
      intakeQuestions: [],
      intakeIdx: 0,
      msgs: [
        { id: 1, role: 'bot', text: 'Hola Ana! ¿Cuál es la placa de la moto?' },
        { id: 2, role: 'user', text: 'XYZ99D' },
        { id: 3, role: 'bot', text: '¿Cuántos kilómetros tiene la moto?\nEscribí, dictá 🎙️ o foto del tablero 📷' },
      ],
    }));

    render(<TgReception />);
    await waitFor(() => screen.getByText(/retomamos donde quedamos/i));

    await walkKMToConfirm();
    await submitOrder();

    await waitFor(() => expect(callsTo('/orders/', 'POST')).toHaveLength(1));

    const userBody    = JSON.parse(callsTo('/users/', 'POST')[0][1].body);
    const vehicleBody = JSON.parse(callsTo('/vehicles/', 'POST')[0][1].body);
    const orderBody   = JSON.parse(callsTo('/orders/', 'POST')[0][1].body);

    expect(userBody.tenant_id).toBe('B');
    expect(vehicleBody.tenant_id).toBe('B');
    expect(orderBody.tenant_id).toBe('B');

    expect(userBody.tenant_id).not.toBe('A');
    expect(vehicleBody.tenant_id).not.toBe('A');
    expect(orderBody.tenant_id).not.toBe('A');
  });
});

describe('TgReception — draft persistence omits tenant_id (task 4.3/4.4)', () => {
  it('never writes a tenant_id key into the sessionStorage vehicleData snapshot', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    vehicleLookupResponse = makeResponse(200, {
      id: 'v-1', plate: 'ABC12D', brand: 'UM', model: 'DSR 150', year: 2022,
      client_id: 'c-1', tenant_id: 'A', active_order: null,
    });

    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('ABC12D');

    await waitFor(() => screen.getByText(/ingresamos al taller/i));

    const raw = sessionStorage.getItem(STORAGE_KEY);
    expect(raw).toBeTruthy();
    const draft = JSON.parse(raw);
    expect(draft.vehicleData).toBeTruthy();
    expect(draft.vehicleData).not.toHaveProperty('tenant_id');
  });
});

describe('TgReception — conflict messaging on lookup (task 4.5)', () => {
  it('names the holding taller and city when the vehicle has an active order elsewhere', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    vehicleLookupResponse = makeResponse(200, {
      active_order: { status: 'in_progress', tenant_name: 'Taller Norte', tenant_city: 'Bogotá' },
    });

    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('ABC12D');

    await waitFor(() => {
      expect(screen.getByText(/taller norte/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/bogotá/i)).toBeInTheDocument();
  });

  it('falls back to "otro taller" when tenant_name is missing, with no empty parentheses', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    vehicleLookupResponse = makeResponse(200, {
      active_order: { status: 'in_progress', tenant_name: null, tenant_city: null },
    });

    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('ABC12D');

    await waitFor(() => {
      expect(screen.getByText(/otro taller/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/\(\)/)).not.toBeInTheDocument();
  });
});

describe('TgReception — structured 409 rendering on order submission (task 4.6)', () => {
  it('renders the nested conflict message instead of [object Object]', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    vehicleLookupResponse = makeResponse(200, {
      id: 'v-1', plate: 'ABC12D', brand: 'UM', model: 'DSR 150', year: 2022,
      client_id: 'c-1', active_order: null,
    });
    orderCreateResponse = makeResponse(409, {
      detail: {
        detail: 'Este vehículo ya tiene una orden activa en Taller Norte.',
        code: 'VEHICLE_CLAIMED_BY_OTHER_TENANT',
      },
    });

    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('ABC12D');

    await waitFor(() => screen.getByText(/ingresamos al taller/i));
    fireEvent.click(screen.getByRole('button', { name: /ingresar al taller/i }));

    await walkKMToConfirm();
    await submitOrder();

    await waitFor(() => {
      expect(screen.getByText(/este vehículo ya tiene una orden activa en taller norte/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
  });
});
