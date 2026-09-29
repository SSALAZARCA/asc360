import { render, screen, fireEvent } from '@testing-library/react';
import MotoredIconAction from '@/components/motored/MotoredIconAction';
import { ACTION_ICONS } from '@/components/motored/actionIcons';

describe('MotoredIconAction', () => {
  it('exposes the label as accessible name and fires onClick', () => {
    const onClick = jest.fn();
    render(<MotoredIconAction action="Editar" onClick={onClick} />);
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('shows the tooltip on hover and hides it on leave', () => {
    render(<MotoredIconAction action="Anular" onClick={() => {}} />);
    const btn = screen.getByRole('button', { name: 'Anular' });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    fireEvent.mouseEnter(btn);
    expect(screen.getByRole('tooltip')).toHaveTextContent('Anular');
    fireEvent.mouseLeave(btn);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('shows the tooltip on keyboard focus and hides it on blur', () => {
    render(<MotoredIconAction action="Aprobar" onClick={() => {}} />);
    const btn = screen.getByRole('button', { name: 'Aprobar' });
    fireEvent.focus(btn);
    expect(screen.getByRole('tooltip')).toHaveTextContent('Aprobar');
    fireEvent.blur(btn);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('uses the danger color for the danger variant only', () => {
    const { rerender } = render(<MotoredIconAction action="Anular" variant="danger" onClick={() => {}} />);
    expect(screen.getByRole('button', { name: 'Anular' }).dataset.variant).toBe('danger');
    rerender(<MotoredIconAction action="Anular" onClick={() => {}} />);
    expect(screen.getByRole('button', { name: 'Anular' }).dataset.variant).toBe('default');
  });

  it('honors disabled and a custom label', () => {
    const onClick = jest.fn();
    render(<MotoredIconAction action="Aplicar" label="Aplicando" disabled onClick={onClick} />);
    const btn = screen.getByRole('button', { name: 'Aplicando' });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('keeps a hit target of at least 32px', () => {
    render(<MotoredIconAction action="Editar" onClick={() => {}} />);
    const { minWidth, minHeight } = screen.getByRole('button', { name: 'Editar' }).style;
    expect(minWidth).toBe('32px');
    expect(minHeight).toBe('32px');
  });
});

describe('ACTION_ICONS', () => {
  it('maps every row action to one icon', () => {
    ['Editar', 'Desactivar', 'Reactivar', 'Anular', 'Aprobar', 'Rechazar', 'Cambiar contraseña',
      'Descargar', 'Ver detalle', 'Aplicar', 'Guardar', 'Cancelar', 'Mapear', 'Ignorar',
      'Crear como OTROS', 'Vincular Telegram', 'Desvincular Telegram'].forEach((a) => {
      expect(ACTION_ICONS[a]).toBeDefined();
    });
  });
});
