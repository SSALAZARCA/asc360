/**
 * Tests for the reusable model <select> (mitigation #4,
 * sdd/historical-order-entry, Decision 7).
 *
 * Mirrors the exact `ModeloField` component in `app/superadmin-data/page.js`:
 * the master VIN catalog often supplies a model string that doesn't match
 * the standardized catalog letter-for-letter (e.g. "RENEGADE SPORT 200S" vs.
 * "Renegade 200"). Without an extra option, an unmatched value would be
 * invisible in the <select> even though it's genuinely saved in the form —
 * so it must always render as a visible extra option, never blank.
 */
import React, { useState } from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import ModelSelectField from '../ModelSelectField';

const MODELS = [
  { id: '1', modelo: 'Renegade 200' },
  { id: '2', modelo: 'Rockville 200' },
];

function Harness({ models, initialValue = '' }) {
  const [value, setValue] = useState(initialValue);
  return <ModelSelectField models={models} value={value} onChange={setValue} />;
}

describe('ModelSelectField', () => {
  it('renders a <select> listing every catalog entry when the value matches one exactly', () => {
    render(<Harness models={MODELS} initialValue="Renegade 200" />);
    const select = screen.getByLabelText('Modelo');
    expect(select.tagName).toBe('SELECT');
    expect(within(select).getByText('Renegade 200')).toBeInTheDocument();
    expect(within(select).getByText('Rockville 200')).toBeInTheDocument();
    expect(select.value).toBe('Renegade 200');
  });

  it('renders the current value as a visible extra option when it does not match any catalog entry', () => {
    render(<Harness models={MODELS} initialValue="RENEGADE SPORT 200S" />);
    const select = screen.getByLabelText('Modelo');
    expect(within(select).getByText(/RENEGADE SPORT 200S/)).toBeInTheDocument();
    expect(select.value).toBe('RENEGADE SPORT 200S');
  });

  it('never renders a blank selection for an unmatched value (selected option is the value itself)', () => {
    render(<Harness models={MODELS} initialValue="Unknown Model" />);
    const select = screen.getByLabelText('Modelo');
    expect(select.value).toBe('Unknown Model');
    expect(select.value).not.toBe('');
  });

  it('falls back to a plain text <input> when the models catalog is empty', () => {
    render(<Harness models={[]} initialValue="Anything Typed" />);
    const field = screen.getByLabelText('Modelo');
    expect(field.tagName).toBe('INPUT');
    expect(field.value).toBe('Anything Typed');
  });

  it('calls onChange with the new value when a different option is selected', () => {
    render(<Harness models={MODELS} initialValue="Renegade 200" />);
    const select = screen.getByLabelText('Modelo');
    fireEvent.change(select, { target: { value: 'Rockville 200' } });
    expect(select.value).toBe('Rockville 200');
  });
});
