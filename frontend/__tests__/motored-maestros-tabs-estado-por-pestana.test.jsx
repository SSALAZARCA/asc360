/**
 * Two tabs that render the same component with a different prop (the
 * movement tabs: Backorder, Facturas, Ingresos...) must not share state:
 * switching tabs starts the new tab fresh, so its list shows its own type.
 */
import React, { useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

jest.mock('../lib/motored/api', () => ({
  getSalud: () => Promise.resolve({ hallazgos: [] }),
}));

import MaestrosTabs from '../components/motored/maestros/MaestrosTabs';

function Lista({ tipo }) {
  const [filtro] = useState(tipo);
  return <p>{`lista de ${filtro}`}</p>;
}

const TABS = [
  { id: 'bo', label: 'Backorder', render: () => <Lista tipo="BACKORDER" /> },
  { id: 'fa', label: 'Facturas', render: () => <Lista tipo="FACTURAS" /> },
];

it('each tab starts with its own state', () => {
  render(<MaestrosTabs tabs={TABS} />);
  expect(screen.getByText('lista de BACKORDER')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Facturas' }));

  expect(screen.getByText('lista de FACTURAS')).toBeInTheDocument();
});
