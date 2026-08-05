/**
 * Tests for splitting "Personal y Acceso" into two tabs -- "Usuarios del
 * Sistema" (default/first, every role except client) and "Clientes"
 * (role=client only) -- plus a per-tab "Exportar Excel" button
 * (`GET /users/export?scope=staff|clients`).
 *
 * Backend contract: `GET /users/export?scope=clients|staff` streams an
 * .xlsx, scoped identically to `GET /users` (see
 * `backend/tests/test_export_users.py`).
 *
 * Regression coverage: the create/edit modal's role `<select>` must keep
 * showing ALL 7 roles from BOTH tabs (explicit user instruction -- do not
 * restrict it), and existing edit/delete/status actions must keep working
 * after the `users.map` -> `visibleUsers.map` filter was introduced.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

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
import { toast as mockToast } from '../lib/toast';

function makeResponse(status, body, isBlob = false) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
    blob: jest.fn().mockResolvedValue(isBlob ? body : new Blob(['xlsx'])),
  };
}

const STAFF_USER = {
  id: 'u-staff', name: 'Técnico Uno', role: 'technician', email: 't@example.com',
  phone: '3001111111', status: 'active', telegram_id: null, service_center_name: 'Taller Centro', tenant: null,
};
const CLIENT_USER = {
  id: 'u-client', name: 'Cliente Uno', role: 'client', email: 'c@example.com',
  phone: '3002222222', status: 'active', telegram_id: 'tg-1', service_center_name: null, tenant: null,
};

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
  mockToast.error.mockReset();
  mockToast.success.mockReset();
  global.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
  global.URL.revokeObjectURL = jest.fn();
});

describe('UsersPage — Usuarios del Sistema / Clientes tabs', () => {
  it('defaults to "Usuarios del Sistema" as the active tab, listed before "Clientes"', async () => {
    queueByUrl([['/users', makeResponse(200, [STAFF_USER, CLIENT_USER])], ['/tenants', makeResponse(200, [])]]);
    render(<UsersPage />);

    await screen.findByText('Técnico Uno');

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['Usuarios del Sistema', 'Clientes']);
    expect(screen.getByRole('tab', { name: 'Usuarios del Sistema' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Clientes' })).toHaveAttribute('aria-selected', 'false');
  });

  it('"Usuarios del Sistema" tab shows every role except client', async () => {
    queueByUrl([['/users', makeResponse(200, [STAFF_USER, CLIENT_USER])], ['/tenants', makeResponse(200, [])]]);
    render(<UsersPage />);

    await screen.findByText('Técnico Uno');
    expect(screen.queryByText('Cliente Uno')).not.toBeInTheDocument();
  });

  it('switching to "Clientes" shows only role=client rows', async () => {
    queueByUrl([['/users', makeResponse(200, [STAFF_USER, CLIENT_USER])], ['/tenants', makeResponse(200, [])]]);
    render(<UsersPage />);

    await screen.findByText('Técnico Uno');
    fireEvent.click(screen.getByRole('tab', { name: 'Clientes' }));

    await screen.findByText('Cliente Uno');
    expect(screen.queryByText('Técnico Uno')).not.toBeInTheDocument();
  });

  it('shows a distinct empty-state message per tab when there are zero matching rows', async () => {
    queueByUrl([['/users', makeResponse(200, [STAFF_USER])], ['/tenants', makeResponse(200, [])]]);
    render(<UsersPage />);

    await screen.findByText('Técnico Uno');
    fireEvent.click(screen.getByRole('tab', { name: 'Clientes' }));

    expect(await screen.findByText(/todavía no hay clientes/i)).toBeInTheDocument();
  });

  it('Exportar Excel calls GET /users/export?scope=staff on the default tab', async () => {
    queueByUrl([
      ['/users/export', makeResponse(200, new Blob(['xlsx']), true)],
      ['/users', makeResponse(200, [STAFF_USER])],
      ['/tenants', makeResponse(200, [])],
    ]);
    render(<UsersPage />);
    await screen.findByText('Técnico Uno');

    fireEvent.click(screen.getByRole('button', { name: /exportar excel/i }));

    await waitFor(() => {
      const call = mockAuthFetch.mock.calls.find(([url]) => typeof url === 'string' && url.includes('/users/export'));
      expect(call).toBeTruthy();
      expect(call[0]).toBe('/users/export?scope=staff');
    });
  });

  it('Exportar Excel calls GET /users/export?scope=clients after switching to the Clientes tab', async () => {
    queueByUrl([
      ['/users/export', makeResponse(200, new Blob(['xlsx']), true)],
      ['/users', makeResponse(200, [CLIENT_USER])],
      ['/tenants', makeResponse(200, [])],
    ]);
    render(<UsersPage />);
    await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('tab', { name: 'Clientes' }));
    await screen.findByText('Cliente Uno');
    fireEvent.click(screen.getByRole('button', { name: /exportar excel/i }));

    await waitFor(() => {
      const call = mockAuthFetch.mock.calls.find(([url]) => typeof url === 'string' && url.includes('/users/export'));
      expect(call[0]).toBe('/users/export?scope=clients');
    });
  });

  it('shows an error toast when the export request fails', async () => {
    queueByUrl([
      ['/users/export', makeResponse(500, {})],
      ['/users', makeResponse(200, [STAFF_USER])],
      ['/tenants', makeResponse(200, [])],
    ]);
    render(<UsersPage />);
    await screen.findByText('Técnico Uno');

    fireEvent.click(screen.getByRole('button', { name: /exportar excel/i }));

    await waitFor(() => expect(mockToast.error).toHaveBeenCalled());
  });

  it('the create/edit role selector always lists all 7 roles regardless of the active tab', async () => {
    queueByUrl([['/users', makeResponse(200, [])], ['/tenants', makeResponse(200, [])]]);
    render(<UsersPage />);
    await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('tab', { name: 'Clientes' }));
    fireEvent.click(screen.getByRole('button', { name: /invitar personal/i }));

    const select = screen.getByLabelText(/rol del sistema/i);
    const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(values).toEqual(
      expect.arrayContaining(['technician', 'jefe_taller', 'administrativo', 'proveedor', 'parts_dealer', 'client', 'superadmin'])
    );
  });

  it('"Invitar Personal" from the Clientes tab defaults the new-user role to client', async () => {
    queueByUrl([['/users', makeResponse(200, [])], ['/tenants', makeResponse(200, [])]]);
    render(<UsersPage />);
    await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('tab', { name: 'Clientes' }));
    fireEvent.click(screen.getByRole('button', { name: /invitar personal/i }));

    expect(screen.getByLabelText(/rol del sistema/i)).toHaveValue('client');
  });

  it('"Invitar Personal" from the default staff tab still defaults the new-user role to technician', async () => {
    queueByUrl([['/users', makeResponse(200, [])], ['/tenants', makeResponse(200, [])]]);
    render(<UsersPage />);
    await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: /invitar personal/i }));

    expect(screen.getByLabelText(/rol del sistema/i)).toHaveValue('technician');
  });
});

describe('UsersPage — pre-existing CRUD actions still work after the tab filter', () => {
  it('editing a user still works from the filtered table', async () => {
    queueByUrl([
      ['/users', makeResponse(200, [STAFF_USER])],
      ['/tenants', makeResponse(200, [])],
    ]);
    render(<UsersPage />);
    await screen.findByText('Técnico Uno');

    fireEvent.click(screen.getByTitle('Editar Perfil'));
    expect(screen.getByLabelText(/rol del sistema/i)).toHaveValue('technician');
    expect(screen.getByPlaceholderText(/Ej: Carlos Técnico/i)).toHaveValue('Técnico Uno');
  });

  it('deleting a user still calls DELETE /users/{id}', async () => {
    queueByUrl([
      ['/users', makeResponse(200, [STAFF_USER])],
      ['/tenants', makeResponse(200, [])],
    ]);
    render(<UsersPage />);
    await screen.findByText('Técnico Uno');

    fireEvent.click(screen.getByTitle('Eliminar Usuario'));
    fireEvent.click(screen.getByRole('button', { name: /^eliminar$/i }));

    await waitFor(() => {
      const call = mockAuthFetch.mock.calls.find(
        ([url, opts]) => typeof url === 'string' && url.includes('/users/u-staff') && opts?.method === 'DELETE'
      );
      expect(call).toBeTruthy();
    });
  });
});
