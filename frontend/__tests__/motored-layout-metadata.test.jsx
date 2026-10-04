jest.mock('next/font/google', () => ({
  Mulish: () => ({ variable: 'mulish' }),
  IBM_Plex_Mono: () => ({ variable: 'plex-mono' }),
  Manrope: () => ({ variable: 'manrope' }),
}));

import { render } from '@testing-library/react';
import MotoredRootLayout, { metadata } from '../app/motored/layout';

describe('Motored layout metadata (link previews)', () => {
  it('uses its own description instead of inheriting the UM one', () => {
    expect(metadata.description).toBe('Sistema de gestión Motored');
    expect(metadata.description).not.toMatch(/UM Colombia/);
  });

  it('declares Open Graph data with the Motored title, description and logo', () => {
    expect(metadata.openGraph).toMatchObject({
      title: 'Motored Pedidos',
      description: 'Sistema de gestión Motored',
      siteName: 'Motored',
    });
    expect(metadata.openGraph.images).toEqual([{ url: '/motored-logo.png' }]);
  });

  it('sets an absolute metadataBase so preview images resolve outside the app', () => {
    expect(metadata.metadataBase).toBeInstanceOf(URL);
  });

  it("loads Manrope for the KPI's and points the KPI font token at it", () => {
    const { container } = render(<MotoredRootLayout><span>hijo</span></MotoredRootLayout>);
    expect(container.firstChild).toHaveClass('manrope');
    expect(container.querySelector('style').textContent).toMatch(/--motored-font-kpi:\s*var\(--motored-font-manrope\)/);
  });
});
