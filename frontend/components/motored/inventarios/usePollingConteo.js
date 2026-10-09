'use client';
/**
 * Live panel polling (odd/motored-conteos-inventario, WU12; owner change of
 * 2026-10-09): every 15 s while the tab is visible, every 60 s when hidden
 * (`document.visibilityState`), an immediate refresh when the tab comes
 * back, and nothing while `activo` is false (a closed conteo). The design's
 * version short-circuit (§9.4) has no endpoint yet, so each tick reloads.
 */
import { useEffect, useRef } from 'react';

export const INTERVALO_VISIBLE_MS = 15000;
export const INTERVALO_OCULTO_MS = 60000;

function intervaloActual() {
  return document.visibilityState === 'hidden' ? INTERVALO_OCULTO_MS : INTERVALO_VISIBLE_MS;
}

export default function usePollingConteo(cargar, activo) {
  const cargarRef = useRef(cargar);
  cargarRef.current = cargar;

  useEffect(() => {
    if (!activo) return undefined;
    let vivo = true;
    let temporizador = null;

    const programar = () => {
      clearTimeout(temporizador);
      temporizador = setTimeout(async () => {
        await cargarRef.current();
        if (vivo) programar();
      }, intervaloActual());
    };
    const alCambiarVisibilidad = () => {
      if (document.visibilityState === 'visible') cargarRef.current();
      programar();
    };

    programar();
    document.addEventListener('visibilitychange', alCambiarVisibilidad);
    return () => {
      vivo = false;
      clearTimeout(temporizador);
      document.removeEventListener('visibilitychange', alCambiarVisibilidad);
    };
  }, [activo]);
}
