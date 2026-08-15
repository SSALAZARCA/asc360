/**
 * Tests for VIN-master authority over the reception chat's vehicle data,
 * `app/tg/reception/page.js`.
 *
 * Regression coverage for a real production bug (2026-08-06): a vehicle's
 * "Marca / Modelo" showed truncated/wrong on the kanban card ("UM RENEGADE
 * SPORT 20" instead of "UM Renegade Sport 200") because the OCR-read model
 * text (from the "tarjeta de propiedad" photo) was saved verbatim -- OCR
 * text is inherently lossy (photo quality, handwriting), so it must never
 * win over the authoritative VIN master catalog when the VIN resolves.
 *
 * Product decision, verbatim: "desde telegram o desde la miniapp cuando
 * toman la foto el sistema lee el numero de chasis o vin, lo busca los
 * datos en la base de datos y eso son los datos del vehiculo" -- only the
 * VIN itself is trusted from OCR; brand/model/year/color come from the DB
 * lookup by that VIN whenever it resolves.
 *
 * This file locks down:
 *   1. OCR "moto nueva" branch: a VIN that resolves in the master REPLACES
 *      the OCR-read model/year/color entirely.
 *   2. Same branch: a VIN that does NOT resolve (or isn't 17 chars, or is
 *      absent) falls back to the OCR-read text exactly as before.
 *   3. The manual VIN input (`lookupVin`, onBlur) now also OVERRIDES
 *      existing form values when the master resolves -- matching the same
 *      "master always wins when present" convention already established in
 *      `distribuidor/entrega` and `historical-orders`, not the old
 *      "fill-only-if-empty" behavior.
 *   4. The returning-vehicle (known plate) branch is untouched -- it never
 *      calls the VIN master endpoint.
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

const OCR_VIN = '1HGCM82633A123456'; // 17 chars

let vehicleLookupResponse;
let extractDocumentResponse;
let vinMasterResponse;

function vinMasterCalls() {
  return mockAuthFetch.mock.calls.filter(([url]) => typeof url === 'string' && url.startsWith('/vehicles/vin/'));
}

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  replaceMock.mockClear();
  mockAuthFetch.mockReset();

  vehicleLookupResponse   = makeResponse(404, {});
  extractDocumentResponse = makeResponse(200, {});
  vinMasterResponse       = makeResponse(404, {}); // not in the master, by default

  mockAuthFetch.mockImplementation((url, options = {}) => {
    const method = options.method || 'GET';
    if (typeof url === 'string' && url.includes('/vehicle-models')) {
      return Promise.resolve(makeResponse(200, []));
    }
    if (typeof url === 'string' && url.startsWith('/vehicles/vin/')) {
      return Promise.resolve(vinMasterResponse);
    }
    if (typeof url === 'string' && url.startsWith('/orders/mini-app/vehicle/')) {
      return Promise.resolve(vehicleLookupResponse);
    }
    if (url === '/mini-app/ai/extract-document' && method === 'POST') {
      return Promise.resolve(extractDocumentResponse);
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
// via the "Sin email" chip -- unrelated to VIN-master authority, which is
// what this file locks down.
async function skipEmailStep() {
  await waitFor(() => screen.getByText(/email del cliente/i));
  fireEvent.click(screen.getByRole('button', { name: /sin email/i }));
}

// Drives an OCR "tarjeta de propiedad" photo through to the new-vehicle
// form, mirroring `reception-new-client-identification-dedup.test.jsx`'s
// established pattern. `numero_documento_propietario` is always included so
// the ASKING_CEDULA step (unrelated to this fix) is skipped.
async function uploadDocPhotoAndReachVehicleForm(container, ocrFields) {
  extractDocumentResponse = makeResponse(200, {
    placa: 'XYZ99D', propietario: 'Carlos Pérez', numero_documento_propietario: '999888777',
    ...ocrFields,
  });

  const fileInput = container.querySelector('input[type="file"]');
  const file = new File(['x'], 'tarjeta.jpg', { type: 'image/jpeg' });
  fireEvent.change(fileInput, { target: { files: [file] } });

  await waitFor(() => screen.getByText(/¿son correctos\?/i));
  fireEvent.click(screen.getByRole('button', { name: /confirmar ✓/i }));

  await waitFor(() => screen.getByText(/moto nueva/i));
  await typeAndEnter('3001234567');

  await skipEmailStep();

  await waitFor(() => screen.getByText(/completá los datos del vehículo/i));
}

describe('TgReception — OCR "moto nueva": VIN master overrides OCR text', () => {
  it('replaces the OCR-read model/year/color with the master catalog data when the VIN resolves', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    vinMasterResponse = makeResponse(200, { model: 'RENEGADE SPORT 200', year: 2026, color: 'Rojo' });

    const { container } = render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));

    await uploadDocPhotoAndReachVehicleForm(container, {
      marca: 'UM', linea: 'RENEGADE SPORT 20', modelo: '2022', color: 'Negro', vin: OCR_VIN,
    });

    expect(vinMasterCalls()).toHaveLength(1);
    expect(vinMasterCalls()[0][0]).toBe(`/vehicles/vin/${OCR_VIN}`);

    expect(screen.getByPlaceholderText(/Renegade 200, NKD 125/i).value).toBe('RENEGADE SPORT 200');
    expect(screen.getByPlaceholderText('2023').value).toBe('2026');
    expect(screen.getByPlaceholderText(/Rojo, Negro/i).value).toBe('Rojo');
    // Master has no brand for a brand-new unit -- falls back to OCR's marca.
    expect(screen.getByPlaceholderText('UM').value).toBe('UM');
    expect(screen.getByText(/datos encontrados y completados abajo/i)).toBeInTheDocument();
  });

  it('prefers the master brand over the OCR-read one when the master returns a brand', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    vinMasterResponse = makeResponse(200, { brand: 'KTM', model: 'DUKE 200', year: 2025, color: 'Naranja' });

    const { container } = render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));

    await uploadDocPhotoAndReachVehicleForm(container, {
      marca: 'UM', linea: 'algo mal leído', vin: OCR_VIN,
    });

    expect(screen.getByPlaceholderText('UM').value).toBe('KTM');
  });

  it('falls back to the raw OCR text when the VIN does not resolve in the master', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    vinMasterResponse = makeResponse(404, {});

    const { container } = render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));

    await uploadDocPhotoAndReachVehicleForm(container, {
      marca: 'UM', linea: 'RENEGADE SPORT 200', modelo: '2022', color: 'Negro', vin: OCR_VIN,
    });

    expect(vinMasterCalls()).toHaveLength(1);
    expect(screen.getByPlaceholderText(/Renegade 200, NKD 125/i).value).toBe('RENEGADE SPORT 200');
    expect(screen.getByPlaceholderText('2023').value).toBe('2022');
    expect(screen.getByPlaceholderText(/Rojo, Negro/i).value).toBe('Negro');
    expect(screen.getByPlaceholderText('UM').value).toBe('UM');
  });

  it('never calls the VIN master when OCR did not capture a (valid) VIN, and falls back to OCR text', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });

    const { container } = render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));

    await uploadDocPhotoAndReachVehicleForm(container, {
      marca: 'UM', linea: 'DSR 150', modelo: '2021', color: 'Azul', vin: '',
    });

    expect(vinMasterCalls()).toHaveLength(0);
    expect(screen.getByPlaceholderText(/Renegade 200, NKD 125/i).value).toBe('DSR 150');
  });
});

describe('TgReception — manual VIN input (onBlur): master now overrides existing values', () => {
  it('overrides model/year/color already present in the form once the VIN resolves', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('XYZ99D');

    await waitFor(() => screen.getByText(/moto nueva/i));
    await typeAndEnter('3001234567');
    await waitFor(() => screen.getByText(/cédula del cliente/i));
    await typeAndEnter('123456789');
    await skipEmailStep();
    await waitFor(() => screen.getByText(/completá los datos del vehículo nuevo/i));

    // Staff already typed something manually before the VIN lookup resolves.
    fireEvent.change(screen.getByPlaceholderText(/Renegade 200, NKD 125/i), { target: { value: 'Modelo Provisional' } });
    fireEvent.change(screen.getByPlaceholderText('2023'), { target: { value: '2019' } });
    fireEvent.change(screen.getByPlaceholderText(/Rojo, Negro/i), { target: { value: 'Verde' } });

    vinMasterResponse = makeResponse(200, { model: 'RENEGADE SPORT 200', year: 2026, color: 'Rojo' });
    const vinInput = screen.getByPlaceholderText(/17 caracteres/i);
    fireEvent.change(vinInput, { target: { value: OCR_VIN } });
    fireEvent.blur(vinInput);

    await waitFor(() => screen.getByText(/datos encontrados y completados abajo/i));
    expect(screen.getByPlaceholderText(/Renegade 200, NKD 125/i).value).toBe('RENEGADE SPORT 200');
    expect(screen.getByPlaceholderText('2023').value).toBe('2026');
    expect(screen.getByPlaceholderText(/Rojo, Negro/i).value).toBe('Rojo');
  });

  it('leaves existing values untouched when the manually-typed VIN does not resolve', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('XYZ99D');

    await waitFor(() => screen.getByText(/moto nueva/i));
    await typeAndEnter('3001234567');
    await waitFor(() => screen.getByText(/cédula del cliente/i));
    await typeAndEnter('123456789');
    await skipEmailStep();
    await waitFor(() => screen.getByText(/completá los datos del vehículo nuevo/i));

    fireEvent.change(screen.getByPlaceholderText(/Renegade 200, NKD 125/i), { target: { value: 'Modelo Provisional' } });

    vinMasterResponse = makeResponse(404, {});
    const vinInput = screen.getByPlaceholderText(/17 caracteres/i);
    fireEvent.change(vinInput, { target: { value: OCR_VIN } });
    fireEvent.blur(vinInput);

    await waitFor(() => screen.getByText(/no está en el maestro/i));
    expect(screen.getByPlaceholderText(/Renegade 200, NKD 125/i).value).toBe('Modelo Provisional');
  });
});

describe('TgReception — returning-vehicle (known plate) branch is unaffected', () => {
  it('never calls the VIN master endpoint for an already-known plate', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    vehicleLookupResponse = makeResponse(200, {
      id: 'v-1', plate: 'ABC12D', brand: 'UM', model: 'DSR 150', year: 2023, client: null,
    });

    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('ABC12D');

    await waitFor(() => screen.getByText(/ya ha estado en el taller/i));
    expect(vinMasterCalls()).toHaveLength(0);
  });
});
