/**
 * The "Salir" button must always be on screen: the aside is sticky and as
 * tall as the viewport, so long pages (Sucursales, Referencias) never push
 * the footer below the fold (feature odd/motored-salir-y-cambio-password, T1).
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/maestros',
}));

import MotoredSidebar from '../components/motored/MotoredSidebar';

describe('MotoredSidebar — Salir always visible', () => {
  it('renders the user name and the Salir button', () => {
    render(<MotoredSidebar user={{ nombre: 'Ana Admin', role: 'ADMIN' }} />);

    expect(screen.getByText('Ana Admin')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Salir/ })).toBeInTheDocument();
  });

  it('pins the aside to the viewport (sticky, top 0, 100vh)', () => {
    render(<MotoredSidebar user={{ nombre: 'Ana Admin', role: 'ADMIN' }} />);

    const aside = screen.getByRole('complementary');
    expect(aside.style.position).toBe('sticky');
    expect(aside.style.top).toBe('0px');
    expect(aside.style.height).toBe('100vh');
  });

  it('lets the nav area scroll instead of pushing the footer out of view', () => {
    render(<MotoredSidebar user={{ nombre: 'Ana Admin', role: 'ADMIN' }} />);

    const nav = screen.getByRole('navigation');
    expect(nav.style.overflowY).toBe('auto');
  });

  it('Salir clears the session and goes to the login page', () => {
    sessionStorage.setItem('motored_user', '{}');
    render(<MotoredSidebar user={{ nombre: 'Ana Admin', role: 'ADMIN' }} />);

    fireEvent.click(screen.getByRole('button', { name: /Salir/ }));

    expect(pushMock).toHaveBeenCalledWith('/motored/login');
  });
});
