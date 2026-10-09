/**
 * Keyboard-wedge scanner support. USB and Bluetooth scanners "type" the
 * code very fast and end with Enter. `esRafaga` tells a scanner burst from
 * a person typing; `useCapturaTeclado` catches a burst that arrives while
 * no text field has the focus (e.g. right after a button was clicked, or on
 * a phone with a Bluetooth scanner) so no scan is ever lost.
 */
import { useEffect, useRef } from 'react';

const MS_POR_TECLA_ESCANER = 35;

function ahora() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

/** True when the keys came in faster than a person types. */
export function esRafaga(tiempos) {
  if (tiempos.length < 3) return false;
  const promedio = (tiempos[tiempos.length - 1] - tiempos[0]) / (tiempos.length - 1);
  return promedio < MS_POR_TECLA_ESCANER;
}

export function registrarTecla(tiempos) {
  tiempos.push(ahora());
}

function esEditable(el) {
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}

/**
 * Calls `onCodigo(codigo)` for a burst typed while the focus is on no text
 * field. Slow typing outside a field is ignored.
 */
export function useCapturaTeclado(onCodigo, activo = true) {
  const callback = useRef(onCodigo);
  callback.current = onCodigo;
  useEffect(() => {
    if (!activo) return undefined;
    let buffer = '';
    let tiempos = [];
    const manejar = (e) => {
      if (esEditable(document.activeElement)) return;
      if (e.key === 'Enter') {
        if (buffer && esRafaga(tiempos)) {
          e.preventDefault();
          callback.current(buffer);
        }
        buffer = '';
        tiempos = [];
        return;
      }
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const t = ahora();
        if (tiempos.length && t - tiempos[tiempos.length - 1] > 300) {
          buffer = '';
          tiempos = [];
        }
        buffer += e.key;
        tiempos.push(t);
      }
    };
    document.addEventListener('keydown', manejar);
    return () => document.removeEventListener('keydown', manejar);
  }, [activo]);
}
