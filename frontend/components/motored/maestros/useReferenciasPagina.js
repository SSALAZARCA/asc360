'use client';
/**
 * frontend/components/motored/maestros/useReferenciasPagina.js
 *
 * Data hooks for the paginated Referencias tab (`odd/tasks/motored-
 * referencias-paginacion.md`). Only the current page is fetched
 * (`buscarReferencias`); filters and search run on the server.
 *
 * Page reset: the page is stored together with the "query key" (debounced
 * search, filters, page size) it belongs to. When the key changes, the
 * effective page is 1 right away, so a filter change triggers ONE fetch
 * (page 1, new filter) instead of one with the old page and then another.
 */
import { useEffect, useState } from 'react';
import {
  buscarReferencias,
  listLineasComerciales,
  createMaestro,
  updateMaestro,
  deactivateMaestro,
} from '../../../lib/motored/api';
import useDebouncedValue from '../../../lib/motored/useDebouncedValue';
import { totalPaginas } from './ReferenciasPaginador';

const ENTIDAD_PLURAL = 'referencias';
const FILTROS_INICIALES = { q: '', linea: '', estado: '' };
const ACTIVA_POR_ESTADO = { '': null, true: true, false: false };

function useConsultaReferencias() {
  const [filtros, setFiltros] = useState(FILTROS_INICIALES);
  const [pageSize, setPageSize] = useState(50);
  const q = useDebouncedValue(filtros.q, 300);
  const consulta = { q, lineaComercial: filtros.linea, activa: ACTIVA_POR_ESTADO[filtros.estado], pageSize };
  const key = JSON.stringify(consulta);
  const [posicion, setPosicion] = useState({ key, page: 1 });
  const page = posicion.key === key ? posicion.page : 1;
  const setPage = (next) => setPosicion({ key, page: next });

  return { filtros, setFiltros, pageSize, setPageSize, consulta: { ...consulta, page }, key, page, setPage };
}

function usePaginaReferencias(consulta, key, version, setPage) {
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let vigente = true;
    setLoading(true);
    setError('');
    buscarReferencias(consulta)
      .then((res) => {
        if (!vigente) return;
        setData({ items: res.items, total: res.total });
        // A write can empty the last page (e.g. deactivating under "Activas").
        const ultima = totalPaginas(res.total, consulta.pageSize);
        if (consulta.page > ultima) setPage(ultima);
      })
      .catch((err) => vigente && setError(err.message || 'Error al cargar referencias'))
      .finally(() => vigente && setLoading(false));
    return () => { vigente = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, consulta.page, version]);

  return { ...data, loading, error, setError };
}

export function useLineasComerciales(version) {
  const [lineas, setLineas] = useState([]);
  useEffect(() => {
    listLineasComerciales().then(setLineas).catch(() => setLineas([]));
  }, [version]);
  return lineas;
}

function useEscriturasReferencia(setError, refrescar) {
  const run = async (write, fallback) => {
    setError('');
    try {
      await write();
      refrescar();
      return true;
    } catch (err) {
      setError(err.message || fallback);
      return false;
    }
  };
  const save = (payload, editingId) => run(
    () => (editingId ? updateMaestro(ENTIDAD_PLURAL, editingId, payload) : createMaestro(ENTIDAD_PLURAL, payload)),
    'Error al guardar referencia'
  );
  const deactivate = (id) => run(() => deactivateMaestro(ENTIDAD_PLURAL, id), 'Error al desactivar referencia');
  return { save, deactivate };
}

export default function useReferenciasPagina() {
  const [version, setVersion] = useState(0);
  const refrescar = () => setVersion((v) => v + 1);
  const consulta = useConsultaReferencias();
  const pagina = usePaginaReferencias(consulta.consulta, consulta.key, version, consulta.setPage);
  const escrituras = useEscriturasReferencia(pagina.setError, refrescar);
  return { ...consulta, ...pagina, ...escrituras, version, reload: refrescar };
}
