/** Motored Fase 4 (F1): the new pedido actions map to real lucide icons. */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { ACTION_ICONS } from '../components/motored/actionIcons';
import MotoredIconAction from '../components/motored/MotoredIconAction';

const NUEVAS = [
  'Cerrar', 'Reabrir', 'Exportar', 'Marcar como enviado', 'Aplicar recorte',
  'Recalcular fallidas', 'Comparar', 'Nuevo escenario', 'Historial',
];

describe('pedido action icons', () => {
  it.each(NUEVAS)('%s has an icon component', (action) => {
    expect(ACTION_ICONS[action]).toBeTruthy();
  });

  it('renders the icon inside the accessible button', () => {
    const { container } = render(<MotoredIconAction action="Cerrar" onClick={() => {}} />);
    expect(screen.getByRole('button', { name: 'Cerrar' })).toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('offers a 44 px touch target on request', () => {
    render(<MotoredIconAction action="Anular" touch onClick={() => {}} />);
    const style = screen.getByRole('button', { name: 'Anular' }).style;
    expect(style.minWidth).toBe('44px');
    expect(style.minHeight).toBe('44px');
  });

  it('keeps the compact 32 px target by default', () => {
    render(<MotoredIconAction action="Anular" onClick={() => {}} />);
    expect(screen.getByRole('button', { name: 'Anular' }).style.minWidth).toBe('32px');
  });
});
