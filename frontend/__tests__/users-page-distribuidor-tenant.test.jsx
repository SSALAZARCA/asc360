/**
 * Tests for assigning a distributor Tenant entity to a `parts_dealer`
 * (Distribuidor) user from Gestión de Usuarios.
 *
 * Backend contract (already supports `tenant_id`, confirmed by reading
 * backend/app/schemas/user.py and backend/app/api/v1/endpoints/users.py --
 * no backend change needed, this is a pure frontend gap):
 *   POST /users    body includes optional `tenant_id`
 *   PATCH /users/{id}  body includes optional `tenant_id`
 *   GET /tenants   -> [{id, name, tenant_type, ...}, ...] (no server-side
 *     type filter -- the picker filters client-side to `tenant_type === 'distribuidor'`)
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));
jest.mock('../lib/toast', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock('../app/admin-layout', () => {
  const MockAdminLayout = ({ children }) => <div>{children}</div>;
  MockAdminLayout.displayName = 'MockAdminLayout';
  return MockAdminLayout;
});

import UsersPage from '../app/users/page';

function makeResponse(status, body) {
  return { ok: status >= 200 && status < 300, status, json: jest.fn().mockResolvedValue(body) };
}

const TENANTS = [
  { id: 't-1', name: 'Distribuidora Norte', tenant_type: 'distribuidor' },
  { id: 't-2', name: 'Taller Centro', tenant_type: 'service_center' },
  { id: 't-3', name: 'Distribuidora Sur', tenant_type: 'distribuidor' },
];

function queueByUrl(routes) {
  mockAuthFetch.mockImplementation((url) => {
    for (const [match, response] of routes) {
      if (typeof url === 'string' && url.includes(match)) return Promise.resolve(response);
    }
    return Promise.resolve(makeResponse(200, []));
  });
}

beforeEach(() => {
  mockAuthFetch.mockReset();
});

describe('UsersPage — Distribuidor tenant assignment', () => {
  it('shows a Distribuidora picker only when the role is parts_dealer', async () => {
    queueByUrl([['/users', makeResponse(200, [])], ['/tenants', makeResponse(200, TENANTS)]]);
    render(<UsersPage />);

    fireEvent.click(screen.getByRole('button', { name: /invitar personal/i }));

    expect(screen.queryByLabelText(/distribuidora/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/rol del sistema/i), { target: { value: 'parts_dealer' } });

    await waitFor(() => {
      expect(screen.getByLabelText(/distribuidora/i)).toBeInTheDocument();
    });
  });

  it('only lists tenants of type distribuidor in the picker, not service_center ones', async () => {
    queueByUrl([['/users', makeResponse(200, [])], ['/tenants', makeResponse(200, TENANTS)]]);
    render(<UsersPage />);
    fireEvent.click(screen.getByRole('button', { name: /invitar personal/i }));
    fireEvent.change(screen.getByLabelText(/rol del sistema/i), { target: { value: 'parts_dealer' } });

    const select = await screen.findByLabelText(/distribuidora/i);
    const optionLabels = Array.from(select.querySelectorAll('option')).map((o) => o.textContent);

    expect(optionLabels).toEqual(expect.arrayContaining(['Distribuidora Norte', 'Distribuidora Sur']));
    expect(optionLabels).not.toEqual(expect.arrayContaining(['Taller Centro']));
  });

  it('sends the selected tenant_id when creating a new Distribuidor user', async () => {
    queueByUrl([
      ['/tenants', makeResponse(200, TENANTS)],
      ['/users', makeResponse(201, { id: 'u-1' })],
    ]);
    render(<UsersPage />);
    fireEvent.click(screen.getByRole('button', { name: /invitar personal/i }));

    fireEvent.change(screen.getByLabelText(/rol del sistema/i), { target: { value: 'parts_dealer' } });
    const select = await screen.findByLabelText(/distribuidora/i);
    fireEvent.change(select, { target: { value: 't-3' } });

    fireEvent.change(screen.getByPlaceholderText(/Ej: Carlos Técnico/i), { target: { value: 'Nuevo Distribuidor' } });

    fireEvent.click(screen.getByRole('button', { name: /generar acceso/i }));

    await waitFor(() => {
      const createCall = mockAuthFetch.mock.calls.find(
        ([url, opts]) => typeof url === 'string' && url.includes('/users') && opts?.method === 'POST'
      );
      expect(createCall).toBeTruthy();
      const body = JSON.parse(createCall[1].body);
      expect(body.tenant_id).toBe('t-3');
    });
  });
});
