/**
 * The referencia master (`[[codigo, nombre], ...]`, design ADR-6), cached in
 * `localStorage` and revalidated with its ETag on every load, so codes are
 * checked instantly and offline. The master is global (not per store), so
 * it reveals nothing about what the store should hold.
 *
 * `buscar(codigo)`: `{codigo, nombre}`, `null` when the code is not in the
 * master, or `undefined` while no master is available (the server decides).
 */
import { useCallback, useEffect, useState } from 'react';
import { normalizar } from './registro';

const CLAVE = 'motored_conteo_catalogo';

function mapaDesde(referencias) {
  const mapa = new Map();
  for (const [codigo, nombre] of referencias || []) {
    const clave = normalizar(codigo);
    if (!mapa.has(clave)) mapa.set(clave, { codigo, nombre: nombre || '' });
  }
  return mapa;
}

function leerCache() {
  try {
    const guardado = JSON.parse(window.localStorage.getItem(CLAVE));
    return guardado && Array.isArray(guardado.referencias) ? guardado : null;
  } catch {
    return null;
  }
}

function guardarCache(etag, referencias) {
  try {
    window.localStorage.setItem(CLAVE, JSON.stringify({ etag, referencias }));
  } catch {
    // Over quota: the master still lives in memory for this visit.
  }
}

export default function useCatalogo(api) {
  const [mapa, setMapa] = useState(null);

  useEffect(() => {
    let vivo = true;
    const cache = leerCache();
    if (cache) setMapa(mapaDesde(cache.referencias));
    api.catalogo(cache && cache.etag)
      .then((r) => {
        if (!vivo || r.noCambio) return;
        setMapa(mapaDesde(r.referencias));
        guardarCache(r.etag, r.referencias);
      })
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, [api]);

  const buscar = useCallback((codigo) => {
    if (!mapa) return undefined;
    return mapa.get(normalizar(codigo)) || null;
  }, [mapa]);

  return buscar;
}
