'use client';
/** State/effects of the corridas list: filters, paging (limite/offset), loading. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { listarCorridas } from '../../../lib/motored/pedidosApi';
import { aLimiteOffset } from '../../../lib/motored/paginacion';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

export const PAGE_SIZE = 50;
const INITIAL = { estado: '', escenario: '', pedidos: '', page: 1 };

export default function useCorridas(enabled) {
  const [filters, setFilters] = useState(INITIAL);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);

  const setFilter = useCallback((key, value) => setFilters((f) => ({ ...f, [key]: value, page: 1 })), []);
  const setPage = useCallback((page) => setFilters((f) => ({ ...f, page })), []);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  const { estado, escenario, pedidos, page } = filters;
  useEffect(() => {
    if (!enabled) return;
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    listarCorridas({ estado, escenario, pedidos, ...aLimiteOffset(page, PAGE_SIZE) })
      .then((body) => { if (id === requestId.current) setData(body); })
      .catch((err) => { if (id === requestId.current) setError(mensajeConCodigo(err, 'No se pudo cargar las corridas.')); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
  }, [enabled, estado, escenario, pedidos, page, nonce]);

  return { filters, setFilter, setPage, reload, data, loading, error };
}
