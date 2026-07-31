/**
 * Tests for `components/EvidencePhoto.js` — the proxy-fetch replacement for
 * the raw (broken-in-production) `damage_photos_urls[i].url` MinIO link
 * previously rendered directly in `kanban/page.js`/`services/page.js`.
 *
 * Covers:
 *   - Calls `authFetch` with the correct `/orders/{orderId}/evidence-
 *     photos/{index}` path.
 *   - On a successful blob response, renders an `<img>` whose `src` is the
 *     object URL returned by `URL.createObjectURL`.
 *   - On a failed/rejected fetch, renders no `<img>` (fail-soft, matches
 *     the existing `onError` hide-on-failure behavior of the old inline
 *     `<img>` these thumbnails used before this component existed).
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));

import EvidencePhoto from '../components/EvidencePhoto';

describe('EvidencePhoto', () => {
  let originalCreateObjectURL;
  let originalRevokeObjectURL;

  beforeEach(() => {
    mockAuthFetch.mockReset();
    originalCreateObjectURL = global.URL.createObjectURL;
    originalRevokeObjectURL = global.URL.revokeObjectURL;
    global.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
    global.URL.revokeObjectURL = jest.fn();
  });

  afterEach(() => {
    global.URL.createObjectURL = originalCreateObjectURL;
    global.URL.revokeObjectURL = originalRevokeObjectURL;
  });

  it('calls authFetch with the correct evidence-photos path', async () => {
    const fakeBlob = new Blob(['fake-bytes'], { type: 'image/jpeg' });
    mockAuthFetch.mockResolvedValue({ ok: true, status: 200, blob: () => Promise.resolve(fakeBlob) });

    render(<EvidencePhoto orderId="order-123" index={2} alt="Foto 3" />);

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith('/orders/order-123/evidence-photos/2');
    });
  });

  it('renders an <img> with the object URL on a successful blob response', async () => {
    const fakeBlob = new Blob(['fake-bytes'], { type: 'image/jpeg' });
    mockAuthFetch.mockResolvedValue({ ok: true, status: 200, blob: () => Promise.resolve(fakeBlob) });

    render(<EvidencePhoto orderId="order-123" index={0} alt="Foto 1" />);

    const img = await screen.findByAltText('Foto 1');
    expect(img).toHaveAttribute('src', 'blob:mock-url');
    expect(global.URL.createObjectURL).toHaveBeenCalledWith(fakeBlob);
  });

  it('renders no <img> when the fetch response is not ok', async () => {
    mockAuthFetch.mockResolvedValue({ ok: false, status: 404 });

    render(<EvidencePhoto orderId="order-123" index={0} alt="Foto 1" />);

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalled();
    });
    expect(screen.queryByAltText('Foto 1')).not.toBeInTheDocument();
  });

  it('renders no <img> when the fetch rejects', async () => {
    mockAuthFetch.mockRejectedValue(new Error('network error'));

    render(<EvidencePhoto orderId="order-123" index={0} alt="Foto 1" />);

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalled();
    });
    expect(screen.queryByAltText('Foto 1')).not.toBeInTheDocument();
  });
});
