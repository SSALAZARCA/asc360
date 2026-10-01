'use client';
/**
 * The cap summary of a corrida (cap, value and excess of each tienda) for the
 * banner and the Tope column of the detail. It reads nothing for a scenario and
 * stays `null` while the mode is off or when the read fails: the cap is
 * advisory and must never break the corrida screen. `estado` makes it read
 * again when the calculation ends.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getTopesCorrida } from '../../../lib/motored/pedidosApi';

export default function useTopesCorrida(corridaId, habilitado, estado) {
  const [topes, setTopes] = useState(null);
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);
  const recargar = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    const id = ++requestId.current;
    if (!habilitado) {
      setTopes(null);
      return;
    }
    getTopesCorrida(corridaId)
      .then((body) => { if (id === requestId.current) setTopes(body && body.activo ? body : null); })
      .catch(() => { if (id === requestId.current) setTopes(null); });
  }, [corridaId, habilitado, estado, nonce]);

  return { topes, recargar };
}
