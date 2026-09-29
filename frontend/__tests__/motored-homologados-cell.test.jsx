/**
 * `HomologadosCell` -- the "Homologados otras marcas" column of the Referencias
 * table. It always renders on one line: the first 3 models plus a `+N` button;
 * hovering the cell shows every model in a popover, clicking `+N` pins it, and
 * Escape or a click outside closes it.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

import HomologadosCell from '../components/motored/maestros/HomologadosCell';

const LONG = ['AK 125 FLEX', 'APACHE 160', 'CB 100', 'FZ 150', 'CB 190R', 'NKD 125'];

function renderCell(values) {
  return render(
    <div>
      <HomologadosCell values={values} />
      <p>fuera</p>
    </div>
  );
}

describe('HomologadosCell', () => {
  it('shows "—" when there are no models', () => {
    renderCell([]);

    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('shows a short list on one line with a hover title and no badge', () => {
    renderCell(['YAM-1', 'HON-2']);

    const text = screen.getByText('YAM-1, HON-2');
    expect(text).toHaveAttribute('title', 'YAM-1, HON-2');
    expect(text).toHaveStyle({ whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' });
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('shows the first 3 models plus a +N button for the rest', () => {
    renderCell(LONG);

    expect(screen.getByText('AK 125 FLEX, APACHE 160, CB 100')).toHaveStyle({ whiteSpace: 'nowrap' });
    const badge = screen.getByRole('button', { name: 'Ver los 6 modelos' });
    expect(badge).toHaveTextContent('+3');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows every model in a popover on hover and hides it on mouse leave', () => {
    renderCell(LONG);
    const cell = screen.getByText('AK 125 FLEX, APACHE 160, CB 100').parentElement;

    fireEvent.mouseEnter(cell);
    const popover = screen.getByRole('dialog', { name: 'Homologados otras marcas' });
    expect(popover).toHaveTextContent(LONG.join(', '));

    fireEvent.mouseLeave(cell);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('pins the popover open when the +N button is clicked (survives mouse leave)', () => {
    renderCell(LONG);
    const badge = screen.getByRole('button', { name: 'Ver los 6 modelos' });

    fireEvent.click(badge);
    fireEvent.mouseLeave(badge.parentElement);

    expect(badge).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('dialog')).toHaveTextContent('NKD 125');
  });

  it('closes the pinned popover with Escape and returns focus to the button', () => {
    renderCell(LONG);
    const badge = screen.getByRole('button', { name: 'Ver los 6 modelos' });
    fireEvent.click(badge);

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(badge).toHaveFocus();
  });

  it('closes the pinned popover on a click outside, but not on a click inside it', () => {
    renderCell(LONG);
    fireEvent.click(screen.getByRole('button', { name: 'Ver los 6 modelos' }));

    fireEvent.mouseDown(screen.getByRole('dialog'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByText('fuera'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
