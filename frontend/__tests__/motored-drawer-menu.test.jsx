/**
 * Below 1024px the Motored sidebar becomes an off-canvas drawer opened from
 * a top bar (feature odd/motored-responsive-tablet, T1). The media query
 * itself lives in the theme CSS (jsdom cannot evaluate it), so these tests
 * cover the behavior: open, close by backdrop / Escape / navigation.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/motored/maestros';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));

import MotoredLayout from '../app/motored/motored-layout';

const openMenuButton = () => screen.getByRole('button', { name: 'Abrir menú' });
const drawer = () => screen.getByRole('complementary');

async function renderLayout() {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'Ana Admin', role: 'ADMIN' }));
  sessionStorage.setItem('motored_token', 'token');
  const view = render(<MotoredLayout><div>Contenido</div></MotoredLayout>);
  await screen.findByText('Contenido');
  return view;
}

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  mockPathname = '/motored/maestros';
});

describe('Motored drawer menu', () => {
  it('starts closed, with a top bar offering the menu button', async () => {
    await renderLayout();

    expect(openMenuButton()).toBeInTheDocument();
    expect(drawer()).not.toHaveClass('is-open');
    expect(screen.queryByTestId('motored-backdrop')).not.toBeInTheDocument();
  });

  it('opens the drawer and shows a backdrop when the menu button is pressed', async () => {
    await renderLayout();

    fireEvent.click(openMenuButton());

    expect(drawer()).toHaveClass('is-open');
    expect(screen.getByTestId('motored-backdrop')).toBeInTheDocument();
  });

  it('closes when the backdrop is tapped', async () => {
    await renderLayout();
    fireEvent.click(openMenuButton());

    fireEvent.click(screen.getByTestId('motored-backdrop'));

    expect(drawer()).not.toHaveClass('is-open');
    expect(screen.queryByTestId('motored-backdrop')).not.toBeInTheDocument();
  });

  it('closes when Escape is pressed', async () => {
    await renderLayout();
    fireEvent.click(openMenuButton());

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(drawer()).not.toHaveClass('is-open');
  });

  it('ignores other keys while open', async () => {
    await renderLayout();
    fireEvent.click(openMenuButton());

    fireEvent.keyDown(document, { key: 'Enter' });

    expect(drawer()).toHaveClass('is-open');
  });

  it('closes when a menu item is chosen', async () => {
    await renderLayout();
    fireEvent.click(openMenuButton());

    fireEvent.click(screen.getByRole('button', { name: /Usuarios/ }));

    expect(pushMock).toHaveBeenCalledWith('/motored/usuarios');
    expect(drawer()).not.toHaveClass('is-open');
  });

  it('closes when the route changes', async () => {
    const view = await renderLayout();
    fireEvent.click(openMenuButton());

    mockPathname = '/motored/usuarios';
    view.rerender(<MotoredLayout><div>Contenido</div></MotoredLayout>);

    await waitFor(() => expect(drawer()).not.toHaveClass('is-open'));
  });

  it('keeps the user name and Salir inside the drawer', async () => {
    await renderLayout();

    expect(drawer()).toHaveTextContent('Ana Admin');
    expect(drawer()).toHaveTextContent('Salir');
  });
});
