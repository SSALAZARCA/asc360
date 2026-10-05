/**
 * `BodegasSecundariasEditor`: chips to add and remove a store's secondary
 * bodega codes in the Sucursales form. Codes are trimmed, upper-cased and
 * never repeated; the backend validates them against the other stores.
 */
import React, { useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

import BodegasSecundariasEditor from '../components/motored/maestros/BodegasSecundariasEditor';

function Harness({ inicial = [], onChange = () => {} }) {
  const [codigos, setCodigos] = useState(inicial);
  return (
    <BodegasSecundariasEditor
      value={codigos}
      onChange={(nuevos) => {
        setCodigos(nuevos);
        onChange(nuevos);
      }}
    />
  );
}

const input = () => screen.getByLabelText(/Bodegas secundarias/, { selector: 'input' });
const chips = () => screen.queryAllByRole('listitem').map((li) => li.firstChild.textContent);

describe('BodegasSecundariasEditor', () => {
  it('shows the current codes as chips', () => {
    render(<Harness inicial={['BA161', 'MC001']} />);

    expect(chips()).toEqual(['BA161', 'MC001']);
  });

  it('adds a code upper-cased and trimmed with Enter, without submitting the form', () => {
    const onSubmit = jest.fn((e) => e.preventDefault());
    render(<form onSubmit={onSubmit}><Harness /></form>);

    fireEvent.change(input(), { target: { value: '  mc001 ' } });
    fireEvent.keyDown(input(), { key: 'Enter' });

    expect(chips()).toEqual(['MC001']);
    expect(input()).toHaveValue('');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('adds several codes pasted with commas, never repeating one', () => {
    render(<Harness inicial={['BA161']} />);

    fireEvent.change(input(), { target: { value: 'mc001, ba161 ,mc002' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar' }));

    expect(chips()).toEqual(['BA161', 'MC001', 'MC002']);
  });

  it('adds the typed code when the input loses focus', () => {
    render(<Harness />);

    fireEvent.change(input(), { target: { value: 'mc009' } });
    fireEvent.blur(input());

    expect(chips()).toEqual(['MC009']);
  });

  it('ignores a blank entry', () => {
    const onChange = jest.fn();
    render(<Harness onChange={onChange} />);

    fireEvent.change(input(), { target: { value: '   ' } });
    fireEvent.keyDown(input(), { key: 'Enter' });

    expect(chips()).toEqual([]);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('removes a code with its chip button', () => {
    const onChange = jest.fn();
    render(<Harness inicial={['BA161', 'MC001']} onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: 'Quitar MC001' }));

    expect(chips()).toEqual(['BA161']);
    expect(onChange).toHaveBeenLastCalledWith(['BA161']);
  });

  it('explains the field in a tooltip', () => {
    render(<Harness />);

    const nota = screen.getByRole('note');
    expect(nota.getAttribute('aria-label')).toMatch(/misma tienda/);
    expect(nota.getAttribute('aria-label')).toMatch(/consignación/);
  });
});
