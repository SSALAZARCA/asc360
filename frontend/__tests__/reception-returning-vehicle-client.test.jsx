/**
 * Tests for the Mini App's returning-vehicle client confirm/edit flow,
 * introduced in:
 *   sdd/distributor-vehicle-delivery, Phase 8 (frontend, PR8)
 *
 * This mirrors the Telegram bot's canonical implementation (PR6,
 * `telegram-bot/bot/handlers/reception.py`: `handle_ocr_confirmation`'s
 * known-vehicle branch, `handle_returning_client_confirmation`,
 * `handle_client_field_selection`, `handle_client_field_value`) field-for-field:
 *
 *   1. When `GET /orders/mini-app/vehicle/{plate}` returns a non-null `client`,
 *      the chat shows the client's current name/phone/email/address and asks
 *      for confirmation with two options: confirm as-is, or edit.
 *   2. Confirming as-is makes NO extra request and proceeds straight to KM.
 *   3. Editing opens a Nombre/Teléfono/Email/Dirección/Listo field-selection
 *      flow; each field capture returns to the selection screen; "Listo"
 *      fires exactly ONE batched `PATCH /vehicles/{plate}/client` with only
 *      the fields that were actually edited.
 *   4. If nothing was edited, "Listo" skips the PATCH entirely.
 *   5. A PATCH failure is surfaced to the advisor but never blocks reception
 *      -- the flow still proceeds to KM.
 *   6. When `client` is null/absent, the step is byte-identical to before
 *      this change (single "Ingresar al taller" button, no client UI at all).
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
let clientPatchResponse;

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

  vehicleLookupResponse = makeResponse(200, {
    id: 'v-1', plate: 'ABC123', brand: 'UM', model: 'DSR 150', year: 2022,
    client_id: 'c-1', active_order: null,
    client: { name: 'Carlos Pérez', phone: '3001234567', email: 'carlos@mail.com', address: 'Cra 1 # 2-3' },
  });
  clientPatchResponse = makeResponse(200, { name: 'Carlos Pérez', phone: '3001234567', email: 'carlos@mail.com', address: 'Cra 1 # 2-3' });

  mockAuthFetch.mockImplementation((url, options = {}) => {
    const method = options.method || 'GET';
    if (typeof url === 'string' && url.includes('/vehicle-models')) {
      return Promise.resolve(makeResponse(200, []));
    }
    if (typeof url === 'string' && url.startsWith('/orders/mini-app/vehicle/')) {
      return Promise.resolve(vehicleLookupResponse);
    }
    if (typeof url === 'string' && url.startsWith('/vehicles/') && url.endsWith('/client') && method === 'PATCH') {
      return Promise.resolve(clientPatchResponse);
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

async function lookupReturningVehicle() {
  setSession({ id: 'u-1', name: 'Ana', role: 'jefe_taller', tenant_id: 'B' });
  render(<TgReception />);
  await waitFor(() => screen.getByText(/cuál es la placa/i));
  await typeAndEnter('ABC123');
}

describe('TgReception — returning-vehicle client confirm/edit (Phase 8, task 8.1/8.2)', () => {
  it('shows the linked client\'s current data and both confirm/edit options', async () => {
    await lookupReturningVehicle();

    await waitFor(() => {
      expect(screen.getByText(/carlos pérez/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/3001234567/)).toBeInTheDocument();
    expect(screen.getByText(/carlos@mail.com/i)).toBeInTheDocument();
    expect(screen.getByText(/cra 1 # 2-3/i)).toBeInTheDocument();

    expect(screen.getByRole('button', { name: /siguen correctos/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /corregir algo/i })).toBeInTheDocument();
  });

  it('confirming as-is makes no PATCH request and proceeds straight to KM', async () => {
    await lookupReturningVehicle();
    await waitFor(() => screen.getByRole('button', { name: /siguen correctos/i }));

    fireEvent.click(screen.getByRole('button', { name: /siguen correctos/i }));

    await waitFor(() => screen.getByText(/cuántos kilómetros/i));
    expect(callsTo('/vehicles/ABC123/client', 'PATCH')).toHaveLength(0);
  });

  it('editing captures only the changed fields and fires exactly ONE batched PATCH on Listo', async () => {
    await lookupReturningVehicle();
    await waitFor(() => screen.getByRole('button', { name: /corregir algo/i }));
    fireEvent.click(screen.getByRole('button', { name: /corregir algo/i }));

    await waitFor(() => screen.getByRole('button', { name: 'Teléfono' }));
    expect(screen.getByRole('button', { name: 'Nombre' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Email' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dirección' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Teléfono' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Teléfono' })).not.toBeInTheDocument());
    await typeAndEnter('3009999999');

    await waitFor(() => screen.getByRole('button', { name: 'Nombre' }));
    fireEvent.click(screen.getByRole('button', { name: 'Nombre' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Nombre' })).not.toBeInTheDocument());
    await typeAndEnter('Carlos Gómez');

    await waitFor(() => screen.getByRole('button', { name: /listo/i }));
    fireEvent.click(screen.getByRole('button', { name: /listo/i }));

    await waitFor(() => expect(callsTo('/vehicles/ABC123/client', 'PATCH')).toHaveLength(1));
    const body = JSON.parse(callsTo('/vehicles/ABC123/client', 'PATCH')[0][1].body);
    expect(body).toEqual({ phone: '3009999999', name: 'Carlos Gómez' });

    await waitFor(() => screen.getByText(/cuántos kilómetros/i));
  });

  it('skips the PATCH entirely when Listo is pressed with no edits made', async () => {
    await lookupReturningVehicle();
    await waitFor(() => screen.getByRole('button', { name: /corregir algo/i }));
    fireEvent.click(screen.getByRole('button', { name: /corregir algo/i }));

    await waitFor(() => screen.getByRole('button', { name: /listo/i }));
    fireEvent.click(screen.getByRole('button', { name: /listo/i }));

    await waitFor(() => screen.getByText(/cuántos kilómetros/i));
    expect(callsTo('/vehicles/ABC123/client', 'PATCH')).toHaveLength(0);
  });

  it('surfaces a PATCH failure to the advisor but still proceeds to KM (never blocks reception)', async () => {
    clientPatchResponse = makeResponse(500, { detail: 'boom' });
    await lookupReturningVehicle();
    await waitFor(() => screen.getByRole('button', { name: /corregir algo/i }));
    fireEvent.click(screen.getByRole('button', { name: /corregir algo/i }));

    await waitFor(() => screen.getByRole('button', { name: 'Nombre' }));
    fireEvent.click(screen.getByRole('button', { name: 'Nombre' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Nombre' })).not.toBeInTheDocument());
    await typeAndEnter('Carlos Gómez');

    await waitFor(() => screen.getByRole('button', { name: /listo/i }));
    fireEvent.click(screen.getByRole('button', { name: /listo/i }));

    await waitFor(() => {
      expect(screen.getByText(/no pude guardar los cambios del cliente/i)).toBeInTheDocument();
    });
    await waitFor(() => screen.getByText(/cuántos kilómetros/i));
  });

  it('behaves exactly as before this change when the vehicle has no linked client', async () => {
    vehicleLookupResponse = makeResponse(200, {
      id: 'v-1', plate: 'ABC123', brand: 'UM', model: 'DSR 150', year: 2022,
      client_id: null, active_order: null, client: null,
    });
    await lookupReturningVehicle();

    await waitFor(() => screen.getByText(/ingresamos al taller/i));
    expect(screen.getByRole('button', { name: /ingresar al taller/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /siguen correctos/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /corregir algo/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /ingresar al taller/i }));
    await waitFor(() => screen.getByText(/cuántos kilómetros/i));
    expect(callsTo('/vehicles/ABC123/client', 'PATCH')).toHaveLength(0);
  });
});
