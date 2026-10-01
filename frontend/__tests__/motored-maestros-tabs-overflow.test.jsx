/**
 * The Maestros tab bar has 12 tabs: it must scroll inside its own box instead
 * of widening the page (found with a real 1440px screenshot).
 */
import React from 'react';
import { render } from '@testing-library/react';

jest.mock('../lib/motored/api', () => ({ getSalud: () => Promise.resolve({ hallazgos: [] }) }));

import MaestrosTabs from '../components/motored/maestros/MaestrosTabs';

it('la barra de pestañas se desplaza dentro de su caja', () => {
  const tabs = [
    { id: 'a', label: 'A', group: 'Maestros', render: () => <p>a</p> },
    { id: 'b', label: 'B', group: 'Movimientos', render: () => <p>b</p> },
  ];
  const { container } = render(<MaestrosTabs tabs={tabs} />);
  const barra = container.querySelector('.motored-tab-bar');
  expect(barra.style.overflowX).toBe('auto');
  expect(barra.style.maxWidth).toBe('100%');
});
