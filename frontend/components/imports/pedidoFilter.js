/**
 * Pure helpers for the "Ajuste de Pedidos" pedido/PI filter — no React, no
 * fetch, kept separate from AnalisisRepuestosTab.js so they're trivially
 * testable and never touch the marked-decisions / execute-adjustments state.
 */

export function getUniquePedidos(items) {
  const seen = new Set();
  const result = [];
  for (const item of items || []) {
    for (const lot of item.lots || []) {
      if (!seen.has(lot.lot_identifier)) {
        seen.add(lot.lot_identifier);
        result.push(lot.lot_identifier);
      }
    }
  }
  return result.sort();
}

// Returns the SAME array reference when no pedido is selected, so callers
// can rely on identity to skip re-deriving anything when the filter is off.
export function filterItemsByPedido(items, pedido) {
  if (!pedido) return items || [];
  const result = [];
  for (const item of items || []) {
    const matchingLots = (item.lots || []).filter(l => l.lot_identifier === pedido);
    if (matchingLots.length === 0) continue;
    const total_qty = matchingLots.reduce((sum, l) => sum + (l.qty || 0), 0);
    result.push({ ...item, lots: matchingLots, total_qty });
  }
  return result;
}

export function getUniqueModelos(items) {
  const seen = new Set();
  for (const item of items || []) {
    for (const modelo of item.models || []) seen.add(modelo);
  }
  return [...seen].sort();
}

// Unlike pedido, `models` is a property of the ITEM itself (which motos use
// that part), not of an individual lot -- so this only drops non-matching
// items, it never trims an item's lots/total_qty.
export function filterItemsByModelo(items, modelo) {
  if (!modelo) return items || [];
  return (items || []).filter(item => (item.models || []).includes(modelo));
}
