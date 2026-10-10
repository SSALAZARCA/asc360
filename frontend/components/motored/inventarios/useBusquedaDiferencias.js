'use client';
/**
 * The on-demand reads of the differences table
 * (odd/tasks/motored-conteo-panel-busqueda.md): the "Contadas" chip and the
 * reference search go to the server (they reach every reference of the
 * conteo, not only the polled differences). The search is debounced; a new
 * panel version (`base`, the polled `todas` answer) refreshes the answer
 * without showing "Buscando…" again. Stale answers are dropped.
 */
import { useEffect, useRef, useState } from 'react';
import * as api from '../../../lib/motored/conteosApi';

export const DEMORA_BUSQUEDA_MS = 350;

export default function useBusquedaDiferencias(conteoId, filtro, texto, base) {
  const q = texto.trim();
  const activa = filtro === 'contadas' || q !== '';
  const clave = `${filtro}|${q}`;
  // { clave, datos } of the last answer, or { clave, error }.
  const [respuesta, setRespuesta] = useState(null);
  const turno = useRef(0);

  useEffect(() => {
    turno.current += 1;
    if (!activa) return undefined;
    const mio = turno.current;
    const espera = setTimeout(async () => {
      try {
        const datos = await api.obtenerDiferencias(conteoId, filtro, q || undefined);
        if (mio === turno.current) setRespuesta({ clave, datos });
      } catch (err) {
        if (mio === turno.current) setRespuesta({ clave, error: err.message || 'No se pudo buscar.' });
      }
    }, DEMORA_BUSQUEDA_MS);
    return () => clearTimeout(espera);
  }, [conteoId, filtro, q, clave, activa, base]);

  const vigente = activa && respuesta?.clave === clave ? respuesta : null;
  return {
    activa,
    buscando: activa && vigente == null,
    datos: vigente?.datos ?? null,
    error: vigente?.error ?? null,
  };
}
