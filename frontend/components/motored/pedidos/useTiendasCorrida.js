'use client';
/** Loads one corrida with its tiendas (the detail endpoint) and lets the caller reload it. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getCorrida } from '../../../lib/motored/pedidosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

export default function useTiendasCorrida(corridaId, enabled) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) return;
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    getCorrida(corridaId)
      .then((body) => { if (id === requestId.current) setData(body); })
      .catch((err) => { if (id === requestId.current) setError(mensajeConCodigo(err, 'No se pudo cargar la corrida.')); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
  }, [enabled, corridaId, nonce]);

  return { data, loading, error, reload };
}
