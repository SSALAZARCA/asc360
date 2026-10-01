'use client';
/** Tiendas ticked in the Tiendas table (for the batch actions), kept as a set of sucursal ids. */
import { useCallback, useState } from 'react';

export default function useSeleccionTiendas() {
  const [marcadas, setMarcadas] = useState(() => new Set());
  const alternar = useCallback((id) => setMarcadas((actual) => {
    const siguiente = new Set(actual);
    if (siguiente.has(id)) siguiente.delete(id); else siguiente.add(id);
    return siguiente;
  }), []);
  const limpiar = useCallback(() => setMarcadas(new Set()), []);
  return { marcadas, alternar, limpiar };
}
