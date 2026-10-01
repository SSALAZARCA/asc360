'use client';
/**
 * Polls `/corridas/{id}/progreso` while a corrida is PENDIENTE or CALCULANDO:
 * once right away, then every 3 s. It stops at a terminal state (and tells the
 * parent), when the server says the corrida is not reachable (401/403/404) and
 * on unmount. A transient failure keeps polling.
 */
import { useEffect, useRef, useState } from 'react';
import { getProgreso } from '../../../lib/motored/pedidosApi';
import { estaCalculando } from './reglas';

export const INTERVALO_MS = 3000;
const SIN_ACCESO = [401, 403, 404];

export default function useProgresoCorrida(corridaId, estado, onTerminal) {
  const [progreso, setProgreso] = useState(null);
  const [error, setError] = useState('');
  const avisar = useRef(onTerminal);
  useEffect(() => { avisar.current = onTerminal; }, [onTerminal]);

  useEffect(() => {
    if (!estaCalculando(estado)) return undefined;
    let activo = true;
    let timer = null;
    const consultar = async () => {
      try {
        const actual = await getProgreso(corridaId);
        if (!activo) return;
        setProgreso(actual);
        setError('');
        if (!estaCalculando(actual.estado)) {
          avisar.current?.(actual);
          return;
        }
      } catch (fallo) {
        if (!activo) return;
        setError(fallo.message || 'No se pudo leer el progreso.');
        if (SIN_ACCESO.includes(fallo.status)) return;
      }
      timer = setTimeout(consultar, INTERVALO_MS);
    };
    consultar();
    return () => { activo = false; clearTimeout(timer); };
  }, [corridaId, estado]);

  return { progreso, error };
}
