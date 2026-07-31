/**
 * Tests for the `/tg/parts` bottom-sheet parts list, added because the
 * backend no longer bakes a position-number -> description table into the
 * composited diagram image (commit d7fe874 removed `create_diagram_card`'s
 * table). Without a real list here, a técnico looking at the diagram has no
 * way to know what a numbered position actually is.
 *
 * Sourced from `GET /parts/section/{section_id}/items` (same endpoint
 * `/distribuidor/repuestos` uses) -- `PartItemResult[]`, natural-sorted by
 * `order_num` server-side, already includes `precio_publico` /
 * `precio_es_preliminar` / `description_es`.
 *
 * This is a separate file from `tg-parts-price-row.test.jsx` (which covers
 * the single-item position-code search card) because this list is a
 * distinct concern with its own fetch/loading/error lifecycle, triggered by
 * opening the section bottom sheet rather than by searching a position code.
 *
 * Covers:
 *   - Opening a section's bottom sheet fetches the items list and renders it
 *     (position, code, description) once loaded.
 *   - A null `precio_publico` item shows "Sin precio", never `$0`.
 *   - A `precio_es_preliminar: true` item shows the "Precio preliminar" label.
 *   - If the items fetch fails, an inline error shows (no silent failure, no
 *     `alert()`).
 *   - The existing position-code search box still works unchanged
 *     (lightweight regression check).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
}));

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));

jest.mock('../components/tg/TgNav', () => {
  const MockTgNav = () => <div data-testid="tg-nav" />;
  MockTgNav.displayName = 'MockTgNav';
  return MockTgNav;
});
jest.mock('../components/tg/VoiceInput', () => {
  const MockVoiceInput = () => <div data-testid="voice-input" />;
  MockVoiceInput.displayName = 'MockVoiceInput';
  return MockVoiceInput;
});
jest.mock('../components/tg/CameraInput', () => {
  const MockCameraInput = () => <div data-testid="camera-input" />;
  MockCameraInput.displayName = 'MockCameraInput';
  return MockCameraInput;
});

import TgParts from '../app/tg/parts/page';

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
    blob: jest.fn().mockResolvedValue(new Blob()),
  };
}

const MODELS = [{ catalog_model_code: 'DSR150', vehicle_model: 'DSR 150' }];
const SECTION = {
  section_id: 'sec-1',
  section_code: 'A',
  section_name: 'Motor',
  diagram_url: null,
  model_code: 'DSR150',
};

const ITEM_1 = {
  id: 'item-1',
  section_id: 'sec-1',
  section_code: 'A',
  section_name: 'Motor',
  order_num: 'A1',
  factory_part_number: 'FP-001',
  um_part_number: 'UM-001',
  description: 'Tornillo de cabeza hexagonal',
  description_es: null,
  unit: 'UND',
  precio_publico: 45000,
  precio_es_preliminar: false,
};

const ITEM_2_NO_PRICE = {
  id: 'item-2',
  section_id: 'sec-1',
  section_code: 'A',
  section_name: 'Motor',
  order_num: 'A2',
  factory_part_number: 'FP-002',
  um_part_number: 'UM-002',
  description: 'Filtro de aceite',
  description_es: null,
  unit: 'UND',
  precio_publico: null,
  precio_es_preliminar: false,
};

const ITEM_3_PRELIMINAR = {
  id: 'item-3',
  section_id: 'sec-1',
  section_code: 'A',
  section_name: 'Motor',
  order_num: 'A3',
  factory_part_number: 'FP-003',
  um_part_number: 'UM-003',
  description: 'Empaque de tapa',
  description_es: null,
  unit: 'UND',
  precio_publico: 12000,
  precio_es_preliminar: true,
};

let mockItemsResponse = { status: 200, body: [ITEM_1, ITEM_2_NO_PRICE] };
let mockPartResult = ITEM_1;

function queueResponses() {
  mockAuthFetch.mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/parts/bot/catalog-models')) {
      return Promise.resolve(makeResponse(200, MODELS));
    }
    if (typeof url === 'string' && url.includes('/all-sections')) {
      return Promise.resolve(makeResponse(200, [SECTION]));
    }
    if (typeof url === 'string' && /\/parts\/section\/[^/]+\/items$/.test(url)) {
      if (mockItemsResponse.status >= 400) {
        return Promise.resolve(makeResponse(mockItemsResponse.status, {}));
      }
      return Promise.resolve(makeResponse(200, mockItemsResponse.body));
    }
    if (typeof url === 'string' && /\/parts\/section\/[^/]+\/item\//.test(url)) {
      return Promise.resolve(makeResponse(200, mockPartResult));
    }
    return Promise.resolve(makeResponse(200, {}));
  });
}

function setUser(role = 'technician') {
  sessionStorage.setItem('um_user', JSON.stringify({ name: 'Test Tech', role }));
  sessionStorage.setItem('um_token', 'fake-token');
}

async function openSection() {
  setUser();
  queueResponses();
  render(<TgParts />);

  await waitFor(() => {
    expect(screen.getByRole('option', { name: 'DSR 150' })).toBeInTheDocument();
  });
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'DSR150' } });

  await waitFor(() => {
    expect(screen.getByText('Motor')).toBeInTheDocument();
  });
  fireEvent.click(screen.getByText('Motor'));
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  sessionStorage.clear();
  mockItemsResponse = { status: 200, body: [ITEM_1, ITEM_2_NO_PRICE] };
  mockPartResult = ITEM_1;
});

describe('TgParts — section bottom-sheet parts list', () => {
  it('fetches GET /parts/section/{id}/items when the bottom sheet opens and renders the list', async () => {
    await openSection();

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/parts\/section\/sec-1\/items$/)
      );
    });

    await waitFor(() => {
      expect(screen.getByText('A1')).toBeInTheDocument();
    });
    expect(screen.getByText('FP-001')).toBeInTheDocument();
    expect(screen.getByText('Tornillo de cabeza hexagonal')).toBeInTheDocument();
    expect(screen.getByText('A2')).toBeInTheDocument();
    expect(screen.getByText('FP-002')).toBeInTheDocument();
    expect(screen.getByText('Filtro de aceite')).toBeInTheDocument();
  });

  it('shows "Sin precio" for a null precio_publico item in the list, never $0', async () => {
    mockItemsResponse = { status: 200, body: [ITEM_2_NO_PRICE] };
    await openSection();

    await waitFor(() => {
      expect(screen.getByText('FP-002')).toBeInTheDocument();
    });

    expect(screen.getByText(/sin precio/i)).toBeInTheDocument();
    expect(screen.queryByText('$0')).not.toBeInTheDocument();
    expect(screen.queryByText(/\$\s?0(?!\d)/)).not.toBeInTheDocument();
  });

  it('shows the "Precio preliminar" label for a precio_es_preliminar item in the list', async () => {
    mockItemsResponse = { status: 200, body: [ITEM_3_PRELIMINAR] };
    await openSection();

    await waitFor(() => {
      expect(screen.getByText('FP-003')).toBeInTheDocument();
    });

    expect(screen.getByText(/precio preliminar/i)).toBeInTheDocument();
  });

  it('shows an inline error if the items fetch fails, without alert()', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});
    mockItemsResponse = { status: 500, body: null };
    await openSection();

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
    expect(alertSpy).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('still allows searching a part by position code after the list loads (regression)', async () => {
    await openSection();

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Ej: A1, B3, C12/)).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText(/Ej: A1, B3, C12/), { target: { value: 'A1' } });
    fireEvent.click(screen.getByRole('button', { name: /buscar/i }));

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/parts\/section\/sec-1\/item\/A1$/)
      );
    });
  });
});
