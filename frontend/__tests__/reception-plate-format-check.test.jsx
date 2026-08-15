/**
 * Tests for Colombian plate-format validation at reception,
 * `app/tg/reception/page.js`.
 *
 * Product request, verbatim intent: Colombian plates are 3 letters + 2
 * digits + 1 letter, no spaces (e.g. `ABC12D`). If a plate entered at
 * reception -- typed, dictated, or read from the OCR'd registration-card
 * photo -- doesn't match that format, ask the person entering it to verify
 * it before looking it up, instead of silently accepting it.
 *
 * All three entry paths (`STEP.PLATE`, `STEP.CORRECTING_OCR`, `confirmOcr`)
 * already funnel through `lookupPlate`, so the check lives there, right
 * before the backend call -- this is NOT a hard block (diplomatic/older
 * plates legitimately don't follow the pattern), just an explicit
 * confirmation step (`STEP.CONFIRMING_PLATE_FORMAT`), mirroring the
 * existing `STEP.CONFIRMING_OCR` confirm/correct UX exactly.
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
let extractDocumentResponse;
let vinMasterResponse;

function vehicleLookupCalls() {
  return mockAuthFetch.mock.calls.filter(([url]) => typeof url === 'string' && url.startsWith('/orders/mini-app/vehicle/'));
}

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  replaceMock.mockClear();
  mockAuthFetch.mockReset();

  vehicleLookupResponse   = makeResponse(404, {});
  extractDocumentResponse = makeResponse(200, {});
  vinMasterResponse       = makeResponse(404, {});

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

describe('TgReception — Colombian plate-format check (typed/dictated entry)', () => {
  it('a well-formed plate skips confirmation entirely and goes straight to the backend lookup', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('ABC12D');

    await waitFor(() => expect(vehicleLookupCalls()).toHaveLength(1));
    expect(screen.queryByText(/no tiene el formato esperado/i)).not.toBeInTheDocument();
  });

  it('a malformed plate triggers the confirmation step instead of calling the backend', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('AB123C');

    await waitFor(() => screen.getByText(/no tiene el formato esperado/i));
    expect(vehicleLookupCalls()).toHaveLength(0);
    expect(screen.getByRole('button', { name: /confirmar ✓/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /corregir ✏️/i })).toBeInTheDocument();
  });

  it('"Confirmar" proceeds with the ORIGINAL malformed plate value, unmodified', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('AB123C');

    await waitFor(() => screen.getByText(/no tiene el formato esperado/i));
    fireEvent.click(screen.getByRole('button', { name: /confirmar ✓/i }));

    await waitFor(() => expect(vehicleLookupCalls()).toHaveLength(1));
    expect(vehicleLookupCalls()[0][0]).toBe('/orders/mini-app/vehicle/AB123C');
  });

  it('"Corregir" returns to STEP.PLATE (no OCR context) without ever calling the backend for the bad value', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));
    await typeAndEnter('AB123C');

    await waitFor(() => screen.getByText(/no tiene el formato esperado/i));
    fireEvent.click(screen.getByRole('button', { name: /corregir ✏️/i }));

    await waitFor(() => screen.getByText(/placa correcta/i));
    expect(vehicleLookupCalls()).toHaveLength(0);

    // Re-entry goes back through the SAME check.
    await typeAndEnter('ABC12D');
    await waitFor(() => expect(vehicleLookupCalls()).toHaveLength(1));
    expect(vehicleLookupCalls()[0][0]).toBe('/orders/mini-app/vehicle/ABC12D');
  });
});

describe('TgReception — plate-format check on the OCR path', () => {
  // sdd/reception-email-notification: the new-client path now always asks
  // for an optional email before the vehicle form (design ADR 6). Skip it
  // via the "Sin email" chip -- unrelated to plate-format checking, which
  // is what this file locks down.
  async function skipEmailStep() {
    await waitFor(() => screen.getByText(/email del cliente/i));
    fireEvent.click(screen.getByRole('button', { name: /sin email/i }));
  }

  async function uploadDocPhoto(container, ocrFields) {
    extractDocumentResponse = makeResponse(200, {
      propietario: 'Carlos Pérez', numero_documento_propietario: '999888777',
      ...ocrFields,
    });
    const fileInput = container.querySelector('input[type="file"]');
    const file = new File(['x'], 'tarjeta.jpg', { type: 'image/jpeg' });
    fireEvent.change(fileInput, { target: { files: [file] } });
    await waitFor(() => screen.getByText(/¿son correctos\?/i));
    fireEvent.click(screen.getByRole('button', { name: /confirmar ✓/i }));
  }

  it('a malformed OCR-read plate triggers confirmation; "Corregir" routes to STEP.CORRECTING_OCR, preserving docData', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    const { container } = render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));

    await uploadDocPhoto(container, { placa: 'AB123C', marca: 'UM', linea: 'DSR 150', vin: '' });

    await waitFor(() => screen.getByText(/no tiene el formato esperado/i));
    expect(vehicleLookupCalls()).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: /corregir ✏️/i }));

    await waitFor(() => screen.getByText(/placa correcta/i));
    // Re-entry via STEP.CORRECTING_OCR must still carry the OCR docData
    // through -- a corrected, well-formed plate that's genuinely new
    // reaches the "moto nueva" branch with the OCR brand/model intact.
    await typeAndEnter('ABC12D');
    await waitFor(() => screen.getByText(/moto nueva/i));
    await typeAndEnter('3001234567');
    await skipEmailStep();
    await waitFor(() => screen.getByText(/completá los datos del vehículo/i));
    expect(screen.getByPlaceholderText('UM').value).toBe('UM');
    expect(screen.getByPlaceholderText(/Renegade 200, NKD 125/i).value).toBe('DSR 150');
  });

  it('"Confirmar" on a malformed OCR-read plate proceeds to the "moto nueva" branch with VIN-master data intact', async () => {
    setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
    vinMasterResponse = makeResponse(200, { model: 'RENEGADE SPORT 200', year: 2026, color: 'Rojo' });

    const { container } = render(<TgReception />);
    await waitFor(() => screen.getByText(/cuál es la placa/i));

    await uploadDocPhoto(container, {
      placa: 'AB123C', marca: 'UM', linea: 'algo mal leído', vin: '1HGCM82633A123456',
    });

    await waitFor(() => screen.getByText(/no tiene el formato esperado/i));
    fireEvent.click(screen.getByRole('button', { name: /confirmar ✓/i }));

    await waitFor(() => expect(vehicleLookupCalls()).toHaveLength(1));
    expect(vehicleLookupCalls()[0][0]).toBe('/orders/mini-app/vehicle/AB123C');

    await waitFor(() => screen.getByText(/moto nueva/i));
    await typeAndEnter('3001234567');
    await skipEmailStep();
    await waitFor(() => screen.getByText(/completá los datos del vehículo/i));
    // VIN-master data (the OTHER fix, from the previous commit) still wins
    // over the OCR text, even though this plate went through the extra
    // format-confirmation hop first.
    expect(screen.getByPlaceholderText(/Renegade 200, NKD 125/i).value).toBe('RENEGADE SPORT 200');
  });
});
