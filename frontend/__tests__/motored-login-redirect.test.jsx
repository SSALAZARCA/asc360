import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
const mockLogin = jest.fn();

jest.mock('next/navigation', () => ({ useRouter: () => ({ push: pushMock }) }));
jest.mock('next/image', () => {
  const MockImage = (props) => <span data-testid="img" data-alt={props.alt} />;
  MockImage.displayName = 'MockImage';
  return MockImage;
});
jest.mock('../lib/motored/api', () => ({ login: (...a) => mockLogin(...a) }));

import MotoredLoginPage from '../app/motored/login/page';

async function submitAs(role) {
  mockLogin.mockResolvedValue({ access_token: 't', user: { role } });
  const { container } = render(<MotoredLoginPage />);
  fireEvent.change(container.querySelector('input[type="email"]'), { target: { value: 'a@b.co' } });
  fireEvent.change(container.querySelector('input[type="password"]'), { target: { value: 'pw' } });
  fireEvent.submit(container.querySelector('form'));
  await waitFor(() => expect(pushMock).toHaveBeenCalled());
}

beforeEach(() => {
  pushMock.mockClear();
  sessionStorage.clear();
});

describe('Motored login redirect', () => {
  it('lands SERVICIO_CLIENTE on the survey admin page', async () => {
    await submitAs('SERVICIO_CLIENTE');
    expect(pushMock).toHaveBeenCalledWith('/motored/encuesta-satisfaccion');
  });

  it.each(['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA'])('keeps %s landing on maestros', async (role) => {
    await submitAs(role);
    expect(pushMock).toHaveBeenCalledWith('/motored/maestros');
  });
});
