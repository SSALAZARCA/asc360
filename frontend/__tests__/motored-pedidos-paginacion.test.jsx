/** Motored Fase 4 (F1): limite/offset (backend) vs page/pageSize (UI) adapter. */
import { aLimiteOffset, aPagina } from '../lib/motored/paginacion';

describe('aLimiteOffset', () => {
  it('maps page 1 to offset 0', () => {
    expect(aLimiteOffset(1, 50)).toEqual({ limite: 50, offset: 0 });
  });

  it('maps page 3 of 25 to offset 50', () => {
    expect(aLimiteOffset(3, 25)).toEqual({ limite: 25, offset: 50 });
  });
});

describe('aPagina', () => {
  it('maps an offset back to its 1-based page', () => {
    expect(aPagina({ total: 130, limite: 50, offset: 100 }))
      .toEqual({ page: 3, pageSize: 50, total: 130 });
  });

  it('maps the first page and round-trips with aLimiteOffset', () => {
    expect(aPagina({ total: 4, limite: 50, offset: 0 })).toEqual({ page: 1, pageSize: 50, total: 4 });
    const { limite, offset } = aLimiteOffset(4, 100);
    expect(aPagina({ total: 999, limite, offset }).page).toBe(4);
  });

  it('is safe when the limit is missing', () => {
    expect(aPagina({ total: 0, limite: 0, offset: 0 })).toEqual({ page: 1, pageSize: 1, total: 0 });
  });
});
