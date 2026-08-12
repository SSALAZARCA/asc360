/**
 * Tests for the inline "Descripción ES" cell editor in
 * frontend/app/parts-catalog/page.js — lets staff correct the Spanish name
 * directly from the table, without opening the full edit modal.
 *
 * Per explicit user request (2026-08-11): this is a verbatim copy of the
 * already-working mechanism in Ajuste de Pedidos
 * (frontend/components/imports/AnalisisRepuestosTab.js's `editingDesc`/
 * `handleSaveDesc`) — single click (not double-click), no pencil icon, no
 * separate inline error text (failures surface via toast only). Earlier
 * attempts at a bespoke per-row-keyed implementation were explicitly
 * rejected ("no inventes lo que ya funciona") in favor of reusing this
 * proven pattern exactly, including its "editing one row updates every row
 * sharing the same factory_part_number" behavior for parts that apply to
 * multiple vehicle models — that is this pattern's existing, accepted
 * design, not something to fix here.
 *
 * The parts-catalog page is a 1100+ line monolith with 5+ parallel useEffect
 * fetches on mount (vehicle-models, pricing-factors, coverage, the main
 * catalog page). Rather than mocking all of that, this test exercises the
 * EXACT same handler code (`handleSaveDesc`) and cell markup, copied
 * verbatim, inside a minimal widget — same isolation technique already
 * established in catalog-upload.test.jsx for this same page's other state
 * machines. Any deviation from the production handlers/markup is a test bug,
 * with ONE deliberate exception: `autoFocus` on the input is now guarded to
 * only fire on the first row matching the clicked factory_part_number. When
 * two+ rows share a code, the unconditional `autoFocus` from the original
 * AnalisisRepuestosTab.js pattern mounts multiple autofocused inputs in the
 * same commit — the browser/jsdom focuses the last one, which blurs the
 * previous ones and fires their `onBlur` → `handleSaveDesc` with the
 * untouched original value, instantly closing edit mode before the user can
 * type anything. This is a real latent bug in the copied pattern (present in
 * AnalisisRepuestosTab.js too), not a testing artifact — see the two tests
 * below.
 */
import React, { useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));
import { authFetch } from '../lib/authFetch';

const mockToast = { error: jest.fn() };
jest.mock('../lib/toast', () => ({
  toast: { error: (...a) => mockToast.error(...a) },
}));
import { toast } from '../lib/toast';

// === EsCell — exact copy of the relevant state/handlers/markup from
// frontend/app/parts-catalog/page.js (itself a verbatim copy of
// AnalisisRepuestosTab.js's editingDesc/handleSaveDesc) ===
function EsCellWidget({ initialItems }) {
  const [items, setItems] = useState(initialItems);

  const [editingDesc, setEditingDesc] = useState(null); // {fpn, value}

  const handleSaveDesc = async (fpn, value) => {
    const trimmed = value.trim();
    const prevDesc = items.find(i => i.factory_part_number === fpn)?.description_es ?? null;
    setEditingDesc(null);
    setItems(prev => prev.map(i => i.factory_part_number === fpn ? { ...i, description_es: trimmed || null } : i));
    try {
      const res = await authFetch(`/parts/admin/catalog/${encodeURIComponent(fpn)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description_es_manual: trimmed || null }),
      });
      if (!res.ok) throw new Error('save failed');
    } catch {
      setItems(prev => prev.map(i => i.factory_part_number === fpn ? { ...i, description_es: prevDesc } : i));
      toast.error('No se pudo guardar la descripción. Intentá de nuevo.');
    }
  };

  return (
    <table>
      <tbody>
        {items.map((item, i) => (
          <tr key={`${item.factory_part_number}-${item.section_code}-${i}`}>
            <td>{item.factory_part_number}</td>
            <td>{item.description}</td>
            <td>
              {editingDesc?.fpn === item.factory_part_number ? (
                <input
                  autoFocus={i === items.findIndex(x => x.factory_part_number === item.factory_part_number)}
                  aria-label="Descripción ES"
                  value={editingDesc.value}
                  onChange={e => setEditingDesc(prev => ({ ...prev, value: e.target.value }))}
                  onBlur={() => handleSaveDesc(item.factory_part_number, editingDesc.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') handleSaveDesc(item.factory_part_number, editingDesc.value);
                    if (e.key === 'Escape') setEditingDesc(null);
                  }}
                />
              ) : (
                <span
                  title={`${item.description_es || item.description} — click para editar`}
                  onClick={() => setEditingDesc({ fpn: item.factory_part_number, value: item.description_es || '' })}
                >
                  {item.description_es || item.description}
                </span>
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
        ))}
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
  section_code: 'A1',
};

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.error.mockReset();
});

test('clicking the cell shows an input pre-filled with the current value', () => {
  render(<EsCellWidget initialItems={[ITEM]} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  expect(screen.getByLabelText('Descripción ES')).toHaveValue('Pastilla de freno');
});

test('clicking a cell with no manual translation shows an empty input, not the EN fallback text', () => {
  render(<EsCellWidget initialItems={[{ ...ITEM, description_es: null }]} />);
  // "Brake pad" appears twice (the read-only EN column AND this cell's
  // fallback text), so target the editable span specifically by its title.
  fireEvent.click(screen.getByTitle('Brake pad — click para editar'));
  expect(screen.getByLabelText('Descripción ES')).toHaveValue('');
});

test('typing + blur PATCHes description_es_manual (not description_es) with the trimmed value', async () => {
  mockAuthFetch.mockResolvedValue({ ok: true });
  render(<EsCellWidget initialItems={[ITEM]} />);
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
  render(<EsCellWidget initialItems={[ITEM]} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  const input = screen.getByLabelText('Descripción ES');
  fireEvent.change(input, { target: { value: 'Otro nombre' } });
  fireEvent.keyDown(input, { key: 'Enter' });

  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  const body = JSON.parse(mockAuthFetch.mock.calls[0][1].body);
  expect(body).toEqual({ description_es_manual: 'Otro nombre' });
});

test('Escape cancels without saving and reverts to the read-only display', () => {
  render(<EsCellWidget initialItems={[ITEM]} />);
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
  render(<EsCellWidget initialItems={[ITEM]} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  const input = screen.getByLabelText('Descripción ES');
  fireEvent.change(input, { target: { value: '   ' } });
  fireEvent.blur(input);

  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  const body = JSON.parse(mockAuthFetch.mock.calls[0][1].body);
  expect(body).toEqual({ description_es_manual: null });
});

test('a failed PATCH reverts the optimistic update and shows a toast', async () => {
  mockAuthFetch.mockResolvedValue({ ok: false, json: async () => ({ detail: 'nope' }) });
  render(<EsCellWidget initialItems={[ITEM]} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  const input = screen.getByLabelText('Descripción ES');
  fireEvent.change(input, { target: { value: 'Nombre fallido' } });
  fireEvent.blur(input);

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo guardar la descripción. Intentá de nuevo.'));
  // await (not a bare sync query) -- ensures the revert's setItems has fully
  // committed before this test hands control back to the runner. Without
  // this, the trailing state update can straggle into the NEXT test's
  // synchronous window and trigger a spurious act() warning there.
  expect(await screen.findByText('Pastilla de freno')).toBeInTheDocument();
  expect(screen.queryByText('Nombre fallido')).not.toBeInTheDocument();
});

test('a network error also reverts and shows a toast', async () => {
  mockAuthFetch.mockRejectedValue(new Error('network down'));
  render(<EsCellWidget initialItems={[ITEM]} />);
  fireEvent.click(screen.getByText('Pastilla de freno'));
  const input = screen.getByLabelText('Descripción ES');
  fireEvent.change(input, { target: { value: 'Otro' } });
  fireEvent.blur(input);

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo guardar la descripción. Intentá de nuevo.'));
  expect(await screen.findByText('Pastilla de freno')).toBeInTheDocument();
});

test('regression: row still renders factory number, description, and model', () => {
  render(<EsCellWidget initialItems={[ITEM]} />);
  expect(screen.getByText('FAB-001')).toBeInTheDocument();
  expect(screen.getByText('Brake pad')).toBeInTheDocument();
  expect(screen.getByText('Renegade 200')).toBeInTheDocument();
});

test('regression: rotation-class buttons still work', () => {
  render(<EsCellWidget initialItems={[ITEM]} />);
  const bajaBtn = screen.getByRole('button', { name: 'B' });
  fireEvent.click(bajaBtn);
  expect(bajaBtn).toHaveAttribute('aria-pressed', 'true');
});

describe('a part applying to multiple vehicle models (same factory_part_number, two rows) — matches AnalisisRepuestosTab exactly, including opening every matching row together', () => {
  const DUP_A = { ...ITEM, description_es: 'Pastilla A texto distinto', vehicle_model_name: 'Renegade 200', section_code: 'A1' };
  const DUP_B = { ...ITEM, description_es: 'Pastilla B texto distinto', vehicle_model_name: 'Renegade 300', section_code: 'B1' };

  test('clicking row A opens BOTH rows into edit mode (same accepted behavior as Ajuste de Pedidos — the edit state is keyed by the shared code, not by row)', () => {
    render(<EsCellWidget initialItems={[DUP_A, DUP_B]} />);
    fireEvent.click(screen.getByText('Pastilla A texto distinto'));
    expect(screen.getAllByLabelText('Descripción ES')).toHaveLength(2);
  });

  test('saving from one of the two open inputs propagates the new translation to BOTH rows', async () => {
    mockAuthFetch.mockResolvedValue({ ok: true });
    render(<EsCellWidget initialItems={[DUP_A, DUP_B]} />);
    fireEvent.click(screen.getByText('Pastilla A texto distinto'));

    const inputs = screen.getAllByLabelText('Descripción ES');
    expect(inputs).toHaveLength(2);
    fireEvent.change(inputs[0], { target: { value: 'Pastilla traducida' } });
    fireEvent.blur(inputs[0]);

    await waitFor(() => expect(mockAuthFetch).toHaveBeenCalledTimes(1));
    const body = JSON.parse(mockAuthFetch.mock.calls[0][1].body);
    expect(body).toEqual({ description_es_manual: 'Pastilla traducida' });
    expect(await screen.findAllByText('Pastilla traducida')).toHaveLength(2);
  });
});
