'use client';
/** State/effects for the login log: filters, pagination, loading. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { listIngresos } from '../../../lib/motored/api';
import useDebouncedValue from '../../../lib/motored/useDebouncedValue';

export const PAGE_SIZE = 50;
const INITIAL = { resultado: '', texto: '', desde: '', hasta: '', page: 1 };

export default function useIngresosList(enabled) {
  const [filters, setFilters] = useState(INITIAL);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestId = useRef(0);
  const texto = useDebouncedValue(filters.texto);

  const setFilter = useCallback((key, value) => setFilters((f) => ({ ...f, [key]: value, page: 1 })), []);
  const setPage = useCallback((page) => setFilters((f) => ({ ...f, page })), []);

  const { resultado, desde, hasta, page } = filters;
  useEffect(() => {
    if (!enabled) return;
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    listIngresos({ resultado, texto: texto.trim(), desde, hasta, page, page_size: PAGE_SIZE })
      .then((body) => { if (id === requestId.current) setData(body); })
      .catch((err) => { if (id === requestId.current) setError(err.message || 'No se pudo cargar el registro.'); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
  }, [enabled, resultado, texto, desde, hasta, page]);

  return { filters, setFilter, setPage, data, loading, error };
}
