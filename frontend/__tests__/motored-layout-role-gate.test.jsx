/**
 * Tests for `motored-layout.js`'s role-gate, introduced in:
 *   sdd/motored-pedidos-cimientos, Phase 6 (frontend, PR6), task 6.5
 *
 * Mirrors `admin-layout-historical-orders-gate.test.jsx`'s convention
 * (mock next/navigation + the sidebar component, assert on `pushMock` and
 * on whether protected content ever rendered). The one hard requirement
 * under test: an unauthenticated (no `motored_token`/`motored_user`) or
 * wrong-role visitor hitting a `/motored/*` route is redirected to
 * `/motored/login` and NEVER sees protected content, not even briefly.
 *
 * Reads/writes ONLY `motored_user`/`motored_token` -- this test never
 * touches `um_user`/`um_token`, proving the two session stores are
 * genuinely independent.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/motored/maestros';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));

jest.mock('../components/motored/MotoredSidebar', () => {
  const MockMotoredSidebar = () => <div data-testid="mock-motored-sidebar" />;
  MockMotoredSidebar.displayName = 'MockMotoredSidebar';
  return MockMotoredSidebar;
});

import MotoredLayout from '../app/motored/motored-layout';

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  mockPathname = '/motored/maestros';
});

describe('MotoredLayout — role gate', () => {
  it('redirects to /motored/login when there is no Motored session at all', async () => {
    render(<MotoredLayout><div>Contenido protegido</div></MotoredLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/motored/login');
    });
    expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
  });

  it('redirects to /motored/login for a wrong/unknown role, and never renders protected content', async () => {
    sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'Intruder', role: 'not_a_real_role' }));
    sessionStorage.setItem('motored_token', 'fake-token');

    render(<MotoredLayout><div>Contenido protegido</div></MotoredLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/motored/login');
    });
    expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();

    // Wrong-role sessions must be scrubbed, not left half-authenticated.
    expect(sessionStorage.getItem('motored_user')).toBeNull();
    expect(sessionStorage.getItem('motored_token')).toBeNull();
  });

  it('never touches asc360 session keys (um_user/um_token) while gating', async () => {
    sessionStorage.setItem('um_user', JSON.stringify({ name: 'AscUser', role: 'superadmin' }));
    sessionStorage.setItem('um_token', 'asc360-token');

    render(<MotoredLayout><div>Contenido protegido</div></MotoredLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/motored/login');
    });
    // A valid asc360 session must NOT authorize a Motored route.
    expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
    expect(sessionStorage.getItem('um_user')).not.toBeNull();
    expect(sessionStorage.getItem('um_token')).not.toBeNull();
  });

  it('renders protected content for a valid ADMIN Motored session', async () => {
    sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'Admin', role: 'ADMIN' }));
    sessionStorage.setItem('motored_token', 'real-token');

    render(<MotoredLayout><div>Contenido protegido</div></MotoredLayout>);

    await waitFor(() => {
      expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
    expect(screen.getByTestId('mock-motored-sidebar')).toBeInTheDocument();
  });
});
