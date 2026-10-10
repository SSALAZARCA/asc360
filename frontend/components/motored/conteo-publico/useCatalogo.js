/**
 * The referencia master (`[[codigo, nombre], ...]`, design ADR-6), cached in
 * `localStorage` and revalidated with its ETag on every load, so codes are
 * checked instantly and offline. The master is global (not per store), so
 * it reveals nothing about what the store should hold.
 *
 * `buscar(codigo)`: `{codigo, nombre}` with the MASTER code, `{ambiguo:
 * [codigos]}` when only the key matches and two or more master codes share
 * it, `null` when the code is not in the master, or `undefined` while no
 * master is available (the server decides). The key index is built here
 * from the codes the catalogue already carries (no payload change), with
 * the server's rule (odd/tasks/motored-conteo-codigo-sin-guiones.md).
 */
import { useCallback, useEffect, useState } from 'react';
import { claveCodigo, esEtiquetaUbicacion, normalizar } from './registro';

const CLAVE = 'motored_conteo_catalogo';

/** `{exactos: Map(normalized code -> ref), claves: Map(key -> [ref])}`. */
export function indiceDesde(referencias) {
  const exactos = new Map();
  const claves = new Map();
  for (const [crudo, nombre] of referencias || []) {
    const codigo = normalizar(crudo);
    if (!codigo || exactos.has(codigo)) continue;
    const referencia = { codigo, nombre: nombre || '' };
    exactos.set(codigo, referencia);
    const clave = claveCodigo(codigo);
    if (clave) claves.set(clave, [...(claves.get(clave) || []), referencia]);
  }
  return { exactos, claves };
}

/** Exact code first; then the key, never for a `UBI-` label. */
export function buscarEn(indice, texto) {
  const codigo = normalizar(texto);
  const exacto = indice.exactos.get(codigo);
  if (exacto) return exacto;
  if (esEtiquetaUbicacion(codigo)) return null;
  const hallados = indice.claves.get(claveCodigo(codigo)) || [];
  if (hallados.length === 1) return hallados[0];
  if (hallados.length > 1) return { ambiguo: hallados.map((r) => r.codigo) };
  return null;
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
  const [indice, setIndice] = useState(null);

  useEffect(() => {
    let vivo = true;
    const cache = leerCache();
    if (cache) setIndice(indiceDesde(cache.referencias));
    api.catalogo(cache && cache.etag)
      .then((r) => {
        if (!vivo || r.noCambio) return;
        setIndice(indiceDesde(r.referencias));
        guardarCache(r.etag, r.referencias);
      })
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, [api]);

  const buscar = useCallback((codigo) => {
    if (!indice) return undefined;
    return buscarEn(indice, codigo);
  }, [indice]);

  return buscar;
}
