/**
 * MotoredLayout role handling for SERVICIO_CLIENTE (survey slice, T7).
 * The backend is the real enforcement; this UI guard is UX only.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/motored/encuesta-satisfaccion';

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

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  mockPathname = '/motored/encuesta-satisfaccion';
});

describe('MotoredLayout — SERVICIO_CLIENTE', () => {
  it('accepts SERVICIO_CLIENTE as a valid role on the survey page', async () => {
    login('SERVICIO_CLIENTE');
    render(<MotoredLayout><div>Contenido encuesta</div></MotoredLayout>);

    expect(await screen.findByText('Contenido encuesta')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('motored_user')).not.toBeNull();
  });

  it.each(['/motored/maestros', '/motored/usuarios', '/motored/ventas-perdidas', '/motored/cargas'])(
    'redirects SERVICIO_CLIENTE away from %s to the survey page without rendering content',
    async (path) => {
      login('SERVICIO_CLIENTE');
      mockPathname = path;
      render(<MotoredLayout><div>Contenido protegido</div></MotoredLayout>);

      await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/encuesta-satisfaccion'));
      expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
      expect(sessionStorage.getItem('motored_user')).not.toBeNull();
    }
  );

  it('does not treat a lookalike prefix as a survey path', async () => {
    login('SERVICIO_CLIENTE');
    mockPathname = '/motored/encuesta-satisfaccionXYZ';
    render(<MotoredLayout><div>Contenido protegido</div></MotoredLayout>);

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/encuesta-satisfaccion'));
  });

  it.each(['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA'])(
    'leaves %s untouched on a non-survey page',
    async (role) => {
      login(role);
      mockPathname = '/motored/maestros';
      render(<MotoredLayout><div>Contenido maestros</div></MotoredLayout>);

      expect(await screen.findByText('Contenido maestros')).toBeInTheDocument();
      expect(pushMock).not.toHaveBeenCalled();
    }
  );
});
