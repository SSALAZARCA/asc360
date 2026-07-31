/**
 * Tests for the Distribuidor parts-search screen, introduced in:
 *   sdd/distributor-parts-search, Phase 4 (frontend, PR4)
 *
 * Structure rewritten 2026-07-31 to match the user's reference prototype
 * (`/mnt/c/proyectos IA/Pagina Servicio/repuestos.html`) more closely:
 *   - "1. Motocicleta" + "2. Sistema / Sección" are two ALWAYS-VISIBLE
 *     `<select>` elements (the second disabled until a model is chosen),
 *     not a select + a clickable list of rows.
 *   - The two-panel workspace (diagram left, parts list right) is ALWAYS
 *     rendered, with its own empty/loading/error state per panel — never a
 *     block that only appears after a section is picked.
 *   - Parts render as numbered-badge CARDS (`data-testid="part-card-{id}"`),
 *     not table rows.
 *   - "Por Descripción" (AI search) is an additional tab, not present in the
 *     prototype, kept separate so it never disturbs the Por Modelo structure.
 *
 * Mirrors `distribuidor-entrega-page.test.jsx`'s mockAuthFetch/queueResponses
 * pattern (`admin-layout` mocked away).
 *
 * Backend contract (already landed, PR1/PR2 of this same change):
 *   GET  /parts/bot/catalog-models              -> [{ vehicle_model, catalog_model_code }]
 *   GET  /parts/model/{code}/all-sections        -> [{ section_id, section_code, section_name, diagram_url }]
 *   POST /parts/search-by-model                  -> [{ section_id, section_code, section_name, diagram_url, model_code }]
 *   GET  /parts/section/{id}/diagram-image       -> binary (blob)
 *   GET  /parts/section/{id}/items                -> [PartItemResult, ...] natural-sorted by order_num
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

function modelSelect() {
  return screen.getByLabelText(/1\. Motocicleta/i);
}

function sectionSelect() {
  return screen.getByLabelText(/2\. Sistema \/ Sección/i);
}

async function selectModelAndOpenSection() {
  await waitFor(() => {
    expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
  });
  fireEvent.change(modelSelect(), { target: { value: 'DSR150' } });

  await waitFor(() => {
    expect(screen.getByRole('option', { name: /Motor/i })).toBeInTheDocument();
  });
  fireEvent.change(sectionSelect(), { target: { value: 'sec-1' } });
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

describe('DistribuidorRepuestosPage — persistent two-panel workspace (matches reference structure)', () => {
  it('renders both panels, with empty states, before anything is selected', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
    });

    // The two-panel workspace exists from the very first render -- it is not
    // gated behind picking a section.
    expect(screen.getByText('Plano de Ensamblaje')).toBeInTheDocument();
    expect(screen.getByText('Listado de Componentes')).toBeInTheDocument();
    expect(screen.getByText(/Aquí aparecerán las piezas numeradas/i)).toBeInTheDocument();
  });

  it('the "2. Sistema / Sección" select is disabled until a model is chosen', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
    });
    expect(sectionSelect()).toBeDisabled();

    fireEvent.change(modelSelect(), { target: { value: 'DSR150' } });

    await waitFor(() => {
      expect(sectionSelect()).not.toBeDisabled();
    });
  });
});

describe('DistribuidorRepuestosPage — model/section browse flow', () => {
  it('selecting a model populates the "2. Sistema / Sección" select', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
    });
    fireEvent.change(modelSelect(), { target: { value: 'DSR150' } });

    await waitFor(() => {
      expect(within(sectionSelect()).getByRole('option', { name: /Motor/i })).toBeInTheDocument();
    });
  });

  it('opening a section fills the workspace: diagram + full item list in order_num order', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();

    await waitFor(() => {
      expect(screen.getByTestId('part-card-item-1')).toBeInTheDocument();
    });
    expect(screen.getByTestId('part-card-item-2')).toBeInTheDocument();

    const card1 = screen.getByTestId('part-card-item-1');
    const card2 = screen.getByTestId('part-card-item-2');
    // eslint-disable-next-line no-bitwise
    expect(card1.compareDocumentPosition(card2) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Panel title switches from the static default to the section's own name.
    expect(screen.getByRole('heading', { name: 'Motor' })).toBeInTheDocument();
    expect(screen.getByAltText('Motor')).toBeInTheDocument();
  });

  it('updates the "Total de Piezas Encontradas" counter once a section is open', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    expect(screen.getByText('Total de Piezas Encontradas').nextSibling).toHaveTextContent('0');

    await selectModelAndOpenSection();

    await waitFor(() => {
      expect(screen.getByText('Total de Piezas Encontradas').nextSibling).toHaveTextContent('2');
    });
  });

  it('a null-price card shows "Sin precio", never $0', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();

    await waitFor(() => {
      expect(screen.getByTestId('part-card-item-2')).toBeInTheDocument();
    });
    const card2 = screen.getByTestId('part-card-item-2');
    expect(within(card2).getByText(/sin precio/i)).toBeInTheDocument();
    expect(within(card2).queryByText('$0')).not.toBeInTheDocument();
  });

  it('a priced card renders precio_publico formatted as currency', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();

    await waitFor(() => {
      expect(screen.getByTestId('part-card-item-1')).toBeInTheDocument();
    });
    const card1 = screen.getByTestId('part-card-item-1');
    expect(within(card1).getByText(/\$\s?45[.,]000/)).toBeInTheDocument();
  });
});

describe('DistribuidorRepuestosPage — AI description search (text/voice/photo)', () => {
  it('text search returns sections via POST /parts/search-by-model unchanged, and opens the workspace', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
    });
    fireEvent.change(modelSelect(), { target: { value: 'DSR150' } });

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

    await waitFor(() => {
      expect(screen.getByText('Ver sección')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Ver sección'));

    await waitFor(() => {
      expect(screen.getByTestId('part-card-item-1')).toBeInTheDocument();
    });
  });

  it('voice search fires the same search-by-model contract', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
    });
    fireEvent.change(modelSelect(), { target: { value: 'DSR150' } });

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
    fireEvent.change(modelSelect(), { target: { value: 'DSR150' } });

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
  it('has no add/request/quote/cart control anywhere on the screen', async () => {
    setUser();
    queueResponses();
    render(<DistribuidorRepuestosPage />);

    await selectModelAndOpenSection();
    await waitFor(() => {
      expect(screen.getByTestId('part-card-item-1')).toBeInTheDocument();
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
    fireEvent.change(modelSelect(), { target: { value: 'DSR150' } });

    await waitFor(() => {
      expect(screen.getByText(/no se pudieron cargar las secciones/i)).toBeInTheDocument();
    });
  });
});
