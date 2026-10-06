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
  it.each(['ADMIN', 'COMPRAS', 'GERENCIA', 'SERVICIO_CLIENTE'])('lands %s on Inicio', async (role) => {
    await submitAs(role);
    expect(pushMock).toHaveBeenCalledWith('/motored/inicio');
  });

  it.each(['SUCURSAL', 'CONSULTA'])('lands %s (no screens yet) on the account page', async (role) => {
    await submitAs(role);
    expect(pushMock).toHaveBeenCalledWith('/motored/mi-cuenta');
  });
});
