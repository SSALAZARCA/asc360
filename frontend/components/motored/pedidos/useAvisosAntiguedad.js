'use client';
/**
 * Reads the data that is about to expire (`/avisos-antiguedad`) once when the
 * screen opens. The banner is a courtesy: a failure is swallowed and nothing
 * is shown, so the screen it sits on never breaks because of it.
 */
import { useEffect, useState } from 'react';
import { getAvisosAntiguedad } from '../../../lib/motored/pedidosApi';

export default function useAvisosAntiguedad(enabled) {
  const [avisos, setAvisos] = useState([]);
  useEffect(() => {
    if (!enabled) return undefined;
    let activo = true;
    getAvisosAntiguedad()
      .then((cuerpo) => { if (activo) setAvisos(Array.isArray(cuerpo?.avisos) ? cuerpo.avisos : []); })
      .catch(() => { if (activo) setAvisos([]); });
    return () => { activo = false; };
  }, [enabled]);
  return avisos;
}
