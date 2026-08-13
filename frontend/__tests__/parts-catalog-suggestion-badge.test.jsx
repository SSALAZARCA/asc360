/**
 * Tests for the unconfirmed-name suggestion badge in
 * frontend/app/parts-catalog/page.js (`sdd/parts-description-source-of-truth`
 * PR5, design D19-D22, task 5.10; PR5 post-review fix pass findings #7/#8).
 *
 * Same isolation technique as `parts-catalog-es-inline-edit.test.jsx`: the
 * page is a 1300+ line monolith with 5+ parallel useEffect fetches on mount
 * -- this test exercises a verbatim copy of the badge button, the
 * pending_task_id badge (for the visual-distinction check), the confirm/
 * dismiss MODAL markup+handlers, and the `onlySuggested` filter toggle,
 * inside a minimal widget instead of mounting the whole page.
 *
 * Fix #8 (pure rename): the implementation is a full modal (fixed overlay +
 * centered panel, the same pattern the sibling `reviewTask` modal uses), not
 * an anchored CSS popover -- a disclosed, reasonable deviation from the
 * design's original "popover" wording. Test names/comments say "modal" now
 * so they don't mislead a future maintainer about the UI shape being
 * tested.
 *
 * Fix #7: `confirmSuggestion`/`dismissSuggestion` now show IN-MODAL
 * success/failure feedback, matching the sibling `reviewTask` modal's
 * `handleReviewAction` pattern (success message + auto-close after
 * ~1200ms; failure message + modal stays open) -- no `toast` calls, same
 * as `handleReviewAction`.
 */
import React, { useState, useCallback, useEffect } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));

// === SuggestionWidget — verbatim copy of the relevant state/handlers/
// markup from frontend/app/parts-catalog/page.js ===
function SuggestionWidget({ initialItems }) {
  const [items, setItems] = useState(initialItems);
  const [page, setPage] = useState(1);
  const [onlySuggested, setOnlySuggested] = useState(false);
  const [suggestion, setSuggestion] = useState(null); // { fpn, text, sourceCode }
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [suggestionMsg, setSuggestionMsg] = useState('');

  const fetchData = useCallback(async () => {
    const params = new URLSearchParams({
      page: String(page),
      only_suggested: String(onlySuggested),
    });
    const res = await mockAuthFetch(`/parts/admin/catalog?${params}`);
    if (res?.ok) {
      const data = await res.json();
      setItems(data.items || []);
    }
  }, [page, onlySuggested]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const confirmSuggestion = async () => {
    if (!suggestion) return;
    setSuggestionLoading(true);
    setSuggestionMsg('');
    try {
      const res = await mockAuthFetch(`/parts/admin/catalog-confirm-suggestion/${encodeURIComponent(suggestion.fpn)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suggested_text: suggestion.text }),
      });
      if (res.ok) {
        setSuggestionMsg('✅ Nombre confirmado.');
        setTimeout(() => { setSuggestion(null); fetchData(); }, 1200);
      } else {
        const data = await res.json().catch(() => ({}));
        setSuggestionMsg(data?.detail?.code === 'SUGGESTION_STALE'
          ? '⚠️ La sugerencia cambió, recargá la lista.'
          : '⚠️ No se pudo confirmar la sugerencia.');
      }
    } catch {
      setSuggestionMsg('⚠️ Error de conexión.');
    } finally {
      setSuggestionLoading(false);
    }
  };

  const dismissSuggestion = async () => {
    if (!suggestion) return;
    setSuggestionLoading(true);
    setSuggestionMsg('');
    try {
      const res = await mockAuthFetch(`/parts/admin/catalog-dismiss-suggestion/${encodeURIComponent(suggestion.fpn)}`, {
        method: 'POST',
      });
      if (res.ok) {
        setSuggestionMsg('✅ Sugerencia descartada.');
        setTimeout(() => { setSuggestion(null); fetchData(); }, 1200);
      } else {
        const data = await res.json().catch(() => ({}));
        setSuggestionMsg(data?.detail?.code === 'NO_ACTIVE_SUGGESTION'
          ? '⚠️ Ya no hay una sugerencia activa para descartar.'
          : '⚠️ No se pudo descartar la sugerencia.');
      }
    } catch {
      setSuggestionMsg('⚠️ Error de conexión.');
    } finally {
      setSuggestionLoading(false);
    }
  };

  return (
    <div>
      <button
        onClick={() => { setOnlySuggested(p => !p); setPage(1); }}
      >
        {onlySuggested ? 'Mostrando sin confirmar' : 'Sin confirmar'}
      </button>
      <table>
        <tbody>
          {items.map(item => (
            <tr key={item.factory_part_number}>
              <td>{item.factory_part_number}</td>
              <td>
                {item.has_unconfirmed_suggestion && (
                  <button
                    onClick={() => { setSuggestionMsg(''); setSuggestion({ fpn: item.factory_part_number, text: item.description_es, sourceCode: item.suggestion_source_code }); }}
                    title="Nombre sin confirmar — sugerido de pedidos anteriores"
                  >
                    bulb
                  </button>
                )}
                {item.pending_task_id && (
                  <button title="Verificar posible cambio de código">triangle</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {suggestion && (
        <div role="dialog">
          <p>
            Encontramos &quot;{suggestion.text}&quot; usado en pedidos anteriores para este código — ¿Confirmar como nombre oficial?
          </p>
          {suggestion.sourceCode && suggestion.sourceCode !== suggestion.fpn && (
            <p>Encontrado bajo el código anterior: <strong>{suggestion.sourceCode}</strong></p>
          )}
          {suggestionMsg && <p>{suggestionMsg}</p>}
          <button onClick={confirmSuggestion} disabled={suggestionLoading}>Confirmar</button>
          <button onClick={dismissSuggestion} disabled={suggestionLoading}>Descartar</button>
        </div>
      )}
    </div>
  );
}

const ITEM = {
  factory_part_number: 'FPN-1',
  description_es: 'Filtro de aceite',
  has_unconfirmed_suggestion: true,
  suggestion_source_code: 'FPN-1',
  pending_task_id: null,
};

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockAuthFetch.mockResolvedValue({ ok: true, json: async () => ({ items: [], total: 0 }) });
});

// The widget's mount `useEffect` calls `fetchData` immediately (same as the
// real page). Default the mock to echo the SAME items back so that
// resolving the mount fetch doesn't clobber `initialItems` with an empty
// list before the test gets a chance to interact with the row.
function renderWidget(items) {
  mockAuthFetch.mockResolvedValue({ ok: true, json: async () => ({ items, total: items.length }) });
  return render(<SuggestionWidget initialItems={items} />);
}

test('bulb renders only when has_unconfirmed_suggestion is true', async () => {
  renderWidget([ITEM, { ...ITEM, factory_part_number: 'FPN-2', has_unconfirmed_suggestion: false }]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  expect(screen.getAllByTitle('Nombre sin confirmar — sugerido de pedidos anteriores')).toHaveLength(1);
});

test('bulb and the code-change badge are visually distinct (different titles) when both present on one row', async () => {
  renderWidget([{ ...ITEM, pending_task_id: 'task-1' }]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  expect(screen.getByTitle('Nombre sin confirmar — sugerido de pedidos anteriores')).toBeInTheDocument();
  expect(screen.getByTitle('Verificar posible cambio de código')).toBeInTheDocument();
});

test('clicking the bulb opens a modal with the suggested text', async () => {
  renderWidget([ITEM]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  fireEvent.click(screen.getByTitle('Nombre sin confirmar — sugerido de pedidos anteriores'));
  expect(screen.getByRole('dialog')).toHaveTextContent('Filtro de aceite');
});

test('the source-code line is shown only when suggestion_source_code differs from the fpn (alias case)', async () => {
  renderWidget([{ ...ITEM, suggestion_source_code: 'OLD-CODE' }]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  fireEvent.click(screen.getByTitle('Nombre sin confirmar — sugerido de pedidos anteriores'));
  expect(screen.getByText('OLD-CODE')).toBeInTheDocument();
});

test('the source-code line is hidden when suggestion_source_code equals the fpn (exact-code case)', async () => {
  renderWidget([ITEM]); // sourceCode === fpn
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  fireEvent.click(screen.getByTitle('Nombre sin confirmar — sugerido de pedidos anteriores'));
  expect(screen.queryByText(/Encontrado bajo el código anterior/)).not.toBeInTheDocument();
});

test('Confirmar POSTs to catalog-confirm-suggestion with the encoded fpn and suggested_text, shows in-modal success, then refetches and auto-closes', async () => {
  renderWidget([ITEM]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  fireEvent.click(screen.getByTitle('Nombre sin confirmar — sugerido de pedidos anteriores'));

  mockAuthFetch.mockResolvedValueOnce({ ok: true }); // confirm POST
  mockAuthFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ items: [], total: 0 }) }); // refetch
  fireEvent.click(screen.getByText('Confirmar'));

  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalledWith(
    '/parts/admin/catalog-confirm-suggestion/FPN-1',
    expect.objectContaining({ method: 'POST' }),
  ));
  const call = mockAuthFetch.mock.calls.find(c => c[0] === '/parts/admin/catalog-confirm-suggestion/FPN-1');
  expect(JSON.parse(call[1].body)).toEqual({ suggested_text: 'Filtro de aceite' });

  // in-modal success feedback shown immediately, modal still open
  await waitFor(() => expect(screen.getByText('✅ Nombre confirmado.')).toBeInTheDocument());

  // auto-closes (and a refetch is triggered) after the ~1200ms timeout
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument(), { timeout: 3000 });
});

test('Descartar POSTs to catalog-dismiss-suggestion, shows in-modal success, then refetches and auto-closes', async () => {
  renderWidget([ITEM]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  fireEvent.click(screen.getByTitle('Nombre sin confirmar — sugerido de pedidos anteriores'));

  mockAuthFetch.mockResolvedValueOnce({ ok: true }); // dismiss POST
  mockAuthFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ items: [], total: 0 }) }); // refetch
  fireEvent.click(screen.getByText('Descartar'));

  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalledWith(
    '/parts/admin/catalog-dismiss-suggestion/FPN-1',
    expect.objectContaining({ method: 'POST' }),
  ));

  await waitFor(() => expect(screen.getByText('✅ Sugerencia descartada.')).toBeInTheDocument());
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument(), { timeout: 3000 });
});

test('a 409 SUGGESTION_STALE response shows an in-modal failure message and keeps the modal open (badge stays)', async () => {
  renderWidget([ITEM]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  fireEvent.click(screen.getByTitle('Nombre sin confirmar — sugerido de pedidos anteriores'));

  mockAuthFetch.mockResolvedValueOnce({
    ok: false,
    json: async () => ({ detail: { code: 'SUGGESTION_STALE', detail: 'stale' } }),
  });
  fireEvent.click(screen.getByText('Confirmar'));

  await waitFor(() => expect(screen.getByText('⚠️ La sugerencia cambió, recargá la lista.')).toBeInTheDocument());
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test('a 409 NO_ACTIVE_SUGGESTION response on dismiss shows an in-modal failure message and keeps the modal open', async () => {
  renderWidget([ITEM]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  fireEvent.click(screen.getByTitle('Nombre sin confirmar — sugerido de pedidos anteriores'));

  mockAuthFetch.mockResolvedValueOnce({
    ok: false,
    json: async () => ({ detail: { code: 'NO_ACTIVE_SUGGESTION', detail: 'nothing to dismiss' } }),
  });
  fireEvent.click(screen.getByText('Descartar'));

  await waitFor(() => expect(screen.getByText('⚠️ Ya no hay una sugerencia activa para descartar.')).toBeInTheDocument());
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test('a network failure on confirm shows an in-modal failure message and keeps the modal open', async () => {
  renderWidget([ITEM]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  fireEvent.click(screen.getByTitle('Nombre sin confirmar — sugerido de pedidos anteriores'));

  mockAuthFetch.mockRejectedValueOnce(new Error('network down'));
  fireEvent.click(screen.getByText('Confirmar'));

  await waitFor(() => expect(screen.getByText('⚠️ Error de conexión.')).toBeInTheDocument());
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test('a network failure on dismiss shows an in-modal failure message and keeps the modal open', async () => {
  renderWidget([ITEM]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  fireEvent.click(screen.getByTitle('Nombre sin confirmar — sugerido de pedidos anteriores'));

  mockAuthFetch.mockRejectedValueOnce(new Error('network down'));
  fireEvent.click(screen.getByText('Descartar'));

  await waitFor(() => expect(screen.getByText('⚠️ Error de conexión.')).toBeInTheDocument());
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test('the filter toggle flips only_suggested in the fetch query string and resets the page', async () => {
  renderWidget([ITEM]);
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  mockAuthFetch.mockClear();

  fireEvent.click(screen.getByText('Sin confirmar'));

  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  const [url] = mockAuthFetch.mock.calls[0];
  expect(url).toContain('only_suggested=true');
  expect(url).toContain('page=1');
  expect(screen.getByText('Mostrando sin confirmar')).toBeInTheDocument();
});
