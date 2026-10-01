'use client';
/**
 * Lines of one tienda pedido: filters, the search box (debounced), paging
 * (limite/offset) and loading. Any filter change goes back to page 1.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { listarLineas } from '../../../lib/motored/pedidosApi';
import { aLimiteOffset } from '../../../lib/motored/paginacion';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';
import useDebouncedValue from '../../../lib/motored/useDebouncedValue';

export const TAMANOS_LINEAS = [50, 100, 200, 500];
const INITIAL = { clase: '', estado_quiebre: '', q: '', solo_editadas: false, incluir_excluidas: false, page: 1, pageSize: 50 };

export default function useLineasPedido(corridaId, sucursalId, enabled) {
  const [filters, setFilters] = useState(INITIAL);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestId = useRef(0);

  const setFilter = useCallback((key, value) => setFilters((f) => ({ ...f, [key]: value, page: 1 })), []);
  const setPage = useCallback((page) => setFilters((f) => ({ ...f, page })), []);
  const setPageSize = useCallback((pageSize) => setFilters((f) => ({ ...f, pageSize, page: 1 })), []);

  const q = useDebouncedValue(filters.q.trim(), 300);
  const { clase, estado_quiebre: quiebre, solo_editadas: editadas, incluir_excluidas: excluidas, page, pageSize } = filters;
  useEffect(() => {
    if (!enabled) return;
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    listarLineas(corridaId, {
      sucursal_id: sucursalId, clase, estado_quiebre: quiebre, q,
      solo_editadas: editadas || '', incluir_excluidas: excluidas || '', ...aLimiteOffset(page, pageSize),
    })
      .then((body) => { if (id === requestId.current) setData(body); })
      .catch((err) => { if (id === requestId.current) setError(mensajeConCodigo(err, 'No se pudo cargar las líneas.')); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
  }, [enabled, corridaId, sucursalId, clase, quiebre, q, editadas, excluidas, page, pageSize]);

  return { filters, setFilter, setPage, setPageSize, data, loading, error };
}
