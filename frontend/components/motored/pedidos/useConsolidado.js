'use client';
/**
 * The consolidated matrix of one corrida: search text (debounced), paging of
 * 100 references (limite/offset) and loading. A new search goes back to page 1
 * without a second request: the page is remembered together with the search
 * text it was chosen for. The previous page stays in `data` while the next one
 * loads or fails to load.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getConsolidado } from '../../../lib/motored/pedidosApi';
import { aLimiteOffset } from '../../../lib/motored/paginacion';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';
import useDebouncedValue from '../../../lib/motored/useDebouncedValue';

export const PAGINA_CONSOLIDADO = 100;

export default function useConsolidado(corridaId, enabled) {
  const [texto, setTexto] = useState('');
  const [pagina, setPagina] = useState({ page: 1, para: '' });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestId = useRef(0);

  const q = useDebouncedValue(texto.trim(), 300);
  const page = pagina.para === q ? pagina.page : 1;
  const setPage = useCallback((siguiente) => setPagina({ page: siguiente, para: q }), [q]);

  useEffect(() => {
    if (!enabled) return;
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    getConsolidado(corridaId, { q, ...aLimiteOffset(page, PAGINA_CONSOLIDADO) })
      .then((body) => { if (id === requestId.current) setData(body); })
      .catch((err) => { if (id === requestId.current) setError(mensajeConCodigo(err, 'No se pudo cargar el consolidado.')); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
  }, [enabled, corridaId, q, page]);

  return { texto, setTexto, page, setPage, pageSize: PAGINA_CONSOLIDADO, data, loading, error };
}
