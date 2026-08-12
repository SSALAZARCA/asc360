/**
 * `CodeCandidateModal` -- superadmin resolution flow for a description edit
 * on an uncatalogued `part_number` (`sdd/parts-description-source-of-truth`
 * PR3, task 3.6, spec's "Not-Yet-Cataloged Code — Superadmin Path").
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));
jest.mock('../lib/toast', () => ({
  toast: { error: jest.fn(), success: jest.fn() },
}));

import CodeCandidateModal from '../components/imports/CodeCandidateModal';
import { toast } from '../lib/toast';

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  };
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  toast.error.mockReset();
  toast.success.mockReset();
});

describe('CodeCandidateModal', () => {
  it('fetches candidates scoped to the part_number and model_applicable on mount', async () => {
    mockAuthFetch.mockResolvedValue(makeResponse(200, []));
    render(
      <CodeCandidateModal
        partNumber="P1"
        modelApplicable="MODELX"
        pendingDescription="Filtro nuevo"
        onClose={jest.fn()}
        onResolved={jest.fn()}
      />
    );

    await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
    const url = mockAuthFetch.mock.calls[0][0];
    expect(url).toContain('/parts/admin/code-candidates');
    expect(url).toContain('part_number=P1');
    expect(url).toContain('model_applicable=MODELX');
  });

  it('shows an empty state when no candidates are found', async () => {
    mockAuthFetch.mockResolvedValue(makeResponse(200, []));
    render(
      <CodeCandidateModal partNumber="P1" modelApplicable="MODELX" pendingDescription="X" onClose={jest.fn()} onResolved={jest.fn()} />
    );
    expect(await screen.findByText(/No se encontraron repuestos similares/i)).toBeInTheDocument();
  });

  it('surfaces a fetch failure via toast and does not render the same message as an empty result', async () => {
    mockAuthFetch.mockRejectedValue(new Error('network down'));
    render(
      <CodeCandidateModal partNumber="P1" modelApplicable="MODELX" pendingDescription="X" onClose={jest.fn()} onResolved={jest.fn()} />
    );

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.queryByText(/No se encontraron repuestos similares/i)).not.toBeInTheDocument();
    expect(await screen.findByText(/No se pudieron buscar repuestos similares/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reintentar/i })).toBeInTheDocument();
  });

  it('surfaces a non-ok candidate-search response via toast, distinct from a genuine empty result', async () => {
    mockAuthFetch.mockResolvedValue(makeResponse(500, { detail: 'boom' }));
    render(
      <CodeCandidateModal partNumber="P1" modelApplicable="MODELX" pendingDescription="X" onClose={jest.fn()} onResolved={jest.fn()} />
    );

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.queryByText(/No se encontraron repuestos similares/i)).not.toBeInTheDocument();
    expect(await screen.findByText(/No se pudieron buscar repuestos similares/i)).toBeInTheDocument();
  });

  it('retries the candidate search when the retry button is clicked after a fetch failure', async () => {
    mockAuthFetch
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(makeResponse(200, []));
    render(
      <CodeCandidateModal partNumber="P1" modelApplicable="MODELX" pendingDescription="X" onClose={jest.fn()} onResolved={jest.fn()} />
    );

    await screen.findByText(/No se pudieron buscar repuestos similares/i);
    fireEvent.click(screen.getByRole('button', { name: /reintentar/i }));

    expect(await screen.findByText(/No se encontraron repuestos similares/i)).toBeInTheDocument();
    expect(mockAuthFetch).toHaveBeenCalledTimes(2);
  });

  it('renders candidates and links the chosen one after confirming, posting the pending description', async () => {
    mockAuthFetch.mockImplementation((url, opts) => {
      if (url.includes('/code-candidates?')) {
        return Promise.resolve(makeResponse(200, [
          { factory_part_number: 'FPN-2', description: 'Filtro viejo', description_es_manual: 'Filtro ES', similarity_score: 0.91 },
        ]));
      }
      if (url.includes('/code-candidates/link')) {
        return Promise.resolve(makeResponse(200, { ok: true, factory_part_number: 'P1' }));
      }
      return Promise.resolve(makeResponse(200, {}));
    });

    const onResolved = jest.fn();
    render(
      <CodeCandidateModal partNumber="P1" modelApplicable="MODELX" pendingDescription="Filtro nuevo" onClose={jest.fn()} onResolved={onResolved} />
    );

    await screen.findByText('FPN-2');
    fireEvent.click(screen.getByRole('button', { name: /vincular/i }));

    // Money-moving confirm step must appear before the POST fires
    expect(await screen.findByText(/Sí, vincular/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Sí, vincular/i));

    await waitFor(() => {
      const linkCall = mockAuthFetch.mock.calls.find(c => c[0].includes('/code-candidates/link'));
      expect(linkCall).toBeTruthy();
      const body = JSON.parse(linkCall[1].body);
      expect(body).toEqual({ part_number: 'P1', existing_code: 'FPN-2', description_es_manual: 'Filtro nuevo' });
    });

    await waitFor(() => expect(onResolved).toHaveBeenCalled());
  });

  it('creates a new orphan reference when there is no candidate to link', async () => {
    mockAuthFetch.mockImplementation((url) => {
      if (url.includes('/code-candidates?')) return Promise.resolve(makeResponse(200, []));
      if (url.includes('/code-candidates/create')) return Promise.resolve(makeResponse(200, { ok: true, factory_part_number: 'P1' }));
      return Promise.resolve(makeResponse(200, {}));
    });

    const onResolved = jest.fn();
    render(
      <CodeCandidateModal partNumber="P1" modelApplicable="MODELX" pendingDescription="Filtro nuevo" onClose={jest.fn()} onResolved={onResolved} />
    );

    await screen.findByText(/No se encontraron repuestos similares/i);
    fireEvent.click(screen.getByRole('button', { name: /crear código nuevo/i }));

    await waitFor(() => {
      const createCall = mockAuthFetch.mock.calls.find(c => c[0].includes('/code-candidates/create'));
      expect(createCall).toBeTruthy();
      const body = JSON.parse(createCall[1].body);
      expect(body).toEqual({ part_number: 'P1', description_es_manual: 'Filtro nuevo' });
    });

    await waitFor(() => expect(onResolved).toHaveBeenCalled());
  });

  it('surfaces a link failure via toast and keeps the modal open (onResolved not called)', async () => {
    mockAuthFetch.mockImplementation((url) => {
      if (url.includes('/code-candidates?')) {
        return Promise.resolve(makeResponse(200, [
          { factory_part_number: 'FPN-2', description: 'Filtro viejo', description_es_manual: null, similarity_score: 0.91 },
        ]));
      }
      if (url.includes('/code-candidates/link')) {
        return Promise.resolve(makeResponse(409, { detail: { detail: 'El código ya existe en el catálogo', code: 'CODE_ALREADY_EXISTS' } }));
      }
      return Promise.resolve(makeResponse(200, {}));
    });

    const onResolved = jest.fn();
    render(
      <CodeCandidateModal partNumber="P1" modelApplicable="MODELX" pendingDescription="X" onClose={jest.fn()} onResolved={onResolved} />
    );

    await screen.findByText('FPN-2');
    fireEvent.click(screen.getByRole('button', { name: /vincular/i }));
    fireEvent.click(await screen.findByText(/Sí, vincular/i));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('El código ya existe en el catálogo'));
    expect(onResolved).not.toHaveBeenCalled();
  });

  it('calls onClose when the cancel button is clicked', async () => {
    mockAuthFetch.mockResolvedValue(makeResponse(200, []));
    const onClose = jest.fn();
    render(
      <CodeCandidateModal partNumber="P1" modelApplicable="MODELX" pendingDescription="X" onClose={onClose} onResolved={jest.fn()} />
    );
    await screen.findByText(/No se encontraron repuestos similares/i);
    fireEvent.click(screen.getByRole('button', { name: /^cancelar$/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
