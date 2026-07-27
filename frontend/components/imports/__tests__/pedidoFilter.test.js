/**
 * Tests for the pure PI/pedido-filtering helpers used by the "Ajuste de
 * Pedidos" screen (AnalisisRepuestosTab.js) to let a superadmin narrow the
 * whole view down to a single pedido (lot_identifier), including the
 * summary cards.
 *
 * These are pure functions with no React/fetch involved, so they're tested
 * in isolation rather than through the (large, currently untested) host
 * component.
 */
import { getUniquePedidos, filterItemsByPedido, getUniqueModelos, filterItemsByModelo } from '../pedidoFilter';

const ITEMS = [
  {
    factory_part_number: 'FPN-1',
    rotation_class: 'baja',
    total_qty: 8,
    models: ['XPEED 125 ADV', 'XPEED 150 ADV'],
    lots: [
      { lot_identifier: 'PI-100', qty: 5, fob_unit: 10 },
      { lot_identifier: 'PI-205', qty: 3, fob_unit: 10 },
    ],
  },
  {
    factory_part_number: 'FPN-2',
    rotation_class: 'media',
    total_qty: 4,
    models: ['ROCKVILLE 200'],
    lots: [
      { lot_identifier: 'PI-205', qty: 4, fob_unit: 20 },
    ],
  },
  {
    factory_part_number: 'FPN-3',
    rotation_class: 'alta',
    total_qty: 2,
    models: [],
    lots: [
      { lot_identifier: 'PI-300', qty: 2, fob_unit: 5 },
    ],
  },
];

describe('getUniquePedidos', () => {
  it('collects every distinct lot_identifier across all items, sorted', () => {
    expect(getUniquePedidos(ITEMS)).toEqual(['PI-100', 'PI-205', 'PI-300']);
  });

  it('returns an empty list for no items', () => {
    expect(getUniquePedidos([])).toEqual([]);
    expect(getUniquePedidos(null)).toEqual([]);
  });
});

describe('filterItemsByPedido', () => {
  it('returns the items unchanged (same reference) when no pedido is selected', () => {
    expect(filterItemsByPedido(ITEMS, '')).toBe(ITEMS);
    expect(filterItemsByPedido(ITEMS, null)).toBe(ITEMS);
  });

  it('drops items that have no lot in the selected pedido', () => {
    const result = filterItemsByPedido(ITEMS, 'PI-300');
    expect(result.map(i => i.factory_part_number)).toEqual(['FPN-3']);
  });

  it('keeps an item that has the selected pedido AND others, trimmed to only the matching lot', () => {
    const result = filterItemsByPedido(ITEMS, 'PI-100');
    expect(result).toHaveLength(1);
    expect(result[0].factory_part_number).toBe('FPN-1');
    expect(result[0].lots).toEqual([{ lot_identifier: 'PI-100', qty: 5, fob_unit: 10 }]);
  });

  it('recomputes total_qty from only the matching lot(s), not the item-wide total', () => {
    const result = filterItemsByPedido(ITEMS, 'PI-100');
    expect(result[0].total_qty).toBe(5); // not the original 8
  });

  it('an item present in the selected pedido via one of several lots keeps only that lot\'s qty', () => {
    const result = filterItemsByPedido(ITEMS, 'PI-205');
    const fpn1 = result.find(i => i.factory_part_number === 'FPN-1');
    const fpn2 = result.find(i => i.factory_part_number === 'FPN-2');
    expect(fpn1.total_qty).toBe(3);
    expect(fpn2.total_qty).toBe(4);
  });
});

describe('getUniqueModelos', () => {
  it('collects every distinct model across all items, sorted', () => {
    expect(getUniqueModelos(ITEMS)).toEqual(['ROCKVILLE 200', 'XPEED 125 ADV', 'XPEED 150 ADV']);
  });

  it('returns an empty list for no items', () => {
    expect(getUniqueModelos([])).toEqual([]);
    expect(getUniqueModelos(null)).toEqual([]);
  });
});

describe('filterItemsByModelo', () => {
  it('returns the items unchanged (same reference) when no modelo is selected', () => {
    expect(filterItemsByModelo(ITEMS, '')).toBe(ITEMS);
    expect(filterItemsByModelo(ITEMS, null)).toBe(ITEMS);
  });

  it('keeps only items whose models list includes the selected modelo', () => {
    const result = filterItemsByModelo(ITEMS, 'ROCKVILLE 200');
    expect(result.map(i => i.factory_part_number)).toEqual(['FPN-2']);
  });

  it('does NOT trim lots/total_qty -- models are item-level, not lot-level', () => {
    const result = filterItemsByModelo(ITEMS, 'XPEED 125 ADV');
    expect(result[0].total_qty).toBe(8);
    expect(result[0].lots).toHaveLength(2);
  });

  it('excludes items with no models at all', () => {
    const result = filterItemsByModelo(ITEMS, 'ROCKVILLE 200');
    expect(result.some(i => i.factory_part_number === 'FPN-3')).toBe(false);
  });
});
