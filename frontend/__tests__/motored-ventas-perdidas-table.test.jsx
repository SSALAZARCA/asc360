/**
 * Tests for `VentasPerdidasTable` (sdd/motored-ventas-perdidas-panel, Phase
 * 7, tasks 7.5/7.6; design D6's inline-edit interaction). This suite has NO
 * `jest.mock` for `lib/motored/api` -- the table receives `onEditar`/
 * `onAnular` as props (jest.fn()), same separation `UsuariosTable` has from
 * `usuarios/page.js`'s own api calls.
 *
 * What's under test:
 * 1. Inline edit: Editar shows a number input + Guardar/Cancelar; Enter
 *    saves and calls onEditar with the right args; Escape cancels WITHOUT
 *    calling onEditar; blur does NOT save (design D6's explicit rejection
 *    of save-on-blur); only one row is editable at a time.
 * 2. An ANULADA line has no Editar and no Anular trigger (read-only,
 *    terminal state per spec).
 * 3. Zero/negative quantity is rejected client-side with a message, without
 *    calling onEditar (steers to Anular instead, per spec).
 * 4. Anular requires window.confirm before calling onAnular; declining the
 *    confirm does not call onAnular.
 * 5. A deactivated sucursal/asesor's line still renders, flagged visually,
 *    not hidden (spec "Deactivated sucursal or asesor does not restrict
 *    visibility").
 * 6. The 2000-row truncation notice appears exactly at the limit.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import VentasPerdidasTable from '../components/motored/ventas-perdidas/VentasPerdidasTable';

function linea(overrides = {}) {
  return {
    linea_id: 'l1', carga_id: 'c1', fecha: '2026-09-01', cantidad: 3, estado: 'ACTIVA',
    metodo: 'manual', created_at: '2026-09-01T10:00:00Z',
    asesor: { id: 'a1', nombre: 'Juan Asesor', activo: true },
    sucursal: { id: 's1', nombre: 'Bogotá Norte', activa: true },
    referencia: { id: 'r1', codigo: 'X1', nombre: 'Filtro de aceite' },
    editado_por: null, editado_en: null, anulado_por: null, anulado_en: null,
    ...overrides,
  };
}

let confirmSpy;
beforeEach(() => {
  confirmSpy = jest.spyOn(window, 'confirm');
});
afterEach(() => {
  confirmSpy.mockRestore();
});

describe('VentasPerdidasTable — icon actions', () => {
  it('renders Editar/Anular as icon-only buttons (no visible text)', () => {
    render(<VentasPerdidasTable lineas={[linea()]} onEditar={jest.fn()} onAnular={jest.fn()} />);
    ['Editar', 'Anular'].forEach((n) => {
      const btn = screen.getByRole('button', { name: n });
      expect(btn.textContent).toBe('');
      expect(btn.querySelector('svg')).not.toBeNull();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    ['Guardar', 'Cancelar'].forEach((n) => {
      expect(screen.getByRole('button', { name: n }).textContent).toBe('');
    });
  });
});

describe('VentasPerdidasTable — inline edit', () => {
  it('Editar shows a number input pre-filled with the current quantity, plus Guardar/Cancelar', () => {
    render(<VentasPerdidasTable lineas={[linea()]} onEditar={jest.fn()} onAnular={jest.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));

    expect(screen.getByRole('spinbutton')).toHaveValue(3);
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeInTheDocument();
  });

  it('Enter saves and calls onEditar with the line id and the new quantity', async () => {
    const onEditar = jest.fn().mockResolvedValue(true);
    render(<VentasPerdidasTable lineas={[linea()]} onEditar={onEditar} onAnular={jest.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    const input = screen.getByRole('spinbutton');
    fireEvent.change(input, { target: { value: '7' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(onEditar).toHaveBeenCalledWith('l1', 7));
    await waitFor(() => expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument());
  });

  it('Escape cancels the edit WITHOUT calling onEditar', () => {
    const onEditar = jest.fn();
    render(<VentasPerdidasTable lineas={[linea()]} onEditar={onEditar} onAnular={jest.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    const input = screen.getByRole('spinbutton');
    fireEvent.change(input, { target: { value: '99' } });
    fireEvent.keyDown(input, { key: 'Escape' });

    expect(onEditar).not.toHaveBeenCalled();
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Editar' })).toBeInTheDocument();
  });

  it('blur does NOT save (design rejects save-on-blur)', () => {
    const onEditar = jest.fn();
    render(<VentasPerdidasTable lineas={[linea()]} onEditar={onEditar} onAnular={jest.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    const input = screen.getByRole('spinbutton');
    fireEvent.change(input, { target: { value: '9' } });
    fireEvent.blur(input);

    expect(onEditar).not.toHaveBeenCalled();
    expect(screen.getByRole('spinbutton')).toBeInTheDocument();
  });

  it('only one row is editable at a time -- Editar is hidden on other rows while editing', () => {
    const lineas = [linea({ linea_id: 'l1', referencia: { id: 'r1', codigo: 'X1', nombre: 'Filtro' } }),
      linea({ linea_id: 'l2', referencia: { id: 'r2', codigo: 'X2', nombre: 'Bujía' } })];
    render(<VentasPerdidasTable lineas={lineas} onEditar={jest.fn()} onAnular={jest.fn()} />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Editar' })[0]);

    expect(screen.queryAllByRole('button', { name: 'Editar' })).toHaveLength(0);
    expect(screen.getAllByRole('spinbutton')).toHaveLength(1);
  });

  it('rejects a zero/negative quantity client-side with a message, without calling onEditar', () => {
    const onEditar = jest.fn();
    render(<VentasPerdidasTable lineas={[linea()]} onEditar={onEditar} onAnular={jest.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    expect(onEditar).not.toHaveBeenCalled();
    expect(screen.getByText(/mayor a 0/i)).toBeInTheDocument();
  });
});

describe('VentasPerdidasTable — ANULADA lines are read-only', () => {
  it('shows no Editar and no Anular trigger for an ANULADA line', () => {
    render(<VentasPerdidasTable lineas={[linea({ estado: 'ANULADA' })]} onEditar={jest.fn()} onAnular={jest.fn()} />);

    expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Anular' })).not.toBeInTheDocument();
    expect(screen.getByText('ANULADA')).toBeInTheDocument();
  });
});

describe('VentasPerdidasTable — Anular requires confirmation', () => {
  it('calls onAnular only after window.confirm returns true', () => {
    confirmSpy.mockReturnValue(true);
    const onAnular = jest.fn();
    render(<VentasPerdidasTable lineas={[linea()]} onEditar={jest.fn()} onAnular={onAnular} />);

    fireEvent.click(screen.getByRole('button', { name: 'Anular' }));

    expect(confirmSpy).toHaveBeenCalled();
    expect(onAnular).toHaveBeenCalledWith('l1');
  });

  it('does NOT call onAnular when window.confirm returns false', () => {
    confirmSpy.mockReturnValue(false);
    const onAnular = jest.fn();
    render(<VentasPerdidasTable lineas={[linea()]} onEditar={jest.fn()} onAnular={onAnular} />);

    fireEvent.click(screen.getByRole('button', { name: 'Anular' }));

    expect(onAnular).not.toHaveBeenCalled();
  });
});

describe('VentasPerdidasTable — deactivated sucursal/asesor stay visible', () => {
  it('renders a line tied to a deactivated sucursal, flagged with "(inactiva)", not hidden', () => {
    render(<VentasPerdidasTable
      lineas={[linea({ sucursal: { id: 's2', nombre: 'Cali Sur', activa: false } })]}
      onEditar={jest.fn()}
      onAnular={jest.fn()}
    />);

    expect(screen.getByText('Cali Sur')).toBeInTheDocument();
    expect(screen.getByText('(inactiva)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Editar' })).toBeInTheDocument();
  });

  it('renders a line tied to a deactivated asesor, flagged with "(inactivo)", still anulable', () => {
    render(<VentasPerdidasTable
      lineas={[linea({ asesor: { id: 'a2', nombre: 'Marta Asesor', activo: false } })]}
      onEditar={jest.fn()}
      onAnular={jest.fn()}
    />);

    expect(screen.getByText('Marta Asesor')).toBeInTheDocument();
    expect(screen.getByText('(inactivo)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Anular' })).toBeInTheDocument();
  });
});

describe('VentasPerdidasTable — truncation notice', () => {
  it('shows the 2000-row truncation notice when exactly at the limit', () => {
    const lineas = Array.from({ length: 2000 }, (_, i) => linea({ linea_id: `l${i}` }));
    render(<VentasPerdidasTable lineas={lineas} onEditar={jest.fn()} onAnular={jest.fn()} />);

    expect(screen.getByText(/2000/)).toBeInTheDocument();
  });

  it('does not show the truncation notice below the limit', () => {
    render(<VentasPerdidasTable lineas={[linea()]} onEditar={jest.fn()} onAnular={jest.fn()} />);

    expect(screen.queryByText(/límite/i)).not.toBeInTheDocument();
  });
});
