/**
 * Tests for the catalog upload state machine introduced in:
 *   fix(catalog): prevent data loss on section re-upload
 *
 * Covers:
 *   - 409 response → warn_exists row with "Sobreescribir" button
 *   - Clicking "Sobreescribir" retries with force=true → success
 *   - 422 response → error row
 *   - Happy-path upload → ok row with parts count
 *
 * The upload logic (handleCatUpload / handleForceUpload) lives inside the
 * SettingsPage monolith. Rather than rendering 1400 lines of component with
 * 10+ async side-effects, we test the same state machine in a minimal
 * CatalogUploadWidget that contains the EXACT same handler code copied
 * verbatim. Any deviation from the production handlers is a test bug.
 */
import React, { useState, useRef } from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

// ---------------------------------------------------------------------------
// Mock authFetch at the module level
// ---------------------------------------------------------------------------
const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));

// Import after mock is registered
import { authFetch } from '../lib/authFetch';

// ---------------------------------------------------------------------------
// Minimal widget — exact copy of the relevant handlers from SettingsPage
// ---------------------------------------------------------------------------
function CatalogUploadWidget({ modelCode = 'renegade_200', vehicleModel = 'Renegade 200' }) {
  const [catFiles, setCatFiles] = useState([]);
  const [catResults, setCatResults] = useState([]);
  const [catLoading, setCatLoading] = useState(false);
  const catFileRef = useRef();

  // === handleCatUpload — copied verbatim from settings/page.js ===
  const handleCatUpload = async () => {
    if (!modelCode.trim() || !vehicleModel || catFiles.length === 0) return;
    setCatLoading(true);
    setCatResults([]);
    const newResults = [];
    for (let i = 0; i < catFiles.length; i++) {
      const file = catFiles[i];
      const fd = new FormData();
      fd.append('pdf_file', file);
      fd.append('model_code', modelCode.trim());
      fd.append('vehicle_model', vehicleModel);
      try {
        const res = await authFetch('/parts/admin/load-section', { method: 'POST', body: fd });
        if (res.ok) {
          const data = await res.json();
          newResults.push({ filename: file.name, status: 'ok', ...data });
        } else if (res.status === 409) {
          const err = await res.json().catch(() => ({}));
          const detail = typeof err.detail === 'object' ? err.detail : {};
          newResults.push({
            filename: file.name,
            status: 'warn_exists',
            existing_parts: detail.existing_parts || 0,
            section_code: detail.section_code || '',
          });
        } else {
          const err = await res.json().catch(() => ({ detail: 'Error desconocido' }));
          const msg = typeof err.detail === 'object' ? err.detail.message : err.detail;
          newResults.push({ filename: file.name, status: 'error', error: msg || 'Error desconocido' });
        }
      } catch (e) {
        newResults.push({ filename: file.name, status: 'error', error: e.message });
      }
      setCatResults([...newResults]);
    }
    setCatLoading(false);
  };

  // === handleForceUpload — copied verbatim from settings/page.js ===
  const handleForceUpload = async (filename) => {
    const file = catFiles.find(f => f.name === filename);
    if (!file) return;
    setCatResults(prev => prev.map(r => r.filename === filename ? { ...r, status: 'loading' } : r));
    const fd = new FormData();
    fd.append('pdf_file', file);
    fd.append('model_code', modelCode.trim());
    fd.append('vehicle_model', vehicleModel);
    fd.append('force', 'true');
    try {
      const res = await authFetch('/parts/admin/load-section', { method: 'POST', body: fd });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setCatResults(prev => prev.map(r => r.filename === filename ? { filename, status: 'ok', ...data } : r));
      } else {
        const msg = typeof data.detail === 'object' ? data.detail.message : data.detail;
        setCatResults(prev => prev.map(r => r.filename === filename ? { filename, status: 'error', error: msg || 'Error desconocido' } : r));
      }
    } catch (e) {
      setCatResults(prev => prev.map(r => r.filename === filename ? { filename, status: 'error', error: e.message } : r));
    }
  };

  const handleFiles = (e) => {
    const selected = Array.from(e.target.files).filter(f => f.name.endsWith('.pdf'));
    setCatFiles(selected);
    setCatResults([]);
  };

  return (
    <div>
      <input
        ref={catFileRef}
        type="file"
        data-testid="file-input"
        multiple
        accept=".pdf"
        onChange={handleFiles}
        style={{ display: 'none' }}
      />
      <button
        data-testid="upload-btn"
        onClick={handleCatUpload}
        disabled={catLoading || catFiles.length === 0}
      >
        {catLoading ? 'Cargando...' : `Cargar ${catFiles.length} PDF(s)`}
      </button>

      {catFiles.map((f) => {
        const result = catResults.find(r => r.filename === f.name);
        const isWarn = result?.status === 'warn_exists';
        return (
          <div key={f.name} data-testid={`file-row-${f.name}`}>
            <span>{f.name}</span>
            {result?.status === 'ok' && (
              <span data-testid={`ok-${f.name}`}>✓ {result.parts_loaded} items</span>
            )}
            {result?.status === 'error' && (
              <span data-testid={`error-${f.name}`}>✗ {result.error}</span>
            )}
            {result?.status === 'loading' && (
              <span data-testid={`loading-${f.name}`}>Cargando...</span>
            )}
            {isWarn && (
              <div data-testid={`warn-${f.name}`}>
                <span>{result.existing_parts} partes existentes</span>
                <button
                  data-testid={`overwrite-${f.name}`}
                  onClick={() => handleForceUpload(f.name)}
                >
                  Sobreescribir
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  };
}

function selectFiles(files) {
  const input = screen.getByTestId('file-input');
  Object.defineProperty(input, 'files', {
    value: files,
    writable: false,
    configurable: true,
  });
  fireEvent.change(input);
}

function makeFile(name = 'MODEL_B01_FRAME.pdf') {
  return new File(['%PDF-content'], name, { type: 'application/pdf' });
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockAuthFetch.mockReset();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('catalog upload — 409 conflict flow', () => {

  it('shows Sobreescribir button when server returns 409', async () => {
    mockAuthFetch.mockResolvedValue(
      makeResponse(409, {
        detail: {
          code: 'section_exists',
          existing_parts: 12,
          section_code: 'B01',
          message: 'La sección B01 ya tiene 12 partes.',
        },
      })
    );

    render(<CatalogUploadWidget />);

    selectFiles([makeFile('MODEL_B01_FRAME.pdf')]);
    fireEvent.click(screen.getByTestId('upload-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('warn-MODEL_B01_FRAME.pdf')).toBeInTheDocument();
    });

    expect(screen.getByText('12 partes existentes')).toBeInTheDocument();
    expect(screen.getByTestId('overwrite-MODEL_B01_FRAME.pdf')).toBeInTheDocument();
  });

  it('retries with force=true when Sobreescribir is clicked and shows ok on success', async () => {
    mockAuthFetch
      .mockResolvedValueOnce(
        makeResponse(409, {
          detail: { code: 'section_exists', existing_parts: 5, section_code: 'B01' },
        })
      )
      .mockResolvedValueOnce(
        makeResponse(200, { parts_loaded: 8, references_new: 2 })
      );

    render(<CatalogUploadWidget />);

    selectFiles([makeFile('MODEL_B01_FRAME.pdf')]);
    fireEvent.click(screen.getByTestId('upload-btn'));

    await waitFor(() => screen.getByTestId('overwrite-MODEL_B01_FRAME.pdf'));

    fireEvent.click(screen.getByTestId('overwrite-MODEL_B01_FRAME.pdf'));

    await waitFor(() => {
      expect(screen.getByTestId('ok-MODEL_B01_FRAME.pdf')).toBeInTheDocument();
    });

    expect(screen.getByText(/8 items/)).toBeInTheDocument();

    // Second call must include force=true in the FormData
    const [, forceOptions] = mockAuthFetch.mock.calls[1];
    const forceBody = forceOptions.body;
    expect(forceBody.get('force')).toBe('true');
  });

  it('leaves other files unaffected when only one returns 409', async () => {
    mockAuthFetch
      .mockResolvedValueOnce(makeResponse(200, { parts_loaded: 3, references_new: 1 }))
      .mockResolvedValueOnce(
        makeResponse(409, {
          detail: { code: 'section_exists', existing_parts: 7, section_code: 'B02' },
        })
      );

    render(<CatalogUploadWidget />);

    selectFiles([makeFile('MODEL_B01_FRAME.pdf'), makeFile('MODEL_B02_ENGINE.pdf')]);
    fireEvent.click(screen.getByTestId('upload-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('ok-MODEL_B01_FRAME.pdf')).toBeInTheDocument();
      expect(screen.getByTestId('warn-MODEL_B02_ENGINE.pdf')).toBeInTheDocument();
    });
  });
});

describe('catalog upload — error flow', () => {

  it('shows error message when server returns 422 (no parts in PDF)', async () => {
    mockAuthFetch.mockResolvedValue(
      makeResponse(422, { detail: 'No se detectaron partes en MODEL_B01_FRAME.pdf' })
    );

    render(<CatalogUploadWidget />);

    selectFiles([makeFile('MODEL_B01_FRAME.pdf')]);
    fireEvent.click(screen.getByTestId('upload-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('error-MODEL_B01_FRAME.pdf')).toBeInTheDocument();
    });

    expect(screen.getByText(/No se detectaron partes/)).toBeInTheDocument();
  });

  it('shows error message on network failure', async () => {
    mockAuthFetch.mockRejectedValue(new Error('Network error'));

    render(<CatalogUploadWidget />);

    selectFiles([makeFile('MODEL_B01_FRAME.pdf')]);
    fireEvent.click(screen.getByTestId('upload-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('error-MODEL_B01_FRAME.pdf')).toBeInTheDocument();
    });

    expect(screen.getByText(/Network error/)).toBeInTheDocument();
  });
});

describe('catalog upload — happy path', () => {

  it('shows parts count on successful upload', async () => {
    mockAuthFetch.mockResolvedValue(
      makeResponse(200, { parts_loaded: 15, references_new: 3 })
    );

    render(<CatalogUploadWidget />);

    selectFiles([makeFile('MODEL_B01_FRAME.pdf')]);
    fireEvent.click(screen.getByTestId('upload-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('ok-MODEL_B01_FRAME.pdf')).toBeInTheDocument();
    });

    expect(screen.getByText(/15 items/)).toBeInTheDocument();
  });

  it('does not show Sobreescribir button on successful upload', async () => {
    mockAuthFetch.mockResolvedValue(
      makeResponse(200, { parts_loaded: 7, references_new: 0 })
    );

    render(<CatalogUploadWidget />);

    selectFiles([makeFile('MODEL_B01_FRAME.pdf')]);
    fireEvent.click(screen.getByTestId('upload-btn'));

    await waitFor(() => screen.getByTestId('ok-MODEL_B01_FRAME.pdf'));

    expect(screen.queryByTestId('overwrite-MODEL_B01_FRAME.pdf')).not.toBeInTheDocument();
    expect(screen.queryByTestId('warn-MODEL_B01_FRAME.pdf')).not.toBeInTheDocument();
  });
});
