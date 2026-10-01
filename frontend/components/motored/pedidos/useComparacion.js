'use client';
/**
 * The comparison of a scenario with one real corrida: filters (tienda, only
 * the rows that differ), paging of 100 rows (limite/offset) and loading. The
 * filters belong to the real corrida they were chosen for: picking another one
 * starts again from the first page with every tienda, and never shows the rows
 * of the previous pair. The previous page stays while the next one loads.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { compararCorridas } from '../../../lib/motored/pedidosApi';
import { aLimiteOffset } from '../../../lib/motored/paginacion';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

export const PAGINA_COMPARACION = 100;
const INICIAL = { sucursal: '', soloDiferencias: true, page: 1 };

export default function useComparacion(escenarioId, realId) {
  const [elegidos, setElegidos] = useState({ ...INICIAL, para: realId });
  const [resultado, setResultado] = useState({ para: null, body: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestId = useRef(0);

  const filtros = elegidos.para === realId ? elegidos : { ...INICIAL, para: realId };
  const setFiltro = useCallback((clave, valor) => {
    setElegidos({ ...filtros, [clave]: valor, ...(clave === 'page' ? {} : { page: 1 }), para: realId });
  }, [filtros, realId]);

  const { sucursal, soloDiferencias, page } = filtros;
  useEffect(() => {
    if (!realId) return;
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    compararCorridas(escenarioId, {
      con: realId, sucursal_id: sucursal, solo_diferencias: soloDiferencias, ...aLimiteOffset(page, PAGINA_COMPARACION),
    })
      .then((body) => { if (id === requestId.current) setResultado({ para: realId, body }); })
      .catch((err) => { if (id === requestId.current) setError(mensajeConCodigo(err, 'No se pudo cargar la comparación.')); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
  }, [escenarioId, realId, sucursal, soloDiferencias, page]);

  const data = resultado.para === realId ? resultado.body : null;
  return { filtros, setFiltro, data, loading, error, pageSize: PAGINA_COMPARACION };
}
