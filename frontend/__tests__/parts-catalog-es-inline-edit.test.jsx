/**
 * Tests for the inline "Descripción ES" cell editor added to
 * frontend/app/parts-catalog/page.js — lets staff correct the Spanish name
 * directly from the table, without opening the full edit modal.
 *
 * The parts-catalog page is a 1100+ line monolith with 5+ parallel useEffect
 * fetches on mount (vehicle-models, pricing-factors, coverage, the main
 * catalog page). Rather than mocking all of that, this test exercises the
 * EXACT same handler code (startEditDescriptionEs/cancelEditDescriptionEs/
 * saveDescriptionEs) and cell markup, copied verbatim, inside a minimal
 * single-row widget — same isolation technique already established in
 * catalog-upload.test.jsx for this same page's other state machines. Any
 * deviation from the production handlers/markup is a test bug.
 */
import React, { useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));
import { authFetch } from '../lib/authFetch';

// === EsCell — exact copy of the relevant state/handlers/markup from
// frontend/app/parts-catalog/page.js ===
function EsCellWidget({ initialItem }) {
  const [items, setItems] = useState([initialItem]);
  const item = items[0];

  const [editingEsCell, setEditingEsCell] = useState(null);
  const [esDraft, setEsDraft] = useState('');
  const [esCellError, setEsCellError] = useState({});

  const startEditDescriptionEs = (item) => {
    setEsCellError(prev => { const next = { ...prev }; delete next[item.factory_part_number]; return next; });
    setEsDraft(item.description_es || '');
    setEditingEsCell(item.factory_part_number);
  };

  const cancelEditDescriptionEs = () => {
    setEditingEsCell(null);
    setEsDraft('');
  };

  const saveDescriptionEs = async (item) => {
    const newVal = esDraft.trim() || null;
    const prevVal = item.description_es;
    setEditingEsCell(null);
    if (newVal === (prevVal || null)) return;
    setItems(prev => prev.map(i => i.factory_part_number === item.factory_part_number ? { ...i, description_es: newVal } : i));
    try {
      const res = await authFetch(`/parts/admin/catalog/${encodeURIComponent(item.factory_part_number)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description_es_manual: newVal }),
      });
      if (!res.ok) {
        setItems(prev => prev.map(i => i.factory_part_number === item.factory_part_number ? { ...i, description_es: prevVal } : i));
        setEsCellError(prev => ({ ...prev, [item.factory_part_number]: 'Error al guardar.' }));
      }
    } catch {
      setItems(prev => prev.map(i => i.factory_part_number === item.factory_part_number ? { ...i, description_es: prevVal } : i));
      setEsCellError(prev => ({ ...prev, [item.factory_part_number]: 'Error de conexión.' }));
    }
  };

  return (
    <table>
      <tbody>
        <tr>
          <td>{item.factory_part_number}</td>
          <td>{item.description}</td>
          <td>
            {editingEsCell === item.factory_part_number ? (
              <input
                autoFocus
                aria-label="Descripción ES"
                value={esDraft}
                onChange={e => setEsDraft(e.target.value)}
                onBlur={() => saveDescriptionEs(item)}
                onKeyDown={e => {
                  if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); }
                  else if (e.key === 'Escape') { e.preventDefault(); cancelEditDescriptionEs(); }
                }}
              />
            ) : (
              <div onClick={() => startEditDescriptionEs(item)} title="Click para editar">
                {item.description_es
                  ? <span>{item.description_es}</span>
                  : <span data-testid="es-placeholder">—</span>
                }
              </div>
            )}
            {esCellError[item.factory_part_number] && (
              <span role="alert">{esCellError[item.factory_part_number]}</span>
            )}
          </td>
          <td>{item.vehicle_model_name}</td>
          <td>
            {[['alta', 'A'], ['media', 'M'], ['baja', 'B']].map(([val, label]) => (
              <button
                key={val}
                aria-pressed={item.rotation_class === val}
                onClick={() => setItems(prev => prev.map(i => ({ ...i, rotation_class: i.rotation_class === val ? null : val })))}
              >
                {label}
              </button>
            ))}
          </td>
        </tr>
      </tbody>
    </table>
  );
}

const ITEM = {
  factory_part_number: 'FAB-001',
  description: 'Brake pad',
  description_es: 'Pastilla de freno',
  vehicle_model_name: 'Renegade 200',
  rotation_class: 'alta',
};

beforeEach(() => {
  mockAuthFetch.mockReset();
});

test('clicking the cell shows an input pre-filled with the current value', () => {
  render(<EsCellWidget initialItem={ITEM} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  expect(screen.getByLabelText('Descripción ES')).toHaveValue('Pastilla de freno');
});

test('clicking a cell with no existing value shows an empty input, not the placeholder', () => {
  render(<EsCellWidget initialItem={{ ...ITEM, description_es: null }} />);
  fireEvent.click(screen.getByTestId('es-placeholder'));
  expect(screen.getByLabelText('Descripción ES')).toHaveValue('');
});

test('typing + blur PATCHes description_es_manual (not description_es) with the trimmed value', async () => {
  mockAuthFetch.mockResolvedValue({ ok: true });
  render(<EsCellWidget initialItem={ITEM} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  const input = screen.getByLabelText('Descripción ES');
  fireEvent.change(input, { target: { value: '  Pastilla nueva  ' } });
  fireEvent.blur(input);

  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  const [url, options] = mockAuthFetch.mock.calls[0];
  expect(url).toBe('/parts/admin/catalog/FAB-001');
  expect(options.method).toBe('PATCH');
  const body = JSON.parse(options.body);
  expect(body).toEqual({ description_es_manual: 'Pastilla nueva' });
  expect(body.description_es).toBeUndefined();

  // Optimistic update — new value visible without a refetch.
  expect(await screen.findByText('Pastilla nueva')).toBeInTheDocument();
});

test('typing + Enter saves the same way as blur', async () => {
  mockAuthFetch.mockResolvedValue({ ok: true });
  render(<EsCellWidget initialItem={ITEM} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  const input = screen.getByLabelText('Descripción ES');
  fireEvent.change(input, { target: { value: 'Otro nombre' } });
  fireEvent.keyDown(input, { key: 'Enter' });

  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  const body = JSON.parse(mockAuthFetch.mock.calls[0][1].body);
  expect(body).toEqual({ description_es_manual: 'Otro nombre' });
});

test('Escape cancels without saving and reverts to the read-only display', () => {
  render(<EsCellWidget initialItem={ITEM} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  const input = screen.getByLabelText('Descripción ES');
  fireEvent.change(input, { target: { value: 'Nombre descartado' } });
  fireEvent.keyDown(input, { key: 'Escape' });

  expect(mockAuthFetch).not.toHaveBeenCalled();
  expect(screen.getByText('Pastilla de freno')).toBeInTheDocument();
  expect(screen.queryByText('Nombre descartado')).not.toBeInTheDocument();
});

test('saving an empty string PATCHes null', async () => {
  mockAuthFetch.mockResolvedValue({ ok: true });
  render(<EsCellWidget initialItem={ITEM} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  const input = screen.getByLabelText('Descripción ES');
  fireEvent.change(input, { target: { value: '   ' } });
  fireEvent.blur(input);

  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  const body = JSON.parse(mockAuthFetch.mock.calls[0][1].body);
  expect(body).toEqual({ description_es_manual: null });
});

test('a failed PATCH reverts the optimistic update and shows an error', async () => {
  mockAuthFetch.mockResolvedValue({ ok: false, json: async () => ({ detail: 'nope' }) });
  render(<EsCellWidget initialItem={ITEM} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  const input = screen.getByLabelText('Descripción ES');
  fireEvent.change(input, { target: { value: 'Nombre fallido' } });
  fireEvent.blur(input);

  await screen.findByRole('alert');
  expect(screen.getByText('Pastilla de freno')).toBeInTheDocument();
  expect(screen.queryByText('Nombre fallido')).not.toBeInTheDocument();
});

test('regression: row still renders factory number, description, and model', () => {
  render(<EsCellWidget initialItem={ITEM} />);
  expect(screen.getByText('FAB-001')).toBeInTheDocument();
  expect(screen.getByText('Brake pad')).toBeInTheDocument();
  expect(screen.getByText('Renegade 200')).toBeInTheDocument();
});

test('regression: rotation-class buttons still work', () => {
  render(<EsCellWidget initialItem={ITEM} />);
  const bajaBtn = screen.getByRole('button', { name: 'B' });
  fireEvent.click(bajaBtn);
  expect(bajaBtn).toHaveAttribute('aria-pressed', 'true');
});
