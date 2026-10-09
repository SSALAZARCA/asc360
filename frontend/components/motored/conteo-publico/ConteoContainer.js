'use client';

/**
 * Counting screen of a joined device. Phones under 600 px get the
 * mobile-first layout ("ConteoCelular"); tablets and laptops get the desktop
 * one ("ConteoPortatil"), built for a USB scanner.
 */
import { useCallback, useEffect, useState } from 'react';
import ConteoEscritorio from './ConteoEscritorio';
import ConteoMovil from './ConteoMovil';
import useConteo from './useConteo';

const ANCHO_MOVIL = 600;

function useEsMovil() {
  const [movil, setMovil] = useState(() => window.innerWidth < ANCHO_MOVIL);
  useEffect(() => {
    const medir = () => setMovil(window.innerWidth < ANCHO_MOVIL);
    window.addEventListener('resize', medir);
    return () => window.removeEventListener('resize', medir);
  }, []);
  return movil;
}

export default function ConteoContainer({
  slug, sesion, intervaloEnvioMs, onSesionPerdida, onSalida, onUbicacion,
}) {
  const conteo = useConteo({ slug, sesion, intervaloEnvioMs, onSesionPerdida, onUbicacion });
  const movil = useEsMovil();
  const { salir } = conteo;

  const alSalir = useCallback(async () => {
    if (await salir()) onSalida();
  }, [salir, onSalida]);

  const Vista = movil ? ConteoMovil : ConteoEscritorio;
  return <Vista conteo={conteo} onSalir={alSalir} />;
}
