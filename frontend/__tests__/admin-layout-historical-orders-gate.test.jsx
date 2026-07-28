/**
 * Tests for the `/historical-orders` route gate in AdminLayout, introduced in:
 *   sdd/historical-order-entry, Phase 7 (frontend, PR4)
 *
 * Mirrors `admin-layout-superadmin-data-gate.test.jsx` 1:1 -- the exact
 * existing `superadminOnly` redirect pattern already used for `/users`,
 * `/settings`, and `/superadmin-data`: a non-superadmin landing on
 * `/historical-orders` MUST be redirected away, while a superadmin is left
 * alone. This is cosmetic UX only -- the real access control is the
 * backend's `_require_superadmin` guard -- but the frontend gate must still
 * route correctly.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/historical-orders';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));

jest.mock('../components/Sidebar', () => {
  const MockSidebar = () => <div data-testid="mock-sidebar" />;
  MockSidebar.displayName = 'MockSidebar';
  return MockSidebar;
});

jest.mock('../components/ToastContainer', () => {
  const MockToastContainer = () => null;
  MockToastContainer.displayName = 'MockToastContainer';
  return MockToastContainer;
});

import AdminLayout from '../app/admin-layout';

function setUser(role) {
  sessionStorage.setItem('um_user', JSON.stringify({ name: 'Test User', role }));
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  pushMock.mockClear();
  mockPathname = '/historical-orders';
});

describe('AdminLayout — /historical-orders route gate', () => {
  it('redirects a non-superadmin (jefe_taller) user away from /historical-orders', async () => {
    setUser('jefe_taller');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/kanban');
    });
    expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
  });

  it('redirects an administrativo user away from /historical-orders to the dashboard', async () => {
    setUser('administrativo');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/');
    });
  });

  it('does NOT redirect a superadmin user visiting /historical-orders', async () => {
    setUser('superadmin');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
  });
});
