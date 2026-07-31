/**
 * Tests for the `/tg/parts` part-detail card price row, introduced in:
 *   sdd/distributor-parts-search, Phase 3 (PR3, frontend)
 *
 * Backend context (already landed on main, PR1/PR2 of this same change):
 *   GET /parts/section/{section_id}/item/{order_num} now returns
 *   `precio_publico` (number | null), `precio_es_preliminar` (bool), and
 *   `description_es` (string | null) on `PartItemResult`, in addition to the
 *   pre-existing `order_num`, `factory_part_number`, `um_part_number`, `unit`,
 *   and `description` fields.
 *
 * This is the FIRST dedicated test file for this page (no prior coverage).
 * Covers:
 *   - `precio_publico` renders formatted as currency.
 *   - `precio_publico: null` renders an explicit "Sin precio" state, NEVER
 *     `$0` (hard requirement -- a técnico must never mistake "unpriced" for
 *     "free").
 *   - `precio_es_preliminar: true` renders a "Precio preliminar" label near
 *     the price.
 *   - The 4 pre-existing fields (Posición / Cód. Fábrica / Cód. UM / Unidad)
 *     still render unchanged -- regression check, this PR must not break the
 *     existing card.
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

const BASE_PART = {
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
  precio_publico: null,
  precio_es_preliminar: false,
};

let mockPartResult = BASE_PART;

function queueResponses() {
  mockAuthFetch.mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/parts/bot/catalog-models')) {
      return Promise.resolve(makeResponse(200, MODELS));
    }
    if (typeof url === 'string' && url.includes('/all-sections')) {
      return Promise.resolve(makeResponse(200, [SECTION]));
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

async function openSectionAndLookupPart(posCode = 'A1') {
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

  await waitFor(() => {
    expect(screen.getByPlaceholderText(/Ej: A1, B3, C12/)).toBeInTheDocument();
  });
  fireEvent.change(screen.getByPlaceholderText(/Ej: A1, B3, C12/), { target: { value: posCode } });
  fireEvent.click(screen.getByRole('button', { name: /buscar/i }));
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  sessionStorage.clear();
  mockPartResult = BASE_PART;
});

describe('TgParts — part-detail card price row', () => {
  it('renders precio_publico formatted as currency', async () => {
    mockPartResult = { ...BASE_PART, precio_publico: 45000, precio_es_preliminar: false };
    await openSectionAndLookupPart();

    await waitFor(() => {
      expect(screen.getByText('FP-001')).toBeInTheDocument();
    });

    expect(screen.getByText(/\$\s?45[.,]000/)).toBeInTheDocument();
  });

  it('renders an explicit "Sin precio" state when precio_publico is null, never $0', async () => {
    mockPartResult = { ...BASE_PART, precio_publico: null, precio_es_preliminar: false };
    await openSectionAndLookupPart();

    await waitFor(() => {
      expect(screen.getByText('FP-001')).toBeInTheDocument();
    });

    expect(screen.getByText(/sin precio/i)).toBeInTheDocument();
    expect(screen.queryByText('$0')).not.toBeInTheDocument();
    expect(screen.queryByText(/\$\s?0(?!\d)/)).not.toBeInTheDocument();
  });

  it('renders a "Precio preliminar" label when precio_es_preliminar is true', async () => {
    mockPartResult = { ...BASE_PART, precio_publico: 30000, precio_es_preliminar: true };
    await openSectionAndLookupPart();

    await waitFor(() => {
      expect(screen.getByText('FP-001')).toBeInTheDocument();
    });

    expect(screen.getByText(/precio preliminar/i)).toBeInTheDocument();
  });

  it('does not render the preliminary label when precio_es_preliminar is false', async () => {
    mockPartResult = { ...BASE_PART, precio_publico: 30000, precio_es_preliminar: false };
    await openSectionAndLookupPart();

    await waitFor(() => {
      expect(screen.getByText('FP-001')).toBeInTheDocument();
    });

    expect(screen.queryByText(/precio preliminar/i)).not.toBeInTheDocument();
  });

  it('still renders the 4 pre-existing fields unchanged (Posición / Cód. Fábrica / Cód. UM / Unidad)', async () => {
    mockPartResult = { ...BASE_PART, precio_publico: 45000, precio_es_preliminar: false };
    await openSectionAndLookupPart();

    await waitFor(() => {
      expect(screen.getByText('FP-001')).toBeInTheDocument();
    });

    expect(screen.getByText('Posición')).toBeInTheDocument();
    expect(screen.getByText('A1')).toBeInTheDocument();
    expect(screen.getByText('Cód. Fábrica')).toBeInTheDocument();
    expect(screen.getByText('FP-001')).toBeInTheDocument();
    expect(screen.getByText('Cód. UM')).toBeInTheDocument();
    expect(screen.getByText('UM-001')).toBeInTheDocument();
    expect(screen.getByText('Unidad')).toBeInTheDocument();
    expect(screen.getByText('UND')).toBeInTheDocument();
  });
});
