'use client';
/**
 * "Tomar caso" from a list row. Success opens the management page; any error
 * (typically a 409: someone else took it first) is kept per row so the message
 * shows where the user clicked, and the list is refreshed to the real state.
 */
import { useCallback, useState } from 'react';
import { tomarDetractor } from '../../../lib/motored/detractoresApi';

export default function useTomarCaso({ onTaken, reload }) {
  const [busyId, setBusyId] = useState(null);
  const [errors, setErrors] = useState({});

  const tomar = useCallback(async (id) => {
    setBusyId(id);
    setErrors((e) => ({ ...e, [id]: '' }));
    try {
      await tomarDetractor(id);
      onTaken(id);
    } catch (err) {
      setErrors((e) => ({ ...e, [id]: err.message || 'No se pudo tomar el caso.' }));
      reload();
    } finally {
      setBusyId(null);
    }
  }, [onTaken, reload]);

  return { tomar, busyId, errors };
}
