'use client';
/**
 * State/effects for one case: load, reload and the two write actions. A 409
 * means someone else changed the case, so the message is shown and the case
 * is reloaded to reflect its real state.
 */
import { useCallback, useEffect, useState } from 'react';
import { agregarAccion, cambiarEstadoDetractor, getDetractor } from '../../../lib/motored/detractoresApi';

export default function useDetractorDetail(id, enabled) {
  const [caso, setCaso] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [accionError, setAccionError] = useState('');
  const [estadoError, setEstadoError] = useState('');
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      setCaso(await getDetractor(id));
      setLoadError('');
    } catch (err) {
      setLoadError(err.message || 'No se pudo cargar el caso.');
    }
  }, [id]);

  useEffect(() => { if (enabled) reload(); }, [enabled, reload]);

  const mutate = useCallback(async (call, setError) => {
    setBusy(true);
    setError('');
    try {
      await call();
      await reload();
      return true;
    } catch (err) {
      setError(err.message || 'No se pudo completar la acción.');
      if (err.status === 409) await reload();
      return false;
    } finally {
      setBusy(false);
    }
  }, [reload]);

  const registrarAccion = (payload) => mutate(() => agregarAccion(id, payload), setAccionError);
  const cambiarEstado = (payload) => mutate(() => cambiarEstadoDetractor(id, payload), setEstadoError);

  return { caso, loadError, accionError, estadoError, busy, registrarAccion, cambiarEstado };
}
