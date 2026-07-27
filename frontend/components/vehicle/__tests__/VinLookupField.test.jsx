/**
 * Tests for the reusable VIN lookup input (mitigation #5,
 * sdd/historical-order-entry, Decision 7).
 *
 * Behavior mirrors the already-fixed `VinField` in
 * `app/superadmin-data/page.js`: the lookup callback fires as soon as the
 * value reaches exactly 17 characters, on `onChange` — NOT on `onBlur` and
 * NOT before the 17th character — so the lookup never feels "stuck" waiting
 * for the user to click away.
 */
import React, { useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import VinLookupField from '../VinLookupField';

const VIN_17 = '1HGCM82633A004352';
const VIN_16 = VIN_17.slice(0, 16);

function Harness({ onLookup, lookupStatus }) {
  const [value, setValue] = useState('');
  return (
    <VinLookupField
      value={value}
      onChange={setValue}
      onLookup={onLookup}
      lookupStatus={lookupStatus}
    />
  );
}

describe('VinLookupField', () => {
  it('fires onLookup as soon as the value reaches exactly 17 characters', () => {
    const onLookup = jest.fn();
    render(<Harness onLookup={onLookup} />);
    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: VIN_17 } });
    expect(onLookup).toHaveBeenCalledTimes(1);
    expect(onLookup).toHaveBeenCalledWith(VIN_17);
  });

  it('does NOT fire onLookup at 16 characters', () => {
    const onLookup = jest.fn();
    render(<Harness onLookup={onLookup} />);
    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: VIN_16 } });
    expect(onLookup).not.toHaveBeenCalled();
  });

  it('does NOT fire onLookup on blur (only a 17-char onChange triggers it)', () => {
    const onLookup = jest.fn();
    render(<Harness onLookup={onLookup} />);
    const input = screen.getByLabelText('VIN');
    fireEvent.change(input, { target: { value: VIN_17 } });
    onLookup.mockClear();
    fireEvent.blur(input);
    expect(onLookup).not.toHaveBeenCalled();
  });

  it('shows the loading hint when lookupStatus is "loading"', () => {
    render(<Harness onLookup={jest.fn()} lookupStatus="loading" />);
    expect(screen.getByText(/Buscando en el maestro de VINs/i)).toBeInTheDocument();
  });

  it('shows the found hint when lookupStatus is "found"', () => {
    render(<Harness onLookup={jest.fn()} lookupStatus="found" />);
    expect(screen.getByText(/Datos encontrados/i)).toBeInTheDocument();
  });

  it('shows the not_found hint when lookupStatus is "not_found"', () => {
    render(<Harness onLookup={jest.fn()} lookupStatus="not_found" />);
    expect(screen.getByText(/No está en el maestro/i)).toBeInTheDocument();
  });

  it('renders no hint at all when lookupStatus is "idle"', () => {
    render(<Harness onLookup={jest.fn()} lookupStatus="idle" />);
    expect(screen.queryByText(/Buscando en el maestro de VINs/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Datos encontrados/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/No está en el maestro/i)).not.toBeInTheDocument();
  });
});
