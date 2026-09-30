'use client';
/** State/effects for the detractors list: tab, filters, pagination, loading. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { listDetractores } from '../../../lib/motored/detractoresApi';
import useDebouncedValue from '../../../lib/motored/useDebouncedValue';

export const PAGE_SIZE = 25;
const INITIAL = { estado: 'ABIERTO', q: '', centro: '', autoriza: '', desde: '', hasta: '', page: 1 };

export default function useDetractoresList(enabled) {
  const [filters, setFilters] = useState(INITIAL);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);
  const q = useDebouncedValue(filters.q);
  const centro = useDebouncedValue(filters.centro);

  const setFilter = useCallback((key, value) => {
    setFilters((f) => ({ ...f, [key]: value, page: 1 }));
  }, []);
  const setPage = useCallback((page) => setFilters((f) => ({ ...f, page })), []);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  const { estado, autoriza, desde, hasta, page } = filters;
  useEffect(() => {
    if (!enabled) return;
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    listDetractores({
      estado, q, centro_servicio: centro, autoriza_datos: autoriza, desde, hasta, page, page_size: PAGE_SIZE,
    })
      .then((body) => { if (id === requestId.current) setData(body); })
      .catch((err) => { if (id === requestId.current) setError(err.message || 'No se pudo cargar los casos.'); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
  }, [enabled, estado, q, centro, autoriza, desde, hasta, page, nonce]);

  return { filters, setFilter, setPage, reload, data, loading, error };
}
