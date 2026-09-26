'use client';
/**
 * frontend/components/motored/ventas-perdidas/useVentasPerdidas.js
 *
 * sdd/motored-ventas-perdidas-panel, Phase 7 (design D6). Owns `filtros`
 * state (initialized to the last-30-days default, task 7.1) plus load/
 * editar/anular, mirroring `useCargasHistory`'s (`CargasHistoryTable.js`)
 * and `useUsuarios`'s (`usuarios/page.js`) shape: the hook owns state and
 * side effects, the components stay dumb.
 *
 * `enabled` gates the initial fetch (and every refetch) until the ADMIN
 * gate (`useAdminGate`) resolves -- same pattern as `useUsuarios(allowed)`.
 *
 * `inconsistencia` (design D4/spec "agregado_consistente surfaced"): set
 * from the LAST anular response's `agregado_consistente` field. `false`
 * means the line ended ANULADA but no matching `demanda_perdida` aggregate
 * row existed to reverse -- a real data problem the ADMIN must investigate
 * manually, not a client bug.
 */
import { useState, useCallback, useEffect } from 'react';
import { listarBotLineas, editarBotLinea, anularBotLinea } from '../../../lib/motored/api';
import { calcularRangoUltimos30Dias } from './fechaDefaults';

export default function useVentasPerdidas(enabled) {
  const [filtros, setFiltros] = useState(() => ({
    ...calcularRangoUltimos30Dias(),
    sucursalId: '',
    usuarioId: '',
    estado: '',
  }));
  const [lineas, setLineas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [inconsistencia, setInconsistencia] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await listarBotLineas(filtros);
      setLineas(data);
    } catch (err) {
      setError(err.message || 'No se pudo cargar la lista de ventas perdidas');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros.desde, filtros.hasta, filtros.sucursalId, filtros.usuarioId, filtros.estado]);

  useEffect(() => {
    if (enabled) load();
  }, [enabled, load]);

  const editar = async (lineaId, cantidad) => {
    setError('');
    try {
      await editarBotLinea(lineaId, cantidad);
      await load();
      return true;
    } catch (err) {
      setError(err.message || 'No se pudo editar la línea');
      return false;
    }
  };

  const anular = async (lineaId) => {
    setError('');
    try {
      const resultado = await anularBotLinea(lineaId);
      setInconsistencia(resultado.agregado_consistente === false);
      await load();
      return true;
    } catch (err) {
      setError(err.message || 'No se pudo anular la línea');
      return false;
    }
  };

  return { filtros, setFiltros, lineas, loading, error, inconsistencia, editar, anular };
}
