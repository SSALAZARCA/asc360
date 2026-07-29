/**
 * Tests for the `/distribuidor/*` route gate in AdminLayout, introduced in:
 *   sdd/distributor-vehicle-delivery, Phase 7 (frontend, PR7)
 *
 * Design ADR 10: gated by PREFIX match (`startsWith('/distribuidor')`),
 * checked FIRST, so a single `ROUTE_ROLES` entry covers this screen AND a
 * future parts-sale screen under the same namespace with zero further
 * edits. Every other role is redirected to its own home
 * (`administrativo` -> '/', `proveedor` -> '/imports', else -> '/kanban').
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/distribuidor/entrega';

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
  mockPathname = '/distribuidor/entrega';
});

describe('AdminLayout — /distribuidor/* route gate', () => {
  it('redirects a non-allowed role (jefe_taller) away from /distribuidor/entrega, to /kanban', async () => {
    setUser('jefe_taller');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/kanban');
    });
    expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
  });

  it('redirects an administrativo user away from /distribuidor/entrega, to its own home (/)', async () => {
    setUser('administrativo');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/');
    });
  });

  it('redirects a proveedor user away from /distribuidor/entrega, to /imports', async () => {
    setUser('proveedor');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/imports');
    });
  });

  it('does NOT redirect a parts_dealer user visiting /distribuidor/entrega', async () => {
    setUser('parts_dealer');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('does NOT redirect a superadmin user visiting /distribuidor/entrega', async () => {
    setUser('superadmin');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('existing /historical-orders gate is unaffected by the new prefix check', async () => {
    mockPathname = '/historical-orders';
    setUser('jefe_taller');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/kanban');
    });
  });
});
