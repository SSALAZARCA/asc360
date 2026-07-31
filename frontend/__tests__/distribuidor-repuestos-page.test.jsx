/**
 * Tests for the new Distribuidor parts-search screen, introduced in:
 *   sdd/distributor-parts-search, Phase 4 (frontend, PR4)
 *
 * Mirrors `distribuidor-entrega-page.test.jsx`'s structure (mockAuthFetch +
 * queueResponses pattern, `admin-layout` mocked away).
 *
 * Backend contract (already landed, PR1/PR2 of this same change):
 *   GET  /parts/bot/catalog-models              -> [{ vehicle_model, catalog_model_code }]
 *   GET  /parts/model/{code}/all-sections        -> [{ section_id, section_code, section_name, diagram_url }]
 *   POST /parts/search-by-model                  -> [{ section_id, section_code, section_name, diagram_url, model_code }]
 *   GET  /parts/section/{id}/diagram-image       -> binary (blob)
 *   GET  /parts/section/{id}/items                -> [PartItemResult, ...] natural-sorted by order_num
 *
 * Covers:
 *   - Selecting a model populates and lists its sections.
 *   - Opening a section renders the diagram AND the full N-row item list,
 *     in `order_num` order, in the SAME view (two panels).
 *   - A null-`precio_publico` row shows "Sin precio", never `$0` (same hard
 *     rule as PR3's `/tg/parts` row).
 *   - A non-null price renders currency-formatted.
 *   - Text search, voice search, and photo search all resolve through the
 *     existing `POST /parts/search-by-model` contract unchanged.
 *   - No add/request/quote control anywhere on the screen (explicit
 *     non-goal, spec requirement).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));

jest.mock('../app/admin-layout', () => {
  const MockAdminLayout = ({ children }) => <div>{children}</div>;
  MockAdminLayout.displayName = 'MockAdminLayout';
  return MockAdminLayout;
});

// Shallow mocks that still expose the callback props, so voice/photo search
// can be driven from a test the same way a real tap/photo would.
jest.mock('../components/tg/VoiceInput', () => {
  const MockVoiceInput = ({ onTranscript }) => (
    <button type="button" data-testid="voice-input" onClick={() => onTranscript('bujía')}>
      voice
    </button>
  );
  MockVoiceInput.displayName = 'MockVoiceInput';
  return MockVoiceInput;
});
jest.mock('../components/tg/CameraInput', () => {
  const MockCameraInput = ({ onResult }) => (
    <button type="button" data-testid="camera-input" onClick={() => onResult({ description: 'freno trasero' })}>
      camera
    </button>
  );
  MockCameraInput.displayName = 'MockCameraInput';
  return MockCameraInput;
});

import DistribuidorRepuestosPage from '../app/distribuidor/repuestos/page';

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
    blob: jest.fn().mockResolvedValue(new Blob(['fake-bytes'], { type: 'image/png' })),
  };
}

const MODELS = [{ catalog_model_code: 'DSR150', vehicle_model: 'DSR 150' }];
const SECTION = {
  section_id: 'sec-1',
  section_code: 'A',
  section_name: 'Motor',
  diagram_url: 'https://minio.example/diagram-a.png',
};

const ITEMS = [
  {
    id: 'item-1', section_id: 'sec-1', section_code: 'A', section_name: 'Motor',
    order_num: 'A1', factory_part_number: 'FP-001', um_part_number: 'UM-001',
    description: 'Tornillo', description_es: null, unit: 'UND',
    precio_publico: 45000, precio_es_preliminar: false,
  },
  {
    id: 'item-2', section_id: 'sec-1', section_code: 'A', section_name: 'Motor',
    order_num: 'A2', factory_part_number: 'FP-002', um_part_number: null,
    description: null, description_es: null, unit: null,
    precio_publico: null, precio_es_preliminar: false,
  },
];

let mockItems = ITEMS;

function queueResponses() {
  mockAuthFetch.mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/parts/bot/catalog-models')) {
      return Promise.resolve(makeResponse(200, MODELS));
    }
    if (typeof url === 'string' && url.includes('/all-sections')) {
      return Promise.resolve(makeResponse(200, [SECTION]));
    }
    if (typeof url === 'string' && url === '/parts/search-by-model') {
      return Promise.resolve(makeResponse(200, [SECTION]));
    }
    if (typeof url === 'string' && url.includes('/diagram-image')) {
      return Promise.resolve(makeResponse(200, {}));
    }
    if (typeof url === 'string' && /\/parts\/section\/[^/]+\/items$/.test(url)) {
      return Promise.resolve(makeResponse(200, mockItems));
    }
    return Promise.resolve(makeResponse(200, {}));
  });
}

function setUser(role = 'parts_dealer') {
  sessionStorage.setItem('um_user', JSON.stringify({ name: 'Test User', role }));
  sessionStorage.setItem('um_token', 'fake-token');
}

async function selectModelAndOpenSection() {
  await waitFor(() => {
    expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
  });
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'DSR150' } });

  await waitFor(() => {
    expect(screen.getByText('Motor')).toBeInTheDocument();
  });
  fireEvent.click(screen.getByText('Motor'));
}

let originalCreateObjectURL;

beforeEach(() => {
  mockAuthFetch.mockReset();
  sessionStorage.clear();
  mockItems = ITEMS;
  originalCreateObjectURL = global.URL.createObjectURL;
  global.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
});

afterEach(() => {
  global.URL.createObjectURL = originalCreateObjectURL;
});

describe('DistribuidorRepuestosPage — model/section browse flow', () => {
  it('selecting a model lists its sections', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();
    // Reaching this assert proves the section click was actionable -- both
    // the list row and the opened detail heading now show "Motor".
    expect(screen.getAllByText('Motor').length).toBeGreaterThan(0);
  });

  it('opening a section renders the diagram and the full item list in order_num order', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();

    await waitFor(() => {
      expect(screen.getByText('FP-001')).toBeInTheDocument();
    });
    expect(screen.getByText('FP-002')).toBeInTheDocument();

    const rows = [screen.getByText('FP-001'), screen.getByText('FP-002')];
    const positions = rows.map((el) => el.compareDocumentPosition(rows[rows.length - 1]));
    // FP-001 (A1) must precede FP-002 (A2) in the document.
    // eslint-disable-next-line no-bitwise
    expect(positions[0] & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    const img = screen.getByAltText('Motor');
    expect(img).toBeInTheDocument();
  });

  it('a null-price row shows "Sin precio", never $0', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();

    await waitFor(() => {
      expect(screen.getByText('FP-002')).toBeInTheDocument();
    });
    const row2 = screen.getByText('FP-002').closest('tr') || screen.getByText('FP-002').parentElement.parentElement;
    expect(within(row2).getByText(/sin precio/i)).toBeInTheDocument();
    expect(within(row2).queryByText('$0')).not.toBeInTheDocument();
  });

  it('a priced row renders precio_publico formatted as currency', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();

    await waitFor(() => {
      expect(screen.getByText('FP-001')).toBeInTheDocument();
    });
    const row1 = screen.getByText('FP-001').closest('tr') || screen.getByText('FP-001').parentElement.parentElement;
    expect(within(row1).getByText(/\$\s?45[.,]000/)).toBeInTheDocument();
  });
});

describe('DistribuidorRepuestosPage — AI description search (text/voice/photo)', () => {
  it('text search returns sections via POST /parts/search-by-model unchanged', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
    });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'DSR150' } });
    await waitFor(() => screen.getByText('Motor'));

    fireEvent.click(screen.getByRole('button', { name: /por descripción/i }));
    fireEvent.change(screen.getByPlaceholderText(/bujía|freno/i), { target: { value: 'bujía' } });
    fireEvent.click(screen.getByRole('button', { name: /buscar/i }));

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        '/parts/search-by-model',
        expect.objectContaining({ method: 'POST' })
      );
    });
    const call = mockAuthFetch.mock.calls.find(([url]) => url === '/parts/search-by-model');
    expect(JSON.parse(call[1].body)).toEqual({ model_code: 'DSR150', description: 'bujía' });
  });

  it('voice search fires the same search-by-model contract', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
    });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'DSR150' } });
    await waitFor(() => screen.getByText('Motor'));

    fireEvent.click(screen.getByRole('button', { name: /por descripción/i }));
    fireEvent.click(screen.getByTestId('voice-input'));

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        '/parts/search-by-model',
        expect.objectContaining({ method: 'POST' })
      );
    });
    const call = mockAuthFetch.mock.calls.find(([url]) => url === '/parts/search-by-model');
    expect(JSON.parse(call[1].body)).toEqual({ model_code: 'DSR150', description: 'bujía' });
  });

  it('photo search fires the same search-by-model contract', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
    });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'DSR150' } });
    await waitFor(() => screen.getByText('Motor'));

    fireEvent.click(screen.getByRole('button', { name: /por descripción/i }));
    fireEvent.click(screen.getByTestId('camera-input'));

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        '/parts/search-by-model',
        expect.objectContaining({ method: 'POST' })
      );
    });
    const call = mockAuthFetch.mock.calls.find(([url]) => url === '/parts/search-by-model');
    expect(JSON.parse(call[1].body)).toEqual({ model_code: 'DSR150', description: 'freno trasero' });
  });
});

describe('DistribuidorRepuestosPage — non-goals', () => {
  it('has no add/request/quote control anywhere on the screen', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();
    await waitFor(() => {
      expect(screen.getByText('FP-001')).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: /agregar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /solicitar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /enviar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /cotiza/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /carrito/i })).not.toBeInTheDocument();
  });
});

describe('DistribuidorRepuestosPage — network failures surface an error, not a silent empty state', () => {
  it('shows an error message when the catalog-models request fails', async () => {
    setUser();
    mockAuthFetch.mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/parts/bot/catalog-models')) {
        return Promise.resolve(makeResponse(500, null));
      }
      return Promise.resolve(makeResponse(200, {}));
    });
    render(<DistribuidorRepuestosPage />);

    await waitFor(() => {
      expect(screen.getByText(/no se pudieron cargar los modelos/i)).toBeInTheDocument();
    });
  });

  it('shows an error message when the diagram-image request fails', async () => {
    setUser();
    mockAuthFetch.mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/parts/bot/catalog-models')) {
        return Promise.resolve(makeResponse(200, MODELS));
      }
      if (typeof url === 'string' && url.includes('/all-sections')) {
        return Promise.resolve(makeResponse(200, [SECTION]));
      }
      if (typeof url === 'string' && url.includes('/diagram-image')) {
        return Promise.resolve(makeResponse(500, null));
      }
      if (typeof url === 'string' && /\/parts\/section\/[^/]+\/items$/.test(url)) {
        return Promise.resolve(makeResponse(200, mockItems));
      }
      return Promise.resolve(makeResponse(200, {}));
    });
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();

    await waitFor(() => {
      expect(screen.getByText(/no se pudo cargar el diagrama/i)).toBeInTheDocument();
    });
  });

  it('shows an error message when the section-items request fails', async () => {
    setUser();
    mockAuthFetch.mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/parts/bot/catalog-models')) {
        return Promise.resolve(makeResponse(200, MODELS));
      }
      if (typeof url === 'string' && url.includes('/all-sections')) {
        return Promise.resolve(makeResponse(200, [SECTION]));
      }
      if (typeof url === 'string' && url.includes('/diagram-image')) {
        return Promise.resolve(makeResponse(200, {}));
      }
      if (typeof url === 'string' && /\/parts\/section\/[^/]+\/items$/.test(url)) {
        return Promise.resolve(makeResponse(500, null));
      }
      return Promise.resolve(makeResponse(200, {}));
    });
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();

    await waitFor(() => {
      expect(screen.getByText(/no se pudieron cargar las piezas/i)).toBeInTheDocument();
    });
  });

  it('shows an error message when the model-sections request fails', async () => {
    setUser();
    mockAuthFetch.mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/parts/bot/catalog-models')) {
        return Promise.resolve(makeResponse(200, MODELS));
      }
      if (typeof url === 'string' && url.includes('/all-sections')) {
        return Promise.resolve(makeResponse(500, null));
      }
      return Promise.resolve(makeResponse(200, {}));
    });
    render(<DistribuidorRepuestosPage />);

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
    });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'DSR150' } });

    await waitFor(() => {
      expect(screen.getByText(/no se pudieron cargar las secciones/i)).toBeInTheDocument();
    });
  });
});
