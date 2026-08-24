/**
 * Tests for the `/distribuidor/repuestos` route gate in AdminLayout,
 * introduced in: sdd/distributor-parts-search, Phase 4 (frontend, PR4)
 *
 * Design ADR 13: ZERO edits to `admin-layout.js`. The existing PREFIX match
 * (`ROUTE_ROLES['/distribuidor'] = ['parts_dealer', 'superadmin']`,
 * `frontend/app/admin-layout.js:77`) already covers this new route by
 * construction, exactly as it was designed to for a "future parts-sale
 * screen" (see `admin-layout-distribuidor-gate.test.jsx`'s own docstring).
 * This test file PROVES that zero further edits are needed rather than
 * assuming it.
 *
 * NOTE (scope adjustment, this session): this route/page gate is deliberately
 * UNCHANGED from the tasks doc -- `parts_dealer` reaches this page via the
 * existing prefix gate exactly like `superadmin` does. Only the SIDEBAR
 * MENU entry is temporarily hidden from `parts_dealer` (see
 * `sidebar-parts-search-gate.test.jsx`); a `parts_dealer` who knows/types
 * the URL directly is not blocked here. This is the intentionally
 * lighter-weight choice for this testing phase, not a bug.
 *
 * Updated 2026-08-24 (accepted side effect, same shape as
 * `admin-layout-distribuidor-gate.test.jsx`'s update): the business-owner
 * decision to widen `ROUTE_ROLES['/distribuidor']` for Registro de
 * Motocicletas (Design ADR 10's shared PREFIX match) also opens THIS route
 * to `administrativo` by construction -- the Sidebar menu entry for
 * "Consulta de Repuestos" stays `roles: ['superadmin']` only (unchanged),
 * so administrativo gets no menu link here, but direct URL entry is no
 * longer blocked. Same "shared gate widens more than the one named screen"
 * shape as Maestro de Partes' `/admin/vehicle-models` side effect.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/distribuidor/repuestos';

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
  mockPathname = '/distribuidor/repuestos';
});

describe('AdminLayout — /distribuidor/repuestos route gate (zero admin-layout.js edits)', () => {
  it('does NOT redirect a parts_dealer user visiting /distribuidor/repuestos', async () => {
    setUser('parts_dealer');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('does NOT redirect a superadmin user visiting /distribuidor/repuestos', async () => {
    setUser('superadmin');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('redirects a non-allowed role (jefe_taller) away from /distribuidor/repuestos, to /kanban', async () => {
    setUser('jefe_taller');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/kanban');
    });
    expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
  });

  it('does NOT redirect an administrativo user visiting /distribuidor/repuestos (2026-08-24: accepted side effect of the shared prefix gate, see file docstring)', async () => {
    setUser('administrativo');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('redirects a proveedor user away from /distribuidor/repuestos, to /imports', async () => {
    setUser('proveedor');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/imports');
    });
  });

  it('redirects a parts_dealer user away from /kanban, to /distribuidor/entrega (still locked to its own prefix)', async () => {
    mockPathname = '/kanban';
    setUser('parts_dealer');
    render(<AdminLayout><div>Contenido protegido</div></AdminLayout>);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/distribuidor/entrega');
    });
    expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
  });
});
