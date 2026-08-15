/**
 * Tests for the "moto nueva" (isNew) client-creation step in the reception
 * chat, `app/tg/reception/page.js`.
 *
 * Regression coverage for a real bug: a client who already exists (from a
 * prior visit with a different plate) got a brand-new duplicate `User` row
 * every time a new/unmatched plate came through reception, because the
 * `POST /users/` call carried no `identification` (cedula) at all -- and
 * when no phone was given, the OCR-read document number was stuffed into
 * the `phone` field instead, conflating the two.
 *
 * This file locks down the fix:
 *   1. When the vehicle's OCR document photo did NOT capture an owner
 *      document number, the chat now asks the advisor for the client's
 *      cedula manually (new ASKING_CEDULA step) before the vehicle form.
 *   2. When OCR DID capture `numero_documento_propietario`, that manual
 *      step is skipped entirely and the value is used automatically.
 *   3. The final `POST /users/` body always carries `identification`
 *      separately from `phone` -- never conflated.
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

let vehicleLookupResponse;
let orderCreateResponse;
let motiveResponse;
let extractDocumentResponse;

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

  vehicleLookupResponse   = makeResponse(404, {});
  orderCreateResponse     = makeResponse(201, { id: 'order-1', reception: { reception_pdf_url: null } });
  motiveResponse          = makeResponse(200, { motivos: ['Ruido en el motor'], service_type: 'regular' });
  extractDocumentResponse = makeResponse(200, {});

  mockAuthFetch.mockImplementation((url, options = {}) => {
    const method = options.method || 'GET';
    if (typeof url === 'string' && url.includes('/vehicle-models')) {
      return Promise.resolve(makeResponse(200, []));
    }
    if (typeof url === 'string' && url.startsWith('/orders/mini-app/vehicle/')) {
      return Promise.resolve(vehicleLookupResponse);
    }
    if (url === '/mini-app/ai/extract-document' && method === 'POST') {
      return Promise.resolve(extractDocumentResponse);
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

// sdd/reception-email-notification: the new-client path now always asks
// for an optional email before the vehicle form (design ADR 6). Skip it
// via the "Sin email" chip -- these tests aren't about the email capture
// itself (see test_bot_miniapp_copy_parity.py / the reception-email-*
// jest coverage for that).
async function skipEmailStep() {
  await waitFor(() => screen.getByText(/email del cliente/i));
  fireEvent.click(screen.getByRole('button', { name: /sin email/i }));
}

// Fills the minimal required field (model) on the new-vehicle form and
// continues -- the catalog is mocked empty, so it's the free-text fallback.
async function fillVehicleFormAndContinue() {
  const modelInput = screen.getByPlaceholderText(/Renegade 200/i);
  fireEvent.change(modelInput, { target: { value: 'DSR 150' } });
  fireEvent.click(screen.getByRole('button', { name: /continuar/i }));
}

// Walks from KM through to the final CONFIRM summary screen.
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

describe('TgReception — new-client identification capture (moto nueva)', () => {
  it('asks for the cedula manually when OCR did not capture it, and sends it separately from phone', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('XYZ99D');

    await waitFor(() => screen.getByText(/moto nueva/i));
    await typeAndEnter('3001234567');

    // New behavior: must ask for the cedula before the vehicle form.
    await waitFor(() => screen.getByText(/cédula del cliente/i));
    await typeAndEnter('123456789');

    await skipEmailStep();

    await waitFor(() => screen.getByText(/completá los datos del vehículo nuevo/i));
    await fillVehicleFormAndContinue();

    await walkKMToConfirm();
    await submitOrder();

    await waitFor(() => expect(callsTo('/orders/', 'POST')).toHaveLength(1));

    const userBody = JSON.parse(callsTo('/users/', 'POST')[0][1].body);
    expect(userBody.phone).toBe('3001234567');
    expect(userBody.identification).toBe('123456789');
    expect(userBody.phone).not.toBe(userBody.identification);
  });

  it('does not ask for the cedula when OCR already captured it, and uses the OCR value', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    extractDocumentResponse = makeResponse(200, {
      placa: 'XYZ99D', marca: 'UM', linea: 'DSR 150', modelo: '2022', color: 'Rojo',
      vin: '1HGCM82633A123456', propietario: 'Carlos Pérez',
      numero_documento_propietario: '999888777',
    });

    const { container } = render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));

    const fileInput = container.querySelector('input[type="file"]');
    const file = new File(['x'], 'tarjeta.jpg', { type: 'image/jpeg' });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => screen.getByText(/¿son correctos\?/i));
    fireEvent.click(screen.getByRole('button', { name: /confirmar ✓/i }));

    await waitFor(() => screen.getByText(/moto nueva/i));
    await typeAndEnter('3001234567');

    await skipEmailStep();

    // Must skip straight to the vehicle form -- no cedula prompt.
    await waitFor(() => screen.getByText(/revisá y completá los datos del vehículo/i));
    expect(screen.queryByText(/cédula del cliente/i)).not.toBeInTheDocument();

    await fillVehicleFormAndContinue();
    await walkKMToConfirm();
    await submitOrder();

    await waitFor(() => expect(callsTo('/orders/', 'POST')).toHaveLength(1));

    const userBody = JSON.parse(callsTo('/users/', 'POST')[0][1].body);
    expect(userBody.identification).toBe('999888777');
    expect(userBody.phone).toBe('3001234567');
    expect(userBody.name).toBe('Carlos Pérez');
  });
});
