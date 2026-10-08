'use client';
/**
 * frontend/components/motored/cargas/BotonRevalidar.js
 *
 * "Volver a validar" (odd/tasks/motored-cargas-revalidar.md, R2): after
 * fixing errors (referencias created, sucursales mapped, rows ignored) the
 * writer processes the SAME stored file again for this carga, without
 * uploading it. Only while the carga is VALIDADO or CON_ERRORES.
 *
 * The endpoint leaves the carga PENDIENTE (queued) and the supervisor moves
 * it to PROCESANDO; the detail page only polls a carga that was already in
 * progress when it loaded, so this button follows it itself: it calls
 * `onChanged` (the page's reload, which returns the fresh carga) every
 * `intervaloMs` until the new validation ends, then `onTerminado`.
 */
import { useEffect, useRef, useState } from 'react';
import { revalidarCarga } from '../../../lib/motored/api';
import InfoTooltip from '../InfoTooltip';

export const ESTADOS_REVALIDABLES = new Set(['VALIDADO', 'CON_ERRORES']);
const ESTADOS_EN_CURSO = new Set(['PENDIENTE', 'PROCESANDO']);
export const CONFIRMAR_REVALIDAR = 'Se volverá a validar el archivo con las correcciones hechas. ¿Continuar?';
const AYUDA = 'Vuelve a procesar el mismo archivo con las referencias, sucursales y filas ignoradas que corrigió. '
  + 'No hace falta subirlo de nuevo.';
const POLL_MS = 3000;

function useSeguimiento(onChanged, onTerminado, intervaloMs) {
  const timer = useRef(null);
  const vivo = useRef(true);
  useEffect(() => () => {
    vivo.current = false;
    clearTimeout(timer.current);
  }, []);

  return async function seguir() {
    const carga = await onChanged?.();
    if (!vivo.current) return;
    if (carga && ESTADOS_EN_CURSO.has(carga.estado)) {
      await new Promise((resolve) => { timer.current = setTimeout(resolve, intervaloMs); });
      if (vivo.current) await seguir();
      return;
    }
    onTerminado?.(carga);
  };
}

export default function BotonRevalidar({ carga, onChanged, onTerminado, intervaloMs = POLL_MS }) {
  const [enCurso, setEnCurso] = useState(false);
  const [error, setError] = useState('');
  const seguir = useSeguimiento(onChanged, onTerminado, intervaloMs);

  if (!enCurso && !ESTADOS_REVALIDABLES.has(carga.estado)) return null;

  const revalidar = async () => {
    if (!window.confirm(CONFIRMAR_REVALIDAR)) return;
    setError('');
    setEnCurso(true);
    try {
      await revalidarCarga(carga.id);
      await seguir();
    } catch (err) {
      setError(err.message || 'No se pudo volver a validar la carga');
    } finally {
      setEnCurso(false);
    }
  };

  return (
    <span style={{ display: 'inline-flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
      <button
        type="button" className="motored-btn motored-btn-secondary"
        onClick={revalidar} disabled={enCurso} aria-label="Volver a validar"
      >
        {enCurso ? 'Validando de nuevo…' : 'Volver a validar'}
      </button>
      <InfoTooltip text={AYUDA} />
      {error && (
        <span role="alert" style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' }}>{error}</span>
      )}
    </span>
  );
}
