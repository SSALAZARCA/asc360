'use client';
/**
 * ADMIN's "Recalcular": asks for a full rebuild of the KPI summaries, then polls the estado every
 * 10 s while it is dirty or rebuilding (at most ~15 min) and calls `alTerminar` once it settles.
 * `estado` is also read once on mount, so the admin can see the summary's state before enabling it.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getEstado, recalcular } from '../../../lib/motored/kpisApi';

export const INTERVALO_MS = 10000;
export const TOPE_MS = 15 * 60 * 1000;
const MENSAJE_ERROR = 'No pudimos pedir el recálculo. Intentá de nuevo.';

const pendiente = (estado) => Boolean(estado && (estado.sucio || estado.reconstruyendo));

export default function useRecalculo(habilitado, alTerminar) {
  const [estado, setEstado] = useState(null);
  const [recalculando, setRecalculando] = useState(false);
  const [error, setError] = useState(null);
  const temporizador = useRef(null);
  const final = useRef(alTerminar);
  final.current = alTerminar;

  const parar = useCallback(() => {
    if (temporizador.current) clearInterval(temporizador.current);
    temporizador.current = null;
  }, []);

  useEffect(() => {
    if (!habilitado) return undefined;
    let vigente = true;
    getEstado().then((e) => { if (vigente) setEstado(e); }, () => {});
    return () => { vigente = false; };
  }, [habilitado]);
  useEffect(() => parar, [parar]);

  const sondear = useCallback(() => {
    const inicio = Date.now();
    temporizador.current = setInterval(async () => {
      const vencido = Date.now() - inicio >= TOPE_MS;
      let actual = null;
      try { actual = await getEstado(); } catch { /* a failed poll is retried on the next tick */ }
      if (actual) setEstado(actual);
      if (actual && !pendiente(actual)) {
        parar(); setRecalculando(false); final.current?.();
      } else if (vencido) {
        parar(); setRecalculando(false);
      }
    }, INTERVALO_MS);
  }, [parar]);

  const pedir = useCallback(async () => {
    setError(null);
    setRecalculando(true);
    try {
      const respuesta = await recalcular();
      setEstado(respuesta);
      if (pendiente(respuesta)) sondear();
      else { setRecalculando(false); final.current?.(); }
    } catch (e) {
      setRecalculando(false);
      setError(e?.message || MENSAJE_ERROR);
    }
  }, [sondear]);

  return { estado, recalculando, error, pedir };
}
