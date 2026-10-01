/**
 * Every Motored data table sits inside one shared horizontal-scroll wrapper
 * so the page itself never scrolls sideways on a tablet (feature
 * odd/motored-responsive-tablet, T2).
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import fs from 'fs';
import path from 'path';

import MotoredTableScroll from '../components/motored/MotoredTableScroll';

const ROOT = path.join(__dirname, '..');

// Tables that already live inside their own overflow:auto preview box.
const OWN_SCROLL_BOX = ['components/motored/cargas/VistaPreviaTab.js', 'components/motored/maestros/BulkUploadModal.js'];

const TABLE_FILES = [
  'app/motored/usuarios/page.js',
  'components/motored/cargas/CargasHistoryTable.js',
  'components/motored/cargas/ErroresTab.js',
  'components/motored/maestros/BodegasTab.js',
  'components/motored/maestros/ProveedoresTab.js',
  'components/motored/maestros/ReferenciasTab.js',
  'components/motored/maestros/SucursalesTab.js',
  'components/motored/ventas-perdidas/VentasPerdidasTable.js',
];

const count = (source, re) => (source.match(re) || []).length;

describe('MotoredTableScroll', () => {
  it('wraps its table in a horizontally scrollable container', () => {
    render(
      <MotoredTableScroll>
        <table><tbody><tr><td>dato</td></tr></tbody></table>
      </MotoredTableScroll>,
    );

    const wrapper = screen.getByRole('table').parentElement;
    expect(wrapper).toHaveClass('motored-table-scroll');
    expect(wrapper.style.overflowX).toBe('auto');
  });
});

describe('Motored tables use the shared wrapper', () => {
  it.each(TABLE_FILES)('%s wraps every <table> in MotoredTableScroll', (file) => {
    const source = fs.readFileSync(path.join(ROOT, file), 'utf8');

    expect(count(source, /<table[\s>]/g)).toBeGreaterThan(0);
    expect(count(source, /<MotoredTableScroll[\s>]/g)).toBe(count(source, /<table[\s>]/g));
  });

  it.each(OWN_SCROLL_BOX)('%s keeps its own scrollable preview box', (file) => {
    const source = fs.readFileSync(path.join(ROOT, file), 'utf8');

    expect(source).toMatch(/overflow: 'auto'/);
  });
});

describe('MotoredTableScroll maxHeight', () => {
  it('scrolls vertically inside the box when a max height is given', () => {
    render(
      <MotoredTableScroll maxHeight="70vh">
        <table><tbody><tr><td>dato</td></tr></tbody></table>
      </MotoredTableScroll>,
    );
    expect(screen.getByRole('table').parentElement).toHaveStyle({ maxHeight: '70vh', overflowY: 'auto' });
  });

  it('does not limit the height by default', () => {
    render(
      <MotoredTableScroll>
        <table><tbody><tr><td>dato</td></tr></tbody></table>
      </MotoredTableScroll>,
    );
    expect(screen.getByRole('table').parentElement.style.maxHeight).toBe('');
  });
});
